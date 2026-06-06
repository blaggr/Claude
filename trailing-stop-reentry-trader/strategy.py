"""Trailing stop-loss with re-entry strategy engine.

The rule, stated plainly:

* **Entry** — go long (fully invested) at the first available price.
* **Trailing stop** — track the highest price seen since entry (the *peak*).
  The stop sits ``trail`` dollars below that peak and only ever ratchets up.
  When price falls to the stop, sell.
* **Re-entry** — after being stopped out, watch the price. As soon as it
  climbs ``reentry`` dollars above the price we were stopped out at
  ("1 point up" by default), buy back in. Repeat forever.

Two consumers share this module:

* :func:`run_backtest` walks historical OHLC bars and is the workhorse behind
  the backtest CLI / Streamlit app.
* :class:`StreamingStrategy` processes one live price tick at a time and powers
  the paper-trading loop.

Both operate on dollar-denominated parameters and are deliberately
self-contained (only pandas/numpy) so the logic is easy to audit.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Literal, Optional

import numpy as np
import pandas as pd


@dataclass
class StrategyParams:
    """Configuration for the trailing-stop / re-entry strategy.

    All distances are in dollars (price points), matching how the rule is
    usually described ("trail by $1.50", "re-enter 1 point up").
    """

    trail: float = 1.0
    """Trailing stop distance below the running peak, in dollars."""

    reentry: float = 1.0
    """Re-enter once price rises this many dollars above the last exit price."""

    use_intrabar: bool = True
    """Use bar highs/lows to detect stop hits and re-entries (more realistic).
    When ``False`` decisions are made on the close only."""

    enter_at_start: bool = True
    """Take the first long position on the opening bar. When ``False`` the
    strategy waits for the first re-entry trigger before ever buying."""

    def validate(self) -> None:
        if self.trail <= 0:
            raise ValueError("trail must be a positive dollar amount")
        if self.reentry < 0:
            raise ValueError("reentry must be zero or a positive dollar amount")


@dataclass
class Trade:
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: Optional[pd.Timestamp]
    exit_price: Optional[float]
    shares: float
    pnl: float
    return_pct: float
    exit_reason: str
    bars_held: int

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entry_time"] = str(self.entry_time)
        d["exit_time"] = None if self.exit_time is None else str(self.exit_time)
        return d


@dataclass
class BacktestResult:
    params: StrategyParams
    initial_capital: float
    trades: list[Trade] = field(default_factory=list)
    equity: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    stop_line: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    trigger_line: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    position: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    price: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))

    # -- summary metrics -------------------------------------------------
    @property
    def final_equity(self) -> float:
        return float(self.equity.iloc[-1]) if len(self.equity) else self.initial_capital

    @property
    def total_return(self) -> float:
        return self.final_equity / self.initial_capital - 1.0

    @property
    def buy_hold_return(self) -> float:
        if len(self.price) < 2:
            return 0.0
        return float(self.price.iloc[-1] / self.price.iloc[0] - 1.0)

    @property
    def num_trades(self) -> int:
        return sum(1 for t in self.trades if t.exit_time is not None)

    @property
    def win_rate(self) -> float:
        closed = [t for t in self.trades if t.exit_time is not None]
        if not closed:
            return 0.0
        return sum(1 for t in closed if t.pnl > 0) / len(closed)

    @property
    def avg_trade_return(self) -> float:
        closed = [t for t in self.trades if t.exit_time is not None]
        if not closed:
            return 0.0
        return float(np.mean([t.return_pct for t in closed]))

    @property
    def max_drawdown(self) -> float:
        if len(self.equity) == 0:
            return 0.0
        running_max = self.equity.cummax()
        drawdown = self.equity / running_max - 1.0
        return float(drawdown.min())

    @property
    def exposure(self) -> float:
        """Fraction of bars spent holding a position."""
        if len(self.position) == 0:
            return 0.0
        return float((self.position > 0).mean())

    def summary(self) -> dict:
        return {
            "initial_capital": self.initial_capital,
            "final_equity": round(self.final_equity, 2),
            "total_return_pct": round(self.total_return * 100, 2),
            "buy_hold_return_pct": round(self.buy_hold_return * 100, 2),
            "num_trades": self.num_trades,
            "win_rate_pct": round(self.win_rate * 100, 2),
            "avg_trade_return_pct": round(self.avg_trade_return * 100, 2),
            "max_drawdown_pct": round(self.max_drawdown * 100, 2),
            "exposure_pct": round(self.exposure * 100, 2),
        }


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Lower-case and validate the OHLC columns we rely on."""
    df = df.rename(columns={c: str(c).lower() for c in df.columns})
    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"data is missing required columns: {sorted(missing)}")
    return df


def run_backtest(
    df: pd.DataFrame,
    params: StrategyParams,
    initial_capital: float = 10_000.0,
) -> BacktestResult:
    """Walk OHLC bars applying the trailing-stop / re-entry rule.

    Intrabar model (when ``use_intrabar`` is on) is deliberately conservative:
    within a bar the stop is checked against the *prior* peak using the bar low
    **before** the high is allowed to extend the peak. A gap below the stop
    fills at the open. This avoids flattering results by assuming the peak
    extends before the stop can trigger.
    """
    params.validate()
    df = _normalize(df)
    if len(df) == 0:
        raise ValueError("no data to backtest")

    cash = float(initial_capital)
    shares = 0.0
    state: Literal["flat", "long"] = "flat"
    peak: Optional[float] = None
    entry_price: Optional[float] = None
    entry_time = None
    entry_idx = 0
    last_exit_price: Optional[float] = None

    trades: list[Trade] = []
    equity_vals: list[float] = []
    stop_vals: list[float] = []
    trigger_vals: list[float] = []
    pos_vals: list[float] = []

    index = df.index
    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)

    for i in range(len(df)):
        t = index[i]

        if state == "flat":
            do_enter = False
            fill = math.nan
            if last_exit_price is None:
                if params.enter_at_start:
                    do_enter, fill = True, o[i]
            else:
                trigger = last_exit_price + params.reentry
                if params.use_intrabar:
                    if h[i] >= trigger:
                        do_enter = True
                        fill = o[i] if o[i] >= trigger else trigger
                else:
                    if c[i] >= trigger:
                        do_enter, fill = True, c[i]

            if do_enter and fill > 0:
                shares = cash / fill
                cash = 0.0
                state = "long"
                entry_price = fill
                entry_time = t
                entry_idx = i
                peak = fill

        elif state == "long":
            assert peak is not None and entry_price is not None
            stop_level = peak - params.trail
            exited = False
            fill = math.nan
            if params.use_intrabar:
                if o[i] <= stop_level:          # gapped through the stop
                    exited, fill = True, o[i]
                elif low[i] <= stop_level:       # stop touched intrabar
                    exited, fill = True, stop_level
                else:
                    peak = max(peak, h[i])       # only now extend the peak
            else:
                if c[i] <= stop_level:
                    exited, fill = True, c[i]
                else:
                    peak = max(peak, c[i])   # ratchet the peak on the close

            if exited:
                cash = shares * fill
                pnl = (fill - entry_price) * shares
                ret = fill / entry_price - 1.0
                trades.append(
                    Trade(
                        entry_time=entry_time,
                        entry_price=float(entry_price),
                        exit_time=t,
                        exit_price=float(fill),
                        shares=float(shares),
                        pnl=float(pnl),
                        return_pct=float(ret),
                        exit_reason="trailing_stop",
                        bars_held=i - entry_idx,
                    )
                )
                shares = 0.0
                state = "flat"
                last_exit_price = float(fill)
                peak = None
                entry_price = None

        # mark-to-market and record per-bar series
        eq = cash + shares * c[i]
        equity_vals.append(eq)
        pos_vals.append(shares)
        if state == "long" and peak is not None:
            stop_vals.append(peak - params.trail)
            trigger_vals.append(math.nan)
        else:
            stop_vals.append(math.nan)
            trigger_vals.append(
                math.nan if last_exit_price is None else last_exit_price + params.reentry
            )

    # leave any open position open (mark-to-market already reflects it), but
    # record it as an open trade for visibility
    if state == "long" and entry_price is not None:
        trades.append(
            Trade(
                entry_time=entry_time,
                entry_price=float(entry_price),
                exit_time=None,
                exit_price=None,
                shares=float(shares),
                pnl=float(shares * c[-1] - shares * entry_price),
                return_pct=float(c[-1] / entry_price - 1.0),
                exit_reason="open",
                bars_held=len(df) - 1 - entry_idx,
            )
        )

    return BacktestResult(
        params=params,
        initial_capital=float(initial_capital),
        trades=trades,
        equity=pd.Series(equity_vals, index=index, name="equity"),
        stop_line=pd.Series(stop_vals, index=index, name="stop"),
        trigger_line=pd.Series(trigger_vals, index=index, name="reentry_trigger"),
        position=pd.Series(pos_vals, index=index, name="shares"),
        price=df["close"].copy(),
    )


class StreamingStrategy:
    """Tick-by-tick version of the rule for live (paper) trading.

    Feed it one price at a time via :meth:`update`; it returns an event dict
    when a buy or sell fires, otherwise ``None``. State is plain attributes so
    it can be serialized to JSON and resumed across restarts.
    """

    def __init__(self, params: StrategyParams):
        params.validate()
        self.params = params
        self.state: Literal["flat", "long"] = "flat"
        self.peak: Optional[float] = None
        self.entry_price: Optional[float] = None
        self.last_exit_price: Optional[float] = None

    # -- serialization for persistence ----------------------------------
    def to_dict(self) -> dict:
        return {
            "params": asdict(self.params),
            "state": self.state,
            "peak": self.peak,
            "entry_price": self.entry_price,
            "last_exit_price": self.last_exit_price,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StreamingStrategy":
        obj = cls(StrategyParams(**d["params"]))
        obj.state = d.get("state", "flat")
        obj.peak = d.get("peak")
        obj.entry_price = d.get("entry_price")
        obj.last_exit_price = d.get("last_exit_price")
        return obj

    @property
    def stop_level(self) -> Optional[float]:
        if self.state == "long" and self.peak is not None:
            return self.peak - self.params.trail
        return None

    @property
    def reentry_trigger(self) -> Optional[float]:
        if self.state == "flat" and self.last_exit_price is not None:
            return self.last_exit_price + self.params.reentry
        return None

    def update(self, price: float) -> Optional[dict]:
        """Process one price tick. Returns a fill event dict or ``None``."""
        if price <= 0 or math.isnan(price):
            return None

        if self.state == "flat":
            if self.last_exit_price is None:
                if not self.params.enter_at_start:
                    return None
                return self._enter(price)
            if price >= self.last_exit_price + self.params.reentry:
                return self._enter(price)
            return None

        # long
        assert self.peak is not None
        self.peak = max(self.peak, price)
        if price <= self.peak - self.params.trail:
            return self._exit(price)
        return None

    def _enter(self, price: float) -> dict:
        self.state = "long"
        self.entry_price = price
        self.peak = price
        return {"action": "BUY", "price": price}

    def _exit(self, price: float) -> dict:
        ret = price / self.entry_price - 1.0 if self.entry_price else 0.0
        self.last_exit_price = price
        self.state = "flat"
        self.entry_price = None
        self.peak = None
        return {"action": "SELL", "price": price, "return_pct": ret}
