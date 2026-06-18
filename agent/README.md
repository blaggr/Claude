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
   | `get_open_positions` / `check_exits` / `close_position` | inspect / run / force exits | `positions.py` + `exits.py` |
   | `remember` | persist a durable lesson | `memory.py` |
4. **VERIFY** — reconcile the orders the agent *intended* against the broker's
   actual positions, and journal the result. An agent that never checks its own
   work is the failure mode the article warns about; this step closes the loop.
5. **REMEMBER** — write one durable lesson and update open-position notes.

Before any of that, every session and every live poll first runs an
**automated exit check** (see below).

## Automated exits

The calibrated edges are overnight/intraday — the move is priced by the next
cash open and does not continue — so holding past the window gives the edge
back. Every position the agent opens is therefore registered with an exit plan
and closed automatically by whichever fires first:

- **Trailing stop** — impulse decay. A long trails below its running high, a
  short above its running low; once price gives back the trail distance
  (40% of the calibrated move, floored 0.3% / capped 1.5%), it flattens.
- **Hard boundary** — time. Anchored to the entry: a pre-cash entry exits at
  09:30 ET, an RTH entry by 15:55 ET, an after-hours/weekend entry at the next
  session's 09:30 ET.

The exit check is **deterministic and LLM-free** (exits are mechanical risk
management, not a decision to deliberate) and runs:

- at the **start of every `run_session`**, before any new entry, and
- **every poll** of `live_agent` — even with no new posts, because a position
  decays on its own clock, not the news cycle.

It reconciles against the broker first, so it never tries to close a position
the broker no longer shows. Open positions and their plans live in
`state/open_positions.json`. The agent also has `get_open_positions`,
`check_exits`, and `close_position` tools if you want the model to inspect or
force an exit, but it never has to — the automated check is the safety net.
This mirrors the trailing-stop + boundary logic in
`experiments/simulation/intraday.py`, reimplemented in pure stdlib so the agent
package stays dependency-free.

## Profitability & risk tooling

Four layers exist so the system is honest about costs and disciplined about
risk — because the calibrated edges are small-sample and fragile.

**1. Transaction-cost model (`costs.py`) + cost re-score (`rescore.py`).**
Spread, slippage, commission, and short-borrow are modeled and **subtracted from
every realized exit P&L** (the exit event records `gross_pnl`, `cost`, and net
`pnl`). `rescore.py` re-scores every calibrated edge net of costs so you can see
which legs actually survive:
```bash
python -m agent.rescore                  # net-of-cost edge table
python -m agent.rescore --slippage-bps 50 --json
```
The default run already flags ~3 of 20 calibrated legs as unprofitable after
costs; under 50 bps of slippage, 18 of 20 flip negative. **Cheap edges die first
to costs — this tells you which ones before you trade them.**

**2. Risk-based position sizing (`sizing.py`).** Replaces flat budget sizing with
volatility-targeting + fractional-Kelly (quarter-Kelly default), layered *under*
the per-event budget ceiling (it only ever shrinks, with a 1-share floor). A
**correlation-aware** check treats `SELL SPY + SELL FXI + BUY GLD` as one
risk-off bet and shrinks correlated pile-ons instead of sizing each in isolation.

**3. Live performance tracker + circuit breaker (`performance.py`).** Pairs the
journal's exits into round-trips and computes realized win-rate / P&L / return
per symbol with a **Wilson confidence interval**, compared to the calibrated
prior. The circuit breaker auto-disables any symbol/topic whose live record
underperforms (≥8 trades and Wilson-upper < 0.5); a disabled leg is flagged in
`analyze_news` and **blocked in `place_order`**.
```bash
python -m agent.performance --evaluate   # per-symbol stats vs prior + breaker
```

**4. Macro surprise feed (`experiments/simulation/surprise_source.py`).** Wires a
consensus/actual feed into the scheduled-event sim (CPI/FOMC) — releases that are
more reliably tradable than posts. Set `MACRO_SURPRISE_FILE` to a JSON/CSV of
consensus+actual and the sim trades them instead of only announcing.

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
trips the kill switch) → **automated exit check** (flatten any position that hit
its trailing stop or boundary — runs even with no new posts) → fetch recent
posts → **cheap keyword pre-filter** so a reasoning turn isn't spent on "great
dinner last night" → one agent session per genuinely new, market-relevant post →
persist processed-post ids so a restart never double-trades. Continuous mode
additionally needs `pandas` (`pip install pandas`); the single-shot `agent.run`
does not.

> Scope: `live_agent` now handles **both** entries (LLM-decided) and exits
> (automated trailing stop + boundary, see above). `experiments/live/live_trader.py`
> remains as the fully-deterministic, no-LLM alternative if you don't want a
> model in the entry decision.

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
| `agent.py` | the loop: `run_session()` + the exit pass + the verification step |
| `live_agent.py` | always-on driver: exits every poll, then polls posts → one agent session each, with kill-switch / daily-loss guards |
| `positions.py` | structured open-position store + exit plans (`state/open_positions.json`) |
| `exits.py` | automated exits: trailing stop + hard boundary (pure-stdlib mirror of `intraday.py`); nets costs into P&L |
| `costs.py` / `rescore.py` | transaction-cost model + cost-adjusted edge re-score CLI |
| `sizing.py` | volatility-target / fractional-Kelly sizing + correlation-aware exposure caps |
| `performance.py` | live win-rate/P&L tracker with Wilson CIs vs the prior + auto-disable circuit breaker |
| `llm.py` | reasoning layer — `AnthropicLLM` (Claude) and the offline `HeuristicLLM`, one `step()` contract |
| `tools.py` | the toolbox: schemas + dispatcher, reusing the repo's engines |
| `broker.py` | `LocalPaperBroker` (offline) and `AlpacaBroker` (risk-gated) |
| `marketdata.py` | price snapshots: live → delayed → offline stub |
| `memory.py` | journal + distilled working memory |
| `run.py` | CLI |
| `deploy/` | unattended runners: `trading-agent.service` (systemd), `run_tmux.sh`, `agent.env.example` |
| `tests/test_agent.py` | offline tests for the loop, broker, risk cap, memory, verification, and automated exits |

## Tests

```bash
python -m pytest agent/tests/test_agent.py -q
```
