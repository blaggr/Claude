"""CLI for the trading agent.

    python -m agent.run --demo
    python -m agent.run --news "BREAKING: ADDITIONAL 100% TARIFF on China!" --news "..."
    python -m agent.run --news "..." --regime out_office --offline -v
    python -m agent.run --show-memory

Paper by default. With ANTHROPIC_API_KEY set it reasons with Claude; otherwise
the deterministic offline policy drives the identical tool loop.
"""
from __future__ import annotations

import argparse
import os
import sys

# allow `python agent/run.py` as well as `python -m agent.run`
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.agent import run_session
from agent.llm import AnthropicLLM, HeuristicLLM
from agent.memory import Memory

DEMO_NEWS = [
    "BREAKING: I am imposing an ADDITIONAL 100% TARIFF on all Chinese imports, effective immediately!",
    "Had a wonderful dinner at Mar-a-Lago last night. Thank you to everyone!",
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--news", action="append", default=[],
                    help="A candidate headline/post (repeatable).")
    ap.add_argument("--objective", help="Override the session objective.")
    ap.add_argument("--regime", choices=["in_office", "out_office"], default="in_office")
    ap.add_argument("--min-confidence", choices=["low", "medium", "high"], default="medium",
                    help="Offline policy: lowest leg confidence it will trade.")
    ap.add_argument("--budget-pct", type=float, default=None,
                    help="Max %% of equity a single order may commit "
                         "(default: EVENT_BUDGET_PCT env, else 25).")
    ap.add_argument("--max-steps", type=int, default=10)
    ap.add_argument("--offline", action="store_true",
                    help="Force the offline heuristic policy (no API, no network).")
    ap.add_argument("--demo", action="store_true", help="Run the built-in demo headlines.")
    ap.add_argument("--show-memory", action="store_true",
                    help="Print the agent's working memory and exit.")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    if args.show_memory:
        print(Memory().as_prompt())
        return 0

    news = DEMO_NEWS if args.demo else args.news
    llm = None
    if args.offline or not AnthropicLLM.available():
        llm = HeuristicLLM(min_confidence=args.min_confidence)
        if args.offline:
            args_allow_net = False
        else:
            args_allow_net = True
    else:
        args_allow_net = True

    objective = args.objective or ("Review the latest news and trade only a "
                                   "confident, calibrated edge.")
    res = run_session(objective=objective, news=news, regime=args.regime,
                      max_steps=args.max_steps, llm=llm,
                      allow_network=args_allow_net,
                      min_confidence=args.min_confidence,
                      event_budget_pct=args.budget_pct, verbose=args.verbose)
    print("\n" + "=" * 72)
    print(res.summary())
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
