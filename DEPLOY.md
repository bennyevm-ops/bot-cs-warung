# Deploying bot-cs-warung

The bot is one long-running process that polls Telegram. It needs outbound HTTPS only:
no domain, no open port, no webhook. Any always-on Linux machine with Python 3.12 works.

## What the owner must provide

| Value | Required | Where it comes from |
| --- | --- | --- |
| `BOT_TOKEN` | yes | @BotFather in Telegram: `/newbot`, then copy the token |
| `OWNER_CHAT_ID` | yes | The owner's Telegram chat id (step 3 below) |
| `LLM_API_BASE`, `LLM_API_KEY`, `LLM_MODEL` | no | An OpenAI-compatible endpoint for smart answers. All three or none |

Without `OWNER_CHAT_ID` the bot still answers customers, but owner commands, handoff to
the owner and the daily summary are off.

## Steps

1. Get the code and create the env file:
   ```bash
   git clone https://github.com/bennyevm-ops/bot-cs-warung.git
   cd bot-cs-warung
   cp .env.example .env
   ```
2. Put `BOT_TOKEN` in `.env`.
3. Find `OWNER_CHAT_ID`: run `./start.sh`, send the bot any message from the owner's
   Telegram account, and read the number after `chat id` in the log line
   `Pesan dari telegram chat id ...`. Stop the bot (Ctrl+C) and put the number in `.env`.
4. Start it:
   ```bash
   ./start.sh
   ```
   The log shows `Bot jalan`. Send `/info` from the owner account to check.

`./start.sh` is the only start command. On first run it creates `.venv` and installs the
bot; set `PYTHON` if Python 3.12 is not called `python3.12`.

## Shop data

On first start the sample `config/warung.json` is copied to `data/warung.json`. That copy
is what the bot uses: edit it for the shop's name, hours, location, services, tariff,
prices and FAQ (restart after editing by hand), or use the owner commands in the chat.
The chat log is in `data/bot.sqlite3`. Back up the `data/` folder; it is not in git.

To keep these files elsewhere, set `WARUNG_CONFIG` and `DB_PATH`.

## Keep it running (systemd)

`/etc/systemd/system/bot-cs-warung.service`, with the path and user adjusted:

```ini
[Unit]
Description=Bot CS Warung
After=network-online.target
Wants=network-online.target

[Service]
User=warung
WorkingDirectory=/home/warung/bot-cs-warung
ExecStart=/home/warung/bot-cs-warung/start.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now bot-cs-warung
journalctl -u bot-cs-warung -f
```

Run only one copy of the bot per token; Telegram rejects two pollers.

## Updating

```bash
git pull
.venv/bin/pip install -e .
sudo systemctl restart bot-cs-warung
```

## Secrets

`.env` is git-ignored and must stay out of git. If the token leaks, revoke it with
`/revoke` in @BotFather and put the new one in `.env`.
