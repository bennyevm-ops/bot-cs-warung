import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bot_cs_warung.brain import Brain
from bot_cs_warung.knowledge import Knowledge
from bot_cs_warung.messages import Incoming
from bot_cs_warung.storage import Store

CONFIG = Path(__file__).parent.parent / "config" / "warung.json"
OWNER = "99"
NOON = datetime(2026, 1, 15, 12, 0, tzinfo=ZoneInfo("Asia/Jakarta"))


@pytest.fixture
def knowledge(tmp_path):
    return Knowledge(shutil.copy(CONFIG, tmp_path / "warung.json"))


@pytest.fixture
def store():
    return Store()


@pytest.fixture
def brain(knowledge, store):
    return Brain(knowledge, store, owner_chat_id=OWNER, clock=lambda: NOON)


def customer(text, chat_id="1"):
    return Incoming("telegram", chat_id, text, user_name="Budi", username="budi")


def owner(text, reply_to_id=None):
    return Incoming("telegram", OWNER, text, user_name="Bu Sari", reply_to_id=reply_to_id)
