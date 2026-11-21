from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bot_cs_warung.brain import MENU_BUTTONS, Brain
from bot_cs_warung.storage import ANSWERED, HANDOFF, MENU
from tests.conftest import OWNER, customer, owner


def reply(brain, text, chat_id="1"):
    """The single message sent back to the customer."""
    outs = [o for o in brain.handle(customer(text, chat_id)) if o.chat_id == chat_id]
    assert len(outs) == 1
    return outs[0]


def last_log(store):
    return store.db.execute(
        "SELECT outcome, source FROM messages WHERE direction = 'in' ORDER BY id DESC LIMIT 1"
    ).fetchone()


@pytest.mark.parametrize("text", ["/start", "halo", "Assalamualaikum kak", "selamat pagi", "p"])
def test_greeting_shows_main_menu(brain, store, text):
    out = reply(brain, text)
    assert "Warung Berkah" in out.text
    assert out.buttons == MENU_BUTTONS
    assert out.buttons == ["Tarif Transfer", "Harga Barang", "Jam Buka", "Layanan", "Chat Pemilik"]
    assert last_log(store)["outcome"] == MENU


def test_menu_buttons_answer_from_config(brain):
    assert "Rp5.000 tiap kelipatan Rp500.000" in reply(brain, "Tarif Transfer").text
    assert "Di atas Rp4.500.000 flat Rp50.000" in reply(brain, "Tarif Transfer").text
    assert "Indomie Goreng: Rp3.500" in reply(brain, "Harga Barang").text
    assert "06.00 - 21.00" in reply(brain, "Jam Buka").text
    assert "Tarik tunai" in reply(brain, "Layanan").text


def test_transfer_fee_reply(brain, store):
    text = reply(brain, "transfer 600rb ke BRI").text
    assert text == (
        "Transfer Rp600.000 ke BRI:\n"
        "• Nominal: Rp600.000\n"
        "• Biaya: Rp10.000\n"
        "• Total bayar: Rp610.000"
    )
    assert tuple(last_log(store)) == (ANSWERED, "fee")


def test_tarik_tunai_fee_reply(brain):
    assert reply(brain, "tarik tunai 1,5jt").text == (
        "Tarik tunai Rp1.500.000:\n"
        "• Nominal: Rp1.500.000\n"
        "• Biaya: Rp15.000\n"
        "• Uang diterima: Rp1.485.000"
    )


@pytest.mark.parametrize(
    ("text", "fee", "total"),
    [
        ("tf 250.000 ke bca", "Rp5.000", "Rp255.000"),
        ("kirim 2 juta ke mandiri", "Rp20.000", "Rp2.020.000"),
        ("transfer 4.500.001", "Rp50.000", "Rp4.550.001"),
        ("mau transfer 10jt bisa?", "Rp50.000", "Rp10.050.000"),
    ],
)
def test_fee_reply_other_formats(brain, text, fee, total):
    out = reply(brain, text).text
    assert f"Biaya: {fee}" in out
    assert f"Total bayar: {total}" in out


def test_fee_question_without_amount_explains_tariff(brain):
    for text in ["transfer", "biaya admin tarik tunai berapa?", "transfer 500"]:
        assert "Tarif transfer & tarik tunai" in reply(brain, text).text


def test_tarik_tunai_smaller_than_fee_is_refused(brain):
    out = reply(brain, "tarik tunai 3rb").text
    assert "Uang diterima" not in out
    assert "Rp5.000" in out


def test_price_lookup(brain, store):
    assert reply(brain, "indomi goreng").text == "Indomie Goreng: Rp3.500 kak."
    assert tuple(last_log(store)) == (ANSWERED, "price")
    assert "Rp17.000" in reply(brain, "harga gula berapa kak?").text
    both = reply(brain, "indomie").text
    assert "Indomie Goreng: Rp3.500" in both and "Indomie Soto: Rp3.500" in both


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("bisa transfer ke bank apa aja", "semua bank"),
        ("bisa tarik tunai?", "Bisa tarik tunai"),
        ("ada pulsa?", "pulsa dan paket data"),
        ("ada paketan?", "pulsa dan paket data"),
        ("bisa bayar pakai QRIS?", "QRIS"),
    ],
)
def test_faq_auto_answers(brain, store, text, expected):
    assert expected in reply(brain, text).text
    assert tuple(last_log(store)) == (ANSWERED, "faq")


def test_shop_info_questions(brain):
    assert "06.00 - 21.00" in reply(brain, "buka jam berapa?").text
    assert "Jl. Mawar" in reply(brain, "alamatnya di mana?").text
    assert "Token listrik" in reply(brain, "ada layanan apa aja?").text


@pytest.mark.parametrize(
    "text",
    [
        "harga rokok surya berapa",  # not in the price list: never invent a price
        "bisa kirim paket ga?",
        "besok lebaran libur nggak?",
        "bisa hutang dulu?",
    ],
)
def test_unknown_question_is_handed_off_to_owner(brain, store, text):
    outs = brain.handle(customer(text))
    to_owner = [o for o in outs if o.chat_id == OWNER]
    to_customer = [o for o in outs if o.chat_id == "1"]

    assert len(to_owner) == 1 and len(to_customer) == 1
    forward = to_owner[0]
    assert forward.handoff_id is not None
    assert text in forward.text
    assert "Budi" in forward.text and "@budi" in forward.text and "id 1" in forward.text
    assert "pemilik" in to_customer[0].text
    assert "Rp" not in to_customer[0].text

    handoff = store.get_handoff(forward.handoff_id)
    assert handoff["question"] == text and handoff["answer"] is None
    assert tuple(last_log(store)) == (HANDOFF, "unknown")


def test_handoff_without_owner_still_logged(knowledge, store):
    brain = Brain(knowledge, store, owner_chat_id=None)
    outs = brain.handle(customer("bisa hutang dulu?"))
    assert len(outs) == 1 and outs[0].chat_id == "1"
    assert store.get_handoff(1)["question"] == "bisa hutang dulu?"


def test_chat_pemilik_forwards_next_message_even_if_answerable(brain, store):
    assert "terusin ke pemilik" in reply(brain, "Chat Pemilik").text
    outs = brain.handle(customer("indomie goreng 2 dus, besok saya ambil"))
    assert [o.chat_id for o in outs] == [OWNER, "1"]
    assert tuple(last_log(store)) == (HANDOFF, "chat_pemilik")
    # only the next message is forwarded; after that the bot answers again
    assert reply(brain, "indomie goreng").text == "Indomie Goreng: Rp3.500 kak."


def test_chat_pemilik_forwards_a_greeting_too(brain, store):
    reply(brain, "Chat Pemilik")
    outs = brain.handle(customer("halo"))
    assert [o.chat_id for o in outs] == [OWNER, "1"]
    assert tuple(last_log(store)) == (HANDOFF, "chat_pemilik")


def test_owner_reply_reaches_customer(brain, store):
    forward = brain.handle(customer("bisa hutang dulu?", chat_id="7"))[0]
    store.link_owner_message(forward.handoff_id, "555")

    outs = brain.handle(owner("Maaf kak, belum bisa ya", reply_to_id="555"))
    assert outs[0].chat_id == "7"
    assert outs[0].text == "Dari pemilik: Maaf kak, belum bisa ya"
    assert outs[1].chat_id == OWNER and "Terkirim" in outs[1].text
    assert store.get_handoff(forward.handoff_id)["answer"] == "Maaf kak, belum bisa ya"


def test_owner_can_reply_by_number(brain):
    forward = brain.handle(customer("bisa hutang dulu?", chat_id="7"))[0]
    outs = brain.handle(owner(f"/balas {forward.handoff_id} boleh kak"))
    assert (outs[0].chat_id, outs[0].text) == ("7", "Dari pemilik: boleh kak")


def test_non_text_message(brain):
    assert "Ketik" in reply(brain, "").text


def test_conversation_is_logged(brain, store):
    reply(brain, "transfer 600rb ke BRI")
    rows = store.db.execute("SELECT direction, text, user_name FROM messages ORDER BY id")
    rows = [tuple(r) for r in rows]
    assert rows[0] == ("in", "transfer 600rb ke BRI", "Budi")
    assert rows[1][0] == "out" and "Rp610.000" in rows[1][1]


class FakeLLM:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def ask(self, question, context):
        self.calls.append((question, context))
        return self.answer


def test_llm_answers_only_what_rules_cannot(knowledge, store):
    llm = FakeLLM("Bisa kak, parkir motor di depan warung.")
    brain = Brain(knowledge, store, owner_chat_id=OWNER, llm=llm)

    assert "Rp610.000" in reply(brain, "transfer 600rb ke BRI").text
    assert llm.calls == []

    out = reply(brain, "bisa parkir motor?")
    assert out.text == "Bisa kak, parkir motor di depan warung."
    question, context = llm.calls[0]
    assert question == "bisa parkir motor?"
    assert "Indomie Goreng: Rp3.500" in context and "Warung Berkah" in context
    assert tuple(last_log(store)) == (ANSWERED, "llm")


def test_llm_without_answer_falls_back_to_handoff(knowledge, store):
    brain = Brain(knowledge, store, owner_chat_id=OWNER, llm=FakeLLM(None))
    outs = brain.handle(customer("bisa hutang dulu?"))
    assert [o.chat_id for o in outs] == [OWNER, "1"]
    assert tuple(last_log(store)) == (HANDOFF, "unknown")


def at(hour, minute=0, day=15):
    return datetime(2026, 1, day, hour, minute, tzinfo=ZoneInfo("Asia/Jakarta"))


def test_daily_summary_sent_once_after_configured_time(knowledge, store):
    now = [at(12)]
    brain = Brain(knowledge, store, owner_chat_id=OWNER, clock=lambda: now[0])
    brain.handle(customer("halo", "1"))
    brain.handle(customer("transfer 600rb ke BRI", "1"))
    brain.handle(customer("indomie", "2"))
    brain.handle(customer("bisa hutang dulu?", "2"))
    brain.handle(customer("besok libur?", "3"))

    assert brain.tick() == []  # 12:00, summary is due at 21:00

    now[0] = at(21)
    (summary,) = brain.tick()
    assert summary.chat_id == OWNER
    assert "Ringkasan 2026-01-15" in summary.text
    assert "Jumlah chat (pelanggan): 3" in summary.text
    assert "Pesan masuk: 5" in summary.text
    assert "Pertanyaan dijawab bot: 2" in summary.text
    assert "Diteruskan ke pemilik: 2 (sudah dibalas: 0)" in summary.text

    now[0] = at(21, 30)
    assert brain.tick() == []  # already sent today

    now[0] = at(21, 5, day=16)
    assert "Ringkasan 2026-01-16" in brain.tick()[0].text


def test_no_summary_without_owner(knowledge, store):
    brain = Brain(knowledge, store, owner_chat_id=None, clock=lambda: at(22))
    assert brain.tick() == []
