"""Always-on paper trading worker.

Polls for macro events, fires drift_signal, places paper OTO stop orders,
sends a daily morning summary email. Runs under launchd (KeepAlive=true).

PAPER ONLY — never imports or calls anything against a live endpoint.
Kill switch: create a file named KILL in the same directory as this script.
State persists across restarts in worker_state.json (atomic write).
Journal: worker_journal.jsonl (one JSON line per event, ISO timestamps).
"""
from __future__ import annotations
import datetime as dt
import json
import os
import time
import traceback
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths — always absolute so launchd can find them
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
STATE_FILE = _HERE / "worker_state.json"
JOURNAL_FILE = _HERE / "worker_journal.jsonl"
KILL_FILE = _HERE / "KILL"

# Signal params (match the backtest Phase-1 defaults)
_DELTA_S = 60
_MEASURE_MIN = 10
_HORIZON_MIN = 30
_SIZE_FRAC = 0.95
_DEFAULT_STOP_PCT = 0.005          # 0.5% protective stop when trail is None
_MAX_CONSECUTIVE_FAILURES = 20     # exit so launchd can restart

# How many bars around the release to fetch (minutes either side)
_FETCH_BEFORE_MIN = 5
_FETCH_AFTER_MIN = 60

# ---------------------------------------------------------------------------
# Pure helpers — no IO, fully unit-testable
# ---------------------------------------------------------------------------

def due_event(now_utc: dt.datetime, events: list, acted_ids: set, *,
              react_window_min: int = 20):
    """Return the first Event whose release ts is within react_window_min of
    now_utc AND whose id (ISO ts string) is NOT already in acted_ids.
    Returns None if no such event exists.
    """
    window = dt.timedelta(minutes=react_window_min)
    for event in events:
        eid = event.ts.isoformat()
        if eid in acted_ids:
            continue
        if event.ts <= now_utc <= event.ts + window:
            return event
    return None


def trade_window_open(now_utc: dt.datetime, event, *, delta_s: int,
                      measure_min: int, settle_s: int = 60) -> bool:
    """True once the drift measurement window [ts+delta_s, ts+delta_s+measure_min]
    has fully elapsed (plus a one-bar settle), so the post-release bars actually
    exist and the reaction can be measured.

    Pair with due_event: due_event caps the UPPER bound (react window) and dedups;
    this caps the LOWER bound. Without it, the first poll after a release reads
    'no bars yet' -> drift_signal returns None -> the event is marked acted and
    burned, so a trade would never fire. settle_s waits one extra bar so the
    measurement-end minute has printed before we read it.
    """
    ready = event.ts + dt.timedelta(seconds=delta_s + settle_s, minutes=measure_min)
    return now_utc >= ready


def should_send_summary(now_et: dt.datetime, last_summary_date, *, after: str = "09:35") -> bool:
    """True if now_et is a weekday, time >= after, and we haven't already sent
    a summary today.

    now_et must be a tz-aware America/New_York datetime.
    last_summary_date is a date object or None.
    """
    if now_et.weekday() >= 5:           # Saturday=5, Sunday=6
        return False
    h, m = (int(x) for x in after.split(":"))
    cutoff = now_et.replace(hour=h, minute=m, second=0, microsecond=0)
    if now_et < cutoff:
        return False
    if last_summary_date is not None and last_summary_date == now_et.date():
        return False
    return True


# ---------------------------------------------------------------------------
# Summary builder — pure, unit-testable
# ---------------------------------------------------------------------------

_FOOTER = (
    "\n---\n"
    "Paper trading only — no real money. "
    "This signal failed its backtest gate (no demonstrated edge); "
    "this run validates plumbing, not profitability."
)


def build_summary(account: dict, positions: list, recent_journal: list,
                  todays_events: list) -> tuple[str, str]:
    """Return (subject, body) for the daily email summary."""
    today = dt.date.today().isoformat()
    subject = f"[paper] news-trader summary {today}"

    equity = account.get("equity", "N/A")
    cash = account.get("cash", "N/A")
    body_lines = [
        f"news-trader daily summary — {today}",
        "",
        f"Account equity:  {equity}",
        f"Account cash:    {cash}",
        "",
    ]

    if positions:
        body_lines.append(f"Open positions ({len(positions)}):")
        for p in positions:
            sym = p.get("symbol", "?")
            qty = p.get("qty", "?")
            side = p.get("side", "?")
            upl = p.get("unrealized_pl", "?")
            body_lines.append(f"  {sym}  qty={qty}  side={side}  unrealized_pl={upl}")
    else:
        body_lines.append("Open positions: none")

    body_lines.append("")
    if recent_journal:
        tail = recent_journal[-10:]
        body_lines.append(f"Recent journal (last {len(tail)}):")
        for entry in tail:
            ts = entry.get("ts", "?")
            ev = entry.get("event", "?")
            detail = entry.get("detail", "")
            line = f"  {ts}  {ev}"
            if detail:
                line += f"  {detail}"
            body_lines.append(line)
    else:
        body_lines.append("Journal: no entries yet")

    body_lines.append("")
    if todays_events:
        body_lines.append(f"Events scheduled today ({len(todays_events)}):")
        for e in todays_events:
            sym = e.payload.get("symbol", "?")
            body_lines.append(f"  {e.ts.isoformat()}  {e.type}  {sym}")
    else:
        body_lines.append("Events scheduled today: none")

    body_lines.append(_FOOTER)
    body = "\n".join(body_lines)
    return subject, body


# ---------------------------------------------------------------------------
# Journal helpers
# ---------------------------------------------------------------------------

def _journal(event: str, **kwargs) -> None:
    entry = {"ts": dt.datetime.now(tz=dt.timezone.utc).isoformat(), "event": event}
    entry.update(kwargs)
    try:
        with open(JOURNAL_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # journalling must never crash the loop


def _load_journal_tail(n: int = 10) -> list:
    entries = []
    try:
        with open(JOURNAL_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except FileNotFoundError:
        pass
    return entries[-n:]


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
        # normalise types
        acted = set(data.get("acted_ids", []))
        lsd_raw = data.get("last_summary_date")
        lsd = dt.date.fromisoformat(lsd_raw) if lsd_raw else None
        return {"acted_ids": acted, "last_summary_date": lsd}
    except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
        _journal("state_load_failed")
        return {"acted_ids": set(), "last_summary_date": None}


def _save_state(state: dict) -> None:
    lsd = state.get("last_summary_date")
    payload = {
        "acted_ids": list(state["acted_ids"]),
        "last_summary_date": lsd.isoformat() if lsd else None,
    }
    tmp = str(STATE_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, STATE_FILE)


# ---------------------------------------------------------------------------
# Account/position helpers (paper Alpaca REST)
# ---------------------------------------------------------------------------

def _get_account(kid: str, sec: str) -> dict:
    import urllib.request
    import urllib.error
    from paper_exec import PAPER_URL
    req = urllib.request.Request(
        PAPER_URL + "/v2/account",
        headers={"APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _get_positions(kid: str, sec: str) -> list:
    import urllib.request
    from paper_exec import PAPER_URL
    req = urllib.request.Request(
        PAPER_URL + "/v2/positions",
        headers={"APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(poll_s: int = 30, events_path: str | None = None,
        kid: str | None = None, sec: str | None = None) -> None:
    """The always-on loop. Intended to be managed by launchd (KeepAlive=true).

    Parameters
    ----------
    poll_s:
        Seconds between each cycle (default 30).
    events_path:
        Path to the macro events CSV; defaults to sample_data/events.csv in the
        package directory. Populate with real Fed release dates before running.
    kid / sec:
        Alpaca paper credentials. Loaded from paper_exec.load_keys() if None.
    """
    # Late imports so offline unit tests never touch network modules
    import zoneinfo
    from macro_calendar import load_events
    from paper_exec import load_keys, place_oto_stop
    from fetch_bars import fetch_bars
    from signals import drift_signal
    import mailer

    ET = zoneinfo.ZoneInfo("America/New_York")

    if kid is None or sec is None:
        kid, sec = load_keys()

    if events_path is None:
        events_path = str(_HERE / "sample_data" / "events.csv")

    try:
        events = load_events(events_path)
    except Exception as exc:
        _journal("events_load_failed", detail=str(exc))
        events = []

    state = _load_state()
    consecutive_failures = 0

    _journal("worker_start", poll_s=poll_s, events_count=len(events))

    while True:
        # ---- kill switch ----
        if KILL_FILE.exists():
            _journal("halt", reason="KILL file present")
            return

        try:
            now_utc = dt.datetime.now(tz=dt.timezone.utc)
            now_et = now_utc.astimezone(ET)
            today_events = [e for e in events if e.ts.date() == now_et.date()]

            # ---- signal check ----
            # due_event caps the upper bound (react window) + dedups; trade_window_open
            # caps the lower bound: wait until the measurement window has elapsed so the
            # post-release bars exist. Without this gate the first poll after release reads
            # 'no bars yet' -> None -> the finally below burns the event and we never trade.
            ev = due_event(now_utc, events, state["acted_ids"])
            if ev is not None and trade_window_open(now_utc, ev, delta_s=_DELTA_S,
                                                    measure_min=_MEASURE_MIN):
                eid = ev.ts.isoformat()
                symbol = ev.payload.get("symbol", "SPY")
                _journal("event_due", event_id=eid, symbol=symbol, event_type=ev.type)
                try:
                    start_dt = ev.ts - dt.timedelta(minutes=_FETCH_BEFORE_MIN)
                    end_dt = ev.ts + dt.timedelta(minutes=_FETCH_AFTER_MIN)
                    start_s = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    end_s = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    raw_bars = fetch_bars(symbol, start_s, end_s, key=kid, secret=sec)

                    import pandas as pd
                    bars_df = pd.DataFrame(raw_bars)
                    bars_df["ts"] = pd.to_datetime(bars_df["ts"], utc=True)
                    bars_df = bars_df.sort_values("ts").reset_index(drop=True)

                    sig = drift_signal(ev, bars_df, delta_s=_DELTA_S,
                                       measure_min=_MEASURE_MIN,
                                       horizon_min=_HORIZON_MIN, trail=None,
                                       size_frac=_SIZE_FRAC)

                    if sig is not None:
                        # Derive entry price from the latest bar close
                        entry_price = float(bars_df["close"].iloc[-1])
                        if sig.side == "long":
                            stop_price = entry_price * (1 - _DEFAULT_STOP_PCT)
                            side = "buy"
                        else:
                            stop_price = entry_price * (1 + _DEFAULT_STOP_PCT)
                            side = "sell"

                        # Phase-1: one position at a time (acted_ids guards re-entry)
                        place_oto_stop(symbol, 1, round(stop_price, 2),
                                       side=side, kid=kid, sec=sec)
                        _journal("BUY", event_id=eid, symbol=symbol,
                                 side=side, entry_price=entry_price,
                                 stop_price=round(stop_price, 2),
                                 rationale=sig.rationale)
                    else:
                        _journal("skip", event_id=eid, symbol=symbol,
                                 reason="no_signal")

                except Exception as exc:
                    _journal("trade_error", event_id=eid, detail=str(exc))
                finally:
                    # Mark acted regardless of trade outcome so we don't re-fire
                    state["acted_ids"].add(eid)

            # ---- daily summary ----
            if should_send_summary(now_et, state["last_summary_date"]):
                try:
                    account = _get_account(kid, sec)
                    positions = _get_positions(kid, sec)
                    recent_journal = _load_journal_tail(10)
                    subject, body = build_summary(account, positions,
                                                  recent_journal, today_events)
                    mailer.send_email(subject, body)
                    state["last_summary_date"] = now_et.date()
                    _journal("summary_sent", date=now_et.date().isoformat())
                except Exception as exc:
                    _journal("summary_error", detail=str(exc))

            # ---- persist state ----
            _save_state(state)
            consecutive_failures = 0

        except Exception as exc:
            consecutive_failures += 1
            _journal("cycle_error", detail=str(exc),
                     traceback=traceback.format_exc(limit=5),
                     consecutive=consecutive_failures)
            if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                _journal("exit_too_many_failures",
                         consecutive=consecutive_failures)
                return

        time.sleep(poll_s)


if __name__ == "__main__":
    run()
