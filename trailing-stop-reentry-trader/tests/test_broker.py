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
    b._safe_last = lambda symbol: None     # keep _await_fill offline (no last-price fetch)
    return b


@pytest.fixture(autouse=True)
def _fast_time(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(bk.time, "time", lambda: clock["t"])
    monkeypatch.setattr(bk.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + 1000))


def test_await_fill_full():
    b = _mk(lambda m, p, body=None: {"status": "filled", "filled_qty": "10", "filled_avg_price": "9.99"})
    assert b._await_fill("o1", "SPY") == {"filled_qty": 10.0, "fill_price": 9.99}


def test_await_fill_partial_then_cancel_settles_returns_partial():
    # Partially filled, then on timeout the cancel SETTLES the order to canceled
    # carrying the 50 filled shares — must surface them, not None.
    calls = {"deleted": False}
    def api(m, p, body=None):
        if m == "DELETE":
            calls["deleted"] = True
            return None
        if calls["deleted"]:
            return {"status": "canceled", "filled_qty": "50", "filled_avg_price": "10.00"}
        return {"status": "partially_filled", "filled_qty": "50", "filled_avg_price": "10.00"}
    b = _mk(api)
    assert b._await_fill("o1", "SPY") == {"filled_qty": 50.0, "fill_price": 10.0}
    assert calls["deleted"]


def test_await_fill_never_terminal_returns_none_not_midflight():
    # Order never reaches a terminal status (cancel never settles). Must return
    # None — NOT a mid-flight partial snapshot of a still-working order.
    b = _mk(lambda m, p, body=None: None if m == "DELETE" else
            {"status": "partially_filled", "filled_qty": "50", "filled_avg_price": "10.00"})
    assert b._await_fill("o1", "SPY") is None


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
    assert b._await_fill("o1", "SPY") == {"filled_qty": 10.0, "fill_price": 100.0}


def test_await_fill_nothing_filled_returns_none():
    b = _mk(lambda m, p, body=None: {"status": "rejected", "filled_qty": "0", "filled_avg_price": None})
    assert b._await_fill("o1", "SPY") is None


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


def test_live_url_guard_is_case_insensitive_and_host_only():
    with pytest.raises(BrokerError):
        AlpacaBroker("https://API.ALPACA.MARKETS", "k", "s")        # uppercase host
    with pytest.raises(BrokerError):
        AlpacaBroker("https://api.alpaca.markets/?paper", "k", "s")  # 'paper' in query, not host
    # the real paper host is NOT the live host -> allowed
    assert AlpacaBroker("https://paper-api.alpaca.markets", "k", "s").base


def test_num_rejects_non_finite():
    b = _mk(lambda *a, **k: None)
    assert b._num("NaN") is None
    assert b._num("inf") is None
    assert b._num(float("nan")) is None
    assert b._num("10.5") == 10.5


def test_fill_from_nan_is_rejected():
    b = _mk(lambda *a, **k: None)
    assert b._fill_from({"filled_qty": "NaN", "filled_avg_price": "10"}, None) is None
    assert b._fill_from({"filled_qty": "10", "filled_avg_price": "NaN"}, 99.0) == \
        {"filled_qty": 10.0, "fill_price": 99.0}   # NaN avg -> fallback price


def test_fill_from_partial_with_null_avg_uses_fallback():
    b = _mk(lambda *a, **k: None)
    f = b._fill_from({"status": "canceled", "filled_qty": "5", "filled_avg_price": None}, 100.0)
    assert f == {"filled_qty": 5.0, "fill_price": 100.0}    # 5 shares not dropped


def test_await_fill_follows_replaced_order():
    def api(m, p, body=None):
        if p.endswith("/orig"):
            return {"status": "replaced", "replaced_by": "repl", "filled_qty": "0",
                    "filled_avg_price": None}
        return {"status": "filled", "filled_qty": "10", "filled_avg_price": "100.0"}
    b = _mk(api)
    assert b._await_fill("orig", "SPY") == {"filled_qty": 10.0, "fill_price": 100.0}


def test_account_empty_response_raises_brokererror():
    b = _mk(lambda *a, **k: None)
    with pytest.raises(BrokerError):
        b.account()


def test_last_price_null_trade_raises_brokererror():
    # {"trade": null} is a real payload; must raise BrokerError, not AttributeError.
    b = AlpacaBroker.__new__(AlpacaBroker)
    b.base = "https://paper-api.alpaca.markets"; b.key = "k"; b.secret = "s"
    b._req = lambda m, u, body=None: {"trade": None}
    with pytest.raises(BrokerError):
        b.last_price("SPY")


def test_null_avg_fallback_is_wired_through_await_fill():
    # A canceled order carrying 5 partial shares with a null avg price must be
    # rescued using the last-price fallback (not dropped). Uses a REAL _safe_last
    # so the wiring is actually exercised (the default _mk stubs it to None).
    b = AlpacaBroker.__new__(AlpacaBroker)
    b.base = "https://paper-api.alpaca.markets"; b.key = "k"; b.secret = "s"
    b._api = lambda m, p, body=None: {"status": "canceled", "filled_qty": "5",
                                      "filled_avg_price": None}
    b._safe_last = lambda symbol: 10.0
    assert b._await_fill("o1", "SPY") == {"filled_qty": 5.0, "fill_price": 10.0}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
