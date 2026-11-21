"""Telegram channel on the raw Bot API (long polling) using httpx."""

import logging
import time
from collections.abc import Callable

import httpx

from ..messages import Incoming, Outgoing

log = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
_BUTTONS_PER_ROW = 2
MAX_TEXT = 4096  # sendMessage limit


def _fit(text: str, limit: int) -> int:
    """How many leading characters fit; astral characters (emoji) count as two to be safe."""
    units = 0
    for i, ch in enumerate(text):
        units += 2 if ord(ch) > 0xFFFF else 1
        if units > limit:
            return i
    return len(text)


def split_text(text: str, limit: int = MAX_TEXT) -> list[str]:
    """Cut text into parts Telegram accepts, at a line or word break when there is one."""
    parts = []
    while text:
        end = _fit(text, limit)
        if end < len(text):
            cut = max(text.rfind("\n", 0, end), text.rfind(" ", 0, end))
            end = cut + 1 if cut > 0 else end
        if text[:end].strip():
            parts.append(text[:end])
        text = text[end:]
    return parts


class TelegramError(Exception):
    pass


class TelegramChannel:
    name = "telegram"

    def __init__(
        self,
        token: str,
        http: httpx.Client | None = None,
        always_listen: frozenset[str] = frozenset(),
        poll_timeout: int = 30,
    ):
        self._token = token
        self._http = http or httpx.Client(timeout=poll_timeout + 10)
        # Chats handled even when they are not private (the owner's chat may be a group).
        self._always_listen = always_listen
        self._poll_timeout = poll_timeout

    def _call(self, method: str, **params) -> object:
        try:
            resp = self._http.post(f"{API_BASE}/bot{self._token}/{method}", json=params)
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Never let the URL (it contains the token) reach logs or tracebacks.
            raise TelegramError(f"{method}: {type(exc).__name__}") from None
        if not data.get("ok"):
            raise TelegramError(f"{method}: {data.get('description', resp.status_code)}")
        return data["result"]

    def send(self, out: Outgoing) -> str | None:
        """Send a message, in several parts when it is too long. Returns the last part's id."""
        *head, last = split_text(out.text) or [out.text]
        for part in head:
            self._call("sendMessage", chat_id=out.chat_id, text=part)
        params: dict = {"chat_id": out.chat_id, "text": last}
        if out.buttons:
            rows = [
                out.buttons[i : i + _BUTTONS_PER_ROW]
                for i in range(0, len(out.buttons), _BUTTONS_PER_ROW)
            ]
            params["reply_markup"] = {
                "inline_keyboard": [
                    [{"text": label, "callback_data": label} for label in row] for row in rows
                ]
            }
        result = self._call("sendMessage", **params)
        return str(result["message_id"])

    def parse_update(self, update: dict) -> Incoming | None:
        """Turn a Telegram update into an Incoming, or None when it is not for the bot."""
        if query := update.get("callback_query"):
            message, sender, text = query.get("message") or {}, query["from"], query.get("data", "")
            try:
                self._call("answerCallbackQuery", callback_query_id=query["id"])
            except TelegramError as exc:
                log.warning("Gagal menjawab tombol: %s", exc)
        elif message := update.get("message"):
            sender = message.get("from") or {}
            text = message.get("text") or message.get("caption") or ""
        else:
            return None
        chat = message.get("chat")
        if not chat or sender.get("is_bot"):
            return None
        chat_id = str(chat["id"])
        if chat.get("type") != "private" and chat_id not in self._always_listen:
            return None
        reply_to = (message.get("reply_to_message") or {}).get("message_id")
        name = " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")]))
        return Incoming(
            channel=self.name,
            chat_id=chat_id,
            text=text,
            user_name=name,
            username=sender.get("username", ""),
            reply_to_id=str(reply_to) if reply_to and "callback_query" not in update else None,
        )

    def run(self, on_message: Callable[[Incoming], None], on_tick: Callable[[], None]) -> None:
        offset = None
        while True:
            try:
                updates = self._call(
                    "getUpdates",
                    timeout=self._poll_timeout,
                    allowed_updates=["message", "callback_query"],
                    **({"offset": offset} if offset is not None else {}),
                )
            except TelegramError as exc:
                log.warning("Gagal ambil pesan: %s", exc)
                time.sleep(3)
                updates = []
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    if incoming := self.parse_update(update):
                        on_message(incoming)
                except Exception:
                    log.exception("Gagal memproses pesan")
            try:
                on_tick()
            except Exception:
                log.exception("Gagal menjalankan tugas berkala")
