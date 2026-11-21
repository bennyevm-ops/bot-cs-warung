"""Fuzzy price lookup and FAQ keyword matching."""

import re
from difflib import SequenceMatcher

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Filler words that say nothing about which item the customer means.
_STOPWORDS = frozenset(
    """
    harga berapa berapaan brp ya kak kakak dong ada min gan bang mas mbak bu pak apa yang yg
    itu ini sekarang saya aku mau beli tanya nanya kalau kalo satu per masih ga gak nggak
    tidak stok jual dijual di sini untuk buat tolong cek info permisi halo hai sih deh nih
    lagi dan atau sama dengan the
    """.split()
)


def tokens(text: str) -> list[str]:
    out = []
    for tok in _TOKEN_RE.findall(text.lower()):
        if tok.endswith("nya") and len(tok) >= 6:
            tok = tok[:-3]
        out.append(tok)
    return out


def _similar(a: str, b: str, threshold: float = 0.8) -> bool:
    if a == b:
        return True
    if len(a) < 4 or len(b) < 4:
        return False
    return SequenceMatcher(None, a, b).ratio() >= threshold


def find_products(query: str, prices: dict[str, int], limit: int = 5) -> list[tuple[str, int]]:
    """Items the query most likely refers to, best first. Empty when nothing fits.

    An item fits when every meaningful query word is in its name ("indomie" fits
    both Indomie Goreng and Indomie Soto) or its whole name is in the query.
    """
    q = [t for t in tokens(query) if t not in _STOPWORDS]
    if not q:
        return []
    scored = []
    for name, price in prices.items():
        p = tokens(name)
        if not p:
            continue
        q_cov = sum(any(_similar(t, pt) for pt in p) for t in q) / len(q)
        p_cov = sum(any(_similar(pt, t) for t in q) for pt in p) / len(p)
        if q_cov == 1 or p_cov == 1:
            scored.append((q_cov + p_cov, name, price))
    if not scored:
        return []
    best = max(s for s, _, _ in scored)
    if best == 2:
        scored = [row for row in scored if row[0] == 2]
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [(name, price) for _, name, price in scored[:limit]]


def phrase_in(phrase: list[str], words: list[str]) -> bool:
    """True when the phrase appears in the words, in order, allowing small typos."""
    # Stricter than item matching so "paket" (parcel) does not hit "paketan" (data plan).
    n = len(phrase)
    return n > 0 and any(
        all(_similar(p, w, 0.85) for p, w in zip(phrase, words[i : i + n], strict=True))
        for i in range(len(words) - n + 1)
    )


def match_faq(text: str, faq: list[dict]) -> dict | None:
    """The FAQ entry whose keywords best match the text, or None."""
    words = tokens(text)
    best, best_score = None, (0, 0)
    for entry in faq:
        hits = [tokens(kw) for kw in entry["kata_kunci"]]
        hits = [kw for kw in hits if phrase_in(kw, words)]
        if not hits:
            continue
        score = (len(hits), max(len(kw) for kw in hits))
        if score > best_score:
            best, best_score = entry, score
    return best
