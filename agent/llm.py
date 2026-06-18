"""The reasoning layer — pluggable so the loop is identical online and offline.

A "step" of the loop is: given the system prompt, the tool schemas, and the
conversation so far, return either tool calls to execute or a final answer.
Both backends below implement that single `step()` contract:

  * AnthropicLLM  — real tool-use with Claude (claude-opus-4-8). Used whenever
    ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) is set.

  * HeuristicLLM  — a deterministic offline policy that walks the *same* tools
    in the order the write-up recommends (remember → analyze → check book →
    size & place → record a lesson → done). No network, no key. This is what
    makes the agent runnable in a locked-down environment and unit-testable,
    mirroring the graceful-fallback pattern used elsewhere in this repo.

The two are interchangeable: the agent loop never branches on which is active.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class Step:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def is_final(self) -> bool:
        return not self.tool_calls


MODEL = "claude-opus-4-8"


class AnthropicLLM:
    """Claude tool-use backend."""

    def __init__(self, model: str = MODEL, max_tokens: int = 1500):
        import anthropic  # lazy
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens

    @staticmethod
    def available() -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))

    def step(self, system: str, tools: list[dict], messages: list[dict],
             last_outputs=None) -> Step:
        resp = self.client.messages.create(
            model=self.model, max_tokens=self.max_tokens,
            system=system, tools=tools, messages=messages,
        )
        text_parts, calls = [], []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                calls.append(ToolCall(block.id, block.name, dict(block.input)))
        # record the assistant turn verbatim so tool_results can reference ids
        messages.append({"role": "assistant", "content":
                         [self._serialize(b) for b in resp.content]})
        return Step(text="\n".join(text_parts) or None, tool_calls=calls)

    @staticmethod
    def _serialize(block):
        if block.type == "text":
            return {"type": "text", "text": block.text}
        if block.type == "tool_use":
            return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
        return {"type": block.type}


class HeuristicLLM:
    """Offline policy that drives the same tools deterministically.

    It keeps a small plan queue and advances it using the tool results handed
    back each step, so its behaviour depends on real observations (e.g. it only
    places an order when analyze_news returns a confident leg with room in the
    book), not a fixed script.
    """

    def __init__(self, *, min_confidence: str = "medium", base_qty: int = 10):
        self.min_confidence = min_confidence
        self.base_qty = base_qty
        self._stage = 0
        self._news_texts: list[str] = []
        self._plan: dict | None = None
        self._acted: list[str] = []
        self._conf_rank = {"low": 0, "medium": 1, "high": 2}

    @staticmethod
    def available() -> bool:
        return True

    def prime(self, news_texts: list[str]) -> None:
        """The loop hands the heuristic the session's candidate news items."""
        self._news_texts = list(news_texts)

    def _ok_conf(self, c: str) -> bool:
        return self._conf_rank.get(c, 0) >= self._conf_rank[self.min_confidence]

    def step(self, system, tools, messages, last_outputs=None) -> Step:
        out = {o["name"]: o["result"] for o in (last_outputs or [])}

        # stage 0: read memory
        if self._stage == 0:
            self._stage = 1
            return Step(tool_calls=[ToolCall("c0", "read_memory", {})])

        # stage 1: analyze the strongest available news item
        if self._stage == 1:
            self._stage = 2
            text = self._news_texts[0] if self._news_texts else \
                "No fresh market-moving headline."
            return Step(tool_calls=[ToolCall("c1", "analyze_news",
                        {"text": text, "base_qty": self.base_qty})])

        # stage 2: inspect the plan; if tradable, look at the book
        if self._stage == 2:
            self._plan = out.get("analyze_news")
            plans = (self._plan or {}).get("plans", [])
            tradable = [p for p in plans if self._ok_conf(p.get("confidence", "low"))]
            self._plan_legs = tradable
            self._stage = 3
            return Step(tool_calls=[ToolCall("c2", "get_portfolio", {})])

        # stage 3: place the lead leg if there is one and we have room
        if self._stage == 3:
            self._stage = 4
            legs = getattr(self, "_plan_legs", [])
            if not legs:
                return Step(text="No confident, calibrated edge in the current news; "
                                 "standing pat. (Logged to memory.)")
            lead = legs[0]
            side = lead["side"].lower()
            return Step(tool_calls=[ToolCall("c3", "place_order", {
                "symbol": lead["instrument"], "side": side,
                "qty": int(lead["quantity"]),
                "reason": lead["rationale"][:160]})])

        # stage 4: record a one-line lesson and finish
        if self._stage == 4:
            self._stage = 5
            order = out.get("place_order", {})
            if order.get("status") == "filled":
                lesson = (f"Acted on calibrated edge: {order['side']} {order['qty']} "
                          f"{order['symbol']} @ {order['price']:.2f}. "
                          "Respect the overnight/intraday exit window.")
                return Step(tool_calls=[ToolCall("c4", "remember", {"lesson": lesson})])
            return Step(text="Order not filled; no position taken this session.")

        return Step(text="Session complete.")
