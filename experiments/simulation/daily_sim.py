"""Daily forward simulation of the news-cycle trade engine — event-time fills.

Each weekday-morning run (GitHub Actions cron, also runnable locally):

  1. RESOLVE open event positions and any legacy close→open position.
  2. SCAN the last 24h of Truth Social posts; classify each (OpenAI if
     OPENAI_API_KEY is set, else Claude if ANTHROPIC_API_KEY, else keyword).
  3. FILL each market-relevant post at event time, reconstructed from
     1-minute bars (see intraday.py): enter at the first bar after
     post + 5 min (pre/post-market included), exit on trailing-stop decay or
     the calibrated hard boundary (next cash open / session close). Posts
     whose venue was closed until the move was priced are marked MISSED.
     One position at a time; bankroll compounds per settled event.
  4. REPORT: reports/YYYY-MM-DD.md + ledger.csv + state.json.

Simulation only — no orders are placed anywhere. Starting bankroll $100,
profits reinvested, no leverage. At a bankroll <= $1 the sim HALTS (BUSTED).

Usage:
    python daily_sim.py            # normal daily step
    python daily_sim.py --dry-run  # no state/report writes, prints to stdout
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # experiments/ -> import the engine
sys.path.insert(0, HERE)
import news_trade_engine as nte  # noqa: E402
import intraday  # noqa: E402

STATE_PATH = os.path.join(HERE, "state.json")
LEDGER_PATH = os.path.join(HERE, "ledger.csv")
REPORTS_DIR = os.path.join(HERE, "reports")

POSTS_SOURCES = [
    # CNN mirror, refreshed ~every 5 minutes (preferred going forward)
    "https://ix.cnn.io/data/truth-social/truth_archive.json",
    # GitHub archive (historical / fallback)
    "https://raw.githubusercontent.com/stiles/trump-truth-social-archive/main/data/truth_archive.csv",
]
BUST_FLOOR = 1.0      # dollars — at/below this the sim halts
MAX_PROCESSED_IDS = 5000

DEFAULT_STATE = {"bankroll": 100.0, "start_bankroll": 100.0, "busted": False,
                 "pending_plan": None,        # legacy close->open position
                 "open_events": [],           # event-time positions awaiting data
                 "processed_ids": [],
                 "last_run": None, "days": 0, "wins": 0, "trades": 0}


# ------------------------------------------------------------------ helpers

def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def load_state() -> dict:
    state = dict(DEFAULT_STATE)
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            state.update(json.load(f))
    return state


def save_state(state: dict) -> None:
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def fetch_posts_since(since: dt.datetime) -> list[dict]:
    """Posts (id, ts, text) newer than `since`, from the first source that works."""
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
                if not text:
                    continue
                pid = str(r.get("id") or hashlib.sha1(
                    f"{ts.isoformat()}|{text[:80]}".encode()).hexdigest()[:16])
                out.append({"id": pid, "ts": ts.isoformat(), "text": text})
            print(f"[posts] {url.split('/')[2]}: {len(out)} posts since {since:%Y-%m-%d %H:%M}Z")
            return sorted(out, key=lambda p: p["ts"])
        except Exception as exc:
            print(f"[posts] {url.split('/')[2]} failed: {type(exc).__name__}: {exc}")
    return []


def choose_classifier():
    """Prefer whichever LLM key is configured; offline keyword model otherwise."""
    if os.environ.get("OPENAI_API_KEY"):
        return nte.classify_openai, f"openai ({nte.OPENAI_MODEL})"
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return nte.classify_llm, "llm (claude)"
    return nte.classify, "keyword"


# ------------------------------------------------- legacy close->open settle

def fetch_prices(tickers: list[str]):
    import yfinance as yf

    return yf.download(tickers, period="10d", interval="1d",
                       auto_adjust=True, progress=False, group_by="ticker")


def px(prices, ticker: str, field: str, date_str: str):
    import pandas as pd

    try:
        df = prices[ticker] if hasattr(prices.columns, "levels") else prices
        row = df.loc[pd.Timestamp(date_str)]
        v = float(row[field])
        return v if v > 0 else None
    except Exception:
        return None


def settle(state: dict, prices, today: str) -> dict | None:
    """Legacy: realize P&L on the old-style pending plan (close -> open)."""
    plan = state.get("pending_plan")
    if not plan:
        return None
    entry_day = plan["decided_on"]
    legs_out, port_ret = [], 0.0
    for leg in plan["legs"]:
        e = px(prices, leg["instrument"], "Close", entry_day)
        x = px(prices, leg["instrument"], "Open", today)
        if e is None or x is None:
            print(f"[settle] prices missing for {entry_day}->{today}; plan stays pending")
            return None
        d = 1 if leg["side"] == "BUY" else -1
        r = d * (x / e - 1)
        legs_out.append({**leg, "entry": round(e, 4), "exit": round(x, 4),
                         "ret_pct": round(r * 100, 3),
                         "pnl": round(leg["notional"] * r, 4)})
        port_ret += leg["weight"] * r
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


# ------------------------------------------------------ event-time pipeline

def build_event(post: dict, classify_fn) -> dict | None:
    """Classify one post; return an event spec if it maps to a calibrated plan."""
    res = nte.plan_trade(post["text"], base_qty=100, classify_fn=classify_fn)
    if not res["plans"]:
        return None
    total_edge = sum(pl["edge_score"] for pl in res["plans"]) or 1.0
    legs = [{
        "instrument": pl["instrument"], "side": pl["side"],
        "weight": round(pl["edge_score"] / total_edge, 4),
        "probability": pl["probability"], "expected_move_pct": pl["expected_move_pct"],
        "trail_pct": intraday.trail_pct_for(pl["expected_move_pct"]),
    } for pl in res["plans"]]
    return {"post_id": post["id"], "post_ts": post["ts"],
            "headline": post["text"][:200], "signal": res["signal"], "legs": legs}


def resolve_event(event: dict, bars: dict, now: dt.datetime | None = None) -> dict:
    """Run every leg through the minute bars. Returns status open|missed|closed."""
    import pandas as pd

    post_ts = pd.Timestamp(event["post_ts"])
    now = now or now_utc()
    stale = (now - post_ts.to_pydatetime()) > dt.timedelta(days=intraday.STALE_AFTER_DAYS)

    legs_out, any_open, any_closed = [], False, False
    for leg in event["legs"]:
        r = intraday.simulate_leg(bars.get(leg["instrument"]), post_ts, leg["side"],
                                  leg["trail_pct"], force_close=stale)
        if r["status"] == "open":
            any_open = True
            break
        if r["status"] == "closed":
            any_closed = True
            legs_out.append({**leg, **r, "ret_pct": round(r["ret"] * 100, 3)})
        else:  # missed — venue closed until the move was priced; capital idle
            legs_out.append({**leg, **r, "ret": 0.0, "ret_pct": 0.0})
    if any_open:
        return {"status": "open"}
    if not any_closed:
        return {"status": "missed", "legs": legs_out}
    port_ret = sum(l["weight"] * l["ret"] for l in legs_out)
    exit_ts = max((l["exit_ts"] for l in legs_out if l.get("exit_ts")), default=None)
    return {"status": "closed", "legs": legs_out, "portfolio_ret": port_ret,
            "exit_ts": exit_ts}


def apply_settlement(state: dict, event: dict, res: dict) -> dict:
    old = state["bankroll"]
    state["bankroll"] = round(old * (1 + res["portfolio_ret"]), 4)
    state["trades"] += 1
    if res["portfolio_ret"] > 0:
        state["wins"] += 1
    return {"headline": event["headline"], "signal": event["signal"],
            "post_ts": event["post_ts"], "exit_ts": res.get("exit_ts"),
            "legs": res["legs"],
            "portfolio_ret_pct": round(res["portfolio_ret"] * 100, 3),
            "bankroll_before": old, "bankroll_after": state["bankroll"]}


def scan_and_trade(state: dict, posts: list[dict], bars: dict, classify_fn,
                   now: dt.datetime | None = None) -> dict:
    """Resolve carried-over events, then walk new posts chronologically with a
    one-position-at-a-time gate. Returns settled/missed/skipped for the report."""
    import pandas as pd

    out = {"settled": [], "missed": [], "skipped": 0, "still_open": 0}
    now = now or now_utc()

    # 1) carried-over events first (chronological)
    remaining = []
    blocked_until = None      # exit ts of the latest position; None+open => block all
    has_open = False
    for ev in sorted(state.get("open_events", []), key=lambda e: e["post_ts"]):
        res = resolve_event(ev, bars, now)
        if res["status"] == "closed":
            out["settled"].append(apply_settlement(state, ev, res))
            blocked_until = pd.Timestamp(res["exit_ts"]) if res.get("exit_ts") else blocked_until
            state["processed_ids"].append(ev["post_id"])
        elif res["status"] == "missed":
            out["missed"].append({"headline": ev["headline"], "legs": res["legs"]})
            state["processed_ids"].append(ev["post_id"])
        else:
            remaining.append(ev)
            has_open = True
    state["open_events"] = remaining

    # 2) new posts
    if not state["busted"]:
        seen = set(state["processed_ids"]) | {e["post_id"] for e in remaining}
        for post in posts:
            if post["id"] in seen:
                continue
            if has_open:
                # an unresolved position blocks newer entries; leave the post
                # unprocessed so the next run reconsiders it
                continue
            ev = build_event(post, classify_fn)
            if ev is None:
                state["processed_ids"].append(post["id"])
                continue
            entry_t = pd.Timestamp(post["ts"]) + pd.Timedelta(minutes=intraday.DETECTION_LATENCY_MIN)
            if blocked_until is not None and entry_t < blocked_until:
                out["skipped"] += 1
                state["processed_ids"].append(post["id"])
                continue
            res = resolve_event(ev, bars, now)
            if res["status"] == "closed":
                out["settled"].append(apply_settlement(state, ev, res))
                blocked_until = pd.Timestamp(res["exit_ts"]) if res.get("exit_ts") else blocked_until
                state["processed_ids"].append(post["id"])
            elif res["status"] == "missed":
                out["missed"].append({"headline": ev["headline"], "legs": res["legs"]})
                state["processed_ids"].append(post["id"])
            else:
                state["open_events"].append(ev)
                has_open = True
            if state["bankroll"] <= BUST_FLOOR:
                state["busted"] = True
                break

    out["still_open"] = len(state["open_events"])
    state["processed_ids"] = state["processed_ids"][-MAX_PROCESSED_IDS:]
    return out


# ------------------------------------------------------------------ report

def write_report(today: str, state: dict, legacy: dict | None, activity: dict,
                 n_posts: int, clf_name: str) -> str:
    ret_total = (state["bankroll"] / state["start_bankroll"] - 1) * 100
    lines = [f"# News-Trade Sim — {today}", ""]
    if state["busted"]:
        lines += ["## 🚨 FUND BUSTED — simulation halted",
                  f"Bankroll ${state['bankroll']:.2f} is at/below the ${BUST_FLOOR:.0f} floor. "
                  "No new positions will be taken.", ""]
    lines += [f"**Bankroll: ${state['bankroll']:.2f}**  "
              f"(started ${state['start_bankroll']:.2f}, total return {ret_total:+.2f}%)",
              f"Events settled: {state['trades']} | wins: {state['wins']} "
              f"({(state['wins'] / state['trades'] * 100) if state['trades'] else 0:.0f}%) | "
              f"classifier: {clf_name} | posts scanned (24h): {n_posts}", "",
              "_Fill model: event-time — entry at the first minute bar ≥ post+5min "
              "(pre/post-market included); exit on trailing-stop decay or the "
              "calibrated boundary (next cash open / session close)._", ""]

    if legacy:
        lines += [f"## Settled legacy overnight trade ({legacy['entry_day']} close → {legacy['exit_day']} open)",
                  f"**Portfolio: {legacy['portfolio_ret_pct']:+.3f}%  "
                  f"(${legacy['bankroll_before']:.2f} → ${legacy['bankroll_after']:.2f})**", ""]

    if activity["settled"]:
        for ev in activity["settled"]:
            lines += [f"## Event trade — “{ev['headline'][:140]}…”",
                      f"Signal `{ev['signal']['topic']}` valence {ev['signal']['valence']:+.2f} | "
                      f"posted {ev['post_ts'][:16]}Z | closed {str(ev['exit_ts'])[:16]}", "",
                      "| leg | side | entry (t) | exit (t) | exit reason | return | weight |",
                      "|---|---|---|---|---|---:|---:|"]
            for l in ev["legs"]:
                if l.get("status") == "closed":
                    lines.append(f"| {l['instrument']} | {l['side']} | {l['entry']:.2f} "
                                 f"({str(l['entry_ts'])[11:16]}) | {l['exit']:.2f} "
                                 f"({str(l['exit_ts'])[11:16]}) | {l['reason']} | "
                                 f"{l['ret_pct']:+.2f}% | {l['weight'] * 100:.0f}% |")
                else:
                    lines.append(f"| {l['instrument']} | {l['side']} | — | — | missed (venue closed) | 0.00% | {l['weight'] * 100:.0f}% |")
            lines += ["", f"**Portfolio: {ev['portfolio_ret_pct']:+.3f}%  "
                          f"(${ev['bankroll_before']:.2f} → ${ev['bankroll_after']:.2f})**", ""]
    elif not legacy:
        lines += ["## No trades settled", ""]

    if activity["missed"]:
        lines += ["## Missed events (venue closed until the move was priced)"]
        lines += [f"- “{m['headline'][:120]}…”" for m in activity["missed"]] + [""]
    if activity["still_open"]:
        lines += [f"## Open positions: {activity['still_open']} (resolve next run)", ""]
    if activity["skipped"]:
        lines += [f"_Skipped {activity['skipped']} signal post(s) while a position was open._", ""]
    if not (activity["settled"] or activity["missed"] or activity["still_open"]):
        lines += ["_No market-relevant news in the last 24h — staying in cash._", ""]

    lines += ["---", "_Simulation only; no real orders. Calibration & caveats: experiments/README.md_"]
    return "\n".join(lines)


def append_ledger(today: str, state: dict, activity: dict) -> None:
    new = not os.path.exists(LEDGER_PATH)
    with open(LEDGER_PATH, "a") as f:
        if new:
            f.write("date,bankroll,event_ret_pct,post_ts,exit_ts,n_legs,headline\n")
        if activity["settled"]:
            for ev in activity["settled"]:
                f.write(f"{today},{ev['bankroll_after']:.4f},{ev['portfolio_ret_pct']:+.3f},"
                        f"{ev['post_ts'][:16]},{str(ev['exit_ts'])[:16]},{len(ev['legs'])},"
                        f"\"{ev['headline'][:80]}\"\n")
        else:
            f.write(f"{today},{state['bankroll']:.4f},,,,0,\n")


# ------------------------------------------------------------------ main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="No writes; print the report")
    args = ap.parse_args(argv)

    state = load_state()
    today = now_utc().strftime("%Y-%m-%d")
    classify_fn, clf_name = choose_classifier()

    # legacy close->open position from the previous fill model (transition)
    legacy = None
    legacy_tickers = sorted({l["instrument"] for l in (state.get("pending_plan") or {}).get("legs", [])})
    if legacy_tickers:
        legacy = settle(state, fetch_prices(legacy_tickers), today)

    if state["bankroll"] <= BUST_FLOOR:
        state["busted"] = True

    posts = [] if state["busted"] else fetch_posts_since(now_utc() - dt.timedelta(hours=24))

    # minute bars for every instrument any event (carried or new) could touch
    tickers = {l["instrument"] for ev in state.get("open_events", []) for l in ev["legs"]}
    if posts:
        tickers |= {i for topic in nte.DEFAULT_BASKET.values() for basket in topic.values() for i in basket}
    bars = intraday.fetch_minute_bars(sorted(tickers)) if tickers else {}

    activity = scan_and_trade(state, posts, bars, classify_fn)
    if state["bankroll"] <= BUST_FLOOR:
        state["busted"] = True

    state["last_run"] = now_utc().isoformat(timespec="seconds")
    state["days"] += 1
    report = write_report(today, state, legacy, activity, len(posts), clf_name)

    if args.dry_run:
        print(report)
        return 0

    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(os.path.join(REPORTS_DIR, f"{today}.md"), "w") as f:
        f.write(report + "\n")
    append_ledger(today, state, activity)
    save_state(state)
    print(report)
    if state["busted"]:
        with open(os.path.join(HERE, "BUSTED"), "w") as f:
            f.write(f"Bankroll ${state['bankroll']:.2f} on {today}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
