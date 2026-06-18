"""Live performance tracker + circuit breaker — the "did the edge actually pay?"
half of the loop.

The calibrated engine (experiments/news_trade_engine.py) tells the agent what an
edge *should* be worth, with a hit probability ``p`` per instrument. This module
closes the feedback loop: it reads the agent's own append-only journal, pairs the
realised EXIT records into closed trades, and measures what actually happened —
per symbol and overall — then asks whether reality is keeping up with the prior.

Two objects, both pure stdlib (no pandas/numpy), offline, paper-only:

  * PerformanceTracker — closed-trade statistics from the journal: count, win
    rate, total/avg realised P&L, avg return %, and a Wilson score 95% CI for the
    win rate (a binomial proportion CI that behaves at small N, unlike the naive
    +/- z*sqrt(pq/n)). It also compares the realised win rate against the
    calibrated prior ``p`` for symbols that map cleanly into CALIB.
  * CircuitBreaker — a persisted kill-switch (state/disabled.json). When a symbol
    has accumulated enough closed trades and its win rate's Wilson UPPER bound is
    still below a floor (i.e. we can be statistically confident the edge is below
    the floor, not just unlucky), it auto-disables that symbol. Disables can also
    be set/cleared by hand. The agent can consult ``is_disabled`` before acting.

Nothing here talks to a broker or the network; it only reads the journal and
writes one small JSON file.
"""
from __future__ import annotations

import json
import math
import os
import sys
from typing import Any

from .memory import Memory

HERE = os.path.dirname(os.path.abspath(__file__))

# --- calibrated priors -------------------------------------------------------
# The priors live in experiments/news_trade_engine.py (stdlib only). Import is
# best-effort: the tracker still works without it, just without the comparison.
try:
    sys.path.insert(0, os.path.join(HERE, "..", "experiments"))
    import news_trade_engine as _nte  # noqa: E402

    _CALIB = getattr(_nte, "CALIB", {})
except Exception:  # pragma: no cover - engine optional
    _CALIB = {}


def wilson_interval(wins: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score confidence interval for a binomial proportion.

    Returns (lower, upper), both clamped to [0, 1]. ``z`` defaults to the 95%
    two-sided normal quantile. With n == 0 the interval is the whole [0, 1].

    This is the small-sample-honest CI: at low N it stays inside [0, 1] and is
    asymmetric, where the textbook normal-approximation interval would run off
    the ends or collapse to a point on a 0% / 100% sample.
    """
    if n <= 0:
        return (0.0, 1.0)
    phat = wins / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (phat + z2 / (2 * n)) / denom
    margin = (z * math.sqrt((phat * (1 - phat) + z2 / (4 * n)) / n)) / denom
    lo = max(0.0, centre - margin)
    hi = min(1.0, centre + margin)
    return (lo, hi)


def prior_for(symbol: str) -> dict | None:
    """Best calibrated prior for ``symbol`` across all CALIB topics/regimes.

    A symbol can appear under several topic/regime tables with different ``p``.
    We pick the entry with the highest ``p`` (the most reliable mapping) so the
    realised-vs-prior comparison uses the strongest claim the calibration makes
    about that instrument. Returns a dict with the prior's fields plus where it
    came from, or None if the symbol isn't calibrated.
    """
    sym = symbol.upper()
    best: dict | None = None
    for topic, regimes in _CALIB.items():
        for regime, table in regimes.items():
            leg = table.get(sym)
            if not leg:
                continue
            p = float(leg.get("p", 0.0))
            if best is None or p > best["prior_p"]:
                best = {
                    "symbol": sym,
                    "topic": topic,
                    "regime": regime,
                    "prior_p": p,
                    "sign": leg.get("sign"),
                    "move": leg.get("move"),
                }
    return best


class PerformanceTracker:
    """Closed-trade statistics derived from the agent's journal.

    Construct with either a ``Memory`` (``PerformanceTracker(memory=mem)``), a
    state directory (``PerformanceTracker(state_dir=dir)``), or an explicit list
    of journal records (``PerformanceTracker(records=[...])``).
    """

    def __init__(self, memory: Memory | None = None, *, state_dir: str | None = None,
                 records: list[dict] | None = None):
        if records is not None:
            self._records = list(records)
        else:
            if memory is None:
                memory = Memory(state_dir=state_dir) if state_dir else Memory()
            self._records = memory.journal()

    # ----------------------------------------------------------- trades
    def closed_trades(self) -> list[dict]:
        """Every EXIT record, normalised to a closed-trade dict.

        EXIT records already carry the full round trip (entry, exit, qty, pnl),
        so a closed trade is just one EXIT record. ``ret_pct`` is the per-share
        return in the direction of the trade.
        """
        trades: list[dict] = []
        for rec in self._records:
            if rec.get("kind") != "EXIT":
                continue
            symbol = rec.get("symbol")
            entry = rec.get("entry")
            exit_ = rec.get("exit")
            pnl = rec.get("pnl")
            if symbol is None or entry is None or exit_ is None or pnl is None:
                continue
            # exit_side is the side that CLOSES the position, so the original
            # position was the opposite. sell-to-close => was long.
            exit_side = str(rec.get("exit_side", "")).lower()
            long = exit_side == "sell"
            try:
                entry_f = float(entry)
                exit_f = float(exit_)
                pnl_f = float(pnl)
            except (TypeError, ValueError):
                continue
            direction = 1.0 if long else -1.0
            ret_pct = (direction * (exit_f - entry_f) / entry_f * 100.0) if entry_f else 0.0
            trades.append({
                "symbol": str(symbol).upper(),
                "entry": entry_f,
                "exit": exit_f,
                "qty": rec.get("qty"),
                "pnl": pnl_f,
                "ret_pct": ret_pct,
                "reason": rec.get("reason"),
                "ts": rec.get("ts"),
            })
        return trades

    @staticmethod
    def _stats(trades: list[dict]) -> dict:
        n = len(trades)
        wins = sum(1 for t in trades if t["pnl"] > 0)
        total_pnl = sum(t["pnl"] for t in trades)
        win_rate = (wins / n) if n else 0.0
        lo, hi = wilson_interval(wins, n)
        return {
            "trades": n,
            "wins": wins,
            "losses": n - wins,
            "win_rate": round(win_rate, 4),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(total_pnl / n, 2) if n else 0.0,
            "avg_return_pct": round(sum(t["ret_pct"] for t in trades) / n, 4) if n else 0.0,
            "wilson_low": round(lo, 4),
            "wilson_high": round(hi, 4),
        }

    def by_symbol(self) -> dict[str, dict]:
        """Per-symbol closed-trade statistics, keyed by symbol."""
        buckets: dict[str, list[dict]] = {}
        for t in self.closed_trades():
            buckets.setdefault(t["symbol"], []).append(t)
        return {sym: self._stats(ts) for sym, ts in sorted(buckets.items())}

    def overall(self) -> dict:
        """Closed-trade statistics across all symbols."""
        return self._stats(self.closed_trades())

    def summary(self) -> dict:
        """Everything: per-symbol stats, overall, and the prior comparison."""
        return {
            "overall": self.overall(),
            "by_symbol": self.by_symbol(),
            "prior_comparison": self.prior_comparison(),
        }

    # ----------------------------------------------------- prior compare
    def prior_comparison(self) -> dict[str, dict]:
        """Realised win rate vs the calibrated prior ``p``, per mapped symbol.

        For each symbol that maps cleanly into CALIB, report the realised win
        rate, its Wilson CI, the prior ``p``, and whether the realised rate is
        below the prior — flagging ``below_prior_ci`` when even the realised
        Wilson LOWER bound sits under the prior (a statistically meaningful
        shortfall, not just noise).
        """
        out: dict[str, dict] = {}
        stats = self.by_symbol()
        for sym, st in stats.items():
            prior = prior_for(sym)
            if prior is None:
                continue
            prior_p = prior["prior_p"]
            out[sym] = {
                "trades": st["trades"],
                "realized_win_rate": st["win_rate"],
                "wilson_low": st["wilson_low"],
                "wilson_high": st["wilson_high"],
                "prior_p": prior_p,
                "prior_topic": prior["topic"],
                "prior_regime": prior["regime"],
                "below_prior": st["win_rate"] < prior_p,
                "below_prior_ci": st["wilson_low"] < prior_p,
            }
        return out


class CircuitBreaker:
    """Persisted kill-switch over symbols (and topics) that have underperformed.

    State is a small JSON file ``state/disabled.json`` mapping each disabled key
    to ``{"reason": ..., "ts": ...}``. ``evaluate`` auto-disables per the rule;
    ``disable`` / ``enable`` are the manual overrides; ``is_disabled`` is the
    cheap check the agent calls before acting on an idea.

    Auto-disable rule: a symbol with >= ``min_trades`` closed trades whose win
    rate's Wilson UPPER bound is still < ``floor`` is disabled — i.e. we are 95%
    confident its true win rate is below the floor, not merely unlucky.
    """

    FILENAME = "disabled.json"

    def __init__(self, state_dir: str | None = None, *, memory: Memory | None = None,
                 min_trades: int = 8, floor: float = 0.5):
        if state_dir is None:
            state_dir = memory.dir if memory is not None else os.path.join(HERE, "state")
        self.dir = state_dir
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, self.FILENAME)
        self.min_trades = min_trades
        self.floor = floor
        self._disabled: dict[str, dict] = self._load()

    # ----------------------------------------------------------- persistence
    def _load(self) -> dict[str, dict]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        # normalise legacy/plain entries to the {reason, ts} shape
        out: dict[str, dict] = {}
        for k, v in data.items():
            out[str(k).upper()] = v if isinstance(v, dict) else {"reason": str(v), "ts": None}
        return out

    def _save(self) -> None:
        with open(self.path, "w") as f:
            json.dump(self._disabled, f, indent=2, sort_keys=True)

    @staticmethod
    def _now() -> str:
        import datetime as dt
        return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    # ----------------------------------------------------------- mutators
    def disable(self, key: str, reason: str = "manual") -> dict:
        key = str(key).upper()
        entry = {"reason": reason, "ts": self._now()}
        self._disabled[key] = entry
        self._save()
        return {key: entry}

    def enable(self, key: str) -> bool:
        """Re-enable ``key``; returns True if it had been disabled."""
        key = str(key).upper()
        existed = self._disabled.pop(key, None) is not None
        if existed:
            self._save()
        return existed

    def is_disabled(self, key: str) -> bool:
        return str(key).upper() in self._disabled

    def disabled(self) -> dict[str, dict]:
        """The current disabled set (copy)."""
        return dict(self._disabled)

    # ----------------------------------------------------------- the rule
    def evaluate(self, tracker: PerformanceTracker) -> dict[str, dict]:
        """Auto-disable any symbol that trips the rule. Returns what was newly
        disabled in this pass (existing manual disables are left untouched)."""
        newly: dict[str, dict] = {}
        for sym, st in tracker.by_symbol().items():
            if self.is_disabled(sym):
                continue
            if st["trades"] >= self.min_trades and st["wilson_high"] < self.floor:
                reason = (f"auto: {st['trades']} trades, win rate {st['win_rate']:.0%} "
                          f"(Wilson upper {st['wilson_high']:.0%}) < floor {self.floor:.0%}")
                newly.update(self.disable(sym, reason))
        return newly


# ----------------------------------------------------------------- CLI
def _format_table(by_symbol: dict[str, dict], overall: dict) -> str:
    header = (f"{'SYMBOL':<8}{'N':>4}{'WIN%':>7}{'WILSON 95% CI':>18}"
              f"{'TOT P&L':>11}{'AVG P&L':>10}{'AVG RET%':>10}")
    lines = [header, "-" * len(header)]
    for sym, st in by_symbol.items():
        ci = f"[{st['wilson_low']:.2f}, {st['wilson_high']:.2f}]"
        lines.append(f"{sym:<8}{st['trades']:>4}{st['win_rate'] * 100:>6.0f}%"
                     f"{ci:>18}{st['total_pnl']:>11.2f}{st['avg_pnl']:>10.2f}"
                     f"{st['avg_return_pct']:>10.2f}")
    ci = f"[{overall['wilson_low']:.2f}, {overall['wilson_high']:.2f}]"
    lines.append("-" * len(header))
    lines.append(f"{'ALL':<8}{overall['trades']:>4}{overall['win_rate'] * 100:>6.0f}%"
                 f"{ci:>18}{overall['total_pnl']:>11.2f}{overall['avg_pnl']:>10.2f}"
                 f"{overall['avg_return_pct']:>10.2f}")
    return "\n".join(lines)


def _format_priors(comparison: dict[str, dict]) -> str:
    if not comparison:
        return "(no symbols map to a calibrated prior)"
    lines = [f"{'SYMBOL':<8}{'REAL%':>7}{'PRIOR%':>8}{'BELOW PRIOR':>13}{'  NOTE'}"]
    for sym, c in comparison.items():
        flag = "yes" if c["below_prior"] else "no"
        note = ""
        if c["below_prior_ci"]:
            note = "  (realised CI lower < prior — meaningful shortfall)"
        lines.append(f"{sym:<8}{c['realized_win_rate'] * 100:>6.0f}%"
                     f"{c['prior_p'] * 100:>7.0f}%{flag:>13}{note}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="python -m agent.performance",
        description="Closed-trade performance + circuit breaker from the agent journal.")
    ap.add_argument("--state-dir", default=None,
                    help="State dir holding journal.jsonl / disabled.json (default: agent/state)")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    ap.add_argument("--evaluate", action="store_true",
                    help="Run the circuit breaker (auto-disable underperformers).")
    ap.add_argument("--min-trades", type=int, default=8,
                    help="Closed trades required before the breaker can fire (default 8).")
    ap.add_argument("--floor", type=float, default=0.5,
                    help="Win-rate floor for the breaker (default 0.5).")
    args = ap.parse_args(argv)

    memory = Memory(state_dir=args.state_dir) if args.state_dir else Memory()
    tracker = PerformanceTracker(memory=memory)
    breaker = CircuitBreaker(state_dir=memory.dir, min_trades=args.min_trades,
                             floor=args.floor)

    newly: dict[str, dict] = {}
    if args.evaluate:
        newly = breaker.evaluate(tracker)

    summary = tracker.summary()
    if args.json:
        print(json.dumps({
            "overall": summary["overall"],
            "by_symbol": summary["by_symbol"],
            "prior_comparison": summary["prior_comparison"],
            "newly_disabled": newly,
            "disabled": breaker.disabled(),
        }, indent=2, sort_keys=True))
        return 0

    print("PER-SYMBOL CLOSED-TRADE PERFORMANCE")
    print(_format_table(summary["by_symbol"], summary["overall"]))
    print()
    print("REALISED vs CALIBRATED PRIOR")
    print(_format_priors(summary["prior_comparison"]))
    print()
    if newly:
        print("NEWLY DISABLED THIS PASS:")
        for k, v in newly.items():
            print(f"  {k}: {v['reason']}")
    print("CURRENTLY DISABLED:")
    disabled = breaker.disabled()
    if disabled:
        for k, v in sorted(disabled.items()):
            print(f"  {k}: {v.get('reason', '')}")
    else:
        print("  (none)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
