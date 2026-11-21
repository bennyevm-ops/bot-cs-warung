"""Shop knowledge: one JSON config file, editable by the owner at runtime."""

import json
import os
import re
from pathlib import Path

from .amount import rupiah
from .tariff import Tariff

PROFILE_FIELDS = ("nama", "jam_buka", "lokasi", "layanan", "jam_ringkasan")
_HHMM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


def _clean(text: str) -> str:
    return " ".join(text.split())


class Knowledge:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.reload()

    def reload(self) -> None:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        for key in ("profil", "tarif", "harga", "faq"):
            if key not in data:
                raise ValueError(f"{self.path}: bagian '{key}' tidak ada")
        self.data = data
        self.tariff = Tariff.from_config(data["tarif"])

    def save(self) -> None:
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    @property
    def profile(self) -> dict:
        return self.data["profil"]

    @property
    def prices(self) -> dict[str, int]:
        return self.data["harga"]

    @property
    def faq(self) -> list[dict]:
        return self.data["faq"]

    def _price_key(self, name: str) -> str | None:
        wanted = _clean(name).casefold()
        return next((k for k in self.prices if k.casefold() == wanted), None)

    def set_price(self, name: str, price: int) -> tuple[str, int | None]:
        """Set a price. Returns (stored name, previous price or None)."""
        if price <= 0:
            raise ValueError("harga harus lebih dari 0")
        key = self._price_key(name) or _clean(name)
        if not key:
            raise ValueError("nama barang kosong")
        old = self.prices.get(key)
        self.prices[key] = price
        self.save()
        return key, old

    def remove_price(self, name: str) -> str | None:
        key = self._price_key(name)
        if key is None:
            return None
        del self.prices[key]
        self.save()
        return key

    def add_faq(self, keywords: list[str], answer: str) -> int:
        """Add an FAQ entry. Returns its 1-based number."""
        self.faq.append({"kata_kunci": self._keywords(keywords), "jawaban": self._answer(answer)})
        self.save()
        return len(self.faq)

    def update_faq(
        self, number: int, answer: str | None = None, keywords: list[str] | None = None
    ) -> dict:
        entry = self.faq[self._faq_index(number)]
        if answer is not None:
            entry["jawaban"] = self._answer(answer)
        if keywords is not None:
            entry["kata_kunci"] = self._keywords(keywords)
        self.save()
        return entry

    def remove_faq(self, number: int) -> dict:
        entry = self.faq.pop(self._faq_index(number))
        self.save()
        return entry

    def _faq_index(self, number: int) -> int:
        if not 1 <= number <= len(self.faq):
            raise ValueError(f"FAQ nomor {number} tidak ada")
        return number - 1

    @staticmethod
    def _keywords(keywords: list[str]) -> list[str]:
        cleaned = [_clean(k).lower() for k in keywords if _clean(k)]
        if not cleaned:
            raise ValueError("kata kunci kosong")
        return cleaned

    @staticmethod
    def _answer(answer: str) -> str:
        if not answer.strip():
            raise ValueError("jawaban kosong")
        return answer.strip()

    def set_profile(self, field: str, value: str) -> None:
        if field not in PROFILE_FIELDS:
            raise ValueError(f"bagian '{field}' tidak dikenal")
        value = value.strip()
        if not value:
            raise ValueError("isinya kosong")
        if field == "layanan":
            self.profile[field] = [_clean(v) for v in value.split(",") if _clean(v)]
        elif field == "jam_ringkasan":
            if not _HHMM.fullmatch(value):
                raise ValueError("format jam harus HH:MM, contoh 21:00")
            self.profile[field] = value
        else:
            self.profile[field] = value
        self.save()

    def tariff_text(self) -> str:
        t = self.tariff
        return (
            f"• {rupiah(t.fee_per_step)} tiap kelipatan {rupiah(t.step)} "
            f"(minimal {rupiah(t.min_fee)})\n"
            f"• Di atas {rupiah(t.flat_threshold)} flat {rupiah(t.flat_fee)}"
        )

    def as_context(self) -> str:
        """Everything the bot knows, as plain text for the optional LLM."""
        p = self.profile
        lines = [
            f"Nama warung: {p['nama']}",
            f"Jam buka: {p['jam_buka']}",
            f"Lokasi: {p['lokasi']}",
            "Layanan: " + ", ".join(p["layanan"]),
            "Tarif transfer & tarik tunai:",
            self.tariff_text(),
            "Daftar harga:",
            *(f"- {name}: {rupiah(price)}" for name, price in self.prices.items()),
            "FAQ:",
            *(f"- {', '.join(e['kata_kunci'])}: {e['jawaban']}" for e in self.faq),
        ]
        return "\n".join(lines)
