"""The agent loop: context -> reason -> tool -> action -> verification -> remember.

This is the whole product, per the 900-hours write-up. One `run_session` does:

  1. CONTEXT   — load distilled memory + any candidate news into the prompt.
  2. REASON    — the model (or the offline policy) decides the next tool call.
  3. TOOL/ACT  — dispatch it (read memory, analyze news, quote, trade, remember).
  4. repeat until the model is done or the step budget is hit.
  5. VERIFY    — reconcile what the agent *intended* (orders it logged) against
                 the broker's actual positions, and journal the result. An agent
                 that never checks its own work is the failure mode the article
                 warns about; this step closes the loop.

Paper by default end-to-end. With no ANTHROPIC_API_KEY the deterministic
HeuristicLLM drives the same tools, so this runs anywhere.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .broker import get_broker
from .llm import AnthropicLLM, HeuristicLLM
from .memory import Memory
from .positions import OpenPositions
from .tools import TOOL_SCHEMAS, Toolbox

SYSTEM_PROMPT = """\
You are an autonomous trading research agent operating a PAPER brokerage account.

Your operating loop is fixed: gather context, reason, call a tool, act, verify,
and write down what you learned. Work in that order and do not skip steps.

How you must behave:
  - Start every session by reading memory. Honour the standing rules and the
    lessons from prior sessions you find there.
  - Turn news into trades only through analyze_news. Its edges are empirically
    calibrated and SMALL-SAMPLE; treat probabilities as priors, not promises.
    Only act on legs whose confidence is 'medium' or 'high'.
  - Before any order, check the portfolio. Never commit more than the per-event
    budget to one idea (the toolbox will cap you, but plan within it anyway).
  - These edges are overnight/intraday. Exits are AUTOMATED: every position you
    open is tracked with a trailing stop and a hard time boundary, and the
    exit check runs before each session and continuously in the live loop, so a
    position is flattened the moment it decays or its window closes. You may
    call check_exits or close_position yourself, but never hold past the window.
  - You place PAPER orders. State that plainly. Do not claim real fills.
  - When unsure, do nothing and say so. A skipped trade is a valid outcome.
  - End by recording one short, durable lesson for next time.

Be concise. Explain each decision in one or two sentences."""


@dataclass
class AgentResult:
    final_text: str
    orders: list[dict] = field(default_factory=list)
    exits: list[dict] = field(default_factory=list)
    account: dict = field(default_factory=dict)
    positions: dict = field(default_factory=dict)
    verification: dict = field(default_factory=dict)
    steps: int = 0

    def summary(self) -> str:
        lines = [self.final_text or "(no final message)", ""]
        if self.exits:
            lines.append("Exits this session:")
            for e in self.exits:
                lines.append(f"  - {e.get('exit_side')} {e.get('qty')} {e.get('symbol')} "
                             f"@ {e.get('exit')} ({e.get('reason')}, pnl {e.get('pnl')})")
        if self.orders:
            lines.append("Orders this session:")
            for o in self.orders:
                lines.append(f"  - [{o.get('status')}] {o.get('side')} {o.get('qty')} "
                             f"{o.get('symbol')} @ {o.get('price')} ({o.get('mode','PAPER')})")
        else:
            lines.append("Orders this session: none")
        a = self.account
        if a:
            lines.append(f"Account: equity {a.get('equity')} "
                         f"(cash {a.get('cash')}) [{a.get('mode','PAPER')}]")
        v = self.verification
        if v:
            lines.append(f"Verification: {v.get('status')} — {v.get('detail','')}")
        return "\n".join(lines)


def _verify(toolbox: Toolbox, session_orders: list[dict]) -> dict:
    """Reconcile intended fills against the broker's actual positions."""
    filled = [o for o in session_orders if o.get("status") == "filled"]
    positions = toolbox.broker.positions()
    if not filled:
        return {"status": "ok", "detail": "no fills to reconcile", "positions": positions}
    # every filled symbol should be reflected (held, or intentionally flat after a close)
    missing = []
    for o in filled:
        sym = o["symbol"]
        if sym not in positions:
            # acceptable only if this order reduced/closed the position
            if o["side"] == "buy":
                missing.append(sym)
    status = "ok" if not missing else "mismatch"
    detail = ("all fills reflected in positions" if not missing
              else f"filled buys not found in book: {missing}")
    toolbox.memory.log("verify", status=status, detail=detail,
                       filled=len(filled), positions=list(positions))
    return {"status": status, "detail": detail, "positions": positions}


def run_session(objective: str = "Review the latest news and trade only a "
                                 "confident, calibrated edge.",
                news: list[str] | None = None,
                *, regime: str = "in_office", max_steps: int = 10,
                llm=None, broker=None, memory: Memory | None = None,
                allow_network: bool = True, min_confidence: str = "medium",
                event_budget_pct: float | None = None, positions=None,
                verbose: bool = False) -> AgentResult:
    """Run one full agent session and return the result.

    news: candidate headlines/posts to consider. If None, the agent proceeds
          with no fresh item (it will typically stand pat).
    llm:  an object with .step(); defaults to Claude when a key is present,
          else the offline HeuristicLLM.
    event_budget_pct: max % of equity one order may commit. None -> the
          EVENT_BUDGET_PCT env var, else 25.
    positions: an OpenPositions store for automated exits. None -> a default
          store under state/, so exits are tracked and managed automatically.
    """
    memory = memory or Memory()
    broker = broker or get_broker()
    if event_budget_pct is None:
        event_budget_pct = float(os.environ.get("EVENT_BUDGET_PCT", "25"))
    if positions is None:
        positions = OpenPositions()
    toolbox = Toolbox(broker, memory, regime=regime, allow_network=allow_network,
                      event_budget_pct=event_budget_pct, positions=positions)
    news = news or []

    # Risk management first: flatten anything that has hit its trailing stop or
    # hard boundary before considering any new entry.
    session_exits: list[dict] = []
    if toolbox._exits is not None:
        session_exits = toolbox._exits.check_and_exit()
        if session_exits and verbose:
            for e in session_exits:
                print(f"[exit] {e['exit_side']} {e['qty']} {e['symbol']} @ {e['exit']} "
                      f"({e['reason']}, pnl {e['pnl']})")

    if llm is None:
        llm = AnthropicLLM() if AnthropicLLM.available() else HeuristicLLM(
            min_confidence=min_confidence)
    if isinstance(llm, HeuristicLLM):
        llm.prime(news)

    mode = getattr(broker, "mode", "PAPER")
    memory.log("session_start", objective=objective, regime=regime,
               mode=mode, news_count=len(news))

    user_context = [
        f"OBJECTIVE: {objective}",
        f"BROKER MODE: {mode}   REGIME: {regime}",
        "",
        memory.as_prompt(),
        "",
    ]
    if news:
        user_context.append("CANDIDATE NEWS ITEMS:")
        user_context += [f"  {i+1}. {t}" for i, t in enumerate(news)]
    else:
        user_context.append("CANDIDATE NEWS ITEMS: (none provided)")
    messages = [{"role": "user", "content": "\n".join(user_context)}]

    orders: list[dict] = []
    final_text = ""
    last_outputs: list[dict] = []
    steps = 0

    for steps in range(1, max_steps + 1):
        step = llm.step(SYSTEM_PROMPT, TOOL_SCHEMAS, messages, last_outputs)
        if verbose and step.text:
            print(f"[agent] {step.text}")
        if step.is_final:
            final_text = step.text or ""
            break
        # execute every tool call in the step
        results_blocks, last_outputs = [], []
        for call in step.tool_calls:
            result = toolbox.dispatch(call.name, call.input)
            if call.name == "place_order":
                orders.append(result)
            if verbose:
                print(f"[tool] {call.name}({call.input}) -> "
                      f"{json.dumps(result, default=str)[:160]}")
            results_blocks.append({"type": "tool_result", "tool_use_id": call.id,
                                   "content": json.dumps(result, default=str)})
            last_outputs.append({"name": call.name, "result": result})
        messages.append({"role": "user", "content": results_blocks})
    else:
        final_text = final_text or "Step budget exhausted before a final summary."

    verification = _verify(toolbox, orders)
    account = toolbox.get_portfolio()
    memory.log("session_end", steps=steps, orders=len(orders),
               exits=len(session_exits), equity=account["account"].get("equity"))

    return AgentResult(final_text=final_text, orders=orders, exits=session_exits,
                       account=account["account"], positions=account["positions"],
                       verification=verification, steps=steps)
