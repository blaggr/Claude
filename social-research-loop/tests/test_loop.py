"""Tests for the Phase 1 research-loop wiring.

These run without an API key: a FakeLLM returns canned JSON so the agent
contract, JSON parsing, revision plumbing, and resumable state are all exercised
deterministically.

    cd social-research-loop && python -m pytest tests/ -q
    # or, without pytest:
    cd social-research-loop && python -m unittest discover tests -v
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import Librarian, Methodologist  # noqa: E402
from agents.base import Agent, LLMClient  # noqa: E402
from agents.interpreter import FRAMEWORK_LEVELS  # noqa: E402
from loop.config import load_config  # noqa: E402
from loop.state import RunState  # noqa: E402


class FakeLLM(LLMClient):
    """Returns a canned response and records the last user prompt it saw."""

    def __init__(self, response: str):
        super().__init__()
        self.response = response
        self.last_user = None

    def complete(self, system: str, user: str) -> str:
        self.last_user = user
        return self.response


class ParsingTests(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(Agent._parse_json('{"a": 1}'), {"a": 1})

    def test_fenced_json(self):
        raw = 'Here you go:\n```json\n{"a": 1}\n```\nHope that helps.'
        self.assertEqual(Agent._parse_json(raw), {"a": 1})

    def test_unparseable_is_flagged(self):
        self.assertIn("_unparsed", Agent._parse_json("not json at all"))


class AgentContractTests(unittest.TestCase):
    def test_librarian_valid_output_passes(self):
        payload = {
            "research_question": "Q",
            "background": "B",
            "known_vs_open": [],
            "hypotheses": [],
            "sources": [],
        }
        agent = Librarian(FakeLLM(json.dumps(payload)))
        out = agent.run({"question": "test", "framework": "kirkpatrick", "seed": {}})
        self.assertEqual(out["research_question"], "Q")

    def test_missing_keys_raise(self):
        agent = Librarian(FakeLLM('{"research_question": "Q"}'))
        with self.assertRaises(ValueError):
            agent.run({"question": "test", "seed": {}})

    def test_revision_feedback_reaches_prompt(self):
        llm = FakeLLM('{"_stub": true}')
        Methodologist(llm).run(
            {"frame": {}, "seed": {}, "_revise_feedback": "name the fairness metric"}
        )
        self.assertIn("name the fairness metric", llm.last_user)

    def test_seed_reaches_librarian_prompt(self):
        llm = FakeLLM('{"_stub": true}')
        Librarian(llm).run({"question": "q", "seed": {"population": "new caseworkers"}})
        self.assertIn("new caseworkers", llm.last_user)


class ProviderTests(unittest.TestCase):
    def test_openai_default_model(self):
        self.assertEqual(LLMClient(provider="openai").model, "gpt-4o")

    def test_unknown_provider_rejected(self):
        with self.assertRaises(ValueError):
            LLMClient(provider="nope")

    def test_stub_without_key_names_the_right_env_var(self):
        import os

        saved = os.environ.pop("OPENAI_API_KEY", None)
        try:
            out = LLMClient(provider="openai").complete("sys", "user")
            self.assertIn("OPENAI_API_KEY", out)
        finally:
            if saved is not None:
                os.environ["OPENAI_API_KEY"] = saved


class StateTests(unittest.TestCase):
    def test_advance_and_status(self):
        s = RunState(run_id="t", question="q")
        self.assertEqual(s.current_stage, "frame")
        s.advance()
        self.assertEqual(s.current_stage, "design")
        self.assertEqual(s.status, "pending_gate")

    def test_completes_after_last_stage(self):
        s = RunState(run_id="t", question="q", stages=["frame"])
        s.advance()
        self.assertIsNone(s.current_stage)
        self.assertEqual(s.status, "done")


class ConfigTests(unittest.TestCase):
    def test_pilot_config_is_valid_and_runnable(self):
        cfg = load_config(Path(__file__).resolve().parent.parent / "config" / "pilot-coaching-turnover.yaml")
        self.assertIn("question", cfg["project"])
        self.assertEqual(cfg["project"]["framework"], "kirkpatrick")
        self.assertIn(cfg["project"]["framework"], FRAMEWORK_LEVELS)
        self.assertTrue(cfg["equity"]["require_subgroup_analysis"])


if __name__ == "__main__":
    unittest.main()
