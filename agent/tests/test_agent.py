"""Offline tests for the trading agent — no network, no API key.

Covers: the full agentic loop end-to-end via the heuristic policy, the paper
broker's accounting and risk cap, memory persistence across "sessions", the
verification step, and that a scripted stub LLM can drive the same loop.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.agent import run_session
from agent.broker import LocalPaperBroker
from agent.llm import HeuristicLLM, Step, ToolCall
from agent.memory import Memory
from agent.tools import Toolbox

ESCALATION = ("BREAKING: I am imposing an ADDITIONAL 100% TARIFF on all "
              "Chinese imports, effective immediately!")
NOISE = "Had a wonderful dinner at Mar-a-Lago last night. Thank you!"


@pytest.fixture
def fresh(tmp_path):
    mem = Memory(state_dir=str(tmp_path))
    brk = LocalPaperBroker(start_cash=10_000.0, state_dir=str(tmp_path))
    return mem, brk


# ---------------------------------------------------------------- broker
def test_paper_broker_buy_and_account(fresh):
    _, brk = fresh
    fill = brk.market_order("SPY", "buy", 5, 600.0)
    assert fill.status == "filled" and fill.qty == 5
    acct = brk.account({"SPY": 600.0})
    assert acct["cash"] == pytest.approx(10_000 - 5 * 600)
    assert acct["equity"] == pytest.approx(10_000)
    assert brk.positions()["SPY"]["qty"] == 5


def test_paper_broker_rejects_overdraft(fresh):
    _, brk = fresh
    fill = brk.market_order("SPY", "buy", 100, 600.0)  # 60k > 10k cash
    assert fill.status == "rejected"
    assert brk.positions() == {}


def test_paper_broker_short_then_account(fresh):
    _, brk = fresh
    fill = brk.market_order("FXI", "sell", 10, 38.0)
    assert fill.status == "filled"
    assert brk.positions()["FXI"]["qty"] == -10
    acct = brk.account({"FXI": 38.0})
    assert acct["cash"] == pytest.approx(10_000 + 380)


# ---------------------------------------------------------------- risk cap
def test_event_budget_caps_order(fresh):
    mem, brk = fresh
    tb = Toolbox(brk, mem, event_budget_pct=25.0, allow_network=False)
    # 25% of 10k = 2500; at stub SPY 600 -> max 4 shares even if we ask for 50
    res = tb.place_order("SPY", "buy", 50, reason="test cap")
    assert res["status"] == "filled"
    assert res["qty"] == 4


# ---------------------------------------------------------------- memory
def test_memory_persists_across_instances(tmp_path):
    m1 = Memory(state_dir=str(tmp_path))
    m1.remember_lesson("Overnight edges decay by the cash open.")
    m1.set_position("FXI", "short 10 @ 38.00")
    m2 = Memory(state_dir=str(tmp_path))
    snap = m2.snapshot()
    assert "Overnight edges decay by the cash open." in snap["lessons"]
    assert snap["open_positions"]["FXI"] == "short 10 @ 38.00"


def test_memory_dedupes_and_prompt(tmp_path):
    m = Memory(state_dir=str(tmp_path))
    m.remember_lesson("Same lesson.")
    m.remember_lesson("Same lesson.")
    assert m.snapshot()["lessons"].count("Same lesson.") == 1
    assert "STANDING RULES" in m.as_prompt()


# ---------------------------------------------------------------- full loop
def test_session_trades_on_escalation(fresh):
    mem, brk = fresh
    res = run_session(news=[ESCALATION], llm=HeuristicLLM(),
                      broker=brk, memory=mem, allow_network=False)
    filled = [o for o in res.orders if o.get("status") == "filled"]
    assert filled, "agent should act on a calibrated escalation edge"
    # lead leg for in-office trade_china escalation is SELL SPY (most reliable)
    assert filled[0]["symbol"] == "SPY" and filled[0]["side"] == "sell"
    assert res.verification["status"] in ("ok", "mismatch")
    assert res.account["mode"] == "PAPER"
    # a lesson was recorded for next time
    assert mem.snapshot()["lessons"]


def test_session_stands_pat_on_noise(fresh):
    mem, brk = fresh
    res = run_session(news=[NOISE], llm=HeuristicLLM(), broker=brk,
                      memory=mem, allow_network=False)
    assert [o for o in res.orders if o.get("status") == "filled"] == []
    assert "standing pat" in res.final_text.lower() or "no " in res.final_text.lower()


def test_session_with_no_news_is_flat(fresh):
    mem, brk = fresh
    res = run_session(news=[], llm=HeuristicLLM(), broker=brk,
                      memory=mem, allow_network=False)
    assert [o for o in res.orders if o.get("status") == "filled"] == []
    assert res.verification["status"] == "ok"


def test_min_confidence_high_skips_medium_edge(fresh):
    mem, brk = fresh
    # SELL SPY on tariff escalation is 'high', but a single weak leg would be skipped.
    res = run_session(news=[ESCALATION], llm=HeuristicLLM(min_confidence="high"),
                      broker=brk, memory=mem, allow_network=False)
    # the high-confidence SPY leg still trades; assert it respected the gate by
    # confirming every fill came from a high-confidence decision (SPY lead)
    for o in res.orders:
        if o.get("status") == "filled":
            assert o["symbol"] == "SPY"


# ---------------------------------------------------------------- stub LLM
class ScriptedLLM:
    """Minimal stub proving an arbitrary model can drive the same tool loop."""
    def __init__(self):
        self.i = 0

    def step(self, system, tools, messages, last_outputs=None):
        self.i += 1
        if self.i == 1:
            return Step(tool_calls=[ToolCall("a", "get_quotes", {"symbols": ["GLD"]})])
        if self.i == 2:
            return Step(tool_calls=[ToolCall("b", "place_order",
                        {"symbol": "GLD", "side": "buy", "qty": 2, "reason": "haven"})])
        return Step(text="Done — bought a small gold hedge (paper).")


def test_scripted_llm_drives_loop(fresh):
    mem, brk = fresh
    res = run_session(news=[], llm=ScriptedLLM(), broker=brk,
                      memory=mem, allow_network=False)
    assert res.final_text.startswith("Done")
    filled = [o for o in res.orders if o.get("status") == "filled"]
    assert filled and filled[0]["symbol"] == "GLD"
    assert brk.positions()["GLD"]["qty"] == 2


# ---------------------------------------------------------------- budget flag
def test_run_session_budget_pct_threads_through(fresh):
    mem, brk = fresh
    # 10% of 10k = 1000; at stub SPY 600 -> max 1 share even though plan asks for 10
    res = run_session(news=[ESCALATION], llm=HeuristicLLM(), broker=brk, memory=mem,
                      allow_network=False, event_budget_pct=10.0)
    filled = [o for o in res.orders if o.get("status") == "filled"]
    assert filled and filled[0]["symbol"] == "SPY"
    assert filled[0]["qty"] == 1  # capped by the 10% budget


# ---------------------------------------------------------------- live agent
def test_live_agent_poll_processes_relevant_post(fresh):
    from agent import live_agent
    mem, brk = fresh
    posts = [
        {"id": "p1", "ts": "2026-06-18T13:00:00+00:00", "text": ESCALATION},
        {"id": "p2", "ts": "2026-06-18T13:01:00+00:00", "text": NOISE},
    ]
    state = {"processed_ids": [], "day": None, "day_start_equity": None}
    results = live_agent.poll_once(brk, mem, state, fetch_fn=lambda since: posts,
                                   allow_network=False,
                                   llm=None if False else HeuristicLLM())
    # only the market-relevant post ran a session; both are marked processed
    assert len(results) == 1
    assert set(state["processed_ids"]) == {"p1", "p2"}
    assert brk.positions()  # the escalation post opened a paper position


def test_live_agent_skips_already_processed(fresh):
    from agent import live_agent
    mem, brk = fresh
    posts = [{"id": "p1", "ts": "2026-06-18T13:00:00+00:00", "text": ESCALATION}]
    state = {"processed_ids": ["p1"], "day": None, "day_start_equity": None}
    results = live_agent.poll_once(brk, mem, state, fetch_fn=lambda since: posts,
                                   allow_network=False, llm=HeuristicLLM())
    assert results == [] and brk.positions() == {}


def test_market_relevance_gate():
    from agent import live_agent
    assert live_agent.is_market_relevant(ESCALATION)
    assert not live_agent.is_market_relevant(NOISE)
