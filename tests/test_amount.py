import pytest

from bot_cs_warung.amount import extract_amount, find_amounts, parse_amount, rupiah


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # formats named in the spec
        ("600rb", 600_000),
        ("1,5jt", 1_500_000),
        ("250.000", 250_000),
        ("2 juta", 2_000_000),
        # unit spellings and spacing
        ("600 rb", 600_000),
        ("600ribu", 600_000),
        ("600 ribu", 600_000),
        ("600k", 600_000),
        ("600RB", 600_000),
        ("2juta", 2_000_000),
        ("2 jt", 2_000_000),
        ("1jt", 1_000_000),
        # decimals with a unit: comma or dot
        ("2,5 juta", 2_500_000),
        ("1.5jt", 1_500_000),
        ("0,5jt", 500_000),
        ("1,25jt", 1_250_000),
        ("1,5rb", 1_500),
        # thousands separators
        ("1.250.000", 1_250_000),
        ("10.000.000", 10_000_000),
        ("250,000", 250_000),
        ("250.000,00", 250_000),
        ("1.500rb", 1_500_000),
        # Rp prefix
        ("Rp250.000", 250_000),
        ("Rp 250.000", 250_000),
        ("rp. 50rb", 50_000),
        ("rp50000", 50_000),
        # plain digits
        ("50000", 50_000),
        ("500", 500),
        ("  75000  ", 75_000),
    ],
)
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "abc",
        "rb",
        "juta",
        "0",
        "0rb",
        "-5000",
        "1,5",  # decimal rupiah without a unit
        "2.5",
        "1.2.3",
        "1,2345rb",  # not a whole rupiah
        "600ml",
        "5kg",
        "12x",
        "600rb lebih",  # not exactly one amount
        "0812345678",  # phone number
        "1234567890123",  # account number
    ],
)
def test_parse_amount_rejects(text):
    assert parse_amount(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("transfer 600rb ke BRI", 600_000),
        ("tarik tunai 1,5jt", 1_500_000),
        ("mau tf 250.000 ke bca dong", 250_000),
        ("kirim 2 juta ke mandiri", 2_000_000),
        ("transfer Rp 1.250.000, ya", 1_250_000),
        ("transfer 50000", 50_000),
        # the account number is not the amount
        ("transfer ke 1234567890 600rb", 600_000),
        ("transfer 250.000 ke bca 1234567890", 250_000),
        ("transfer ke 0812345678 sejumlah 75000", 75_000),
        # an explicit amount wins over bare digits that come first
        ("transfer 2 kali 300rb", 300_000),
        ("transfer Rp500", 500),
    ],
)
def test_extract_amount(text, expected):
    assert extract_amount(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "transfer ke BRI",
        "transfer 500",  # Rp500 or 500rb? too ambiguous to quote
        "kirim paket 2 kg",
        "beras 5 kg",
        "transfer 1234567890",
        "air mineral 600ml",
    ],
)
def test_extract_amount_none(text):
    assert extract_amount(text) is None


def test_find_amounts_returns_all_in_order():
    assert [a.value for a in find_amounts("dari 600rb jadi 1,5jt atau 2 juta")] == [
        600_000,
        1_500_000,
        2_000_000,
    ]


def test_rupiah_format():
    assert rupiah(5_000) == "Rp5.000"
    assert rupiah(1_500_000) == "Rp1.500.000"
    assert rupiah(500) == "Rp500"
