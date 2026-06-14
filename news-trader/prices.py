"""Minute-bar access. Fails loud rather than silently returning bad data."""
from __future__ import annotations
import datetime as dt
import pandas as pd


class PriceError(RuntimeError):
    pass


def load_bars(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "ts" not in df.columns or "close" not in df.columns:
        raise PriceError(f"{path}: bars need at least ts and close columns; got {list(df.columns)}")
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def first_at_or_after(bars: pd.DataFrame, ts: dt.datetime) -> tuple[dt.datetime, float]:
    """Return (timestamp, close) of the first bar at/after ts. Raises if none."""
    target = pd.Timestamp(ts, tz="UTC") if ts.tzinfo is None else pd.Timestamp(ts)
    hit = bars[bars["ts"] >= target]
    if hit.empty:
        raise PriceError(f"no bar at or after {ts}")
    row = hit.iloc[0]
    return row["ts"].to_pydatetime(), float(row["close"])
