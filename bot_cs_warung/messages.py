"""Channel-agnostic message types shared by the brain and every channel."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Incoming:
    channel: str
    chat_id: str
    text: str
    user_name: str = ""
    username: str = ""
    reply_to_id: str | None = None  # id of the bot message this one replies to

    @property
    def identity(self) -> str:
        name = self.user_name or "Pelanggan"
        handle = f"@{self.username}, " if self.username else ""
        return f"{name} ({handle}{self.channel} id {self.chat_id})"


@dataclass(frozen=True)
class Outgoing:
    channel: str
    chat_id: str
    text: str
    buttons: list[str] = field(default_factory=list)
    handoff_id: int | None = None  # set on the copy forwarded to the owner
