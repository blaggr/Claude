"""Walk-forward: tune on train, lock, evaluate on held-out test. Plus the gate.
Honesty: reports n_configs (sweep breadth) and n so a lucky in-sample peak on a
handful of events cannot masquerade as edge."""
from __future__ import annotations
from backtest import run_backtest
from signals import drift_signal
from metrics import summarize
from prices import first_at_or_after, PriceError


def _classify_factory(p):
    return lambda ev, bars: drift_signal(
        ev, bars, delta_s=p["delta_s"], measure_min=p["measure_min"],
        horizon_min=p["horizon_min"], trail=p["trail"])


def _buy_hold_return(events, bars_by_symbol):
    """Buy-and-hold of the window's primary symbol from the first event to the
    last available bar — the benchmark the strategy must beat."""
    if not events:
        return None
    symbol = events[0].payload.get("symbol")
    bars = bars_by_symbol.get(symbol)
    if bars is None or bars.empty:
        return None
    try:
        _, p_in = first_at_or_after(bars, events[0].ts)
    except PriceError:
        return None
    p_out = float(bars.iloc[-1]["close"])
    return p_out / p_in - 1.0


def walk_forward(events, bars, grid, cost_model, train_frac=0.6, capital=10_000.0):
    events = sorted(events, key=lambda e: e.ts)
    cut = max(1, int(len(events) * train_frac))
    train, test = events[:cut], events[cut:]
    best, best_metric = None, -1e18
    for p in grid:
        m = summarize(run_backtest(train, bars, _classify_factory(p), cost_model, capital))
        score = m["sharpe"]            # primary tuning key on TRAIN only
        if score > best_metric:
            best, best_metric = p, score
    train_m = summarize(run_backtest(train, bars, _classify_factory(best), cost_model, capital),
                        benchmark_return=_buy_hold_return(train, bars))
    test_m = summarize(run_backtest(test, bars, _classify_factory(best), cost_model, capital),
                       benchmark_return=_buy_hold_return(test, bars))
    return {"best_params": best, "train": train_m, "test": test_m,
            "n_configs": len(grid), "n_train": len(train), "n_test": len(test)}


def gate(test_metrics: dict, *, n: int, min_sharpe: float, max_dd: float,
         min_n: int) -> bool:
    """All must hold on the OUT-OF-SAMPLE window: enough events, Sharpe bar,
    drawdown within limit, and BEATS buy-and-hold."""
    return (n >= min_n
            and test_metrics.get("sharpe", 0.0) >= min_sharpe
            and test_metrics.get("max_drawdown", -1.0) >= max_dd       # max_dd is negative
            and test_metrics.get("vs_buyhold", -1.0) >= 0.0)
