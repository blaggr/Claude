"""Risk-adjusted summary of a backtest Result."""
from __future__ import annotations
import math
import numpy as np
from backtest import Result


def summarize(res: Result, benchmark_return: float | None = None) -> dict:
    trades = res.trades
    n = len(trades)
    if n == 0:
        out = {"total_return": 0.0, "sharpe": 0.0, "max_drawdown": 0.0,
               "hit_rate": 0.0, "n_trades": 0}
    else:
        scaled = np.array([t.size_frac * t.ret for t in trades], dtype=float)  # actual portfolio step returns
        eq = res.initial_capital * np.cumprod(1 + scaled)
        eq = np.concatenate([[res.initial_capital], eq])
        total = res.final_equity / res.initial_capital - 1.0 if res.initial_capital else 0.0
        sd = scaled.std(ddof=1) if n > 1 else 0.0
        sharpe = float(scaled.mean() / sd * math.sqrt(12)) if sd > 0 else 0.0
        peak = np.maximum.accumulate(eq)
        dd = float((eq / peak - 1.0).min())
        hit = float((np.array([t.ret for t in trades]) > 0).mean())
        out = {"total_return": float(total), "sharpe": sharpe, "max_drawdown": dd,
               "hit_rate": hit, "n_trades": n}
    if benchmark_return is not None:
        out["buy_hold_return"] = float(benchmark_return)
        out["vs_buyhold"] = float(out["total_return"] - benchmark_return)
    return out
