"""Offline tests for the performance tracker + circuit breaker — no network.

Builds a temp journal by calling Memory.log(...) with synthetic EXIT records:
a clear WINNER symbol and a clear LOSER symbol, both with enough trades for the
breaker to fire. Then exercises the win-rate math, the Wilson CI invariants, the
auto-disable rule, on-disk persistence across instances, and the JSON CLI.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.memory import Memory
from agent.performance import (
    CircuitBreaker,
    PerformanceTracker,
    main,
    prior_for,
    wilson_interval,
)

WINNER = "SPY"   # maps to a calibrated prior
LOSER = "FXI"    # maps to a calibrated prior


def _log_exit(mem, symbol, pnl, *, side="sell", entry=100.0):
    """Append one EXIT record. side is the CLOSING side (sell => was long)."""
    exit_price = entry + pnl if side == "sell" else entry - pnl
    mem.log("EXIT", symbol=symbol, exit_side=side, qty=10, entry=entry,
            exit=exit_price, reason="trailing_stop", pnl=float(pnl), mode="PAPER")


@pytest.fixture
def journal(tmp_path):
    """A journal with a clear winner (9/10 wins) and clear loser (1/10 wins)."""
    mem = Memory(state_dir=str(tmp_path))
    # WINNER: 9 wins, 1 loss out of 10
    for _ in range(9):
        _log_exit(mem, WINNER, +5.0)
    _log_exit(mem, WINNER, -3.0)
    # LOSER: 1 win, 9 losses out of 10
    _log_exit(mem, LOSER, +2.0)
    for _ in range(9):
        _log_exit(mem, LOSER, -4.0)
    # a little noise that must be ignored by the tracker
    mem.log("order", reason="x", symbol=WINNER, side="buy", qty=10,
            price=100.0, status="filled", mode="PAPER")
    mem.log("analyze_news", text="tariffs on china", decision="SELL SPY")
    return str(tmp_path), mem


# ----------------------------------------------------------- win-rate math
def test_win_rate_and_pnl_math(journal):
    state_dir, mem = journal
    tracker = PerformanceTracker(memory=mem)
    stats = tracker.by_symbol()

    assert stats[WINNER]["trades"] == 10
    assert stats[WINNER]["wins"] == 9
    assert stats[WINNER]["win_rate"] == pytest.approx(0.9)
    # 9 * 5 - 3 = 42
    assert stats[WINNER]["total_pnl"] == pytest.approx(42.0)
    assert stats[WINNER]["avg_pnl"] == pytest.approx(4.2)

    assert stats[LOSER]["trades"] == 10
    assert stats[LOSER]["wins"] == 1
    assert stats[LOSER]["win_rate"] == pytest.approx(0.1)
    # 2 - 9 * 4 = -34
    assert stats[LOSER]["total_pnl"] == pytest.approx(-34.0)

    overall = tracker.overall()
    assert overall["trades"] == 20
    assert overall["wins"] == 10
    assert overall["total_pnl"] == pytest.approx(8.0)
    # order / analyze_news records are ignored
    assert len(tracker.closed_trades()) == 20


# ----------------------------------------------------------- Wilson CI
def test_wilson_interval_invariants():
    # ordered, inside [0, 1], for a spread of inputs incl. the 0% / 100% edges
    for wins, n in [(0, 0), (0, 5), (5, 5), (1, 10), (9, 10), (3, 7), (50, 100)]:
        lo, hi = wilson_interval(wins, n)
        assert 0.0 <= lo <= hi <= 1.0
    # n == 0 => maximally uncertain
    assert wilson_interval(0, 0) == (0.0, 1.0)
    # a known value: 9/10 wins, 95% CI ~ [0.596, 0.982]
    lo, hi = wilson_interval(9, 10)
    assert lo == pytest.approx(0.5958, abs=1e-3)
    assert hi == pytest.approx(0.9821, abs=1e-3)


def test_tracker_ci_bounds_ordered_and_bounded(journal):
    _, mem = journal
    tracker = PerformanceTracker(memory=mem)
    for st in list(tracker.by_symbol().values()) + [tracker.overall()]:
        assert 0.0 <= st["wilson_low"] <= st["win_rate"] <= st["wilson_high"] <= 1.0


# ----------------------------------------------------------- prior compare
def test_prior_comparison(journal):
    _, mem = journal
    tracker = PerformanceTracker(memory=mem)
    comp = tracker.prior_comparison()
    # both symbols map to a calibrated prior
    assert WINNER in comp and LOSER in comp
    # the loser's realised win rate is below its prior, with the CI confirming it
    assert comp[LOSER]["below_prior"] is True
    assert comp[LOSER]["below_prior_ci"] is True
    assert comp[LOSER]["prior_p"] > comp[LOSER]["realized_win_rate"]
    # prior_for returns None for an uncalibrated symbol
    assert prior_for("ZZZZ") is None
    assert prior_for(WINNER)["prior_p"] > 0


# ----------------------------------------------------------- circuit breaker
def test_breaker_disables_loser_not_winner(journal):
    state_dir, mem = journal
    tracker = PerformanceTracker(memory=mem)
    breaker = CircuitBreaker(state_dir=state_dir, min_trades=8, floor=0.5)
    newly = breaker.evaluate(tracker)

    assert LOSER in newly
    assert breaker.is_disabled(LOSER) is True
    assert breaker.is_disabled(WINNER) is False
    assert WINNER not in newly


def test_breaker_respects_min_trades(tmp_path):
    """A loser with too few trades is NOT disabled even at 0% win rate."""
    mem = Memory(state_dir=str(tmp_path))
    for _ in range(3):
        _log_exit(mem, LOSER, -4.0)
    tracker = PerformanceTracker(memory=mem)
    breaker = CircuitBreaker(state_dir=str(tmp_path), min_trades=8, floor=0.5)
    assert breaker.evaluate(tracker) == {}
    assert breaker.is_disabled(LOSER) is False


def test_disabled_set_persists_across_instances(journal):
    state_dir, mem = journal
    b1 = CircuitBreaker(state_dir=state_dir, min_trades=8, floor=0.5)
    b1.evaluate(PerformanceTracker(memory=mem))
    b1.disable("FED", reason="manual halt")

    # a fresh instance reads the same on-disk state
    b2 = CircuitBreaker(state_dir=state_dir)
    assert b2.is_disabled(LOSER) is True
    assert b2.is_disabled("FED") is True
    assert os.path.exists(os.path.join(state_dir, "disabled.json"))

    # enable clears it and persists
    assert b2.enable("FED") is True
    b3 = CircuitBreaker(state_dir=state_dir)
    assert b3.is_disabled("FED") is False
    assert b3.is_disabled(LOSER) is True


def test_manual_disable_enable_roundtrip(tmp_path):
    b = CircuitBreaker(state_dir=str(tmp_path))
    assert b.is_disabled("KWEB") is False
    b.disable("kweb", reason="testing")          # case-insensitive
    assert b.is_disabled("KWEB") is True
    assert "KWEB" in b.disabled()
    assert b.enable("KWEB") is True
    assert b.enable("KWEB") is False             # already enabled


# ----------------------------------------------------------- CLI
def test_main_json_and_evaluate(journal, capsys):
    state_dir, _ = journal
    rc = main(["--state-dir", state_dir, "--json", "--evaluate"])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)  # parseable JSON

    assert data["by_symbol"][WINNER]["trades"] == 10
    assert data["overall"]["trades"] == 20
    assert LOSER in data["disabled"]
    assert LOSER in data["newly_disabled"]
    assert WINNER not in data["disabled"]
    # the evaluate persisted to disk
    assert os.path.exists(os.path.join(state_dir, "disabled.json"))


def test_main_text_runs(journal, capsys):
    state_dir, _ = journal
    rc = main(["--state-dir", state_dir])
    assert rc == 0
    out = capsys.readouterr().out
    assert "PER-SYMBOL CLOSED-TRADE PERFORMANCE" in out
    assert WINNER in out and LOSER in out
