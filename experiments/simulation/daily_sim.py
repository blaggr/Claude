"""Daily forward simulation of the news-cycle trade engine.

Each weekday-morning run (designed for GitHub Actions cron, also runnable
locally):

  1. SETTLE yesterday's plan: entry = yesterday's close, exit = today's open
     (the calibrated overnight window). Compound the bankroll.
  2. SIGNAL: fetch Trump's Truth Social posts from the last 24h, classify each
     (Claude classifier if ANTHROPIC_API_KEY is set, else keyword), and adopt
     the strongest-edge plan as today's pending position.
  3. REPORT: write reports/YYYY-MM-DD.md + ledger.csv + state.json.

Simulation only — no orders are placed anywhere. Starting bankroll $100,
profits reinvested, no leverage (leg notionals sum to the bankroll). If the
bankroll falls to <= $1 the sim HALTS and flags BUSTED (the workflow turns
that into an alert issue).

Usage:
    python daily_sim.py            # normal daily step
    python daily_sim.py --dry-run  # no state/report writes, prints to stdout
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # experiments/ -> import the engine
import news_trade_engine as nte  # noqa: E402

STATE_PATH = os.path.join(HERE, "state.json")
LEDGER_PATH = os.path.join(HERE, "ledger.csv")
REPORTS_DIR = os.path.join(HERE, "reports")

POSTS_SOURCES = [
    # CNN mirror, refreshed ~every 5 minutes (preferred going forward)
    "https://ix.cnn.io/data/truth-social/truth_archive.json",
    # GitHub archive (historical / fallback)
    "https://raw.githubusercontent.com/stiles/trump-truth-social-archive/main/data/truth_archive.csv",
]
BUST_FLOOR = 1.0  # dollars — at/below this the sim halts


# ------------------------------------------------------------------ helpers

def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"bankroll": 100.0, "start_bankroll": 100.0, "busted": False,
            "pending_plan": None, "last_run": None, "days": 0, "wins": 0, "trades": 0}


def save_state(state: dict) -> None:
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def fetch_posts_since(since: dt.datetime) -> list[dict]:
    """Posts (ts, text) newer than `since`, from the first source that works."""
    import html as html_mod
    import re
    import pandas as pd

    tag = re.compile(r"<[^>]+>")
    for url in POSTS_SOURCES:
        try:
            raw = urllib.request.urlopen(url, timeout=60).read()
            if url.endswith(".json"):
                rows = json.loads(raw)
            else:
                rows = pd.read_csv(io.BytesIO(raw)).to_dict("records")
            out = []
            for r in rows:
                ts = pd.to_datetime(r.get("created_at"), utc=True, errors="coerce")
                if ts is pd.NaT or ts <= since:
                    continue
                text = html_mod.unescape(tag.sub(" ", str(r.get("content") or "")))
                text = re.sub(r"\s+", " ", text).strip()
                if text:
                    out.append({"ts": ts.isoformat(), "text": text})
            print(f"[posts] {url.split('/')[2]}: {len(out)} posts since {since:%Y-%m-%d %H:%M}Z")
            return sorted(out, key=lambda p: p["ts"])
        except Exception as exc:
            print(f"[posts] {url.split('/')[2]} failed: {type(exc).__name__}: {exc}")
    return []


def fetch_prices(tickers: list[str]) -> "object":
    """Last ~10 daily OHLC rows per ticker via yfinance (works on GH runners)."""
    import yfinance as yf

    return yf.download(tickers, period="10d", interval="1d",
                       auto_adjust=True, progress=False, group_by="ticker")


def px(prices, ticker: str, field: str, date_str: str):
    """Close/Open for ticker on date (None if absent)."""
    import pandas as pd

    try:
        df = prices[ticker] if hasattr(prices.columns, "levels") else prices
        row = df.loc[pd.Timestamp(date_str)]
        v = float(row[field])
        return v if v > 0 else None
    except Exception:
        return None


def choose_classifier():
    """Prefer whichever LLM key is configured; offline keyword model otherwise."""
    if os.environ.get("OPENAI_API_KEY"):
        return nte.classify_openai, f"openai ({nte.OPENAI_MODEL})"
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return nte.classify_llm, "llm (claude)"
    return nte.classify, "keyword"


# ------------------------------------------------------------------ steps

def settle(state: dict, prices, today: str) -> dict | None:
    """Realize P&L on the pending plan: close(decided day) -> open(today)."""
    plan = state.get("pending_plan")
    if not plan:
        return None
    entry_day = plan["decided_on"]
    legs_out, port_ret, priced = [], 0.0, True
    for leg in plan["legs"]:
        e = px(prices, leg["instrument"], "Close", entry_day)
        x = px(prices, leg["instrument"], "Open", today)
        if e is None or x is None:
            priced = False
            break
        d = 1 if leg["side"] == "BUY" else -1
        r = d * (x / e - 1)
        legs_out.append({**leg, "entry": round(e, 4), "exit": round(x, 4),
                         "ret_pct": round(r * 100, 3),
                         "pnl": round(leg["notional"] * r, 4)})
        port_ret += leg["weight"] * r
    if not priced:
        # market closed yesterday/today (holiday) — keep the plan pending
        print(f"[settle] prices missing for {entry_day}->{today}; plan stays pending")
        return None
    old = state["bankroll"]
    state["bankroll"] = round(old * (1 + port_ret), 4)
    state["trades"] += 1
    if port_ret > 0:
        state["wins"] += 1
    state["pending_plan"] = None
    return {"entry_day": entry_day, "exit_day": today, "legs": legs_out,
            "portfolio_ret_pct": round(port_ret * 100, 3),
            "bankroll_before": old, "bankroll_after": state["bankroll"],
            "headline": plan.get("headline", "")}


def build_plan(state: dict, posts: list[dict], today: str, classify_fn) -> dict | None:
    """Classify each post; adopt the highest-edge plan as today's position."""
    best, best_edge, best_post = None, 0.0, None
    for p in posts:
        res = nte.plan_trade(p["text"], base_qty=100, classify_fn=classify_fn)
        if res["plans"] and res["plans"][0]["edge_score"] > best_edge:
            best, best_edge, best_post = res, res["plans"][0]["edge_score"], p
    if best is None:
        return None
    total_edge = sum(pl["edge_score"] for pl in best["plans"]) or 1.0
    legs = [{
        "instrument": pl["instrument"], "side": pl["side"],
        "weight": round(pl["edge_score"] / total_edge, 4),
        "notional": round(state["bankroll"] * pl["edge_score"] / total_edge, 2),
        "probability": pl["probability"], "expected_move_pct": pl["expected_move_pct"],
    } for pl in best["plans"]]
    return {"decided_on": today, "signal": best["signal"], "legs": legs,
            "headline": best_post["text"][:200]}


def write_report(today: str, state: dict, settled: dict | None,
                 plan: dict | None, n_posts: int, clf_name: str) -> str:
    ret_total = (state["bankroll"] / state["start_bankroll"] - 1) * 100
    lines = [f"# News-Trade Sim — {today}", ""]
    if state["busted"]:
        lines += ["## 🚨 FUND BUSTED — simulation halted",
                  f"Bankroll ${state['bankroll']:.2f} is at/below the ${BUST_FLOOR:.0f} floor. "
                  "No new positions will be taken.", ""]
    lines += [f"**Bankroll: ${state['bankroll']:.2f}**  "
              f"(started $%.2f, total return %+.2f%%)" % (state["start_bankroll"], ret_total),
              f"Trades settled: {state['trades']} | wins: {state['wins']} "
              f"({(state['wins'] / state['trades'] * 100) if state['trades'] else 0:.0f}%) | "
              f"classifier: {clf_name} | posts scanned (24h): {n_posts}", ""]
    if settled:
        lines += [f"## Settled overnight trade ({settled['entry_day']} close → {settled['exit_day']} open)",
                  f"Triggered by: “{settled['headline'][:160]}…”" if settled["headline"] else "",
                  "", "| leg | side | entry | exit | return | P&L |", "|---|---|---:|---:|---:|---:|"]
        for l in settled["legs"]:
            lines.append(f"| {l['instrument']} | {l['side']} | {l['entry']:.2f} | "
                         f"{l['exit']:.2f} | {l['ret_pct']:+.2f}% | ${l['pnl']:+.2f} |")
        lines += ["", f"**Portfolio: {settled['portfolio_ret_pct']:+.3f}%  "
                      f"(${settled['bankroll_before']:.2f} → ${settled['bankroll_after']:.2f})**", ""]
    else:
        lines += ["## No trade settled", "_No pending position, or markets were closed._", ""]
    if plan:
        s = plan["signal"]
        lines += [f"## Today's position (enter at today's close, exit tomorrow's open)",
                  f"Signal: `{s['topic']}` valence {s['valence']:+.2f} — “{plan['headline'][:160]}…”", "",
                  "| leg | side | weight | notional | P(move) | exp move |", "|---|---|---:|---:|---:|---:|"]
        for l in plan["legs"]:
            lines.append(f"| {l['instrument']} | {l['side']} | {l['weight'] * 100:.0f}% | "
                         f"${l['notional']:.2f} | {l['probability']:.0%} | {l['expected_move_pct']:+.2f}% |")
    else:
        lines += ["## Today's position", "_No market-relevant news in the last 24h — staying in cash._"]
    lines += ["", "---", "_Simulation only; no real orders. Calibration & caveats: experiments/README.md_"]
    return "\n".join(lines)


def append_ledger(today: str, state: dict, settled: dict | None) -> None:
    new = not os.path.exists(LEDGER_PATH)
    with open(LEDGER_PATH, "a") as f:
        if new:
            f.write("date,bankroll,trade_ret_pct,entry_day,n_legs,headline\n")
        if settled:
            f.write(f"{today},{state['bankroll']:.4f},{settled['portfolio_ret_pct']:+.3f},"
                    f"{settled['entry_day']},{len(settled['legs'])},"
                    f"\"{settled['headline'][:80]}\"\n")
        else:
            f.write(f"{today},{state['bankroll']:.4f},,,0,\n")


# ------------------------------------------------------------------ main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="No writes; print the report")
    args = ap.parse_args(argv)

    state = load_state()
    today = now_utc().strftime("%Y-%m-%d")
    classify_fn, clf_name = choose_classifier()

    # 1. settle yesterday's plan
    settled = None
    tickers = sorted({l["instrument"] for l in (state.get("pending_plan") or {}).get("legs", [])})
    if tickers:
        settled = settle(state, fetch_prices(tickers), today)

    # 2. bust check
    if state["bankroll"] <= BUST_FLOOR:
        state["busted"] = True

    # 3. new plan from the last 24h of posts (skip if busted)
    posts, plan = [], None
    if not state["busted"]:
        posts = fetch_posts_since(now_utc() - dt.timedelta(hours=24))
        plan = build_plan(state, posts, today, classify_fn)
        if plan and state.get("pending_plan") is None:
            state["pending_plan"] = plan
        elif plan:
            plan = None  # still holding an unsettled position (holiday) — don't stack

    state["last_run"] = now_utc().isoformat(timespec="seconds")
    state["days"] += 1
    report = write_report(today, state, settled, plan, len(posts), clf_name)

    if args.dry_run:
        print(report)
        return 0

    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(os.path.join(REPORTS_DIR, f"{today}.md"), "w") as f:
        f.write(report + "\n")
    append_ledger(today, state, settled)
    save_state(state)
    print(report)
    # signal bust to the workflow via a marker file
    if state["busted"]:
        with open(os.path.join(HERE, "BUSTED"), "w") as f:
            f.write(f"Bankroll ${state['bankroll']:.2f} on {today}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
