import json

import httpx
import pytest

from bot_cs_warung.channels.telegram import TelegramChannel, TelegramError
from bot_cs_warung.messages import Outgoing

TOKEN = "123456:SECRET-token"


def channel(handler, **kwargs):
    calls = []

    def record(request):
        body = json.loads(request.content)
        calls.append((request.url.path.rsplit("/", 1)[-1], body))
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(record))
    return TelegramChannel(TOKEN, http=http, **kwargs), calls


def ok(result):
    return httpx.Response(200, json={"ok": True, "result": result})


def message(text="halo", chat_type="private", chat_id=42, **extra):
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "from": {"id": 42, "first_name": "Budi", "last_name": "S", "username": "budi"},
            "chat": {"id": chat_id, "type": chat_type},
            "text": text,
            **extra,
        },
    }


def test_send_plain_text_returns_message_id():
    tg, calls = channel(lambda r: ok({"message_id": 77}))
    assert tg.send(Outgoing("telegram", "42", "halo")) == "77"
    assert calls == [("sendMessage", {"chat_id": "42", "text": "halo"})]


def test_send_buttons_as_inline_keyboard():
    tg, calls = channel(lambda r: ok({"message_id": 1}))
    tg.send(Outgoing("telegram", "42", "menu", buttons=["A", "B", "C"]))
    keyboard = calls[0][1]["reply_markup"]["inline_keyboard"]
    assert keyboard == [
        [{"text": "A", "callback_data": "A"}, {"text": "B", "callback_data": "B"}],
        [{"text": "C", "callback_data": "C"}],
    ]


def test_parse_text_message():
    tg, _ = channel(lambda r: ok(True))
    msg = tg.parse_update(message("transfer 600rb"))
    assert (msg.channel, msg.chat_id, msg.text) == ("telegram", "42", "transfer 600rb")
    assert (msg.user_name, msg.username, msg.reply_to_id) == ("Budi S", "budi", None)


def test_parse_reply_keeps_replied_message_id():
    tg, _ = channel(lambda r: ok(True))
    msg = tg.parse_update(message("oke", reply_to_message={"message_id": 555}))
    assert msg.reply_to_id == "555"


def test_parse_button_press_as_text_and_acknowledges_it():
    tg, calls = channel(lambda r: ok(True))
    update = {
        "update_id": 2,
        "callback_query": {
            "id": "cb1",
            "from": {"id": 42, "first_name": "Budi"},
            "data": "Jam Buka",
            "message": {
                "message_id": 11,
                "from": {"id": 1, "is_bot": True},
                "chat": {"id": 42, "type": "private"},
            },
        },
    }
    msg = tg.parse_update(update)
    assert (msg.chat_id, msg.text, msg.user_name) == ("42", "Jam Buka", "Budi")
    assert calls == [("answerCallbackQuery", {"callback_query_id": "cb1"})]


def test_parse_photo_without_caption_has_empty_text():
    tg, _ = channel(lambda r: ok(True))
    update = message()
    del update["message"]["text"]
    assert tg.parse_update(update).text == ""


def test_group_chats_ignored_unless_listed():
    tg, _ = channel(lambda r: ok(True))
    assert tg.parse_update(message(chat_type="group", chat_id=-100)) is None
    tg, _ = channel(lambda r: ok(True), always_listen=frozenset({"-100"}))
    assert tg.parse_update(message(chat_type="group", chat_id=-100)).chat_id == "-100"


def test_other_updates_ignored():
    tg, _ = channel(lambda r: ok(True))
    assert tg.parse_update({"update_id": 3, "edited_message": {}}) is None


def test_api_error_raises_with_description():
    tg, _ = channel(
        lambda r: httpx.Response(403, json={"ok": False, "description": "Forbidden: blocked"})
    )
    with pytest.raises(TelegramError, match="Forbidden: blocked"):
        tg.send(Outgoing("telegram", "42", "halo"))


def test_network_error_never_leaks_token():
    def handler(request):
        raise httpx.ConnectError(f"cannot reach {request.url}")

    tg, _ = channel(handler)
    with pytest.raises(TelegramError) as info:
        tg.send(Outgoing("telegram", "42", "halo"))
    assert "SECRET" not in str(info.value)
    assert info.value.__cause__ is None and info.value.__suppress_context__


class Stop(BaseException):
    pass


def test_run_polls_dispatches_and_advances_offset():
    batches = [[message("halo")], []]

    def handler(request):
        if request.url.path.endswith("/getUpdates"):
            return ok(batches.pop(0))
        return ok(True)

    tg, calls = channel(handler, poll_timeout=0)
    received, ticks = [], []

    def on_tick():
        ticks.append(1)
        if len(ticks) == 2:
            raise Stop

    with pytest.raises(Stop):
        tg.run(received.append, on_tick)

    assert [m.text for m in received] == ["halo"]
    polls = [body for method, body in calls if method == "getUpdates"]
    assert "offset" not in polls[0]
    assert polls[1]["offset"] == 2


def test_run_survives_handler_errors():
    batches = [[message("satu"), {**message("dua"), "update_id": 2}]]

    def handler(request):
        return ok(batches.pop(0))

    tg, _ = channel(handler, poll_timeout=0)
    seen = []

    def on_message(msg):
        seen.append(msg.text)
        raise RuntimeError("boom")

    def on_tick():
        raise Stop

    with pytest.raises(Stop):
        tg.run(on_message, on_tick)
    assert seen == ["satu", "dua"]
