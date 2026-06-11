"""Tests for the live-trading risk interlocks and order construction (no network).

Run:  python -m pytest experiments/tests/test_live.py -q
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "live"))

import risk  # noqa: E402
from alpaca import Alpaca, AlpacaError  # noqa: E402


# ---- live-mode interlocks ---------------------------------------------------

def test_default_is_paper(monkeypatch):
    monkeypatch.delenv("ALPACA_LIVE", raising=False)
    url, mode = risk.resolve_mode()
    assert mode == "PAPER" and "paper" in url


def test_live_flag_without_ack_file_refuses_to_start(monkeypatch, tmp_path):
    monkeypatch.setenv("ALPACA_LIVE", "1")
    monkeypatch.setattr(risk, "ACK_FILE", str(tmp_path / "LIVE_TRADING_ENABLED"))
    with pytest.raises(SystemExit):
        risk.resolve_mode()


def test_live_requires_both_flag_and_exact_ack_text(monkeypatch, tmp_path):
    ack = tmp_path / "LIVE_TRADING_ENABLED"
    monkeypatch.setattr(risk, "ACK_FILE", str(ack))
    # ack file alone (no env flag) stays paper
    ack.write_text(risk.ACK_TEXT)
    monkeypatch.delenv("ALPACA_LIVE", raising=False)
    assert risk.resolve_mode()[1] == "PAPER"
    # wrong text + flag refuses
    ack.write_text("yes please")
    monkeypatch.setenv("ALPACA_LIVE", "1")
    with pytest.raises(SystemExit):
        risk.resolve_mode()
    # both correct -> live
    ack.write_text(risk.ACK_TEXT)
    url, mode = risk.resolve_mode()
    assert mode == "LIVE" and "paper" not in url


def test_kill_switch_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(risk, "KILL_FILE", str(tmp_path / "KILL"))
    assert not risk.kill_switch_active()
    risk.trip_kill_switch("test")
    assert risk.kill_switch_active()


def test_daily_loss_breach_threshold():
    assert not risk.daily_loss_breached(1000.0, 960.0)   # -4% with 5% limit
    assert risk.daily_loss_breached(1000.0, 940.0)       # -6%


# ---- sizing -----------------------------------------------------------------

def test_size_legs_whole_shares_and_drops_dust():
    legs = [{"instrument": "USO", "side": "BUY", "weight": 0.6},
            {"instrument": "SPY", "side": "SELL", "weight": 0.4}]
    prices = {"USO": 130.0, "SPY": 700.0}
    # 25% of $10k = $2500 budget -> USO 0.6*2500/130 = 11 shares; SPY 0.4*2500/700 = 1
    sized = risk.size_legs(legs, prices, equity=10_000.0)
    by = {l["instrument"]: l for l in sized}
    assert by["USO"]["qty"] == 11 and by["SPY"]["qty"] == 1
    # tiny equity -> everything rounds to dust and is dropped
    assert risk.size_legs(legs, prices, equity=100.0) == [
        l for l in risk.size_legs(legs, prices, equity=100.0) if l["qty"] >= 1]


def test_marketable_limit_buffers_both_sides():
    assert risk.marketable_limit(100.0, "buy") == 100.2
    assert risk.marketable_limit(100.0, "sell") == 99.8


# ---- order construction -----------------------------------------------------

def _broker(monkeypatch, captured):
    monkeypatch.setenv("ALPACA_KEY_ID", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")
    b = Alpaca(risk.PAPER_URL)
    monkeypatch.setattr(b, "_api", lambda method, path, body=None:
                        captured.append((method, path, body)) or {"id": "o1", "status": "accepted"})
    return b


def test_rth_entry_is_market_day_order(monkeypatch):
    captured = []
    b = _broker(monkeypatch, captured)
    b.submit_order("USO", 11, "buy", extended_hours=False, client_order_id="abc-USO-in")
    _, path, body = captured[0]
    assert path == "/v2/orders"
    assert body["type"] == "market" and body["time_in_force"] == "day"
    assert body["extended_hours"] is False and body["qty"] == "11"
    assert body["client_order_id"] == "abc-USO-in"


def test_extended_hours_requires_limit_and_builds_limit_order(monkeypatch):
    captured = []
    b = _broker(monkeypatch, captured)
    with pytest.raises(AlpacaError):
        b.submit_order("USO", 5, "buy", extended_hours=True)   # no limit price
    b.submit_order("USO", 5, "sell", extended_hours=True, limit_price=99.8)
    _, _, body = captured[0]
    assert body["type"] == "limit" and body["limit_price"] == "99.80"
    assert body["extended_hours"] is True and body["side"] == "sell"


def test_missing_keys_refuse_to_construct(monkeypatch):
    monkeypatch.delenv("ALPACA_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    with pytest.raises(AlpacaError):
        Alpaca(risk.PAPER_URL)
