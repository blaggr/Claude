"""Provider-agnostic LLM adapter and the Agent base class.

Modules import cleanly without an API key or the SDK installed; both are only
required when an agent actually calls the model. Without a key, agents return a
clearly-marked stub so the loop's control flow runs end-to-end.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class LLMClient:
    """Thin, provider-agnostic wrapper. Default target: the Claude API.

    Swap this class to retarget providers without touching agents.
    """

    def __init__(
        self,
        model: str = "claude-opus-4-8",
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def complete(self, system: str, user: str) -> str:
        """Return the model's text response.

        Falls back to a placeholder if no API key is present, so the
        orchestrator can be exercised without secrets. With a key, makes a real
        Claude API call (lazy SDK import so the module imports without it).
        """
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return json.dumps(
                {"_stub": True, "note": "Set ANTHROPIC_API_KEY to run agents for real."}
            )
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # SDK not installed
            raise RuntimeError(
                "The anthropic SDK is required to run agents. "
                "Install it with: pip install -r requirements.txt"
            ) from exc

        client = Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in msg.content if getattr(block, "type", None) == "text"
        )


class Agent:
    """Base class for a research-loop agent.

    Subclasses set ROLE and OUTPUT_SCHEMA (a dict of expected top-level keys)
    and implement build_user_prompt(context). The base class loads the system
    prompt, appends any reviewer revision feedback, calls the model, parses
    JSON, and validates the output shape.
    """

    ROLE: str = "agent"
    OUTPUT_SCHEMA: dict[str, str] = {}

    def __init__(self, llm: LLMClient):
        self.llm = llm

    @property
    def system_prompt(self) -> str:
        path = PROMPTS_DIR / f"{self.ROLE}.md"
        return path.read_text(encoding="utf-8") if path.exists() else f"You are the {self.ROLE}."

    def build_user_prompt(self, context: dict[str, Any]) -> str:
        raise NotImplementedError

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        user = self.build_user_prompt(context)
        feedback = context.get("_revise_feedback")
        if feedback:
            user += (
                "\n\nA reviewer requested revisions to your previous output. "
                f"Address this specifically and re-output the full JSON:\n{feedback}"
            )
        raw = self.llm.complete(self.system_prompt, user)
        data = self._parse_json(raw)
        self._validate(data)
        return data

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        """Parse the model response, tolerating ```json fences and stray prose."""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # Strip a fenced code block if present.
        fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
        candidate = fence.group(1) if fence else None
        if candidate is None:
            # Fall back to the outermost braces.
            start, end = raw.find("{"), raw.rfind("}")
            candidate = raw[start : end + 1] if start != -1 and end > start else None
        if candidate:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        return {"_unparsed": raw}

    def _validate(self, data: dict[str, Any]) -> None:
        if data.get("_stub") or "_unparsed" in data:
            return  # stub / unparsed — skip strict validation
        missing = [k for k in self.OUTPUT_SCHEMA if k not in data]
        if missing:
            raise ValueError(f"{self.ROLE} output missing keys: {missing}")
