"""Runtime settings. Secrets come from env vars only (optionally via a local .env)."""

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """Load KEY=VALUE lines into os.environ without overriding what is already set."""
    file = Path(path)
    if not file.is_file():
        return
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    owner_chat_id: str | None
    config_path: str
    db_path: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        # TELEGRAM_BOT_TOKEN is the older name and still works.
        token = (env.get("BOT_TOKEN") or env.get("TELEGRAM_BOT_TOKEN") or "").strip()
        if not token:
            raise SystemExit("BOT_TOKEN belum diisi. Lihat .env.example.")
        return cls(
            telegram_token=token,
            owner_chat_id=env.get("OWNER_CHAT_ID", "").strip() or None,
            config_path=env.get("WARUNG_CONFIG", "").strip() or "config/warung.json",
            db_path=env.get("DB_PATH", "").strip() or "data/bot.sqlite3",
        )
