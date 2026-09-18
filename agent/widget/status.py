#!/usr/bin/env python3
"""Status reader for the menu-bar widget (and any other front-end).

Assembles a compact view of the live agent from local state + the broker:
  * account equity / cash / mode (Alpaca paper when keys are set)
  * today's P&L % (from Alpaca's last_equity, when available)
  * open positions (with their entry side/price)
  * whether the driver is running, from a heartbeat file it touches each poll
  * the last trade/exit recorded in the journal
  * whether the KILL switch is active

`--swiftbar` prints SwiftBar/xbar menu-bar format; the default prints JSON so
any other widget (Übersicht, a Stream Deck, etc.) can consume it. Pure read-only
— it never trades.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # agent/widget -> agent -> repo
if REPO not in sys.path:
    sys.path.insert(0, REPO)

STATE = os.path.join(REPO, "agent", "state")
LOG = os.path.join(STATE, "live_agent.log")
HEARTBEAT = os.path.join(STATE, "heartbeat")
KILL = os.path.join(REPO, "experiments", "live", "KILL")
RUNNER = os.path.join(REPO, "agent", "deploy", "run_tmux.sh")
DASHBOARD = "https://app.alpaca.markets/paper/dashboard/overview"


def _age_seconds(path: str) -> float | None:
    try:
        return dt.datetime.now().timestamp() - os.path.getmtime(path)
    except OSError:
        return None


def gather(state_dir: str = STATE, broker=None, interval_hint: int = 60) -> dict:
    """Read everything the widget needs. ``broker``/``state_dir`` are injectable
    for tests; by default the real broker + repo state dir are used."""
    out = {"mode": "?", "equity": None, "cash": None, "day_pl_pct": None,
           "positions": [], "running": False, "heartbeat_age": None,
           "killed": os.path.exists(KILL), "last_action": None, "error": None}

    try:
        if broker is None:
            from agent.broker import get_broker
            with contextlib.redirect_stdout(io.StringIO()):   # keep stray prints out of output
                broker = get_broker()
        out["mode"] = getattr(broker, "mode", "PAPER")
        acct = broker.account()
        out["equity"] = acct.get("equity")
        out["cash"] = acct.get("cash")
        # today's P&L from Alpaca's prior-close equity, if this is the Alpaca broker
        try:
            raw = broker.api.account()
            le = float(raw.get("last_equity") or 0)
            if le:
                out["day_pl_pct"] = round((float(raw["equity"]) - le) / le * 100, 2)
        except Exception:
            pass
        for sym, p in broker.positions().items():
            out["positions"].append({"symbol": sym, "qty": p.get("qty"), "avg": p.get("avg")})
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"

    hb = os.path.join(state_dir, "heartbeat")
    out["heartbeat_age"] = _age_seconds(hb)
    if out["heartbeat_age"] is not None and out["heartbeat_age"] < max(180, interval_hint * 3):
        out["running"] = True

    try:
        from agent.memory import Memory
        for r in reversed(Memory(state_dir=state_dir).journal(limit=300)):
            if r.get("kind") in ("EXIT", "order", "close_position") and r.get("status") != "rejected":
                out["last_action"] = r
                break
    except Exception:
        pass
    return out


def _fmt_money(v) -> str:
    return f"${v:,.0f}" if v is not None else "—"


def swiftbar(s: dict) -> str:
    """Render the status dict as SwiftBar/xbar menu-bar text."""
    # ---- menu-bar title (one line) ----
    if s["killed"]:
        title = "🛑 agent HALTED"
    elif not s["running"]:
        title = "🟠 agent off"
    else:
        pl = s["day_pl_pct"]
        tag = ""
        if pl is not None:
            tag = f" {'▲' if pl >= 0 else '▼'}{abs(pl):.2f}%"
        title = f"📈 {_fmt_money(s['equity'])}{tag}"
    lines = [title, "---"]

    # ---- detail ----
    lines.append(f"Mode: {s['mode']}")
    if s["equity"] is not None:
        lines.append(f"Equity: ${s['equity']:,.2f}  ·  cash ${s['cash']:,.2f} | font=Menlo")
    if s["day_pl_pct"] is not None:
        lines.append(f"Today: {s['day_pl_pct']:+.2f}% | color={'green' if s['day_pl_pct'] >= 0 else 'red'}")
    if s["killed"]:
        lines.append("KILL switch active — flat & halted | color=red")
    elif s["running"]:
        lines.append(f"Running ✓  (last poll {int(s['heartbeat_age'])}s ago) | color=green")
    else:
        age = s["heartbeat_age"]
        lines.append(("Not running" + (f"  (last poll {int(age)}s ago)" if age is not None else "")) +
                     " | color=orange")

    lines.append("---")
    if s["positions"]:
        lines.append(f"Open positions: {len(s['positions'])}")
        for p in s["positions"]:
            avg = p.get("avg") or 0.0
            lines.append(f"{p['symbol']} {int(p['qty']):+d} @ {avg:.2f} | font=Menlo")
    else:
        lines.append("Flat — no open positions")
    la = s["last_action"]
    if la:
        if la.get("kind") == "EXIT":
            lines.append(f"Last: exit {la.get('symbol')} pnl {la.get('pnl')} ({la.get('reason')}) | font=Menlo")
        else:
            lines.append(f"Last: {la.get('side')} {la.get('qty')} {la.get('symbol')} @ {la.get('price')} | font=Menlo")
    if s["error"]:
        lines.append(f"⚠️ {s['error']} | color=red")

    # ---- actions ----
    lines.append("---")
    lines.append(f"Open Alpaca paper dashboard | href={DASHBOARD}")
    lines.append(f"View log | bash=open param1={LOG} terminal=false")
    lines.append(f"Stop agent | bash=\"{RUNNER}\" param1=stop terminal=false refresh=true")
    lines.append(f"🛑 KILL — flatten & halt | bash=\"{RUNNER}\" param1=kill terminal=false refresh=true")
    lines.append("Refresh | refresh=true")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--swiftbar", action="store_true", help="Emit SwiftBar/xbar format")
    ap.add_argument("--interval", type=int, default=60, help="Poll interval hint (running threshold)")
    args = ap.parse_args(argv)
    s = gather(interval_hint=args.interval)
    print(swiftbar(s) if args.swiftbar else json.dumps(s, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
