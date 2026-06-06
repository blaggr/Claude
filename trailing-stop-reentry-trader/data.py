"""Market data loaders for any stock or index-fund ticker.

Three sources, in order of convenience:

1. :func:`fetch_ohlcv` — pull historical bars from Yahoo Finance via
   ``yfinance`` (no API key needed). Works for stocks, ETFs and index funds
   (e.g. ``AAPL``, ``SPY``, ``VTI``, ``^GSPC``).
2. :func:`load_csv` — read a local OHLC CSV if you already have data or the
   network is locked down.
3. :func:`synthetic_ohlcv` — generate a reproducible random-walk series so the
   engine and UI work offline (handy for demos and tests).

All return a DataFrame indexed by timestamp with lower-case
``open/high/low/close/volume`` columns.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

_COLS = ["open", "high", "low", "close", "volume"]


def _flatten_yf(df: pd.DataFrame) -> pd.DataFrame:
    # yfinance may return a MultiIndex (field, ticker) for a single symbol
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [str(c[0]).lower() for c in df.columns]
    else:
        df.columns = [str(c).lower() for c in df.columns]
    if "adj close" in df.columns and "close" not in df.columns:
        df = df.rename(columns={"adj close": "close"})
    keep = [c for c in _COLS if c in df.columns]
    df = df[keep].dropna()
    df.index.name = "time"
    return df


def fetch_ohlcv(
    ticker: str,
    period: str = "1y",
    interval: str = "1d",
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """Download OHLCV bars for ``ticker`` from Yahoo Finance.

    ``period`` examples: ``5d``, ``1mo``, ``6mo``, ``1y``, ``5y``, ``max``.
    ``interval`` examples: ``1m``, ``5m``, ``1h``, ``1d``, ``1wk``.
    Intraday intervals are only available for recent, shorter periods.
    """
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "yfinance is not installed. Run `pip install yfinance`, "
            "use load_csv(), or use synthetic_ohlcv() for offline runs."
        ) from exc

    kwargs = dict(interval=interval, auto_adjust=True, progress=False)
    if start:
        df = yf.download(ticker, start=start, end=end, **kwargs)
    else:
        df = yf.download(ticker, period=period, **kwargs)

    if df is None or len(df) == 0:
        raise ValueError(
            f"no data returned for '{ticker}' (period={period}, interval={interval}). "
            "Check the ticker symbol and that the period/interval combination is valid."
        )
    return _flatten_yf(df)


def load_csv(path: str, time_col: Optional[str] = None) -> pd.DataFrame:
    """Load OHLC(V) bars from a CSV. The time column is auto-detected from a
    column named time/date/datetime/timestamp (or pass ``time_col``)."""
    df = pd.read_csv(path)
    df.columns = [str(c).lower() for c in df.columns]
    if time_col is None:
        for cand in ("time", "date", "datetime", "timestamp"):
            if cand in df.columns:
                time_col = cand
                break
    if time_col and time_col in df.columns:
        df[time_col] = pd.to_datetime(df[time_col])
        df = df.set_index(time_col)
    df.index.name = "time"
    return df.dropna(subset=[c for c in ("close",) if c in df.columns])


def synthetic_ohlcv(
    n: int = 252,
    start_price: float = 100.0,
    annual_vol: float = 0.25,
    annual_drift: float = 0.08,
    seed: int = 7,
    freq: str = "B",
) -> pd.DataFrame:
    """Generate a reproducible random-walk OHLC series for offline use/tests."""
    rng = np.random.default_rng(seed)
    dt = 1.0 / 252.0
    mu = annual_drift
    sigma = annual_vol
    shocks = rng.normal(
        (mu - 0.5 * sigma**2) * dt, sigma * np.sqrt(dt), size=n
    )
    close = start_price * np.exp(np.cumsum(shocks))
    open_ = np.empty(n)
    open_[0] = start_price
    open_[1:] = close[:-1]
    # build plausible intrabar highs/lows around open/close
    span = np.abs(rng.normal(0, sigma * np.sqrt(dt) * start_price, size=n)) + 1e-6
    high = np.maximum(open_, close) + span
    low = np.minimum(open_, close) - span
    volume = rng.integers(1_000_000, 5_000_000, size=n).astype(float)
    idx = pd.date_range("2023-01-02", periods=n, freq=freq, name="time")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def latest_price(ticker: str) -> float:
    """Fetch the most recent trade/quote price for live paper trading."""
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("yfinance is required for live prices.") from exc

    tk = yf.Ticker(ticker)
    # fast_info is cheap; fall back to a 1-minute download if unavailable
    try:
        price = float(tk.fast_info["last_price"])
        if price > 0:
            return price
    except Exception:
        pass
    hist = tk.history(period="1d", interval="1m")
    if len(hist) == 0:
        raise ValueError(f"could not fetch a live price for '{ticker}'")
    return float(hist["Close"].iloc[-1])
