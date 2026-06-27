"""Provider-agnostic LLM adapter and the Agent base class.

Modules import cleanly without an API key; the key (ANTHROPIC_API_KEY) is only
required when an agent actually calls the model. Until the client is wired
(Phase 1), agents return a clearly-marked stub so the loop runs end-to-end.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class LLMClient:
    """Thin, provider-agnostic wrapper. Default target: the Claude API.

    Swap this class to retarget providers without touching agents.
    """

    def __init__(self, model: str = "claude-opus-4-8", temperature: float = 0.2):
        self.model = model
        self.temperature = temperature

    def complete(self, system: str, user: str) -> str:
        """Return the model's text response.

        Phase 0 stub: if no API key is present, returns a placeholder so the
        orchestrator can be exercised without secrets. Phase 1 replaces the
        body with a real Claude API call.
        """
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return json.dumps(
                {"_stub": True, "note": "Set ANTHROPIC_API_KEY and wire LLMClient.complete()"}
            )
        # Phase 1: implement the real call here, e.g.:
        #   from anthropic import Anthropic
        #   client = Anthropic(api_key=api_key)
        #   msg = client.messages.create(
        #       model=self.model, max_tokens=4096, temperature=self.temperature,
        #       system=system, messages=[{"role": "user", "content": user}])
        #   return msg.content[0].text
        raise NotImplementedError("Wire the Claude API call in Phase 1 (see comment).")


class Agent:
    """Base class for a research-loop agent.

    Subclasses set ROLE and OUTPUT_SCHEMA (a dict of expected top-level keys)
    and implement build_user_prompt(context). The base class loads the system
    prompt, calls the model, parses JSON, and validates the output shape.
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
        raw = self.llm.complete(self.system_prompt, self.build_user_prompt(context))
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"_unparsed": raw}
        self._validate(data)
        return data

    def _validate(self, data: dict[str, Any]) -> None:
        if data.get("_stub") or "_unparsed" in data:
            return  # Phase 0 stub / unwired model — skip strict validation
        missing = [k for k in self.OUTPUT_SCHEMA if k not in data]
        if missing:
            raise ValueError(f"{self.ROLE} output missing keys: {missing}")
