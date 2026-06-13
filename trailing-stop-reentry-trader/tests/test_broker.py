"""Tests for the AlpacaBroker REST adapter — especially the fill lifecycle that
the in-memory FakeBroker cannot exercise (partial fills, the cancel/fill race,
status parsing). These drive a fake _api so there is no network."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import broker as bk  # noqa: E402
from broker import AlpacaBroker, BrokerError  # noqa: E402


def _mk(api):
    b = AlpacaBroker.__new__(AlpacaBroker)
    b.base = "https://paper-api.alpaca.markets"; b.key = "k"; b.secret = "s"
    b._api = api
    return b


@pytest.fixture(autouse=True)
def _fast_time(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(bk.time, "time", lambda: clock["t"])
    monkeypatch.setattr(bk.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + 1000))


def test_await_fill_full():
    b = _mk(lambda m, p, body=None: {"status": "filled", "filled_qty": "10", "filled_avg_price": "9.99"})
    assert b._await_fill("o1") == {"filled_qty": 10.0, "fill_price": 9.99}


def test_await_fill_partial_through_timeout_returns_partial():
    # GET always shows partially_filled; on timeout we cancel then re-read and
    # must surface the 50 shares that DID fill, not None.
    calls = []
    def api(m, p, body=None):
        calls.append(m)
        if m == "DELETE":
            return None
        return {"status": "partially_filled", "filled_qty": "50", "filled_avg_price": "10.00"}
    b = _mk(api)
    assert b._await_fill("o1") == {"filled_qty": 50.0, "fill_price": 10.0}
    assert "DELETE" in calls


def test_await_fill_cancel_fill_race_recovers_fill():
    # Order looks 'new', times out, DELETE rejected (already filling), re-GET
    # shows it filled. Must return the fill, not None.
    state = {"phase": 0}
    def api(m, p, body=None):
        if m == "DELETE":
            raise BrokerError("order is not cancelable", code=422)
        if state["phase"] == 0:
            state["phase"] = 1
            return {"status": "new", "filled_qty": "0", "filled_avg_price": None}
        return {"status": "filled", "filled_qty": "10", "filled_avg_price": "100.0"}
    b = _mk(api)
    assert b._await_fill("o1") == {"filled_qty": 10.0, "fill_price": 100.0}


def test_await_fill_nothing_filled_returns_none():
    b = _mk(lambda m, p, body=None: {"status": "rejected", "filled_qty": "0", "filled_avg_price": None})
    assert b._await_fill("o1") is None


def test_submit_rejects_bad_qty():
    b = _mk(lambda m, p, body=None: {"id": "x"})
    for bad in (0, -1, 2.5):
        with pytest.raises(BrokerError):
            b._submit("SPY", bad, "buy", extended_hours=False, limit_price=None, client_order_id=None)


def test_position_404_is_none_but_500_raises():
    b404 = _mk(lambda m, p, body=None: (_ for _ in ()).throw(BrokerError("not found", code=404)))
    assert b404.position("SPY") is None
    b500 = _mk(lambda m, p, body=None: (_ for _ in ()).throw(BrokerError("err 404 in body", code=500)))
    with pytest.raises(BrokerError):
        b500.position("SPY")           # 500 must NOT be swallowed as "no position"


def test_account_null_balance_raises_brokererror():
    b = _mk(lambda m, p, body=None: {"equity": None, "cash": "0", "status": "BLOCKED"})
    with pytest.raises(BrokerError):
        b.account()


def test_live_url_refused_without_allow_live():
    with pytest.raises(BrokerError):
        AlpacaBroker("https://api.alpaca.markets", "k", "s")
    # explicit opt-in is accepted
    assert AlpacaBroker("https://api.alpaca.markets", "k", "s", allow_live=True).base


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
