# bot-cs-warung

Customer-service bot for an Indonesian warung kelontong that also runs a money
transfer / tarik tunai service. Telegram first, with a channel-agnostic core so a
WhatsApp channel can be added without touching the brain. The bot talks Indonesian:
short, casual, like a shopkeeper.

## What it does

For customers:

- Greeting and main menu buttons: Tarif Transfer, Harga Barang, Jam Buka, Layanan, Chat Pemilik.
- Fee calculator in chat: `transfer 600rb ke BRI` or `tarik tunai 1,5jt` gets the
  principal, the fee and the total. Understands `600rb`, `1,5jt`, `250.000`, `2 juta`,
  `Rp 1.250.000`, `600k`.
- Price lookup: type an item name (typos are fine) and get the price.
- FAQ auto-answers (bank tujuan, tarik tunai, pulsa/paketan, QRIS, ...).
- Optional smart answers from an OpenAI-compatible model, limited to the shop knowledge.
- Human handoff: anything the bot cannot answer is forwarded to the owner with the
  customer identity. The owner replies through the bot.

For the owner (only the chat in `OWNER_CHAT_ID`):

| Command | What it does |
| --- | --- |
| `/harga <barang> <harga>` | Set or update a price, e.g. `/harga indomie goreng 3500`, `/harga beras 5kg 75rb` |
| `/harga` | List all prices |
| `/hapus <barang>` | Remove an item |
| `/faq` | List FAQ entries with their numbers |
| `/faq tambah <kata kunci, dipisah koma> \| <jawaban>` | Add an FAQ entry |
| `/faq ubah <nomor> \| <jawaban baru>` | Change an answer |
| `/faq kunci <nomor> \| <kata kunci baru>` | Change the keywords |
| `/faq hapus <nomor>` | Remove an entry |
| `/info` | Show the shop profile |
| `/info <nama\|jam\|lokasi\|layanan\|ringkasan> <isi>` | Update a profile line (`layanan` is comma-separated, `ringkasan` is the daily summary time `HH:MM`) |
| `/ringkasan [YYYY-MM-DD]` | Daily summary on demand |
| `/balas <nomor chat> <jawaban>` | Answer a forwarded chat by its number |

To answer a customer, reply to the forwarded message in Telegram (or use `/balas`).
The daily summary (number of chats, questions answered by the bot, questions handed
off) is also sent automatically once a day at `jam_ringkasan`.

## Setup

1. **Create the bot.** In Telegram, open [@BotFather](https://t.me/BotFather), send
   `/newbot`, pick a name and a username, and copy the token it gives you.
2. **Set the environment.** Copy `.env.example` to `.env` and fill it in. `.env` is
   git-ignored; the token must never be committed.

   | Variable | Required | Meaning |
   | --- | --- | --- |
   | `BOT_TOKEN` | yes | Token from BotFather (`TELEGRAM_BOT_TOKEN` also works) |
   | `OWNER_CHAT_ID` | for owner features | Telegram chat id of the owner |
   | `LLM_API_BASE`, `LLM_API_KEY`, `LLM_MODEL` | no | OpenAI-compatible endpoint for smart answers; all three must be set |
   | `WARUNG_CONFIG` | no | Shop knowledge file; `./start.sh` uses `data/warung.json` |
   | `DB_PATH` | no | SQLite log, default `data/bot.sqlite3` |

   To find `OWNER_CHAT_ID`: start the bot with it empty, send the bot any message from
   the owner's Telegram account, and read the `chat id` from the bot's log line. Put it
   in `.env` and restart. The owner has to message the bot once anyway: Telegram bots
   cannot start a conversation.
3. **Run** (needs Python 3.12):
   ```bash
   ./start.sh
   ```
   The first run creates `.venv`, installs the bot and copies the sample
   `config/warung.json` to `data/warung.json`, which is the file the bot then uses.
4. **Fill in the shop knowledge** in `data/warung.json` (see below), or with the owner
   commands in the chat.

Running it on a server: see [DEPLOY.md](DEPLOY.md).

## Shop knowledge: `config/warung.json`

Everything the bot knows comes from this one file; nothing is hardcoded.

- `profil`: `nama`, `jam_buka`, `lokasi`, `layanan`, plus `zona_waktu` and
  `jam_ringkasan` for the daily summary.
- `tarif`: fee = `min(ceil(amount / kelipatan), maks_kelipatan) * biaya_per_kelipatan`,
  never below `biaya_minimum`, and a flat `biaya_flat` above `batas_flat`. The shipped
  values give Rp5.000 per Rp500.000, minimum Rp5.000, flat Rp50.000 above Rp4.500.000.
- `harga`: item name → price.
- `faq`: list of `{ "kata_kunci": [...], "jawaban": "..." }`.

The owner commands write their changes back to the file in use, so they survive a
restart. `./start.sh` runs the bot on a copy, `data/warung.json`, which is outside git;
`config/warung.json` stays the sample.

## How a customer message is answered

1. Greeting or menu button → menu / the matching info.
2. Transfer or tarik tunai with an amount → fee calculation.
3. Price question that matches an item → price.
4. FAQ keywords → FAQ answer.
5. Opening hours, location, services → from the profile.
6. A bare item name → price.
7. Smart answer, if configured.
8. Otherwise → handoff to the owner.

Behaviours worth knowing:

- Transfer: the customer pays principal + fee. Tarik tunai: the fee is taken out of
  the cash, so the customer receives principal − fee.
- A bare number below 1.000 (`transfer 500`) is not treated as an amount, because
  Rp500 and 500rb are both plausible; the bot shows the tariff and an example instead.
- After the customer taps Chat Pemilik, their next message goes straight to the owner.

### Smart answers

When `LLM_API_BASE`, `LLM_API_KEY` and `LLM_MODEL` are all set, questions the rules
cannot answer are sent to `{LLM_API_BASE}/chat/completions` together with the shop
knowledge. The model is told to answer only from that knowledge and to say `HANDOFF`
otherwise. As a second guard, an answer that mentions a rupiah amount not present in
the shop knowledge (or in the customer's own question) is discarded and the chat is
handed off, so the bot never invents a price or a fee. If the endpoint fails, the bot
hands off as well. Note that with this enabled, customer questions are sent to that
endpoint.

## Why the raw Bot API instead of python-telegram-bot

The bot needs three Bot API methods: `getUpdates` (long polling), `sendMessage` and
`answerCallbackQuery`. Calling them directly with httpx takes about 100 lines, and
httpx is needed anyway for the optional LLM call, so the project has exactly one
runtime dependency. It also keeps the core synchronous and free of any Telegram
types, which is what makes a second channel cheap to add. python-telegram-bot would
bring an async application framework the bot would not otherwise use.

## Layout

| Module | Role |
| --- | --- |
| `amount.py` | Indonesian rupiah amount parser |
| `tariff.py` | Fee calculator |
| `matching.py` | Fuzzy price lookup and FAQ keyword match |
| `knowledge.py` | Loads and saves `config/warung.json` |
| `brain.py` | Channel-agnostic core: one `Incoming` in, a list of `Outgoing` out |
| `owner.py` | Owner commands and replies to customers |
| `llm.py` | Optional OpenAI-compatible client with the grounding guard |
| `storage.py` | SQLite conversation and handoff log |
| `summary.py` | Daily summary text |
| `channels/telegram.py` | Telegram channel (raw Bot API) |
| `app.py`, `settings.py` | Wiring and env settings |

To add WhatsApp: write a class with `name`, `send(out)` and `run(on_message, on_tick)`
(see `channels/base.py`) that converts WhatsApp webhooks to `Incoming`, and add it to
the channel list in `app.py`. The brain does not change.

## Tests

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

CI (GitHub Actions) runs the same on Python 3.12 for every pull request.
