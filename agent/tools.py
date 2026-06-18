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
        "name": "get_open_positions",
        "description": "List the agent's tracked open positions with their exit plans: "
                       "entry, side, the calibrated exit window, trailing-stop distance, "
                       "and the hard boundary timestamp.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "check_exits",
        "description": "Run the deterministic exit check now: flatten any tracked position "
                       "that has hit its trailing stop or its hard boundary. Returns the "
                       "exits taken. Safe to call every cycle.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "close_position",
        "description": "Immediately flatten one tracked position regardless of its stop "
                       "(e.g. the thesis is invalidated). PAPER unless live is armed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["symbol"],
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
                 event_budget_pct: float = 25.0, allow_network: bool = True,
                 positions=None):
        self.broker = broker
        self.memory = memory
        self.regime = regime
        self.event_budget_pct = event_budget_pct
        self.allow_network = allow_network
        self.positions = positions          # OpenPositions store (optional)
        self._quote_cache: dict[str, float] = {}
        self._last_plan: dict[str, dict] = {}   # instrument -> calibrated leg
        self._exits = None
        if positions is not None:
            from .exits import ExitManager
            self._exits = ExitManager(broker, memory, positions,
                                      allow_network=allow_network)

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
        # remember each leg's exit plan so place_order can set the right
        # trailing stop / boundary when the agent acts on it
        self._last_headline = text[:160]
        for leg in plan.get("plans", []):
            self._last_plan[leg["instrument"]] = leg
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
                self._record_exit_plan(symbol, side, fill.qty, fill.price)
            else:
                self.memory.clear_position(symbol)
                if self.positions is not None:
                    self.positions.remove(symbol)
        return rec

    def _record_exit_plan(self, symbol: str, side: str, qty: int, price: float) -> None:
        """Register the freshly-opened position with the exit manager, deriving
        the window + trail from the calibrated leg analyze_news produced."""
        if self._exits is None:
            return
        leg = self._last_plan.get(symbol, {})
        window = leg.get("window", "intraday")
        exp_move = abs(leg.get("expected_move_pct", 1.0)) or 1.0
        self._exits.record_entry(symbol, side, qty, price, window=window,
                                 expected_move_pct=exp_move,
                                 headline=getattr(self, "_last_headline", ""))

    def get_open_positions(self) -> dict:
        """Tracked open positions with their exit plans (window, trailing stop,
        hard boundary)."""
        if self.positions is None:
            return {"positions": {}, "note": "no exit tracking configured"}
        return {"positions": self.positions.all()}

    def check_exits(self) -> dict:
        """Run the deterministic exit check now; flatten any position that has
        hit its trailing stop or boundary. Returns the exits taken."""
        if self._exits is None:
            return {"exits": [], "note": "no exit tracking configured"}
        return {"exits": self._exits.check_and_exit()}

    def close_position(self, symbol: str, reason: str = "manual") -> dict:
        """Flatten one tracked position immediately, regardless of its stop."""
        symbol = symbol.upper()
        held = self.broker.positions().get(symbol)
        if not held:
            if self.positions is not None:
                self.positions.remove(symbol)
            return {"status": "flat", "symbol": symbol}
        price = self._quote([symbol])[symbol]["price"]
        side = "sell" if held["qty"] > 0 else "buy"
        fill = self.broker.market_order(symbol, side, abs(int(held["qty"])), price)
        rec = fill.to_dict()
        rec["mode"] = getattr(self.broker, "mode", "PAPER")
        self.memory.log("close_position", reason=reason, **rec)
        if fill.status == "filled":
            self.memory.clear_position(symbol)
            if self.positions is not None:
                self.positions.remove(symbol)
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
            "get_open_positions": self.get_open_positions,
            "check_exits": self.check_exits,
            "close_position": self.close_position,
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
