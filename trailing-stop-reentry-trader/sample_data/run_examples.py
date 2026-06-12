"""Reproduce the historical backtests in ../RESULTS.md.

Runs the trailing-stop / re-entry strategy over two real daily OHLC series
(bundled as CSVs in this folder) across a sweep of trail / re-entry sizes and
prints a comparison table against buy-and-hold.

    python sample_data/run_examples.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data as d
from strategy import StrategyParams, run_backtest

HERE = os.path.dirname(os.path.abspath(__file__))


def max_drawdown_pct(close):
    return float((close / close.cummax() - 1).min() * 100)


def sweep(name, path, trails, reentries):
    df = d.load_csv(path)
    c = df["close"]
    # Benchmark buy-and-hold from the first OPEN (the price the strategy itself
    # first fills at), so this header matches the vs-B&H column.
    bh = (c.iloc[-1] / df["open"].iloc[0] - 1) * 100
    print()
    print(f"{name} | {len(df)} bars | {df.index[0].date()} -> {df.index[-1].date()} "
          f"| price ${c.iloc[0]:.0f} -> ${c.iloc[-1]:.0f}")
    print(f"Buy & hold: {bh:+.2f}%   (max drawdown {max_drawdown_pct(c):.2f}%)")
    hdr = ("trail$", "reentry$", "ret%", "vsB&H", "trades", "win%", "maxDD%", "expo%")
    print("{:>6} {:>8} {:>8} {:>8} {:>7} {:>6} {:>8} {:>7}".format(*hdr))
    print("-" * 62)
    for tr in trails:
        for re in reentries:
            r = run_backtest(df, StrategyParams(trail=tr, reentry=re, use_intrabar=True), 10_000)
            s = r.summary()
            print("{:>6} {:>8} {:>8.2f} {:>+8.2f} {:>7} {:>6.0f} {:>8.2f} {:>7.0f}".format(
                tr, re, s["total_return_pct"], s["total_return_pct"] - s["buy_hold_return_pct"],
                s["num_trades"], s["win_rate_pct"], s["max_drawdown_pct"], s["exposure_pct"]))


if __name__ == "__main__":
    sweep("AAPL daily (~$125)", os.path.join(HERE, "AAPL_daily.csv"), [1, 2, 3, 5], [1, 2])
    sweep("TSLA daily (~$220)", os.path.join(HERE, "TSLA_daily.csv"), [5, 10, 15, 20], [1, 5])
