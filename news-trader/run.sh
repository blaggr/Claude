#!/bin/bash
# launchd entrypoint for the news-trader paper worker.
# Loads credentials from .env.local (gitignored, chmod 600) so secrets stay out
# of the plist and out of git, then execs the worker in the project venv.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$HERE/.env.local" ]; then
  set -a
  . "$HERE/.env.local"
  set +a
fi
exec "$HERE/.venv/bin/python3" "$HERE/worker.py"
