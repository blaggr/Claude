#!/bin/bash
# launchd entrypoint for the news-trader paper worker.
# Robustly loads KEY=VALUE pairs from .env.local (gitignored, chmod 600) WITHOUT
# executing the file, so values containing spaces or shell metacharacters can't
# break it, then execs the worker in the project venv.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$HERE/.env.local" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue ;; esac     # skip blank / comment lines
    [ "$line" = "${line#*=}" ] && continue          # skip lines with no '='
    export "${line%%=*}=${line#*=}"                 # value taken literally, not run
  done < "$HERE/.env.local"
fi
exec "$HERE/.venv/bin/python3" "$HERE/worker.py"
