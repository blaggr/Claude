"""Command-line backtester for the trailing-stop / re-entry strategy.

Examples
--------
Backtest SPY over the last 2 years of daily bars with a $2 trail and re-entry
1 point up::

    python backtest.py --ticker SPY --period 2y --trail 2 --reentry 1

Offline demo on synthetic data (no network)::

    python backtest.py --synthetic --trail 1.5 --reentry 1

Use your own CSV::

    python backtest.py --csv mydata.csv --trail 1 --reentry 1
"""
from __future__ import annotations

import argparse
import json
import sys

import data as data_mod
from strategy import StrategyParams, run_backtest


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_argument_group("data source")
    src.add_argument("--ticker", help="Stock/ETF/index symbol, e.g. AAPL, SPY, VTI, ^GSPC")
    src.add_argument("--period", default="1y", help="History window for --ticker (default 1y)")
    src.add_argument("--interval", default="1d", help="Bar size for --ticker (default 1d)")
    src.add_argument("--start", help="Start date YYYY-MM-DD (overrides --period)")
    src.add_argument("--end", help="End date YYYY-MM-DD")
    src.add_argument("--csv", help="Load bars from a local OHLC CSV instead")
    src.add_argument("--synthetic", action="store_true", help="Use generated offline data")

    strat = p.add_argument_group("strategy")
    strat.add_argument("--trail", type=float, default=1.0, help="Trailing stop distance in $ (default 1.0)")
    strat.add_argument("--reentry", type=float, default=1.0, help="Re-entry trigger in $ above last exit (default 1.0)")
    strat.add_argument("--capital", type=float, default=10_000.0, help="Starting capital (default 10000)")
    strat.add_argument("--close-only", action="store_true", help="Decide on bar close instead of intrabar high/low")
    strat.add_argument("--no-start-entry", action="store_true", help="Don't buy on the first bar; wait for a re-entry trigger")

    p.add_argument("--json", action="store_true", help="Emit the summary as JSON")
    return p


def load_data(args) -> "data_mod.pd.DataFrame":
    if args.synthetic:
        return data_mod.synthetic_ohlcv()
    if args.csv:
        return data_mod.load_csv(args.csv)
    if args.ticker:
        return data_mod.fetch_ohlcv(
            args.ticker, period=args.period, interval=args.interval,
            start=args.start, end=args.end,
        )
    raise SystemExit("Pick a data source: --ticker SYMBOL, --csv FILE, or --synthetic")


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    df = load_data(args)

    params = StrategyParams(
        trail=args.trail,
        reentry=args.reentry,
        use_intrabar=not args.close_only,
        enter_at_start=not args.no_start_entry,
    )
    result = run_backtest(df, params, initial_capital=args.capital)
    summary = result.summary()

    if args.json:
        print(json.dumps({
            "summary": summary,
            "trades": [t.to_dict() for t in result.trades],
        }, indent=2))
        return 0

    label = args.ticker or args.csv or "synthetic"
    print(f"\nTrailing-stop / re-entry backtest — {label}")
    print(f"  bars: {len(df)}   trail: ${params.trail:g}   re-entry: +${params.reentry:g}")
    print("  " + "-" * 48)
    print(f"  Strategy total return : {summary['total_return_pct']:>8.2f}%")
    print(f"  Buy & hold return     : {summary['buy_hold_return_pct']:>8.2f}%")
    print(f"  Final equity          : ${summary['final_equity']:>12,.2f}")
    print(f"  Trades (closed)       : {summary['num_trades']:>8}")
    print(f"  Win rate              : {summary['win_rate_pct']:>8.2f}%")
    print(f"  Avg trade return      : {summary['avg_trade_return_pct']:>8.2f}%")
    print(f"  Max drawdown          : {summary['max_drawdown_pct']:>8.2f}%")
    print(f"  Time in market        : {summary['exposure_pct']:>8.2f}%")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
