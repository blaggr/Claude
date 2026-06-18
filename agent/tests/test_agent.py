"""Offline tests for the trading agent — no network, no API key.

Covers: the full agentic loop end-to-end via the heuristic policy, the paper
broker's accounting and risk cap, memory persistence across "sessions", the
verification step, a scripted stub LLM driving the same loop, the live-agent
poll, and automated exits (trailing stop, hard boundary, broker reconciliation,
and the exit pass inside both run_session and the live poll).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import datetime as dt

from agent.agent import run_session
from agent.broker import LocalPaperBroker
from agent.exits import ExitManager, TrailingTracker, boundary_after, trail_pct_for
from agent.llm import HeuristicLLM, Step, ToolCall
from agent.memory import Memory
from agent.positions import OpenPositions
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


# ---------------------------------------------------------------- exit math
def test_trailing_tracker_long_and_short():
    long = TrailingTracker("BUY", 0.01, 100.0)
    assert not long.update(105.0)        # new high, no stop
    assert not long.update(104.5)        # 104.5 > 105*0.99=103.95
    assert long.update(103.0)            # 103 <= 103.95 -> stop out
    short = TrailingTracker("SELL", 0.01, 100.0)
    assert not short.update(95.0)        # new low
    assert short.update(96.5)            # 96.5 >= 95*1.01=95.95 -> stop out


def test_trail_pct_floor_and_cap():
    assert trail_pct_for(0.1) == 0.003   # floored
    assert trail_pct_for(100) == 0.015   # capped
    assert abs(trail_pct_for(2.0) - 0.008) < 1e-9   # 40% of 2%


def test_boundary_after_windows():
    ny = dt.timezone(dt.timedelta(hours=-4))  # EDT in June
    # RTH entry -> same-day 15:55
    b = boundary_after(dt.datetime(2026, 6, 18, 10, 0, tzinfo=ny))
    assert (b.hour, b.minute) == (15, 55) and b.day == 18
    # pre-cash entry -> same-day 09:30
    b = boundary_after(dt.datetime(2026, 6, 18, 7, 0, tzinfo=ny))
    assert (b.hour, b.minute) == (9, 30) and b.day == 18
    # Friday after-hours -> Monday 09:30
    b = boundary_after(dt.datetime(2026, 6, 19, 18, 0, tzinfo=ny))
    assert b.weekday() == 0 and (b.hour, b.minute) == (9, 30)


# ---------------------------------------------------------------- exit manager
def test_exit_on_boundary(tmp_path):
    mem = Memory(state_dir=str(tmp_path))
    brk = LocalPaperBroker(start_cash=10_000.0, state_dir=str(tmp_path))
    pos = OpenPositions(state_dir=str(tmp_path))
    brk.market_order("SPY", "buy", 5, 600.0)          # open a long
    mgr = ExitManager(brk, mem, pos, allow_network=False)
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2))
    mgr.record_entry("SPY", "BUY", 5, 600.0, window="overnight",
                     expected_move_pct=1.0, entry_ts=past)
    exits = mgr.check_and_exit(prices={"SPY": 605.0})
    assert len(exits) == 1 and exits[0]["reason"] == "boundary"
    assert exits[0]["pnl"] == 25.0          # (605-600)*5
    assert "SPY" not in brk.positions() and pos.get("SPY") is None


def test_exit_on_trailing_stop(tmp_path):
    mem = Memory(state_dir=str(tmp_path))
    brk = LocalPaperBroker(start_cash=10_000.0, state_dir=str(tmp_path))
    pos = OpenPositions(state_dir=str(tmp_path))
    brk.market_order("FXI", "sell", 10, 38.0)         # open a short
    mgr = ExitManager(brk, mem, pos, allow_network=False)
    mgr.record_entry("FXI", "SELL", 10, 38.0, window="overnight", expected_move_pct=2.0)
    # short trail is 0.8%: best stays at the running low; a bounce above triggers
    assert mgr.check_and_exit(prices={"FXI": 37.0}) == []      # new low, no stop
    exits = mgr.check_and_exit(prices={"FXI": 37.4})           # 37.4 >= 37*1.008
    assert len(exits) == 1 and exits[0]["reason"] == "trailing_stop"
    assert "FXI" not in brk.positions()


def test_exit_reconciles_when_broker_flat(tmp_path):
    mem = Memory(state_dir=str(tmp_path))
    brk = LocalPaperBroker(start_cash=10_000.0, state_dir=str(tmp_path))
    pos = OpenPositions(state_dir=str(tmp_path))
    mgr = ExitManager(brk, mem, pos, allow_network=False)
    # tracked position the broker doesn't actually hold -> reconciled away
    mgr.record_entry("GLD", "BUY", 2, 310.0)
    exits = mgr.check_and_exit(prices={"GLD": 320.0})
    assert exits == [] and pos.get("GLD") is None


def test_agent_loop_records_exit_plan_on_entry(fresh):
    mem, brk = fresh
    pos = OpenPositions(state_dir=mem.dir)
    run_session(news=[ESCALATION], llm=HeuristicLLM(), broker=brk, memory=mem,
                allow_network=False, positions=pos)
    # the SELL SPY entry was registered with an overnight exit plan
    rec = pos.get("SPY")
    assert rec and rec["side"] == "SELL" and rec["window"] == "overnight"
    assert 0.003 <= rec["trail_pct"] <= 0.015 and rec["boundary"]


def test_agent_loop_exits_due_position_first(fresh):
    mem, brk = fresh
    pos = OpenPositions(state_dir=mem.dir)
    # pre-existing long whose boundary already passed
    brk.market_order("SPY", "buy", 3, 600.0)
    past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)
    ExitManager(brk, mem, pos, allow_network=False).record_entry(
        "SPY", "BUY", 3, 600.0, window="overnight", entry_ts=past)
    res = run_session(news=[NOISE], llm=HeuristicLLM(), broker=brk, memory=mem,
                      allow_network=False, positions=pos)
    assert res.exits and res.exits[0]["symbol"] == "SPY"
    assert res.exits[0]["reason"] == "boundary"
    assert "SPY" not in brk.positions()


def test_live_agent_poll_runs_exits_with_no_news(fresh):
    from agent import live_agent
    mem, brk = fresh
    pos = OpenPositions(state_dir=mem.dir)
    brk.market_order("SPY", "buy", 4, 600.0)
    past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)
    ExitManager(brk, mem, pos, allow_network=False).record_entry(
        "SPY", "BUY", 4, 600.0, window="overnight", entry_ts=past)
    state = {"processed_ids": [], "day": None, "day_start_equity": None}
    # no posts at all this poll, but the due position must still be flattened
    live_agent.poll_once(brk, mem, state, fetch_fn=lambda since: [],
                         allow_network=False, positions=pos)
    assert "SPY" not in brk.positions() and pos.get("SPY") is None
