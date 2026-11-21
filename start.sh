#!/usr/bin/env bash
# Start the bot: ./start.sh  (reads .env; see DEPLOY.md)
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  "${PYTHON:-python3.12}" -m venv .venv
  .venv/bin/pip install --quiet -e .
fi

# Shop data lives in data/ (git-ignored), so updating the code never touches the owner's edits.
if [ -z "${WARUNG_CONFIG:-}" ] && ! grep -qs '^WARUNG_CONFIG=' .env; then
  export WARUNG_CONFIG=data/warung.json
  mkdir -p data
  [ -f "$WARUNG_CONFIG" ] || cp config/warung.json "$WARUNG_CONFIG"
fi

exec .venv/bin/python -m bot_cs_warung
