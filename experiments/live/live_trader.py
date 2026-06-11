"""Always-on news trader — Alpaca execution, paper by default.

This is the execution-grade version of the news strategy: an event-driven
worker that polls Truth Social every POLL_SECONDS, classifies new posts, and
places real orders at a connected brokerage (Alpaca paper by default; live
only behind the interlocks in risk.py).

    python live_trader.py            # paper trading (needs ALPACA_KEY_ID/SECRET)
    ALPACA_LIVE=1 python live_trader.py   # live — requires the ack file too

Strategy mechanics mirror the calibrated sim exactly:
  * entry ASAP after the post (market order in RTH; marketable DAY limit in
    extended hours 4:00–9:30 / 16:00–20:00 ET; overnight posts arm and enter
    at 4am; events whose boundary passes before a fill are skipped as missed)
  * exit on trailing-stop impulse decay (intraday.TrailingTracker) or the
    hard boundary anchored to post time (next cash open / session close)
  * one event at a time; idempotent client_order_ids; whole shares only

Safety posture (see risk.py): paper default, double interlock for live, KILL
file flattens and halts, daily loss limit auto-kills, per-event budget cap.
Without an LLM classifier key the worker runs in SHADOW mode (journals the
signals it would have traded, places no orders) — the keyword classifier is
too crude for real execution.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))                      # experiments/
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "simulation"))
import daily_sim as ds          # fetch_posts_since, build_event, choose_classifier  # noqa: E402
import intraday                  # TrailingTracker, boundary_after, NY               # noqa: E402
import risk                      # noqa: E402
from alpaca import Alpaca, AlpacaError  # noqa: E402

STATE_PATH = os.path.join(HERE, "live_state.json")
JOURNAL_PATH = os.path.join(HERE, "journal.jsonl")
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "30"))
ENTRY_FILL_TIMEOUT_S = 120
NY = intraday.NY


# ------------------------------------------------------------------ logging

def journal(kind: str, **payload) -> None:
    rec = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "kind": kind, **payload}
    print(f"[{rec['ts']}] {kind}: " + json.dumps(payload, default=str)[:400])
    with open(JOURNAL_PATH, "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def alert(msg: str) -> None:
    journal("ALERT", message=msg)
    url = os.environ.get("ALERT_WEBHOOK_URL")
    if url:
        try:
            import urllib.request
            body = json.dumps({"text": msg, "content": msg}).encode()
            urllib.request.urlopen(urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"}), timeout=15)
        except Exception as exc:
            print(f"[alert] webhook failed: {exc}")


# ------------------------------------------------------------------ state

def load_state() -> dict:
    st = {"processed_ids": [], "open_event": None, "day": None, "day_start_equity": None}
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            st.update(json.load(f))
    return st


def save_state(st: dict) -> None:
    with open(STATE_PATH, "w") as f:
        json.dump(st, f, indent=2, default=str)


# ------------------------------------------------------------------ session

def ny_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz=NY)


def tradable_session(broker: Alpaca, clock_cache: dict) -> str | None:
    """'rth', 'ext', or None (closed). Clock refreshed at most once a minute."""
    if time.time() - clock_cache.get("at", 0) > 60:
        try:
            clock_cache["clock"] = broker.clock()
            clock_cache["at"] = time.time()
        except AlpacaError as exc:
            journal("WARN", message=f"clock fetch failed: {exc}")
    c = clock_cache.get("clock") or {}
    if c.get("is_open"):
        return "rth"
    t = ny_now()
    if t.weekday() < 5:
        hm = t.hour * 60 + t.minute
        if 4 * 60 <= hm < 9 * 60 + 30 or 16 * 60 <= hm < 20 * 60:
            return "ext"
    return None


# ------------------------------------------------------------------ entries

def try_enter(broker: Alpaca, st: dict, event: dict, session: str, shadow: bool) -> None:
    post_ts = pd.Timestamp(event["post_ts"])
    boundary = intraday.boundary_after(post_ts)
    if ny_now() >= boundary:
        journal("MISSED", headline=event["headline"][:120],
                note="boundary passed before a tradable session")
        st["processed_ids"].append(event["post_id"])
        st["open_event"] = None
        return

    if shadow:
        journal("SHADOW_SIGNAL", headline=event["headline"][:120],
                signal=event["signal"], note="no LLM classifier key — not trading")
        st["processed_ids"].append(event["post_id"])
        st["open_event"] = None
        return

    equity = broker.equity()
    prices = {}
    for leg in event["legs"]:
        try:
            prices[leg["instrument"]] = broker.last_price(leg["instrument"])
        except AlpacaError as exc:
            journal("WARN", message=f"no quote for {leg['instrument']}: {exc}")
    sized = risk.size_legs(event["legs"], prices, equity)
    if not sized:
        journal("SKIP", headline=event["headline"][:120],
                note=f"no leg sizes >= 1 share at equity ${equity:.2f}")
        st["processed_ids"].append(event["post_id"])
        st["open_event"] = None
        return

    filled_legs = []
    for leg in sized:
        side = "buy" if leg["side"] == "BUY" else "sell"
        coid = f"{event['post_id'][:12]}-{leg['instrument']}-in"
        limit = risk.marketable_limit(leg["ref_price"], side) if session == "ext" else None
        try:
            o = broker.submit_order(leg["instrument"], leg["qty"], side,
                                    extended_hours=(session == "ext"),
                                    limit_price=limit, client_order_id=coid)
        except AlpacaError as exc:
            if "client_order_id" in str(exc).lower() or "duplicate" in str(exc).lower():
                journal("WARN", message=f"duplicate order suppressed: {coid}")
                continue
            journal("WARN", message=f"entry rejected {leg['instrument']}: {exc}")
            continue
        fill = broker.await_fill(o["id"], ENTRY_FILL_TIMEOUT_S)
        if not fill:
            journal("WARN", message=f"entry unfilled, cancelled: {leg['instrument']}")
            continue
        entry_px = float(fill["filled_avg_price"])
        filled_legs.append({**leg, "entry": entry_px, "best": entry_px,
                            "qty": int(float(fill["filled_qty"])), "status": "open"})
        journal("ENTRY", instrument=leg["instrument"], side=leg["side"],
                qty=leg["qty"], price=entry_px, headline=event["headline"][:100])

    st["processed_ids"].append(event["post_id"])
    if filled_legs:
        st["open_event"] = {"post_id": event["post_id"], "post_ts": event["post_ts"],
                            "headline": event["headline"], "signal": event["signal"],
                            "boundary": str(boundary), "legs": filled_legs}
    else:
        st["open_event"] = None


# ------------------------------------------------------------------ exits

def exit_leg(broker: Alpaca, ev: dict, leg: dict, session: str, reason: str) -> bool:
    side = "sell" if leg["side"] == "BUY" else "buy"
    # reconcile first: if the broker shows no position (e.g. an exit filled just
    # before a crash/restart), never submit another closing order blind
    held = {p["symbol"]: float(p["qty"]) for p in broker.positions()}
    if leg["instrument"] not in held or held[leg["instrument"]] == 0:
        leg.update(status="closed", exit=leg["entry"], reason="reconciled_flat", pnl=0.0)
        journal("WARN", message=f"{leg['instrument']} already flat at broker — marked reconciled")
        return True
    coid = f"{ev['post_id'][:10]}-{leg['instrument']}-out-{int(time.time())}"
    try:
        price = broker.last_price(leg["instrument"])
        if session == "rth":
            o = broker.submit_order(leg["instrument"], leg["qty"], side, extended_hours=False,
                                    client_order_id=coid)
        else:
            o = broker.submit_order(leg["instrument"], leg["qty"], side, extended_hours=True,
                                    limit_price=risk.marketable_limit(price, side),
                                    client_order_id=coid)
        fill = broker.await_fill(o["id"], 90)
    except AlpacaError as exc:
        journal("WARN", message=f"exit failed {leg['instrument']}: {exc}")
        return False
    if not fill:
        return False  # retry next loop with a fresh limit
    exit_px = float(fill["filled_avg_price"])
    d = 1 if leg["side"] == "BUY" else -1
    pnl = d * (exit_px - leg["entry"]) * leg["qty"]
    leg.update(status="closed", exit=exit_px, reason=reason, pnl=round(pnl, 2))
    journal("EXIT", instrument=leg["instrument"], side=leg["side"], qty=leg["qty"],
            entry=leg["entry"], exit=exit_px, reason=reason, pnl=round(pnl, 2))
    return True


def manage_exits(broker: Alpaca, st: dict, session: str | None) -> None:
    ev = st["open_event"]
    boundary = pd.Timestamp(ev["boundary"])
    past_boundary = ny_now() >= boundary
    for leg in ev["legs"]:
        if leg["status"] != "open":
            continue
        if session is None:
            continue   # venue closed; boundary exit happens at next session
        if past_boundary:
            exit_leg(broker, ev, leg, session, "boundary")
            continue
        try:
            price = broker.last_price(leg["instrument"])
        except AlpacaError:
            continue
        trk = intraday.TrailingTracker(leg["side"], leg["trail_pct"], leg["best"])
        trk.best = leg["best"]
        if trk.update(price):
            exit_leg(broker, ev, leg, session, "trailing_stop")
        else:
            leg["best"] = trk.best
    if all(l["status"] == "closed" for l in ev["legs"]):
        total = round(sum(l.get("pnl", 0) for l in ev["legs"]), 2)
        journal("EVENT_CLOSED", headline=ev["headline"][:100], pnl=total)
        st["open_event"] = None


# ------------------------------------------------------------------ main

def main() -> int:
    base_url, mode = risk.resolve_mode()
    broker = Alpaca(base_url)
    acct = broker.account()
    if acct.get("status") != "ACTIVE":
        raise SystemExit(f"account status {acct.get('status')} — refusing to trade")
    classify_fn, clf_name = ds.choose_classifier()
    shadow = clf_name == "keyword" and os.environ.get("ALLOW_KEYWORD_CLASSIFIER") != "1"

    st = load_state()
    eq = float(acct["equity"])
    journal("START", mode=mode, classifier=clf_name, shadow=shadow,
            equity=eq, event_budget_pct=risk.EVENT_BUDGET_PCT,
            max_daily_loss_pct=risk.MAX_DAILY_LOSS_PCT, poll_seconds=POLL_SECONDS)
    if mode == "LIVE":
        alert(f"LIVE trading started — equity ${eq:.2f}. Kill switch: touch {risk.KILL_FILE}")

    # reconcile: unknown broker positions => never trade blind
    if broker.positions() and not st["open_event"]:
        alert("Unknown open positions at the broker with no local state — "
              "entries halted. Flatten manually or remove positions, then restart.")
        shadow = True

    clock_cache: dict = {}
    last_eq_check = 0.0
    while True:
        try:
            if risk.kill_switch_active():
                alert("KILL switch active — flattening everything and halting.")
                broker.flatten_all()
                save_state(st)
                return 0

            today = ny_now().strftime("%Y-%m-%d")
            if st["day"] != today:
                st["day"] = today
                st["day_start_equity"] = broker.equity()
                journal("DAY_START", equity=st["day_start_equity"])

            if time.time() - last_eq_check > 60:
                last_eq_check = time.time()
                eq = broker.equity()
                if risk.daily_loss_breached(st["day_start_equity"], eq):
                    risk.trip_kill_switch(f"daily loss limit: ${st['day_start_equity']:.2f} -> ${eq:.2f}")
                    alert(f"DAILY LOSS LIMIT BREACHED (${eq:.2f}) — kill switch tripped.")
                    continue

            session = tradable_session(broker, clock_cache)

            oe = st["open_event"]
            if oe and oe.get("armed"):
                # signal arrived while the venue was closed — enter at the next
                # session, or expire as missed once the boundary passes
                ev = {k: v for k, v in oe.items() if k != "armed"}
                if session is not None:
                    st["open_event"] = None
                    try_enter(broker, st, ev, session, shadow)
                elif ny_now() >= intraday.boundary_after(pd.Timestamp(ev["post_ts"])):
                    journal("MISSED", headline=ev["headline"][:120],
                            note="venue stayed closed past the boundary")
                    st["processed_ids"].append(ev["post_id"])
                    st["open_event"] = None
            elif oe:
                manage_exits(broker, st, session)
            else:
                since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=90)
                for post in ds.fetch_posts_since(since):
                    if post["id"] in st["processed_ids"]:
                        continue
                    ev = ds.build_event(post, classify_fn)
                    if ev is None:
                        st["processed_ids"].append(post["id"])
                        continue
                    journal("SIGNAL", headline=ev["headline"][:120], signal=ev["signal"])
                    if session is None and ny_now() < intraday.boundary_after(pd.Timestamp(ev["post_ts"])):
                        st["open_event"] = {"armed": True, **ev}
                        journal("ARMED", headline=ev["headline"][:120],
                                note="venue closed — will enter at the next session")
                    else:
                        try_enter(broker, st, ev, session or "ext", shadow)
                    break

            st["processed_ids"] = st["processed_ids"][-5000:]
            save_state(st)
        except KeyboardInterrupt:
            journal("STOP", note="keyboard interrupt — positions left as-is; "
                                 "touch KILL before restarting to flatten instead")
            save_state(st)
            return 0
        except Exception as exc:
            journal("ERROR", error=f"{type(exc).__name__}: {exc}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
