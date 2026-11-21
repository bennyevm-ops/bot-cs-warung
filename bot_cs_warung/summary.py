"""Daily summary for the owner."""

from .knowledge import Knowledge
from .storage import Store


def build_summary(knowledge: Knowledge, store: Store, day: str) -> str:
    s = store.daily_stats(day)
    return (
        f"Ringkasan {day} - {knowledge.profile['nama']}\n"
        f"• Jumlah chat (pelanggan): {s['chats']}\n"
        f"• Pesan masuk: {s['messages']}\n"
        f"• Pertanyaan dijawab bot: {s['answered']}\n"
        f"• Diteruskan ke pemilik: {s['handed_off']} (sudah dibalas: {s['owner_replied']})"
    )
