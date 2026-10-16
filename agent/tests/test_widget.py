"""Offline tests for the SwiftBar status reader."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.broker import LocalPaperBroker
from agent.memory import Memory
from agent.widget import status as st


def test_gather_running_with_positions(tmp_path):
    brk = LocalPaperBroker(start_cash=10_000.0, state_dir=str(tmp_path))
    brk.market_order("SPY", "sell", 3, 600.0)
    mem = Memory(state_dir=str(tmp_path))
    mem.log("order", symbol="SPY", side="sell", qty=3, price=600.0, status="filled")
    open(os.path.join(tmp_path, "heartbeat"), "w").write("now")   # fresh => running

    s = st.gather(state_dir=str(tmp_path), broker=brk, interval_hint=60)
    assert s["mode"] == "PAPER"
    assert s["running"] is True
    assert s["positions"] and s["positions"][0]["symbol"] == "SPY"
    assert s["positions"][0]["qty"] == -3
    assert s["last_action"]["symbol"] == "SPY"
    assert s["error"] is None

    out = st.swiftbar(s)
    assert out.splitlines()[0].startswith("📈")     # title shows equity
    assert "---" in out and "PAPER" in out
    assert "SPY -3 @ 600.00" in out
    assert "Open Alpaca paper dashboard | href=" in out


def test_gather_not_running_when_heartbeat_stale(tmp_path):
    brk = LocalPaperBroker(start_cash=10_000.0, state_dir=str(tmp_path))
    hb = os.path.join(tmp_path, "heartbeat")
    open(hb, "w").write("old")
    old = time.time() - 600
    os.utime(hb, (old, old))                                     # 10 min stale
    s = st.gather(state_dir=str(tmp_path), broker=brk, interval_hint=60)
    assert s["running"] is False
    assert st.swiftbar(s).splitlines()[0] == "🟠 agent off"


def test_kill_switch_titles(tmp_path, monkeypatch):
    brk = LocalPaperBroker(start_cash=10_000.0, state_dir=str(tmp_path))
    monkeypatch.setattr(st, "KILL", str(tmp_path / "KILL"))
    open(st.KILL, "w").write("halt")
    s = st.gather(state_dir=str(tmp_path), broker=brk)
    assert s["killed"] is True
    assert st.swiftbar(s).splitlines()[0] == "🛑 agent HALTED"
