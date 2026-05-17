#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Создайте venv: python3.9 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi
source .venv/bin/activate
exec python -m app.main
