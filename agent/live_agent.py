"""Always-on driver: run the agent loop continuously against a paper account.

This is the agentic counterpart to experiments/live/live_trader.py. Where that
worker is a fixed entry/exit state machine, this one hands every new
market-relevant post to the reasoning agent (agent.run_session) and lets the
agent decide — using its tools, memory, and the per-event risk cap.

Each poll:
  1. safety first — KILL switch flattens and halts; a daily-loss breach trips
     the kill switch (both reuse experiments/live/risk.py, so the controls are
     identical to the existing worker).
  2. fetch posts since the lookback window (Truth Social, via daily_sim).
  3. cheap pre-filter with the keyword classifier — skip posts with no plausible
     market topic so we don't spend a reasoning turn on "great dinner last night".
  4. for each genuinely new, market-relevant post, run one agent session
     (news=[post]). The agent reads memory, sizes within the budget, places a
     PAPER order, verifies, and records a lesson.
  5. persist processed-post ids so a restart never double-trades a post.

Paper by default (the broker is paper unless the live interlocks are armed).
Runs with the offline policy if no ANTHROPIC_API_KEY is set, but you will want
Claude for live reasoning.

    python -m agent.live_agent                 # poll forever (needs Alpaca keys)
    python -m agent.live_agent --once           # single pass, then exit
    python -m agent.live_agent --interval 60 --budget-pct 10 -v
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "experiments"))
sys.path.insert(0, os.path.join(HERE, "..", "experiments", "simulation"))
sys.path.insert(0, os.path.join(HERE, "..", "experiments", "live"))

import news_trade_engine as nte  # noqa: E402

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(HERE))
from agent.agent import run_session  # noqa: E402
from agent.broker import get_broker  # noqa: E402
from agent.exits import ExitManager  # noqa: E402
from agent.memory import Memory  # noqa: E402
from agent.positions import OpenPositions  # noqa: E402

STATE_PATH = os.path.join(HERE, "state", "live_agent_state.json")


def _default_fetch(since: dt.datetime):
    """Truth Social posts since ``since`` (lazy import so tests can inject)."""
    import daily_sim as ds
    return ds.fetch_posts_since(since)


def _load_risk():
    try:
        import risk
        return risk
    except Exception:
        return None


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def load_state() -> dict:
    st = {"processed_ids": [], "day": None, "day_start_equity": None}
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            st.update(json.load(f))
    return st


def save_state(st: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    st["processed_ids"] = st["processed_ids"][-5000:]
    with open(STATE_PATH, "w") as f:
        json.dump(st, f, indent=2, default=str)


def is_market_relevant(text: str) -> bool:
    """Cheap, offline gate: only spend a reasoning turn on a real topic."""
    sig = nte.classify(text)
    return sig.topic != "none" and abs(sig.valence) > 1e-6


def poll_once(broker, memory: Memory, state: dict, *, fetch_fn=_default_fetch,
              lookback_min: int = 90, regime: str = "in_office",
              event_budget_pct: float | None = None, min_confidence: str = "medium",
              allow_network: bool = True, llm=None, positions=None,
              verbose: bool = False) -> list:
    """Process exits, then all new market-relevant posts in the lookback window.

    Returns the list of AgentResult for the sessions that were run this pass.
    ``llm`` is normally None so run_session builds a fresh reasoner per session
    (the offline policy is stateful and must not be shared across sessions)."""
    # automated exits run EVERY poll, before any entry and even with no new
    # posts — a position decays on its own clock, not on the news cycle.
    positions = positions if positions is not None else OpenPositions()
    exit_mgr = ExitManager(broker, memory, positions, allow_network=allow_network)
    taken = exit_mgr.check_and_exit()
    if taken and verbose:
        for e in taken:
            print(f"[live_agent] exit {e['exit_side']} {e['qty']} {e['symbol']} "
                  f"@ {e['exit']} ({e['reason']}, pnl {e['pnl']})")

    since = _now() - dt.timedelta(minutes=lookback_min)
    processed = set(state["processed_ids"])
    results = []
    for post in fetch_fn(since):
        pid = post["id"]
        if pid in processed:
            continue
        text = post.get("text", "")
        if not is_market_relevant(text):
            memory.log("skip_post", post_id=pid, reason="no market topic",
                       text=text[:120])
            state["processed_ids"].append(pid)
            continue
        if verbose:
            print(f"[live_agent] session on post {pid}: {text[:100]}")
        res = run_session(news=[text], regime=regime, broker=broker, memory=memory,
                          event_budget_pct=event_budget_pct, min_confidence=min_confidence,
                          allow_network=allow_network, llm=llm, positions=positions,
                          verbose=verbose)
        memory.log("live_session", post_id=pid, orders=len(res.orders),
                   filled=sum(1 for o in res.orders if o.get("status") == "filled"))
        results.append(res)
        state["processed_ids"].append(pid)
    return results


def _safety_check(broker, memory: Memory, state: dict, risk) -> bool:
    """Returns True if the loop should halt (kill switch fired)."""
    if risk is None:
        return False
    if risk.kill_switch_active():
        memory.log("KILL", note="kill switch active — flattening and halting")
        try:
            broker.flatten_all()
        except Exception as exc:
            memory.log("WARN", note=f"flatten failed: {exc}")
        return True
    # daily-loss guard
    today = _now().strftime("%Y-%m-%d")
    equity = broker.account().get("equity")
    if state["day"] != today:
        state["day"] = today
        state["day_start_equity"] = equity
        memory.log("day_start", equity=equity)
    start = state.get("day_start_equity")
    if start and equity is not None and risk.daily_loss_breached(start, equity):
        risk.trip_kill_switch(f"daily loss limit: {start} -> {equity}")
        memory.log("KILL", note=f"daily loss limit breached ({start} -> {equity})")
        try:
            broker.flatten_all()
        except Exception as exc:
            memory.log("WARN", note=f"flatten failed: {exc}")
        return True
    return False


def run_forever(*, interval: int = 30, once: bool = False, **poll_kwargs) -> int:
    broker = get_broker()
    memory = Memory()
    risk = _load_risk()
    state = load_state()
    poll_kwargs.setdefault("positions", OpenPositions())   # shared across polls
    mode = getattr(broker, "mode", "PAPER")
    memory.log("live_agent_start", mode=mode, interval=interval,
               broker=broker.__class__.__name__)
    print(f"[live_agent] started — broker={broker.__class__.__name__} mode={mode} "
          f"interval={interval}s. Ctrl-C to stop.")
    verbose = poll_kwargs.get("verbose", False)
    while True:
        try:
            if _safety_check(broker, memory, state, risk):
                save_state(state)
                print("[live_agent] kill switch — flattened and halted.")
                return 0
            poll_once(broker, memory, state, **poll_kwargs)
            save_state(state)
        except KeyboardInterrupt:
            save_state(state)
            memory.log("live_agent_stop", note="keyboard interrupt")
            print("\n[live_agent] stopped (positions left as-is).")
            return 0
        except Exception as exc:
            memory.log("ERROR", error=f"{type(exc).__name__}: {exc}")
            if verbose:
                print(f"[live_agent] error: {exc}")
        if once:
            save_state(state)
            return 0
        time.sleep(interval)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interval", type=int, default=int(os.environ.get("POLL_SECONDS", "30")),
                    help="Seconds between polls (default 30 / POLL_SECONDS).")
    ap.add_argument("--lookback-min", type=int, default=90,
                    help="How far back to scan for new posts each pass.")
    ap.add_argument("--once", action="store_true", help="Single pass, then exit.")
    ap.add_argument("--regime", choices=["in_office", "out_office"], default="in_office")
    ap.add_argument("--budget-pct", type=float, default=None,
                    help="Max %% of equity per order (default EVENT_BUDGET_PCT env / 25).")
    ap.add_argument("--min-confidence", choices=["low", "medium", "high"], default="medium")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    return run_forever(interval=args.interval, once=args.once,
                       lookback_min=args.lookback_min, regime=args.regime,
                       event_budget_pct=args.budget_pct,
                       min_confidence=args.min_confidence, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
