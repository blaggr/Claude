"""Resumable run state + audit trail.

One JSON file per research run under loop/state/. Persisting to disk makes runs
survive process restarts and auditable after the fact (a reproducibility
requirement). Timestamps are injected by the caller to keep this deterministic.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

STATE_DIR = Path(__file__).resolve().parent / "state"


@dataclass
class RunState:
    run_id: str
    question: str
    framework: str = "kirkpatrick"
    stages: list[str] = field(
        default_factory=lambda: ["frame", "design", "collect", "analyze", "interpret", "report", "recommend"]
    )
    current_stage_index: int = 0
    status: str = "pending_gate"  # pending_gate | approved | done
    outputs: dict[str, Any] = field(default_factory=dict)      # stage -> agent output
    critic: dict[str, Any] = field(default_factory=dict)       # stage -> critic result
    audit: list[dict[str, Any]] = field(default_factory=list)  # ordered event log

    # --- convenience -----------------------------------------------------
    @property
    def current_stage(self) -> str | None:
        if self.current_stage_index < len(self.stages):
            return self.stages[self.current_stage_index]
        return None

    def log(self, event: str, **details: Any) -> None:
        self.audit.append({"event": event, **details})

    def advance(self) -> None:
        self.current_stage_index += 1
        self.status = "done" if self.current_stage is None else "pending_gate"

    # --- persistence -----------------------------------------------------
    def path(self) -> Path:
        return STATE_DIR / f"run-{self.run_id}.json"

    def save(self) -> Path:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        p = self.path()
        p.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        return p

    @classmethod
    def load(cls, run_id: str) -> "RunState":
        p = STATE_DIR / f"run-{run_id}.json"
        if not p.exists():
            raise FileNotFoundError(f"No run state for id {run_id!r} at {p}")
        return cls(**json.loads(p.read_text(encoding="utf-8")))
