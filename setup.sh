#!/usr/bin/env bash
# Install Python dependencies and prepare configuration; never starts a bot.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
old_dir=''
if [[ $# -gt 0 ]]; then
  if [[ $# -ne 2 || "$1" != '--migrate' ]]; then
    echo 'Usage: bash setup.sh [--migrate /path/to/old/bot]'
    exit 2
  fi
  old_dir="$2"
fi
cd "$project_dir"
python_bin="${ANIPOST_PYTHON:-python3}"
"$python_bin" -c 'import sys; sys.exit("Python 3.10 or newer is required.") if sys.version_info < (3, 10) else None'
if [[ ! -x .venv/bin/python ]]; then
  "$python_bin" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
if [[ -n "$old_dir" ]]; then
  .venv/bin/python migrate.py "$old_dir"
fi
if [[ ! -f .env ]]; then
  cp .env.example .env
fi
chmod 600 .env
.venv/bin/python -c 'import bot, manga_poster, publishing; from poster import font; font(20); print("Python imports and bundled fonts: OK")'
echo 'Setup complete. Edit .env with your bot token and numeric user ID.'
echo 'Run .venv/bin/python check_setup.py before starting the bot.'
echo 'This script did not start or stop any bot. Follow README.md for PM2.'
