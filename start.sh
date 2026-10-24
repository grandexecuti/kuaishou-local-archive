#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if command -v python3 >/dev/null 2>&1; then
  python3 server.py --open
elif command -v python >/dev/null 2>&1; then
  python server.py --open
else
  echo "Python 3.10+ is required. Install it from https://www.python.org/downloads/"
  exit 1
fi
