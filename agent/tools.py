"""The agent's toolbox — the "tools" half of the prompt→context→tool→action loop.

Each tool is a plain Python callable returning a JSON-serialisable dict, plus an
Anthropic tool-use schema describing it to the model. The schemas and the
dispatcher are the only contract the agent loop needs; swapping the model out
(or driving the loop with the offline heuristic policy) does not change them.

Every tool reuses infrastructure that already exists in this repo rather than
reinventing it:

  * analyze_news   -> experiments/news_trade_engine.plan_trade (calibrated edges)
  * get_quotes     -> agent/marketdata.snapshot (live -> delayed -> stub)
  * get_portfolio / place_order -> agent/broker (paper by default, risk-gated)
  * read_memory / remember / record_position -> agent/memory.Memory

place_order is deliberately the only state-changing tool, and it is paper
unless the live interlocks in experiments/live/risk.py are armed.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Callable

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "experiments"))

import news_trade_engine as nte  # noqa: E402

from . import marketdata
from .broker import Fill
from .memory import Memory


# ---------------------------------------------------------------- schemas
# Anthropic tool-use definitions. Names match the dispatcher keys below.
TOOL_SCHEMAS = [
    {
        "name": "read_memory",
        "description": "Read the agent's distilled working memory: standing rules, "
                       "lessons from prior sessions, and open positions. Call this FIRST.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "analyze_news",
        "description": "Classify a news item / social post and return the empirically-"
                       "calibrated trade plan (instruments, side, probability, expected "
                       "move, entry/exit window). Use this to turn a headline into a sized idea.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The headline or post text."},
                "regime": {"type": "string", "enum": ["in_office", "out_office"],
                           "description": "Political regime for calibration (default in_office)."},
                "base_qty": {"type": "integer", "description": "Reference share quantity (default 10)."},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_quotes",
        "description": "Current price snapshot for one or more symbols. Each quote is "
                       "tagged with its source (live, delayed, or offline-stub).",
        "input_schema": {
            "type": "object",
            "properties": {"symbols": {"type": "array", "items": {"type": "string"}}},
            "required": ["symbols"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_portfolio",
        "description": "Account equity, cash, and current positions from the broker "
                       "(paper unless live interlocks are armed).",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "place_order",
        "description": "Place a whole-share market order through the broker. PAPER unless "
                       "live is explicitly armed. Use after analyze_news + get_portfolio "
                       "confirm the idea and that there is room within risk limits.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string", "enum": ["buy", "sell"]},
                "qty": {"type": "integer", "minimum": 1},
                "reason": {"type": "string", "description": "One line: why this trade now."},
            },
            "required": ["symbol", "side", "qty", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "name": "remember",
        "description": "Persist a durable lesson to working memory for future sessions. "
                       "Keep it one short, general sentence.",
        "input_schema": {
            "type": "object",
            "properties": {"lesson": {"type": "string"}},
            "required": ["lesson"],
            "additionalProperties": False,
        },
    },
]


class Toolbox:
    """Binds the tool callables to a broker + memory + risk caps for one agent run."""

    def __init__(self, broker, memory: Memory, *, regime: str = "in_office",
                 event_budget_pct: float = 25.0, allow_network: bool = True):
        self.broker = broker
        self.memory = memory
        self.regime = regime
        self.event_budget_pct = event_budget_pct
        self.allow_network = allow_network
        self._quote_cache: dict[str, float] = {}

    # -- helpers ------------------------------------------------------
    def _quote(self, symbols):
        snap = marketdata.snapshot(symbols, allow_network=self.allow_network)
        for s, q in snap.items():
            self._quote_cache[s] = q["price"]
        return snap

    # -- tools --------------------------------------------------------
    def read_memory(self) -> dict:
        return self.memory.snapshot()

    def analyze_news(self, text: str, regime: str | None = None,
                     base_qty: int = 10) -> dict:
        plan = nte.plan_trade(text, base_qty, regime or self.regime,
                              classify_fn=nte.classify)
        self.memory.log("analyze_news", text=text[:200], decision=plan.get("decision"))
        return plan

    def get_quotes(self, symbols) -> dict:
        return self._quote(symbols)

    def get_portfolio(self) -> dict:
        pos = self.broker.positions()
        prices = self._quote(list(pos)) if pos else {}
        acct = self.broker.account({s: q["price"] for s, q in prices.items()})
        return {"account": acct, "positions": pos}

    def place_order(self, symbol: str, side: str, qty: int, reason: str = "") -> dict:
        symbol = symbol.upper()
        q = self._quote([symbol])[symbol]
        price = q["price"]
        # risk cap: a single order cannot commit more than the per-event budget
        acct = self.broker.account({symbol: price})
        equity = acct.get("equity", 0.0) or 0.0
        max_notional = equity * self.event_budget_pct / 100.0
        if equity and qty * price > max_notional + 1e-6:
            capped = int(max_notional // price)
            self.memory.log("risk_cap", symbol=symbol, requested=qty, capped=capped,
                            reason=f"{self.event_budget_pct}% per-event budget")
            if capped < 1:
                return {"symbol": symbol, "side": side, "qty": 0, "price": price,
                        "status": "rejected",
                        "note": f"order exceeds {self.event_budget_pct}% per-event budget; "
                                f"max {max_notional:.2f} < one share at {price:.2f}"}
            qty = capped
        fill: Fill = self.broker.market_order(symbol, side, qty, price)
        rec = fill.to_dict()
        rec["mode"] = getattr(self.broker, "mode", "PAPER")
        self.memory.log("order", reason=reason, **rec)
        if fill.status == "filled":
            note = f"{side} {fill.qty} @ {fill.price:.2f} — {reason}".strip()
            # net the position note: a flatten clears it, otherwise record it
            if symbol in self.broker.positions():
                self.memory.set_position(symbol, note)
            else:
                self.memory.clear_position(symbol)
        return rec

    def remember(self, lesson: str) -> dict:
        self.memory.remember_lesson(lesson)
        return {"stored": lesson}

    # -- dispatch -----------------------------------------------------
    def dispatch(self, name: str, args: dict[str, Any]) -> dict:
        fn: Callable | None = {
            "read_memory": self.read_memory,
            "analyze_news": self.analyze_news,
            "get_quotes": self.get_quotes,
            "get_portfolio": self.get_portfolio,
            "place_order": self.place_order,
            "remember": self.remember,
        }.get(name)
        if fn is None:
            return {"error": f"unknown tool '{name}'"}
        try:
            return fn(**args)
        except TypeError as exc:
            return {"error": f"bad arguments for {name}: {exc}"}
        except Exception as exc:  # never let a tool crash the loop
            return {"error": f"{type(exc).__name__}: {exc}"}
