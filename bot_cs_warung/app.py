"""Wires settings, knowledge, storage, brain and channels together."""

import logging

from .brain import Brain
from .channels.base import Channel
from .channels.telegram import TelegramChannel
from .knowledge import Knowledge
from .llm import LLMClient
from .messages import Incoming, Outgoing
from .settings import Settings, load_dotenv
from .storage import Store

log = logging.getLogger(__name__)


class App:
    def __init__(self, brain: Brain, channels: list[Channel]):
        self.brain = brain
        self.channels = {c.name: c for c in channels}

    def deliver(self, outgoing: list[Outgoing]) -> None:
        for out in outgoing:
            channel = self.channels.get(out.channel)
            try:
                if channel is None:
                    raise LookupError("channel tidak aktif")
                message_ids = channel.send(out)
            except Exception as exc:
                log.error("Gagal kirim pesan ke %s: %s", out.channel, exc)
                follow_up = self.brain.undelivered(out)
            else:
                follow_up = self.brain.delivered(out, message_ids)
            self.deliver(follow_up)

    def on_message(self, msg: Incoming) -> None:
        if not self.brain.owner_chat_id:
            # Lets the owner find the value to put in OWNER_CHAT_ID.
            log.info("Pesan dari %s chat id %s", msg.channel, msg.chat_id)
        self.deliver(self.brain.handle(msg))

    def on_tick(self) -> None:
        self.deliver(self.brain.tick())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # httpx logs full request URLs at INFO, and Telegram URLs contain the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv()
    settings = Settings.from_env()
    llm = LLMClient.from_env()
    brain = Brain(
        Knowledge(settings.config_path),
        Store(settings.db_path),
        owner_chat_id=settings.owner_chat_id,
        llm=llm,
    )
    listen = frozenset({settings.owner_chat_id}) if settings.owner_chat_id else frozenset()
    telegram = TelegramChannel(settings.telegram_token, always_listen=listen)
    app = App(brain, [telegram])
    if not settings.owner_chat_id:
        log.warning("OWNER_CHAT_ID kosong: fitur pemilik dan terusan chat tidak aktif")
    log.info("Bot jalan (jawaban pintar: %s)", "aktif" if llm else "mati, pakai aturan saja")
    telegram.run(app.on_message, app.on_tick)
