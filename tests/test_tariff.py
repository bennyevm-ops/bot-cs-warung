import json
import math

import pytest

from bot_cs_warung.tariff import TARIK_TUNAI, TRANSFER, Tariff
from tests.conftest import CONFIG


@pytest.fixture(scope="module")
def tariff():
    return Tariff.from_config(json.loads(CONFIG.read_text(encoding="utf-8"))["tarif"])


BAND_EDGES = [
    # (amount, fee): lower edge, upper edge of every Rp500.000 band
    (1, 5_000),
    (10_000, 5_000),
    (500_000, 5_000),
    (500_001, 10_000),
    (1_000_000, 10_000),
    (1_000_001, 15_000),
    (1_500_000, 15_000),
    (1_500_001, 20_000),
    (2_000_000, 20_000),
    (2_000_001, 25_000),
    (2_500_000, 25_000),
    (2_500_001, 30_000),
    (3_000_000, 30_000),
    (3_000_001, 35_000),
    (3_500_000, 35_000),
    (3_500_001, 40_000),
    (4_000_000, 40_000),
    (4_000_001, 45_000),
    (4_500_000, 45_000),
    # flat Rp50.000 above Rp4.500.000
    (4_500_001, 50_000),
    (5_000_000, 50_000),
    (5_000_001, 50_000),
    (10_000_000, 50_000),
    (100_000_000, 50_000),
]


@pytest.mark.parametrize(("amount", "fee"), BAND_EDGES)
def test_fee_band_edges(tariff, amount, fee):
    assert tariff.fee(amount) == fee


@pytest.mark.parametrize("amount", [1, 499_999, 1_234_567, 4_500_000, 4_500_001, 7_000_000])
def test_fee_matches_spec_formula(tariff, amount):
    assert tariff.fee(amount) == min(math.ceil(amount / 500_000), 10) * 5_000


def test_fee_never_below_minimum_or_above_flat(tariff):
    for amount in range(1, 6_000_000, 37_511):
        assert 5_000 <= tariff.fee(amount) <= 50_000


@pytest.mark.parametrize("amount", [0, -1, -500_000])
def test_fee_rejects_non_positive(tariff, amount):
    with pytest.raises(ValueError):
        tariff.fee(amount)


def test_transfer_quote_customer_pays_principal_plus_fee(tariff):
    q = tariff.quote(TRANSFER, 600_000)
    assert (q.principal, q.fee, q.total) == (600_000, 10_000, 610_000)


def test_tarik_tunai_quote_customer_receives_principal_minus_fee(tariff):
    q = tariff.quote(TARIK_TUNAI, 1_500_000)
    assert (q.principal, q.fee, q.total) == (1_500_000, 15_000, 1_485_000)


def test_tariff_comes_from_config():
    custom = Tariff.from_config(
        {
            "kelipatan": 1_000_000,
            "biaya_per_kelipatan": 7_500,
            "maks_kelipatan": 3,
            "biaya_minimum": 10_000,
            "batas_flat": 3_000_000,
            "biaya_flat": 30_000,
        }
    )
    assert custom.fee(500_000) == 10_000  # minimum applies
    assert custom.fee(2_000_000) == 15_000
    assert custom.fee(3_000_000) == 22_500
    assert custom.fee(3_000_001) == 30_000
