"""Risk-adjusted summary of a backtest Result."""
from __future__ import annotations
import math
import numpy as np
from backtest import Result


def summarize(res: Result, benchmark_return: float | None = None) -> dict:
    rets = [t.ret for t in res.trades]
    n = len(rets)
    if n == 0:
        out = {"total_return": 0.0, "sharpe": 0.0, "max_drawdown": 0.0,
               "hit_rate": 0.0, "n_trades": 0}
    else:
        total = res.final_equity / res.initial_capital - 1.0 if res.initial_capital else 0.0
        arr = np.array(rets, dtype=float)
        # per-trade Sharpe, annualized by trades/year (assume ~12 macro events/yr/type).
        sd = arr.std(ddof=1) if n > 1 else 0.0
        sharpe = float(arr.mean() / sd * math.sqrt(12)) if sd > 0 else 0.0
        eq = res.initial_capital * np.cumprod(1 + arr)     # compounding equity path
        peak = np.maximum.accumulate(eq)
        dd = float((eq / peak - 1.0).min())
        out = {"total_return": float(total), "sharpe": sharpe, "max_drawdown": dd,
               "hit_rate": float((arr > 0).mean()), "n_trades": n}
    if benchmark_return is not None:
        out["buy_hold_return"] = float(benchmark_return)
        out["vs_buyhold"] = float(out["total_return"] - benchmark_return)
    return out
