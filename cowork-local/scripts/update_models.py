#!/usr/bin/env python3
"""Keep Cowork Local on the newest Qwen / GLM open model available in Ollama.

What it does, each run:
  1. Discovers the newest *base* model published in the Ollama library for each
     tracked family (default: qwen, glm). "Newest" = highest version number in
     the model name (qwen3 > qwen2.5 > qwen2). This adapts automatically when a
     vendor ships a new major version under a new name.
  2. Pulls that model via the local Ollama daemon (skips if already current).
  3. Writes the chosen default to ~/.cowork-local/config.json, which the app
     reads to pre-select the best model on launch.

Why discovery instead of a hardcoded version: new releases get new names that
can't be predicted ahead of time, so we look at what Ollama actually publishes
and take the latest.

No third-party dependencies — standard library only.

Usage:
    python3 update_models.py                # update all tracked families
    python3 update_models.py --primary glm  # make GLM the default if present
    python3 update_models.py --check        # report only; do not pull
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

OLLAMA_LIBRARY_SEARCH = "https://ollama.com/search?q={q}"
OLLAMA_REGISTRY_TAGS = "https://registry.ollama.ai/v2/library/{model}/tags/list"
LOCAL_OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
CONFIG_DIR = Path.home() / ".cowork-local"
CONFIG_PATH = CONFIG_DIR / "config.json"

# Families we track. The key is the name prefix used both for the library
# search and for matching "base" model slugs.
DEFAULT_FAMILIES = ["qwen", "glm"]

# Slugs we never want as the chat default even if they match a family prefix.
EXCLUDE_SUBSTRINGS = ("coder", "embed", "vl", "vision", "math", "guard", "edge")


def http_get(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "cowork-local-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def version_key(slug: str, family: str) -> tuple:
    """Turn 'qwen2.5' -> (2, 5); 'qwen' -> (0,); used to rank releases."""
    rest = slug[len(family):]
    nums = re.findall(r"\d+", rest)
    return tuple(int(n) for n in nums) if nums else (0,)


def discover_latest(family: str) -> str | None:
    """Return the newest base model slug for a family, or None if not found."""
    candidates: set[str] = set()

    # Primary source: the library search page lists /library/<slug> links.
    try:
        html = http_get(OLLAMA_LIBRARY_SEARCH.format(q=family))
        for slug in re.findall(r'/library/([a-z0-9._-]+)', html):
            candidates.add(slug)
    except Exception as e:  # noqa: BLE001
        print(f"  ! library search failed for {family}: {e}", file=sys.stderr)

    # Keep only "base" models: prefix + version digits/dots, no extra words,
    # and not an excluded specialty variant.
    base_re = re.compile(rf"^{re.escape(family)}[0-9.]*$")
    bases = [
        s for s in candidates
        if base_re.match(s) and not any(x in s for x in EXCLUDE_SUBSTRINGS)
    ]

    if not bases:
        return None
    bases.sort(key=lambda s: version_key(s, family), reverse=True)
    return bases[0]


def installed_models() -> list[str]:
    try:
        raw = http_get(f"{LOCAL_OLLAMA}/api/tags", timeout=10)
        data = json.loads(raw)
        return [m["name"] for m in data.get("models", [])]
    except Exception:  # noqa: BLE001
        return []


def is_installed(slug: str, installed: list[str]) -> bool:
    # Ollama reports installed names with a tag, e.g. "qwen3:latest".
    return any(name == slug or name.startswith(slug + ":") for name in installed)


def pull(slug: str) -> bool:
    """Pull a model with the ollama CLI, streaming progress to the console."""
    print(f"  → pulling {slug} (this can take several GB)…")
    try:
        subprocess.run(["ollama", "pull", slug], check=True)
        return True
    except FileNotFoundError:
        print("  ! 'ollama' CLI not found on PATH. Install from https://ollama.com",
              file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print(f"  ! pull failed for {slug}: {e}", file=sys.stderr)
    return False


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:  # noqa: BLE001
            pass
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
    print(f"  wrote {CONFIG_PATH}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Update Cowork Local's open models.")
    ap.add_argument("--families", nargs="+", default=DEFAULT_FAMILIES,
                    help="Model family prefixes to track (default: qwen glm).")
    ap.add_argument("--primary", default=None,
                    help="Family to use as the app default when present "
                         "(default: first family that resolves).")
    ap.add_argument("--check", action="store_true",
                    help="Report the latest available models without pulling.")
    args = ap.parse_args()

    families = [f.lower() for f in args.families]
    primary = (args.primary or "").lower() or None

    print(f"Tracking families: {', '.join(families)}")
    installed = installed_models()

    resolved: dict[str, str] = {}
    for fam in families:
        latest = discover_latest(fam)
        if not latest:
            print(f"- {fam}: no base model found in the Ollama library "
                  f"(it may not be published there yet).")
            continue
        here = is_installed(latest, installed)
        print(f"- {fam}: latest = {latest}" + ("  [installed]" if here else "  [missing]"))
        resolved[fam] = latest
        if args.check:
            continue
        if not here and not pull(latest):
            continue
        resolved[fam] = latest

    if not resolved:
        print("No Qwen/GLM models could be resolved. If you're offline or behind "
              "a proxy, retry later. For GLM specifically, you may need to import "
              "a GGUF manually (see README).", file=sys.stderr)
        return 1

    # Decide the default the app pre-selects.
    order = [primary] if primary and primary in resolved else []
    order += [f for f in families if f in resolved and f not in order]
    preferred = resolved[order[0]]

    cfg = load_config()
    cfg.update({
        "preferredModel": preferred,
        "families": families,
        "primaryFamily": order[0],
        "resolved": resolved,
    })
    if not args.check:
        save_config(cfg)
        print(f"\nDefault model set to: {preferred}")
    else:
        print(f"\n(check only) would set default to: {preferred}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
