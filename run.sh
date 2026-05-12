#!/bin/sh
set -e
cd "$(dirname "$0")"
. ./.env
export TELEGRAM_TOKEN
exec ./venv/bin/python3 main.py
