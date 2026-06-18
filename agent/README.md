# AI Trading Agent

An LLM-driven trading **agent** — not another backtest script. It runs the loop
the [*900+ Hours of Using Claude Code for Trading*](https://aiintrading.substack.com/p/claude-code-trading-900-hours)
write-up argues *is* the whole product:

```
context  ->  reason  ->  tool  ->  action  ->  verification  ->  remember  ->  (repeat)
```

The rest of this repo gives the agent its hands: a calibrated news→trade engine,
an audited Alpaca adapter, and risk interlocks. The agent is the part that ties
them together — it decides *what* to do, *checks its own work*, and *remembers*
across sessions. Paper trading only.

## Why this exists

The existing `experiments/` code is a deterministic pipeline: the LLM is used
only as a news classifier, and every other decision is hard-coded. The article's
core lesson is the opposite — the leverage isn't a cleverer signal, it's giving
a reasoning agent **good tools, live context, and a memory**, then letting it run
the loop. This module is that agent.

## The loop, concretely

1. **CONTEXT** — load distilled memory (rules, lessons, open positions) + any
   candidate headlines into the prompt.
2. **REASON** — the model picks the next tool call.
3. **TOOL / ACT** — dispatch it. Tools available to the agent:
   | Tool | What it does | Backed by |
   |------|--------------|-----------|
   | `read_memory` | rules, lessons, open positions | `memory.py` |
   | `analyze_news` | headline → calibrated, sized trade plan | `experiments/news_trade_engine.py` |
   | `get_quotes` | price snapshot (live → delayed → offline stub) | `marketdata.py` |
   | `get_portfolio` | equity, cash, positions | `broker.py` |
   | `place_order` | **paper** whole-share market order, risk-capped | `broker.py` + `experiments/live/risk.py` |
   | `remember` | persist a durable lesson | `memory.py` |
4. **VERIFY** — reconcile the orders the agent *intended* against the broker's
   actual positions, and journal the result. An agent that never checks its own
   work is the failure mode the article warns about; this step closes the loop.
5. **REMEMBER** — write one durable lesson and update open-position notes.

## Run it

Works with **zero dependencies, zero network, zero API key** — the offline
heuristic policy drives the exact same tool loop as Claude would.

```bash
# built-in demo (offline): a tariff escalation headline + some noise
python -m agent.run --demo --offline -v

# your own headlines
python -m agent.run --news "BREAKING: ADDITIONAL 100% TARIFF on China!" \
                    --news "Productive call with Xi; we agreed to pause tariffs."

# out-of-office regime, only trade high-confidence legs
python -m agent.run --news "..." --regime out_office --min-confidence high

# cap any single order at 10% of equity (overrides EVENT_BUDGET_PCT)
python -m agent.run --news "..." --budget-pct 10

# inspect what the agent remembers
python -m agent.run --show-memory
```

## Run it continuously (always-on)

`live_agent.py` is the always-on driver: it polls Truth Social and hands every
new *market-relevant* post to the agent loop, so the agent runs continuously
against your paper account. It reuses the post-fetch stack from `experiments/`
and the same KILL-switch / daily-loss interlocks as the existing worker.

```bash
# poll forever (needs Alpaca paper keys + pandas; Claude key recommended)
python -m agent.live_agent --interval 60 --budget-pct 10 -v

# single pass then exit (good for cron, or a smoke test)
python -m agent.live_agent --once -v
```

Each poll: **safety check** (kill switch flattens & halts; a daily-loss breach
trips the kill switch) → fetch recent posts → **cheap keyword pre-filter** so a
reasoning turn isn't spent on "great dinner last night" → one agent session per
genuinely new, market-relevant post → persist processed-post ids so a restart
never double-trades. Continuous mode additionally needs `pandas`
(`pip install pandas`); the single-shot `agent.run` does not.

> Scope: the agent decides *entries* and verifies them; it does not run the
> trailing-stop exit lifecycle. If you want fully automated entries **and**
> exits, `experiments/live/live_trader.py` is the deterministic worker that does
> both. Use `live_agent` when you want the LLM in the decision loop.

## Run it unattended (auto-restart)

Ready-made supervisors live in [`deploy/`](deploy/) so the driver survives
logout and restarts on crash. Both are **paper only** (neither sets
`ALPACA_LIVE`). Put your secrets in `deploy/agent.env` first
(`cp deploy/agent.env.example deploy/agent.env`, fill in, `chmod 600`).

**systemd (Linux, starts on boot):**
```bash
# edit User / WorkingDirectory / secrets in the unit first
sudo cp agent/deploy/trading-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now trading-agent
journalctl -u trading-agent -f          # watch it
```

**tmux (macOS / no systemd / quick VPS run):**
```bash
set -a; source agent/deploy/agent.env; set +a   # load secrets
./agent/deploy/run_tmux.sh start         # detached, auto-restarting
./agent/deploy/run_tmux.sh attach        # watch (Ctrl-b d to detach)
./agent/deploy/run_tmux.sh kill          # flatten everything + stop
```

Both restart **only on crash**; a clean exit or a tripped kill switch ends the
loop and stays stopped (so a daily-loss halt isn't immediately undone). The
kill switch is the same file the rest of the system uses —
`touch experiments/live/KILL` flattens and halts on the next poll; delete it to
resume.

### Upgraded paths (optional, all auto-detected)

- **Reasoning with Claude** — set `ANTHROPIC_API_KEY` (and `pip install
  anthropic`). Without it, the deterministic `HeuristicLLM` runs the loop.
- **Live/delayed quotes** — `ALPACA_KEY_ID`/`ALPACA_SECRET_KEY` (free IEX feed)
  or `yfinance`. Without either, a deterministic offline price stub is used and
  every quote is tagged with its `source`.
- **Real broker (still paper)** — with Alpaca keys, `place_order` routes through
  the audited adapter and `experiments/live/risk.py`. It stays **PAPER** unless
  you arm *both* `ALPACA_LIVE=1` *and* the acknowledgement file (see that
  module). No code path reaches the live endpoint by accident.

## Memory — "a system that remembers"

Two human-readable layers under `state/` (git-ignored, regenerated per run):

- `journal.jsonl` — append-only event log; every observation, order, fill,
  verification and lesson, timestamped. The immutable record.
- `memory.md` — small, rewritable working memory the agent carries forward:
  standing rules, lessons, and a one-line note per open position. Kept short on
  purpose — context is precious, so old lessons are pruned.

You can read and even hand-edit `memory.md` between sessions; the agent picks it
up next run.

## Safety

- **Paper by default, everywhere.** The default backend is a self-contained
  offline paper account; the Alpaca backend is paper unless the double interlock
  is armed.
- **Per-event budget cap.** A single order can't commit more than 25% of equity
  (default; set with `--budget-pct` or `EVENT_BUDGET_PCT`); the toolbox silently
  caps the size and journals it.
- **Calibration honesty.** Edges come from small-sample event studies
  (6–29 events); the agent treats probabilities as priors and is told to stand
  pat when there's no confident, calibrated edge.

This is a research and learning tool. Backtested/calibrated edges do not predict
future returns; fees, slippage and taxes are not modeled. Not investment advice.

## Files

| File | Role |
|------|------|
| `agent.py` | the loop: `run_session()` + the verification step |
| `live_agent.py` | always-on driver: polls posts → one agent session each, with kill-switch / daily-loss guards |
| `llm.py` | reasoning layer — `AnthropicLLM` (Claude) and the offline `HeuristicLLM`, one `step()` contract |
| `tools.py` | the toolbox: schemas + dispatcher, reusing the repo's engines |
| `broker.py` | `LocalPaperBroker` (offline) and `AlpacaBroker` (risk-gated) |
| `marketdata.py` | price snapshots: live → delayed → offline stub |
| `memory.py` | journal + distilled working memory |
| `run.py` | CLI |
| `deploy/` | unattended runners: `trading-agent.service` (systemd), `run_tmux.sh`, `agent.env.example` |
| `tests/test_agent.py` | offline tests for the loop, broker, risk cap, memory, verification |

## Tests

```bash
python -m pytest agent/tests/test_agent.py -q
```
