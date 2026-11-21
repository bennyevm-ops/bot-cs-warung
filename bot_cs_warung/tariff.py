"""Transfer / tarik tunai fee calculator. All numbers come from the config file."""

import math
from dataclasses import dataclass

TRANSFER = "transfer"
TARIK_TUNAI = "tarik_tunai"


@dataclass(frozen=True)
class Quote:
    kind: str
    principal: int
    fee: int
    total: int  # transfer: what the customer pays; tarik tunai: cash the customer receives


@dataclass(frozen=True)
class Tariff:
    step: int
    fee_per_step: int
    max_steps: int
    min_fee: int
    flat_threshold: int
    flat_fee: int

    @classmethod
    def from_config(cls, cfg: dict) -> "Tariff":
        return cls(
            step=int(cfg["kelipatan"]),
            fee_per_step=int(cfg["biaya_per_kelipatan"]),
            max_steps=int(cfg["maks_kelipatan"]),
            min_fee=int(cfg["biaya_minimum"]),
            flat_threshold=int(cfg["batas_flat"]),
            flat_fee=int(cfg["biaya_flat"]),
        )

    def fee(self, amount: int) -> int:
        if amount <= 0:
            raise ValueError("amount must be positive")
        if amount > self.flat_threshold:
            return self.flat_fee
        steps = min(math.ceil(amount / self.step), self.max_steps)
        return max(steps * self.fee_per_step, self.min_fee)

    def quote(self, kind: str, amount: int) -> Quote:
        fee = self.fee(amount)
        total = amount + fee if kind == TRANSFER else amount - fee
        return Quote(kind, amount, fee, total)
