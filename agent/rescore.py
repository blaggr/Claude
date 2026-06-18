"""Rescore the calibrated edges net of transaction costs.

For every topic / regime / leg in ``news_trade_engine.CALIB`` this computes:

  * GROSS expected edge per share — the probability-weighted expected dollar
    move of the directional bet at a reference price:
        edge_gross = (2p - 1) * (move% / 100) * ref_price
    (``2p-1`` is the expected sign realization; a coin-flip leg has zero edge.)
  * ROUND-TRIP COST per share — entry + exit half-spread/slippage (and, for a
    short leg, pro-rata borrow over ``--hold-days``) from ``CostModel``,
    divided by quantity to express it per share.
  * NET edge per share — gross minus cost.

It prints a table flagging which calibrated legs still have positive expected
value after costs (OK) and which flip negative (NEG). Reference prices come
from ``agent.marketdata._REF`` if importable, else a small built-in table.

Pure arithmetic, no network. Paper / planning tool only.

Examples:
    python -m agent.rescore
    python -m agent.rescore --slippage-bps 50 --hold-days 1
    python -m agent.rescore --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Allow ``python agent/rescore.py`` as well as ``python -m agent.rescore``.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# ...and let the CALIB import find the experiments package.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "experiments"))

from agent.costs import CostModel  # noqa: E402

# Reference prices for sizing the per-share edge. Prefer the live agent's table.
try:
    from agent.marketdata import _REF as REF_PRICES  # type: ignore
except Exception:  # pragma: no cover - fallback only
    REF_PRICES = {
        "SPY": 600.0, "QQQ": 530.0, "GLD": 310.0, "FXI": 38.0, "KWEB": 35.0,
        "USO": 80.0, "ITA": 165.0, "TLT": 88.0,
    }
_FALLBACK_PRICE = 100.0


def _load_calib() -> dict:
    """Import CALIB from the news trade engine (stdlib-only module)."""
    from news_trade_engine import CALIB
    return CALIB


def _ref_price(symbol: str) -> float:
    return float(REF_PRICES.get(symbol.upper(), _FALLBACK_PRICE))


def rescore(cost: CostModel, hold_days: float, qty: int = 100,
            calib: dict | None = None) -> list[dict]:
    """Return one row per (topic, regime, symbol) leg with gross/net edge.

    ``side`` is the calibrated direction: a +1 sign is a long (BUY), -1 a
    short (SELL). Edge and cost are reported per share; the totals scale by
    ``qty``. Borrow only applies to short legs.
    """
    calib = calib if calib is not None else _load_calib()
    rows: list[dict] = []
    for topic, regimes in calib.items():
        for regime, legs in regimes.items():
            for symbol, c in legs.items():
                sign = int(c["sign"])
                p = float(c["p"])
                move_pct = float(c["move"])
                price = _ref_price(symbol)
                side = "BUY" if sign > 0 else "SELL"
                # expected per-share $ move of the directional bet
                edge_gross = (2 * p - 1) * (move_pct / 100.0) * price
                rt_cost = cost.round_trip_cost(
                    symbol, qty, price, price, side, hold_days)
                cost_ps = rt_cost / qty if qty else 0.0
                edge_net = edge_gross - cost_ps
                rows.append({
                    "topic": topic,
                    "regime": regime,
                    "symbol": symbol,
                    "side": side,
                    "p": round(p, 3),
                    "move_pct": round(move_pct, 3),
                    "ref_price": round(price, 2),
                    "edge_gross_ps": round(edge_gross, 4),
                    "cost_ps": round(cost_ps, 4),
                    "edge_net_ps": round(edge_net, 4),
                    "positive": edge_net > 0,
                    "flipped_negative": edge_gross > 0 and edge_net <= 0,
                })
    return rows


def _print_table(rows: list[dict], cost: CostModel, hold_days: float,
                 qty: int) -> None:
    print(f"# Cost-adjusted calibrated edges  (qty={qty}, hold_days={hold_days})")
    print(f"# half_spread={cost.half_spread_bps}bps  slippage={cost.slippage_bps}bps  "
          f"commission/sh={cost.commission_per_share}  "
          f"borrow={cost.borrow_rate_annual:.2%}/yr")
    hdr = (f"{'topic':22} {'regime':11} {'sym':5} {'side':4} {'p':>5} "
           f"{'move%':>6} {'gross/sh':>9} {'cost/sh':>8} {'net/sh':>8}  flag")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        flag = "NEG " if not r["positive"] else "OK  "
        if r["flipped_negative"]:
            flag = "FLIP"
        print(f"{r['topic']:22} {r['regime']:11} {r['symbol']:5} {r['side']:4} "
              f"{r['p']:>5.2f} {r['move_pct']:>6.2f} {r['edge_gross_ps']:>9.4f} "
              f"{r['cost_ps']:>8.4f} {r['edge_net_ps']:>8.4f}  {flag}")
    n_pos = sum(1 for r in rows if r["positive"])
    n_flip = sum(1 for r in rows if r["flipped_negative"])
    print("-" * len(hdr))
    print(f"# {len(rows)} legs: {n_pos} positive net, {len(rows) - n_pos} "
          f"non-positive ({n_flip} flipped negative by costs)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slippage-bps", type=float, default=None,
                    help="Per-side slippage in bps (default: CostModel default)")
    ap.add_argument("--spread-bps", type=float, default=None,
                    help="Per-side half-spread in bps (default: CostModel default)")
    ap.add_argument("--hold-days", type=float, default=0.0,
                    help="Holding period in days (drives short-borrow accrual)")
    ap.add_argument("--qty", type=int, default=100,
                    help="Share quantity used to scale per-order minimums")
    ap.add_argument("--json", action="store_true", help="Emit JSON")
    args = ap.parse_args(argv)

    overrides: dict[str, float] = {}
    if args.slippage_bps is not None:
        overrides["slippage_bps"] = args.slippage_bps
    if args.spread_bps is not None:
        overrides["half_spread_bps"] = args.spread_bps
    cost = CostModel.from_env(**overrides)

    rows = rescore(cost, args.hold_days, qty=args.qty)
    if args.json:
        print(json.dumps({
            "params": {
                "half_spread_bps": cost.half_spread_bps,
                "slippage_bps": cost.slippage_bps,
                "commission_per_share": cost.commission_per_share,
                "borrow_rate_annual": cost.borrow_rate_annual,
                "hold_days": args.hold_days,
                "qty": args.qty,
            },
            "legs": rows,
        }, indent=2))
    else:
        _print_table(rows, cost, args.hold_days, args.qty)
    return 0


if __name__ == "__main__":
    sys.exit(main())
