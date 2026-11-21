"""The channel-agnostic brain: one incoming message in, a list of replies out."""

import re
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from . import owner
from .amount import extract_amount, rupiah
from .knowledge import Knowledge
from .llm import LLMClient
from .matching import find_products, match_faq, phrase_in, tokens
from .messages import Incoming, Outgoing
from .storage import ANSWERED, HANDOFF, MENU, Store
from .summary import build_summary
from .tariff import TARIK_TUNAI, TRANSFER

MENU_TARIF = "Tarif Transfer"
MENU_HARGA = "Harga Barang"
MENU_JAM = "Jam Buka"
MENU_LAYANAN = "Layanan"
MENU_PEMILIK = "Chat Pemilik"
MENU_BUTTONS = [MENU_TARIF, MENU_HARGA, MENU_JAM, MENU_LAYANAN, MENU_PEMILIK]

AWAITING_OWNER = "awaiting_owner"
_MAX_PRICE_LIST = 40

_GREETINGS = frozenset(
    """
    halo hai hi hello hallo helo hei hey p permisi punten assalamualaikum assalamu alaikum
    salam pagi siang sore malam selamat kak kakak min gan bang mas mbak bu pak menu start mulai
    """.split()
)
_TRANSFER_WORDS = frozenset({"transfer", "tf", "trf", "transferin", "kirim", "ngirim"})
_TARIK_WORDS = frozenset({"tarik", "narik", "tartun", "gestun"})
# Enough on their own (no amount needed) to show the tariff.
_TARIFF_WORDS = frozenset({"transfer", "tf", "trf", "tarik", "narik", "tartun", "tarif", "admin"})
_FEE_WORDS = frozenset({"biaya", "ongkos", "fee", "potongan", "tarif", "admin"})
_PRICE_WORDS = frozenset({"harga", "berapa", "berapaan", "brp"})
_HOURS_WORDS = frozenset({"buka", "tutup", "operasional"})
_LOCATION_WORDS = frozenset({"alamat", "lokasi", "dimana", "patokan", "maps"})
_SERVICE_WORDS = frozenset({"layanan", "jasa", "servis"})
_DEST_FILLER = frozenset({"bank", "rekening", "rek", "norek", "no", "nomor", "akun"})
_DEST_RE = re.compile(r"\bke\s+((?:[a-z]+\s+){0,2}[a-z]+)", re.IGNORECASE)

Answer = tuple[str, str, str]  # reply text, outcome, source


class Brain:
    def __init__(
        self,
        knowledge: Knowledge,
        store: Store,
        owner_chat_id: str | None = None,
        owner_channel: str = "telegram",
        llm: LLMClient | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self.knowledge = knowledge
        self.store = store
        self.owner_chat_id = str(owner_chat_id) if owner_chat_id else None
        self.owner_channel = owner_channel
        self.llm = llm
        self._clock = clock

    def now(self) -> datetime:
        if self._clock:
            return self._clock()
        return datetime.now(ZoneInfo(self.knowledge.profile.get("zona_waktu", "Asia/Jakarta")))

    def today(self) -> str:
        return self.now().date().isoformat()

    def is_owner(self, msg: Incoming) -> bool:
        return (
            self.owner_chat_id is not None
            and msg.chat_id == self.owner_chat_id
            and msg.channel == self.owner_channel
        )

    def to_owner(self, text: str, handoff_id: int | None = None) -> Outgoing:
        return Outgoing(self.owner_channel, self.owner_chat_id, text, handoff_id=handoff_id)

    def handle(self, msg: Incoming) -> list[Outgoing]:
        if self.is_owner(msg):
            return owner.handle(self, msg)
        return self._handle_customer(msg)

    def tick(self) -> list[Outgoing]:
        """Called regularly by the app; sends the daily summary once it is due."""
        due = self.knowledge.profile.get("jam_ringkasan")
        now = self.now()
        day = now.date().isoformat()
        if not (self.owner_chat_id and due) or now.strftime("%H:%M") < due:
            return []
        if self.store.get("last_summary_day") == day:
            return []
        self.store.set("last_summary_day", day)
        return [self.to_owner(build_summary(self.knowledge, self.store, day))]

    # --- customer side -------------------------------------------------

    def _handle_customer(self, msg: Incoming) -> list[Outgoing]:
        day = self.today()
        text, outcome, source, forwards = self._route(msg, day)
        buttons = MENU_BUTTONS if source == "greeting" else []
        self.store.log_message(
            day, msg.channel, msg.chat_id, "in", msg.text, msg.user_name, outcome, source
        )
        self.store.log_message(day, msg.channel, msg.chat_id, "out", text, source=source)
        return [*forwards, Outgoing(msg.channel, msg.chat_id, text, buttons=buttons)]

    def _route(self, msg: Incoming, day: str) -> tuple[str, str, str, list[Outgoing]]:
        """Decide the reply: (text, outcome, source, messages for the owner)."""
        state_key = f"state:{msg.channel}:{msg.chat_id}"
        awaiting_owner = self.store.get(state_key) == AWAITING_OWNER
        self.store.set(state_key, None)

        if not msg.text.strip():
            text = "Maaf kak, saya cuma bisa baca tulisan. Ketik aja pertanyaannya ya."
            return text, MENU, "non_text", []
        words = tokens(msg.text)
        choice = self._menu_choice(msg.text)
        if choice == MENU_PEMILIK:
            self.store.set(state_key, AWAITING_OWNER)
            text = "Siap kak, tulis aja pesannya di sini. Nanti saya terusin ke pemilik ya."
            return text, MENU, "menu", []
        if choice:
            return self._menu_answer(choice), MENU, "menu", []
        if not awaiting_owner:
            if words and all(w in _GREETINGS for w in words):
                return self._greeting(), MENU, "greeting", []
            if answer := self._answer(msg.text, words):
                return *answer, []
        source = "chat_pemilik" if awaiting_owner else "unknown"
        text, forwards = self._handoff(msg, day)
        return text, HANDOFF, source, forwards

    @staticmethod
    def _menu_choice(text: str) -> str | None:
        wanted = " ".join(tokens(text))
        return next((b for b in MENU_BUTTONS if b.lower() == wanted), None)

    def _greeting(self) -> str:
        return (
            f"Halo kak, selamat datang di {self.knowledge.profile['nama']}. "
            "Mau tanya apa? Pilih menu di bawah atau langsung ketik aja ya."
        )

    def _menu_answer(self, choice: str) -> str:
        if choice == MENU_TARIF:
            return self._tariff_info()
        if choice == MENU_HARGA:
            return self._price_list()
        if choice == MENU_JAM:
            return self._hours()
        return self._services()

    def _tariff_info(self) -> str:
        return (
            "Tarif transfer & tarik tunai:\n"
            f"{self.knowledge.tariff_text()}\n\n"
            'Mau dihitungin? Ketik aja, contoh: "transfer 600rb ke BRI" atau "tarik tunai 1,5jt".'
        )

    def _price_list(self) -> str:
        prices = self.knowledge.prices
        if not prices:
            return "Daftar harganya belum diisi kak. Tanya pemilik aja lewat Chat Pemilik ya."
        shown = list(prices.items())[:_MAX_PRICE_LIST]
        lines = [f"• {name}: {rupiah(price)}" for name, price in shown]
        more = "\n…dan lainnya." if len(prices) > len(shown) else ""
        return "Daftar harga:\n" + "\n".join(lines) + more + "\n\nKetik nama barang buat cek harga."

    def _hours(self) -> str:
        p = self.knowledge.profile
        return f"{p['nama']} buka: {p['jam_buka']}"

    def _location(self) -> str:
        return f"Lokasi {self.knowledge.profile['nama']}: {self.knowledge.profile['lokasi']}"

    def _services(self) -> str:
        return "Layanan di sini:\n" + "\n".join(f"• {s}" for s in self.knowledge.profile["layanan"])

    def _answer(self, text: str, words: list[str]) -> Answer | None:
        """Answer from the shop knowledge, or None when a human has to take over."""
        wordset = set(words)
        kind = self._fee_kind(words)
        amount = extract_amount(text) if kind else None
        if kind and amount:
            return self._quote(kind, amount, text), ANSWERED, "fee"

        if wordset & _FEE_WORDS and wordset & _TARIFF_WORDS:
            return self._tariff_info(), ANSWERED, "fee"

        prices = self.knowledge.prices
        if wordset & _PRICE_WORDS and (found := find_products(text, prices)):
            return self._price_answer(found), ANSWERED, "price"
        if entry := match_faq(text, self.knowledge.faq):
            return entry["jawaban"], ANSWERED, "faq"
        if wordset & _HOURS_WORDS:
            return self._hours(), ANSWERED, "info"
        if wordset & _LOCATION_WORDS or phrase_in(["di", "mana"], words):
            return self._location(), ANSWERED, "info"
        if wordset & _SERVICE_WORDS:
            return self._services(), ANSWERED, "info"
        if found := find_products(text, prices):
            return self._price_answer(found), ANSWERED, "price"
        if wordset & _TARIFF_WORDS:
            return self._tariff_info(), ANSWERED, "fee"
        if self.llm and (reply := self.llm.ask(text, self.knowledge.as_context())):
            return reply, ANSWERED, "llm"
        return None

    @staticmethod
    def _fee_kind(words: list[str]) -> str | None:
        for w in words:
            if w in _TRANSFER_WORDS:
                return TRANSFER
            if w in _TARIK_WORDS:
                return TARIK_TUNAI
        return None

    def _quote(self, kind: str, amount: int, text: str) -> str:
        q = self.knowledge.tariff.quote(kind, amount)
        if kind == TRANSFER:
            dest = self._destination(text)
            head = f"Transfer {rupiah(amount)}" + (f" ke {dest}" if dest else "")
            last = f"• Total bayar: {rupiah(q.total)}"
        else:
            if q.total <= 0:
                return f"Nominalnya kekecilan kak, biaya tarik tunainya aja {rupiah(q.fee)}."
            head = f"Tarik tunai {rupiah(amount)}"
            last = f"• Uang diterima: {rupiah(q.total)}"
        return f"{head}:\n• Nominal: {rupiah(q.principal)}\n• Biaya: {rupiah(q.fee)}\n{last}"

    @staticmethod
    def _destination(text: str) -> str | None:
        m = _DEST_RE.search(text)
        if not m:
            return None
        for word in m.group(1).split():
            if word.lower() not in _DEST_FILLER:
                return word.upper() if len(word) <= 4 else word.capitalize()
        return None

    @staticmethod
    def _price_answer(found: list[tuple[str, int]]) -> str:
        if len(found) == 1:
            name, price = found[0]
            return f"{name}: {rupiah(price)} kak."
        return "Yang ada:\n" + "\n".join(f"• {name}: {rupiah(price)}" for name, price in found)

    def _handoff(self, msg: Incoming, day: str) -> tuple[str, list[Outgoing]]:
        """Log a handoff. Returns (reply to the customer, messages for the owner)."""
        handoff_id = self.store.create_handoff(
            day, msg.channel, msg.chat_id, msg.identity, msg.text
        )
        if not self.owner_chat_id:
            return "Maaf kak, yang itu saya belum bisa jawab. Mampir langsung ke warung aja ya.", []
        forward = self.to_owner(
            f"Chat #{handoff_id} dari {msg.identity}:\n\n{msg.text}\n\n"
            f"Balas (reply) pesan ini untuk menjawab, atau ketik /balas {handoff_id} <jawaban>.",
            handoff_id=handoff_id,
        )
        return "Bentar ya kak, saya tanyain ke pemilik dulu. Nanti dibalas di sini.", [forward]
