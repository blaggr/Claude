"""Persistent memory — the agent's "system that remembers".

The 900-hours write-up makes one point louder than any other: a model that
forgets everything between runs cannot trade. The human's leverage is *planning,
live context, and a system that remembers*. This module is that system.

Two layers, both human-readable on disk so you can audit (and edit) what the
agent believes:

  * JOURNAL  (journal.jsonl) — an append-only event log. Every observation,
             decision, order, fill and lesson the agent records, timestamped.
             This is the immutable record; nothing is ever rewritten.
  * NOTES    (memory.md) — a small, distilled, *rewritable* working memory the
             agent carries into the next session: durable lessons, standing
             rules, and a one-line note on each open position. Kept short on
             purpose — context is precious, so the agent prunes it.

Nothing here talks to a broker or the network; it is pure local state.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIR = os.path.join(HERE, "state")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class Memory:
    """Journal + distilled notes, persisted under ``state_dir``."""

    MAX_LESSONS = 25  # keep working memory small; prune oldest beyond this

    def __init__(self, state_dir: str = DEFAULT_DIR):
        self.dir = state_dir
        os.makedirs(self.dir, exist_ok=True)
        self.journal_path = os.path.join(self.dir, "journal.jsonl")
        self.notes_path = os.path.join(self.dir, "memory.md")
        self._notes = self._load_notes()

    # ----------------------------------------------------------- journal
    def log(self, kind: str, **payload: Any) -> dict:
        """Append one timestamped event to the immutable journal."""
        rec = {"ts": _now(), "kind": kind, **payload}
        with open(self.journal_path, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        return rec

    def journal(self, limit: int | None = None) -> list[dict]:
        if not os.path.exists(self.journal_path):
            return []
        with open(self.journal_path) as f:
            rows = [json.loads(line) for line in f if line.strip()]
        return rows[-limit:] if limit else rows

    # ----------------------------------------------------------- notes
    def _default_notes(self) -> dict:
        return {"lessons": [], "rules": [
            "Paper trading only unless the live interlocks are explicitly armed.",
            "Never risk more than the per-event budget on a single idea.",
            "Calibrated edges are overnight/intraday — do not hold past the exit window.",
        ], "positions": {}}

    def _load_notes(self) -> dict:
        if not os.path.exists(self.notes_path):
            return self._default_notes()
        notes = self._default_notes()
        section = None
        for line in open(self.notes_path):
            line = line.rstrip("\n")
            low = line.strip().lower()
            if low.startswith("## "):
                if "lesson" in low:
                    section = "lessons"
                elif "rule" in low:
                    section = "rules"
                elif "position" in low:
                    section = "positions"
                else:
                    section = None
                continue
            if not line.strip().startswith("- "):
                continue
            item = line.strip()[2:].strip()
            if section == "positions" and ":" in item:
                sym, _, note = item.partition(":")
                notes["positions"][sym.strip()] = note.strip()
            elif section in ("lessons", "rules"):
                notes[section].append(item)
        return notes

    def _save_notes(self) -> None:
        n = self._notes
        lines = ["# Agent working memory",
                 f"_Last updated {_now()}_", "",
                 "## Standing rules"]
        lines += [f"- {r}" for r in n["rules"]]
        lines += ["", "## Lessons learned"]
        lines += [f"- {l}" for l in n["lessons"]] or ["- (none yet)"]
        lines += ["", "## Open positions"]
        if n["positions"]:
            lines += [f"- {sym}: {note}" for sym, note in n["positions"].items()]
        else:
            lines += ["- (flat)"]
        lines.append("")
        with open(self.notes_path, "w") as f:
            f.write("\n".join(lines))

    # ---- mutators (each also journals, so the rewrite is auditable) ----
    def remember_lesson(self, lesson: str) -> None:
        lesson = lesson.strip()
        if not lesson or lesson in self._notes["lessons"]:
            return
        self._notes["lessons"].append(lesson)
        # prune oldest beyond the cap, keeping working memory small
        self._notes["lessons"] = self._notes["lessons"][-self.MAX_LESSONS:]
        self._save_notes()
        self.log("lesson", text=lesson)

    def set_position(self, symbol: str, note: str) -> None:
        self._notes["positions"][symbol.upper()] = note.strip()
        self._save_notes()

    def clear_position(self, symbol: str) -> None:
        if self._notes["positions"].pop(symbol.upper(), None) is not None:
            self._save_notes()

    # ----------------------------------------------------------- views
    def snapshot(self) -> dict:
        """The distilled memory the agent carries into a session."""
        return {
            "rules": list(self._notes["rules"]),
            "lessons": list(self._notes["lessons"]),
            "open_positions": dict(self._notes["positions"]),
        }

    def as_prompt(self) -> str:
        """Compact text block for injection into the model's context."""
        s = self.snapshot()
        out = ["STANDING RULES:"]
        out += [f"  - {r}" for r in s["rules"]]
        out.append("LESSONS FROM PRIOR SESSIONS:")
        out += [f"  - {l}" for l in s["lessons"]] or ["  - (none yet)"]
        if s["open_positions"]:
            out.append("OPEN POSITIONS (from memory):")
            out += [f"  - {k}: {v}" for k, v in s["open_positions"].items()]
        else:
            out.append("OPEN POSITIONS: flat")
        return "\n".join(out)
