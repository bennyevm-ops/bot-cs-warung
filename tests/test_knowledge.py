import json
import os

import pytest

from bot_cs_warung.knowledge import Knowledge
from bot_cs_warung.settings import Settings, load_dotenv
from bot_cs_warung.storage import Store


def test_default_config_carries_the_spec_tariff(knowledge):
    t = knowledge.tariff
    assert (t.step, t.fee_per_step, t.max_steps) == (500_000, 5_000, 10)
    assert (t.min_fee, t.flat_threshold, t.flat_fee) == (5_000, 4_500_000, 50_000)


def test_tariff_change_in_config_changes_fees(knowledge):
    data = json.loads(knowledge.path.read_text(encoding="utf-8"))
    data["tarif"]["biaya_per_kelipatan"] = 6_000
    knowledge.path.write_text(json.dumps(data), encoding="utf-8")
    knowledge.reload()
    assert knowledge.tariff.fee(600_000) == 12_000


def test_missing_section_is_reported(tmp_path):
    path = tmp_path / "warung.json"
    path.write_text('{"profil": {}, "tarif": {}, "harga": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="faq"):
        Knowledge(path)


def test_save_leaves_no_temp_file(knowledge):
    knowledge.set_price("Teh Botol", 5_000)
    assert [p.name for p in knowledge.path.parent.iterdir()] == ["warung.json"]


def test_context_lists_everything_the_bot_knows(knowledge):
    context = knowledge.as_context()
    for expected in ["Warung Berkah", "06.00 - 21.00", "Gula Pasir 1kg: Rp17.000", "qris"]:
        assert expected in context
    assert "Rp5.000 tiap kelipatan Rp500.000" in context


def test_settings_from_env():
    s = Settings.from_env({"TELEGRAM_BOT_TOKEN": " abc ", "OWNER_CHAT_ID": "99"})
    assert (s.telegram_token, s.owner_chat_id) == ("abc", "99")
    assert (s.config_path, s.db_path) == ("config/warung.json", "data/bot.sqlite3")
    assert Settings.from_env({"TELEGRAM_BOT_TOKEN": "abc"}).owner_chat_id is None
    assert Settings.from_env({"BOT_TOKEN": "xyz"}).telegram_token == "xyz"
    with pytest.raises(SystemExit):
        Settings.from_env({})


def test_load_dotenv_does_not_override_real_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("# komentar\nWARUNG_TEST_A=dari-file\nWARUNG_TEST_B='x y'\n")
    monkeypatch.setenv("WARUNG_TEST_A", "dari-env")
    monkeypatch.delenv("WARUNG_TEST_B", raising=False)
    load_dotenv(env_file)
    assert os.environ["WARUNG_TEST_A"] == "dari-env"
    assert os.environ.pop("WARUNG_TEST_B") == "x y"


def test_store_persists_to_file(tmp_path):
    path = tmp_path / "data" / "bot.sqlite3"
    store = Store(path)
    hid = store.create_handoff("2026-01-15", "telegram", "1", "Budi", "halo?")
    store.link_owner_message(hid, "555")
    store.db.close()
    assert Store(path).handoff_by_owner_message("555")["question"] == "halo?"
