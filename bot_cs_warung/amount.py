"""Parse Indonesian rupiah amounts: 600rb, 1,5jt, 250.000, 2 juta."""

import re
from dataclasses import dataclass
from decimal import Decimal

UNITS = {"rb": 1_000, "ribu": 1_000, "k": 1_000, "jt": 1_000_000, "juta": 1_000_000}

_AMOUNT_RE = re.compile(
    r"(?<![\w.,-])(?P<rp>rp\.?\s*)?(?P<num>\d+(?:[.,]\d+)*)\s*(?P<unit>ribu|rb|juta|jt|k)?(?!\w)",
    re.IGNORECASE,
)
_DOT_GROUPED = re.compile(r"\d{1,3}(\.\d{3})+")
_COMMA_GROUPED = re.compile(r"\d{1,3}(,\d{3})+")
_DOT_GROUPED_ZERO_CENTS = re.compile(r"(\d{1,3}(?:\.\d{3})+),0{1,2}")
_DECIMAL = re.compile(r"\d+[.,]\d+")

# A bare run of digits this long is an account or phone number, not money.
_MAX_BARE_DIGITS = 9


@dataclass(frozen=True)
class Amount:
    value: int
    explicit: bool  # has a unit, an "Rp" prefix or thousands separators


def _to_rupiah(num: str, unit: str | None) -> int | None:
    if unit:
        if _DOT_GROUPED.fullmatch(num):
            base = Decimal(num.replace(".", ""))
        elif num.isdigit():
            base = Decimal(num)
        elif _DECIMAL.fullmatch(num):
            base = Decimal(num.replace(",", "."))
        else:
            return None
        value = base * UNITS[unit.lower()]
        if value != value.to_integral_value():
            return None
        return int(value)
    if num.isdigit():
        return int(num)
    if _DOT_GROUPED.fullmatch(num):
        return int(num.replace(".", ""))
    if _COMMA_GROUPED.fullmatch(num):
        return int(num.replace(",", ""))
    if m := _DOT_GROUPED_ZERO_CENTS.fullmatch(num):
        return int(m.group(1).replace(".", ""))
    return None


def _from_match(m: re.Match) -> Amount | None:
    num, unit = m.group("num"), m.group("unit")
    value = _to_rupiah(num, unit)
    if value is None or value <= 0:
        return None
    explicit = bool(unit or m.group("rp") or not num.isdigit())
    if not explicit and (len(num) > _MAX_BARE_DIGITS or num.startswith("0")):
        return None
    return Amount(value, explicit)


def find_amounts(text: str) -> list[Amount]:
    """All rupiah amounts mentioned in free text, in order."""
    return [a for m in _AMOUNT_RE.finditer(text) if (a := _from_match(m))]


def parse_amount(text: str) -> int | None:
    """Parse a string that is exactly one amount, e.g. "1,5jt". None if it is not."""
    m = _AMOUNT_RE.fullmatch(text.strip())
    amount = _from_match(m) if m else None
    return amount.value if amount else None


def extract_amount(text: str, min_bare: int = 1_000) -> int | None:
    """The amount meant in a chat message.

    Explicit amounts (600rb, Rp500, 250.000) win over bare digits, and bare digits
    below `min_bare` are ignored: "transfer 500" is too ambiguous to quote a fee for.
    """
    amounts = find_amounts(text)
    for a in amounts:
        if a.explicit:
            return a.value
    for a in amounts:
        if a.value >= min_bare:
            return a.value
    return None


def rupiah(value: int) -> str:
    return "Rp" + f"{value:,}".replace(",", ".")
