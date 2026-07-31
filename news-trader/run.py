"""Run the drift backtest on a data directory and print the report.

    python run.py --events sample_data/events.csv --bars-dir sample_data
"""
from __future__ import annotations
import argparse, glob, os
from macro_calendar import load_events
from prices import load_bars
from costs import CostModel
from signals import drift_signal
from backtest import run_backtest
from metrics import summarize

DELTA_S, MEASURE_MIN = 60, 10     # fill delay + reaction-measurement window


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--bars-dir", required=True)
    ap.add_argument("--horizon-min", type=int, default=30)
    ap.add_argument("--trail", type=float, default=None)
    ap.add_argument("--capital", type=float, default=10_000.0)
    a = ap.parse_args(argv)
    events = load_events(a.events)
    bars = {os.path.splitext(os.path.basename(p))[0]: load_bars(p)
            for p in glob.glob(os.path.join(a.bars_dir, "*.csv"))
            if not p.endswith("events.csv")}
    classify = lambda ev, b: drift_signal(ev, b, delta_s=DELTA_S, measure_min=MEASURE_MIN,
                                           horizon_min=a.horizon_min, trail=a.trail)
    res = run_backtest(events, bars, classify, CostModel(), a.capital)
    s = summarize(res)
    print(f"trades={s['n_trades']}  total={s['total_return']:+.2%}  "
          f"sharpe={s['sharpe']:.2f}  maxDD={s['max_drawdown']:+.2%}  hit={s['hit_rate']:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
