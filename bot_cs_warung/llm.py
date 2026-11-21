"""Optional smart answers through an OpenAI-compatible chat endpoint."""

import logging
import os

import httpx

from .amount import find_amounts

log = logging.getLogger(__name__)

HANDOFF_TOKEN = "HANDOFF"

_SYSTEM = (
    "Kamu asisten customer service sebuah warung kelontong di Indonesia. "
    "Jawab singkat, ramah, santai, dalam bahasa Indonesia, seperti penjaga warung.\n"
    "Jawab HANYA berdasarkan DATA WARUNG di bawah. Jangan pernah mengarang harga, "
    "biaya, tarif, stok, atau info lain yang tidak tertulis di data. Jangan menghitung "
    "biaya sendiri; minta pelanggan mengetik contoh: transfer 600rb.\n"
    f"Kalau jawabannya tidak ada di data, balas persis satu kata: {HANDOFF_TOKEN}\n\n"
    "DATA WARUNG:\n"
)

# Smaller numbers are quantities or hours, not prices.
_MIN_MONEY = 1_000


def is_grounded(answer: str, *sources: str) -> bool:
    """True when every rupiah amount in the answer also appears in the sources."""
    known = {a.value for src in sources for a in find_amounts(src)}
    return all(a.value in known for a in find_amounts(answer) if a.value >= _MIN_MONEY)


class LLMClient:
    def __init__(
        self,
        api_base: str,
        api_key: str,
        model: str,
        http: httpx.Client | None = None,
        timeout: float = 20.0,
    ):
        self.url = api_base.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.http = http or httpx.Client(timeout=timeout)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "LLMClient | None":
        """A client when LLM_API_BASE, LLM_API_KEY and LLM_MODEL are all set, else None."""
        env = os.environ if env is None else env
        base, key, model = (
            env.get(k, "").strip() for k in ("LLM_API_BASE", "LLM_API_KEY", "LLM_MODEL")
        )
        return cls(base, key, model) if base and key and model else None

    def ask(self, question: str, context: str) -> str | None:
        """An answer grounded in the shop knowledge, or None to hand off to a human."""
        try:
            resp = self.http.post(
                self.url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": _SYSTEM + context},
                        {"role": "user", "content": question},
                    ],
                },
            )
            resp.raise_for_status()
            answer = (resp.json()["choices"][0]["message"]["content"] or "").strip()
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            log.warning("LLM tidak bisa dipakai (%s), lanjut ke pemilik", type(exc).__name__)
            return None
        if not answer or HANDOFF_TOKEN in answer.upper():
            return None
        if not is_grounded(answer, context, question):
            log.warning("Jawaban LLM menyebut nominal di luar data warung, lanjut ke pemilik")
            return None
        return answer
