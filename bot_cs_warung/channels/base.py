"""What the app needs from a chat channel (Telegram today, WhatsApp later)."""

from collections.abc import Callable
from typing import Protocol

from ..messages import Incoming, Outgoing


class Channel(Protocol):
    name: str

    def send(self, out: Outgoing) -> list[str]:
        """Deliver a message. Returns the platform ids of the message(s) it became."""

    def run(self, on_message: Callable[[Incoming], None], on_tick: Callable[[], None]) -> None:
        """Receive messages forever, calling on_tick regularly in between."""
