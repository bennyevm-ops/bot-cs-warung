"""SQLite log of conversations and handoffs."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

ANSWERED = "answered"
HANDOFF = "handoff"
MENU = "menu"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    day TEXT NOT NULL,
    channel TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    user_name TEXT NOT NULL DEFAULT '',
    direction TEXT NOT NULL,          -- in | out
    text TEXT NOT NULL,
    outcome TEXT,                     -- in only: answered | handoff | menu
    source TEXT                       -- fee, price, faq, info, llm, owner, ...
);
CREATE INDEX IF NOT EXISTS messages_day ON messages (day);
CREATE TABLE IF NOT EXISTS handoffs (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    day TEXT NOT NULL,
    channel TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    identity TEXT NOT NULL,
    question TEXT NOT NULL,
    owner_message_id TEXT,
    answer TEXT,
    answered_ts TEXT
);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)

    def log_message(
        self,
        day: str,
        channel: str,
        chat_id: str,
        direction: str,
        text: str,
        user_name: str = "",
        outcome: str | None = None,
        source: str | None = None,
    ) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO messages (ts, day, channel, chat_id, user_name, direction, text,"
                " outcome, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (_now(), day, channel, chat_id, user_name, direction, text, outcome, source),
            )

    def create_handoff(
        self, day: str, channel: str, chat_id: str, identity: str, question: str
    ) -> int:
        with self.db:
            cur = self.db.execute(
                "INSERT INTO handoffs (ts, day, channel, chat_id, identity, question)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (_now(), day, channel, chat_id, identity, question),
            )
        return cur.lastrowid

    def link_owner_message(self, handoff_id: int, owner_message_id: str) -> None:
        with self.db:
            self.db.execute(
                "UPDATE handoffs SET owner_message_id = ? WHERE id = ?",
                (owner_message_id, handoff_id),
            )

    def get_handoff(self, handoff_id: int) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM handoffs WHERE id = ?", (handoff_id,)).fetchone()

    def handoff_by_owner_message(self, owner_message_id: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM handoffs WHERE owner_message_id = ?", (owner_message_id,)
        ).fetchone()

    def answer_handoff(self, handoff_id: int, answer: str) -> None:
        with self.db:
            self.db.execute(
                "UPDATE handoffs SET answer = ?, answered_ts = ? WHERE id = ?",
                (answer, _now(), handoff_id),
            )

    def get(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set(self, key: str, value: str | None) -> None:
        with self.db:
            if value is None:
                self.db.execute("DELETE FROM kv WHERE key = ?", (key,))
            else:
                self.db.execute(
                    "INSERT INTO kv (key, value) VALUES (?, ?)"
                    " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )

    def daily_stats(self, day: str) -> dict[str, int]:
        row = self.db.execute(
            "SELECT COUNT(DISTINCT channel || ':' || chat_id) AS chats,"
            " COUNT(*) AS messages,"
            " COALESCE(SUM(outcome = 'answered'), 0) AS answered,"
            " COALESCE(SUM(outcome = 'handoff'), 0) AS handed_off"
            " FROM messages WHERE day = ? AND direction = 'in'",
            (day,),
        ).fetchone()
        replied = self.db.execute(
            "SELECT COUNT(*) FROM handoffs WHERE day = ? AND answer IS NOT NULL", (day,)
        ).fetchone()[0]
        return {**dict(row), "owner_replied": replied}
