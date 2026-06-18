"""Price snapshots for the agent.

Order of preference, each degrading gracefully to the next so the agent always
gets *some* number to reason with:

  1. Alpaca's free IEX feed, if ALPACA keys are set (live last-trade).
  2. yfinance, if installed and the network allows it (last close).
  3. A deterministic offline stub keyed off a small reference table, so the
     agent and the tests run with no network at all.

Prices are a tool input the agent reads; they are never fabricated silently —
the snapshot tags each quote with its ``source`` so downstream code (and the
journal) knows whether it was live, delayed, or offline-stub.
"""
from __future__ import annotations

import os

# Rough reference levels (mid-2026) for the instruments the strategy touches,
# used only by the offline stub so behaviour is deterministic without a feed.
_REF = {
    "SPY": 600.0, "QQQ": 530.0, "GLD": 310.0, "FXI": 38.0, "KWEB": 35.0,
    "USO": 80.0, "ITA": 165.0, "TLT": 88.0, "XLK": 255.0, "SMH": 280.0,
    "AAPL": 220.0, "TSLA": 250.0, "EWZ": 30.0,
}


def _alpaca_prices(symbols):
    sys_path_added = False
    try:
        import sys
        live = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "experiments", "live")
        sys.path.insert(0, os.path.abspath(live)); sys_path_added = True
        from alpaca import Alpaca
        api = Alpaca(os.environ.get("ALPACA_BASE", "https://paper-api.alpaca.markets"))
        out = {}
        for s in symbols:
            out[s] = {"price": round(api.last_price(s), 2), "source": "alpaca-iex"}
        return out
    except Exception:
        return None
    finally:
        if sys_path_added:
            pass


def _yf_prices(symbols):
    try:
        import yfinance as yf
        out = {}
        data = yf.download(list(symbols), period="1d", progress=False, threads=False)
        closes = data["Close"]
        for s in symbols:
            try:
                px = float(closes[s].dropna().iloc[-1]) if hasattr(closes, "columns") \
                    else float(closes.dropna().iloc[-1])
                out[s] = {"price": round(px, 2), "source": "yfinance-close"}
            except Exception:
                continue
        return out or None
    except Exception:
        return None


def _stub_prices(symbols):
    out = {}
    for s in symbols:
        base = _REF.get(s.upper(), 100.0)
        out[s] = {"price": base, "source": "offline-stub"}
    return out


def snapshot(symbols, allow_network: bool = True) -> dict:
    """Return {symbol: {price, source}}. Tries live, then delayed, then stub."""
    symbols = [s.upper() for s in symbols]
    if allow_network and os.environ.get("ALPACA_KEY_ID"):
        got = _alpaca_prices(symbols)
        if got:
            return got
    if allow_network:
        got = _yf_prices(symbols)
        if got and len(got) == len(symbols):
            return got
    return _stub_prices(symbols)
