import json

import pytest

from bot_cs_warung.knowledge import Knowledge
from tests.conftest import OWNER, customer, owner


def run(brain, text):
    outs = brain.handle(owner(text))
    assert all(o.chat_id == OWNER for o in outs)
    return outs[0].text


def on_disk(knowledge):
    return json.loads(knowledge.path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("command", "name", "price"),
    [
        ("/harga rokok surya 12 25000", "rokok surya 12", 25_000),
        ("/harga Beras 10kg 150rb", "Beras 10kg", 150_000),
        ("/harga sabun mandi 4.500", "sabun mandi", 4_500),
        ("/harga permen 500", "permen", 500),
        ("/harga gula merah 17 ribu", "gula merah", 17_000),
        ("/harga@WarungBot teh botol Rp5.000", "teh botol", 5_000),
    ],
)
def test_harga_adds_item_and_persists(brain, knowledge, command, name, price):
    assert "ditambah" in run(brain, command)
    assert on_disk(knowledge)["harga"][name] == price
    assert Knowledge(knowledge.path).prices[name] == price


def test_harga_updates_existing_item_case_insensitively(brain, knowledge):
    text = run(brain, "/harga indomie goreng 4000")
    assert "Indomie Goreng sekarang Rp4.000 (tadinya Rp3.500)" in text
    assert on_disk(knowledge)["harga"]["Indomie Goreng"] == 4_000
    assert "indomie goreng" not in on_disk(knowledge)["harga"]


def test_new_price_is_used_for_customers_immediately(brain):
    run(brain, "/harga rokok surya 12 25rb")
    (out,) = brain.handle(customer("rokok surya"))
    assert out.text == "rokok surya 12: Rp25.000 kak."


@pytest.mark.parametrize("command", ["/harga indomie", "/harga 3500", "/harga indomie nol"])
def test_harga_bad_input_changes_nothing(brain, knowledge, command):
    before = on_disk(knowledge)
    assert run(brain, command).startswith("Gagal")
    assert on_disk(knowledge) == before


def test_harga_without_arguments_lists_prices(brain):
    assert "Indomie Goreng: Rp3.500" in run(brain, "/harga")


def test_hapus(brain, knowledge):
    assert "Indomie Soto dihapus" in run(brain, "/hapus indomie soto")
    assert "Indomie Soto" not in on_disk(knowledge)["harga"]


def test_hapus_unknown_item_suggests_and_keeps_list(brain, knowledge):
    before = on_disk(knowledge)
    text = run(brain, "/hapus indomi")
    assert "tidak ada" in text and "Indomie Goreng" in text
    assert on_disk(knowledge) == before


def test_faq_add_edit_delete(brain, knowledge):
    assert "nomor 5 ditambah" in run(brain, "/faq tambah token listrik, pln | Ada kak.")
    assert on_disk(knowledge)["faq"][4] == {
        "kata_kunci": ["token listrik", "pln"],
        "jawaban": "Ada kak.",
    }
    assert brain.handle(customer("ada token listrik?"))[0].text == "Ada kak."

    run(brain, "/faq ubah 5 | Ada kak, mulai 20rb.")
    assert on_disk(knowledge)["faq"][4]["jawaban"] == "Ada kak, mulai 20rb."

    run(brain, "/faq kunci 5 | token, listrik prabayar")
    assert on_disk(knowledge)["faq"][4]["kata_kunci"] == ["token", "listrik prabayar"]

    assert "listrik prabayar" in run(brain, "/faq")

    run(brain, "/faq hapus 5")
    assert len(on_disk(knowledge)["faq"]) == 4


@pytest.mark.parametrize(
    "command",
    ["/faq hapus 9", "/faq ubah x | y", "/faq tambah | jawaban", "/faq tambah kunci |", "/faq apa"],
)
def test_faq_bad_input_changes_nothing(brain, knowledge, command):
    before = on_disk(knowledge)
    assert run(brain, command).startswith("Gagal")
    assert on_disk(knowledge) == before


def test_info_updates_profile(brain, knowledge):
    assert "Jam buka: Tiap hari 07.00 - 22.00" in run(brain, "/info jam Tiap hari 07.00 - 22.00")
    run(brain, "/info nama Warung Bu Sari")
    run(brain, "/info lokasi Jl. Melati 5")
    run(brain, "/info layanan Sembako, Transfer, Tarik tunai")
    run(brain, "/info ringkasan 20:30")
    assert on_disk(knowledge)["profil"] == {
        "nama": "Warung Bu Sari",
        "jam_buka": "Tiap hari 07.00 - 22.00",
        "lokasi": "Jl. Melati 5",
        "layanan": ["Sembako", "Transfer", "Tarik tunai"],
        "zona_waktu": "Asia/Jakarta",
        "jam_ringkasan": "20:30",
    }
    assert "07.00 - 22.00" in brain.handle(customer("Jam Buka"))[0].text


@pytest.mark.parametrize("command", ["/info ringkasan 9", "/info jam", "/info warna merah"])
def test_info_bad_input(brain, knowledge, command):
    before = on_disk(knowledge)
    assert run(brain, command).startswith("Gagal")
    assert on_disk(knowledge) == before


def test_ringkasan_on_demand(brain):
    brain.handle(customer("transfer 600rb"))
    brain.handle(customer("bisa hutang dulu?"))
    text = run(brain, "/ringkasan")
    assert "Ringkasan 2026-01-15" in text
    assert "Pertanyaan dijawab bot: 1" in text and "Diteruskan ke pemilik: 1" in text
    assert "Jumlah chat (pelanggan): 0" in run(brain, "/ringkasan 2026-01-14")
    assert run(brain, "/ringkasan kemarin").startswith("Gagal")


def test_unknown_command_and_plain_text_show_help(brain):
    assert "/harga" in run(brain, "/xyz")
    assert "/harga" in run(brain, "apa kabar")


@pytest.mark.parametrize(
    "command", ["/harga indomie goreng 1", "/hapus indomie goreng", "/faq hapus 1", "/info nama X"]
)
def test_customers_cannot_use_owner_commands(brain, knowledge, command):
    before = on_disk(knowledge)
    brain.handle(customer(command))
    assert on_disk(knowledge) == before


def test_balas_unknown_number(brain):
    assert run(brain, "/balas 42 halo").startswith("Gagal")
