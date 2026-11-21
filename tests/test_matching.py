import pytest

from bot_cs_warung.matching import find_products, match_faq

PRICES = {
    "Indomie Goreng": 3_500,
    "Indomie Soto": 3_500,
    "Beras 5kg": 75_000,
    "Gula Pasir 1kg": 17_000,
    "Minyak Goreng 1L": 18_000,
    "Telur Ayam 1kg": 28_000,
    "Air Mineral 600ml": 4_000,
    "Kopi Sachet": 2_000,
}

FAQ = [
    {"kata_kunci": ["bank apa", "bank mana", "ke bank"], "jawaban": "bank"},
    {"kata_kunci": ["tarik tunai", "tartun"], "jawaban": "tarik"},
    {"kata_kunci": ["pulsa", "paketan", "paket data", "kuota"], "jawaban": "pulsa"},
    {"kata_kunci": ["qris", "scan"], "jawaban": "qris"},
]


def names(query):
    return [name for name, _ in find_products(query, PRICES)]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Indomie Goreng", ["Indomie Goreng"]),
        ("indomie goreng", ["Indomie Goreng"]),
        ("indomi goreng", ["Indomie Goreng"]),  # typo
        ("indomee soto", ["Indomie Soto"]),
        ("minyk goreng", ["Minyak Goreng 1L"]),
        ("harga gula berapa kak?", ["Gula Pasir 1kg"]),
        ("beras", ["Beras 5kg"]),
        ("telor ayam", ["Telur Ayam 1kg"]),
        ("kak, air mineral 600ml masih ada?", ["Air Mineral 600ml"]),
        ("kopi sachet 2 ya", ["Kopi Sachet"]),
        # an ambiguous name lists every candidate
        ("indomie", ["Indomie Goreng", "Indomie Soto"]),
        ("goreng", ["Indomie Goreng", "Minyak Goreng 1L"]),
    ],
)
def test_find_products(query, expected):
    assert names(query) == expected


@pytest.mark.parametrize(
    "query",
    [
        "rokok surya",
        "sabun mandi",
        "indomie rendang",  # this variant is not in the list
        "harga berapa?",
        "",
        "es",  # short words must match exactly
        "bisa kirim paket ga",
    ],
)
def test_find_products_no_match(query):
    assert find_products(query, PRICES) == []


def test_find_products_returns_price():
    assert find_products("gula pasir", PRICES) == [("Gula Pasir 1kg", 17_000)]


def test_find_products_respects_limit():
    many = {f"Permen {flavor}": 500 for flavor in "abcdefgh"}
    assert len(find_products("permen", many, limit=3)) == 3


@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ("bisa transfer ke bank apa aja", "bank"),
        ("Transfernya ke bank mana saja kak?", "bank"),
        ("bisa tarik tunai?", "tarik"),
        ("bisa tartun ga", "tarik"),
        ("ada pulsa?", "pulsa"),
        ("pulsanya ada kak?", "pulsa"),
        ("ada paketan?", "pulsa"),
        ("jual paket data nggak", "pulsa"),
        ("bisa bayar pakai QRIS?", "qris"),
        ("bayar pake qriss bisa?", "qris"),  # typo
    ],
)
def test_match_faq(text, answer):
    assert match_faq(text, FAQ)["jawaban"] == answer


@pytest.mark.parametrize(
    "text",
    ["bisa kirim paket ga?", "besok libur?", "mau tarik napas", "bank", ""],
)
def test_match_faq_no_match(text):
    assert match_faq(text, FAQ) is None


def test_match_faq_prefers_entry_with_more_keyword_hits():
    faq = [
        {"kata_kunci": ["pulsa"], "jawaban": "satu"},
        {"kata_kunci": ["pulsa", "telkomsel"], "jawaban": "dua"},
    ]
    assert match_faq("ada pulsa telkomsel?", faq)["jawaban"] == "dua"
