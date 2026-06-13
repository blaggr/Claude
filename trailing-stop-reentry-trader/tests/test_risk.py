"""Tests for the risk interlocks: exact ack, budget clamp, safe env parsing,
loss-limit positivity and boundary."""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import risk  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    monkeypatch.delenv("ALPACA_LIVE", raising=False)
    monkeypatch.setattr(risk, "ACK_FILE", str(tmp_path / "LIVE_TRADING_ENABLED"))


def test_paper_is_default():
    base, mode = risk.resolve_mode()
    assert mode == "PAPER" and "paper" in base


def test_live_requires_exact_ack_not_substring(monkeypatch):
    monkeypatch.setenv("ALPACA_LIVE", "1")
    # junk around the phrase must NOT pass — it should refuse to start.
    open(risk.ACK_FILE, "w").write("junk " + risk.ACK_TEXT + " lol")
    with pytest.raises(SystemExit):
        risk.resolve_mode()
    # exact (whitespace-stripped) line is accepted.
    open(risk.ACK_FILE, "w").write("  " + risk.ACK_TEXT + "\n")
    base, mode = risk.resolve_mode()
    assert mode == "LIVE"


def test_entry_qty_is_clamped_to_cash():
    assert risk.entry_qty(10_000, 100, budget_pct=150) == 100  # clamped to 100% (not 150%)
    assert risk.entry_qty(10_000, 100, budget_pct=95) == 95
    assert risk.entry_qty(50, 100) == 0                        # dust


def test_daily_loss_positivity_and_boundary():
    assert risk.daily_loss_breached(-100000.0, -90000.0) is False   # no usable baseline
    assert risk.daily_loss_breached(0, 1.0) is False
    thr = 100000.0 * (1 - risk.MAX_DAILY_LOSS_PCT / 100.0)
    assert risk.daily_loss_breached(100000.0, thr) is True          # exactly -5% trips (inclusive)
    assert risk.daily_loss_breached("100000.0", 95000.0) is True    # string baseline coerced


def test_env_parse_does_not_crash_import(monkeypatch):
    monkeypatch.setenv("BUDGET_PCT", "95%")
    importlib.reload(risk)            # must not raise
    assert risk.BUDGET_PCT == 95.0    # fell back to default
    monkeypatch.delenv("BUDGET_PCT", raising=False)
    importlib.reload(risk)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
