"""Owner-only side: replies to customers and commands that edit the shop knowledge."""

from datetime import date

from .amount import UNITS, parse_amount, rupiah
from .matching import find_products
from .messages import Incoming, Outgoing
from .summary import build_summary

HELP = (
    "Perintah pemilik:\n"
    "/harga <barang> <harga> - set/ubah harga (contoh: /harga indomie goreng 3500)\n"
    "/harga - lihat semua harga\n"
    "/hapus <barang> - hapus barang\n"
    "/faq - lihat FAQ\n"
    "/faq tambah <kata kunci, dipisah koma> | <jawaban>\n"
    "/faq ubah <nomor> | <jawaban baru>\n"
    "/faq kunci <nomor> | <kata kunci baru>\n"
    "/faq hapus <nomor>\n"
    "/info - lihat profil warung\n"
    "/info <nama|jam|lokasi|layanan|ringkasan> <isi baru>\n"
    "/ringkasan [YYYY-MM-DD] - ringkasan harian\n"
    "/balas <nomor chat> <jawaban> - balas pelanggan\n\n"
    "Untuk menjawab pelanggan, cukup balas (reply) pesan terusannya."
)

_INFO_FIELDS = {
    "nama": "nama",
    "jam": "jam_buka",
    "lokasi": "lokasi",
    "layanan": "layanan",
    "ringkasan": "jam_ringkasan",
}


def handle(brain, msg: Incoming) -> list[Outgoing]:
    text = msg.text.strip()
    if text.startswith("/"):
        head, _, args = text.partition(" ")
        command = head[1:].split("@")[0].lower()
        handler = _COMMANDS.get(command)
        if handler is None:
            return [brain.to_owner(HELP)]
        try:
            return handler(brain, args.strip())
        except ValueError as exc:
            return [brain.to_owner(f"Gagal: {exc}")]
    if msg.reply_to_id and text:
        handoff = brain.store.handoff_by_owner_message(msg.reply_to_id)
        if handoff:
            return _reply_to_customer(brain, handoff, text)
    return [brain.to_owner(HELP)]


def _reply_to_customer(brain, handoff, text: str) -> list[Outgoing]:
    brain.store.answer_handoff(handoff["id"], text)
    brain.store.log_message(
        brain.today(), handoff["channel"], handoff["chat_id"], "out", text, source="owner"
    )
    return [
        Outgoing(handoff["channel"], handoff["chat_id"], f"Dari pemilik: {text}"),
        brain.to_owner(f"Terkirim ke {handoff['identity']}."),
    ]


def _balas(brain, args: str) -> list[Outgoing]:
    number, _, text = args.partition(" ")
    if not number.lstrip("#").isdigit() or not text.strip():
        raise ValueError("format: /balas <nomor chat> <jawaban>")
    handoff = brain.store.get_handoff(int(number.lstrip("#")))
    if handoff is None:
        raise ValueError(f"chat #{number.lstrip('#')} tidak ada")
    return _reply_to_customer(brain, handoff, text.strip())


def _split_item_price(args: str) -> tuple[str, int]:
    parts = args.split()
    for take in (2, 1):  # "17 ribu" first, then "17rb"
        if len(parts) > take and (take == 1 or parts[-1].lower() in UNITS):
            price = parse_amount(" ".join(parts[-take:]))
            if price:
                return " ".join(parts[:-take]), price
    raise ValueError("format: /harga <barang> <harga>, contoh: /harga indomie goreng 3500")


def _harga(brain, args: str) -> list[Outgoing]:
    kb = brain.knowledge
    if not args:
        lines = [f"• {name}: {rupiah(price)}" for name, price in kb.prices.items()]
        return [brain.to_owner("Daftar harga:\n" + "\n".join(lines) if lines else "Belum ada.")]
    name, price = _split_item_price(args)
    key, old = kb.set_price(name, price)
    if old is None:
        return [brain.to_owner(f"Oke, {key} ditambah: {rupiah(price)}.")]
    return [brain.to_owner(f"Oke, harga {key} sekarang {rupiah(price)} (tadinya {rupiah(old)}).")]


def _hapus(brain, args: str) -> list[Outgoing]:
    if not args:
        raise ValueError("format: /hapus <barang>")
    removed = brain.knowledge.remove_price(args)
    if removed:
        return [brain.to_owner(f"Oke, {removed} dihapus dari daftar harga.")]
    near = [name for name, _ in find_products(args, brain.knowledge.prices)]
    hint = f" Maksudnya: {', '.join(near)}?" if near else ""
    return [brain.to_owner(f"Barang '{args}' tidak ada di daftar.{hint}")]


def _faq_number(text: str) -> int:
    if not text.strip().isdigit():
        raise ValueError("nomor FAQ harus angka, cek dengan /faq")
    return int(text)


def _faq(brain, args: str) -> list[Outgoing]:
    kb = brain.knowledge
    if not args:
        lines = [
            f"{i}. [{', '.join(e['kata_kunci'])}]\n   {e['jawaban']}"
            for i, e in enumerate(kb.faq, 1)
        ]
        return [brain.to_owner("FAQ:\n" + "\n".join(lines) if lines else "FAQ masih kosong.")]
    action, _, rest = args.partition(" ")
    left, _, right = (part.strip() for part in rest.partition("|"))
    match action.lower():
        case "tambah":
            number = kb.add_faq(left.split(","), right)
            return [brain.to_owner(f"Oke, FAQ nomor {number} ditambah.")]
        case "ubah":
            kb.update_faq(_faq_number(left), answer=right)
            return [brain.to_owner(f"Oke, jawaban FAQ nomor {left} diubah.")]
        case "kunci":
            kb.update_faq(_faq_number(left), keywords=right.split(","))
            return [brain.to_owner(f"Oke, kata kunci FAQ nomor {left} diubah.")]
        case "hapus":
            kb.remove_faq(_faq_number(left))
            return [brain.to_owner(f"Oke, FAQ nomor {left} dihapus.")]
    raise ValueError("pilih: tambah, ubah, kunci, atau hapus. Lihat /bantuan")


def _info(brain, args: str) -> list[Outgoing]:
    kb = brain.knowledge
    if args:
        field, _, value = args.partition(" ")
        if field.lower() not in _INFO_FIELDS:
            raise ValueError("pilih: " + ", ".join(_INFO_FIELDS))
        kb.set_profile(_INFO_FIELDS[field.lower()], value)
    p = kb.profile
    return [
        brain.to_owner(
            ("Oke, sudah diubah.\n\n" if args else "")
            + f"Nama: {p['nama']}\nJam buka: {p['jam_buka']}\nLokasi: {p['lokasi']}\n"
            f"Layanan: {', '.join(p['layanan'])}\n"
            f"Ringkasan harian: {p.get('jam_ringkasan', '-')}"
        )
    ]


def _ringkasan(brain, args: str) -> list[Outgoing]:
    try:
        day = date.fromisoformat(args).isoformat() if args else brain.today()
    except ValueError:
        raise ValueError("format tanggal: YYYY-MM-DD") from None
    return [brain.to_owner(build_summary(brain.knowledge, brain.store, day))]


def _bantuan(brain, args: str) -> list[Outgoing]:
    return [brain.to_owner(HELP)]


_COMMANDS = {
    "harga": _harga,
    "hapus": _hapus,
    "faq": _faq,
    "info": _info,
    "ringkasan": _ringkasan,
    "balas": _balas,
    "bantuan": _bantuan,
    "help": _bantuan,
    "start": _bantuan,
}
