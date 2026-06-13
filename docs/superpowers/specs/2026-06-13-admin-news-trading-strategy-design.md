# Administration-News Trading Strategy — Design Spec

**Date:** 2026-06-13
**Status:** Approved design (Phase 1), pending implementation plan
**Goal:** A research-first, event-driven trading strategy on Alpaca whose *only*
path to real money is surviving an honest, out-of-sample, after-cost backtest.

---

## 1. Goal & success criterion

Eventually trade **real money**. Therefore, before anything goes live, the
strategy must clear a **risk-adjusted, after-cost, out-of-sample** gate:

- Positive **Sharpe** above a set bar (target ≥ ~0.8 OOS), and
- **Max drawdown** within a stated limit, and
- **Beats buy-and-hold** of equivalent exposure over the same window, and
- On an **adequate event count** `n` (small-n results flagged as luck, not edge).

If the strategy fails this gate, the deliverable is a documented **"no edge"**
finding. That is a valid, valuable outcome — not a failure to paper over.

Non-goal: "most profitable possible." No one can build that; optimizing for it
without a risk denominator selects for blow-up. We optimize for the gate above.

## 2. Scope & sequencing (decomposition)

Four signal sources were requested. They share one pipeline but differ wildly in
data quality and backtestability, so they are **separate sub-projects**, built
and validated one at a time:

1. **Phase 1 — Scheduled macro releases (FOMC / CPI / jobs).** This spec.
   Chosen first because it is the *only* source with second-precise timestamps,
   decades of history, and a *measurable* surprise (actual vs. consensus) — the
   cleanest possible place to learn whether event-driven trading has edge for us.
2. **Phase 2 — Administration social posts + official policy/press.** Same
   pipeline, messier data, an LLM classifier behind the same interface. Carries
   a hard **latency requirement** (see §7).
3. **Phase 3 — Broad financial-news headlines.** Widest, noisiest; only if the
   cleaner sources show the machine works.

Each phase is its own spec → plan → build → validate cycle. The **architecture
is built source-agnostic from day one** so Phases 2–3 slot in without rework.

## 3. Architecture (source-agnostic spine)

New package `news-trader/` in the repo. Each module has one job + a clean
interface:

| Module | Responsibility | Depends on |
|---|---|---|
| `events.py` | Contracts: `Event{ts, source, type, payload}` and `Signal{symbol, side, size_frac, horizon, confidence, rationale}`. Pure data. | — |
| `sources/macro.py` | Phase-1 source: release calendar + consensus + actual → `Event`s at release timestamps (historical for backtest; scheduled fetch for live). | events |
| `classify.py` | `Event → [Signal]`. Phase-1 macro logic is **deterministic** (no LLM): surprise→direction (A) and drift (B). Phase-2 plugs an LLM classifier behind the same interface. | events |
| `prices.py` | Historical minute bars around each event + live last price. | (data vendor) |
| `costs.py` | Realistic-cost model: fill at first bar `≥ event_ts + Δ`, slippage, fees, short borrow. | — |
| `backtest.py` | Replay: per Event → classify → fill via costs → hold to exit → trade ledger + equity curve. | events, classify, prices, costs |
| `metrics.py` | Sharpe, max-DD, total/CAGR, hit-rate, vs-benchmark. | — |
| `validate.py` | Walk-forward split; tune-on-train / lock / evaluate-on-test; the pass/fail gate; multiple-comparisons accounting. | backtest, metrics |
| `execution/` | **Deferred, specified only.** `alpaca_exec.py` (SDK bracket order) + `realtime.py` (Phase-2 posts fast-path). Built **only after** the gate passes. | events, classify |

**Backtest flow:** `macro source → events → classify → signals → backtest(fill+costs) → ledger → validate/metrics`.
**Live flow (later):** `realtime source → event → classify → signal → bracket order via alpaca-py`.

## 4. Signal (Phase 1: A + B)

- **A — surprise (core).** At release, `z = (actual − consensus) / σ`, where σ is
  the historical surprise standard deviation. If `|z| ≥ threshold`, trade the
  mapped direction; size scales with `|z|`, capped. Direction map per release
  type (e.g. hot CPI → short rate-sensitive instrument).
- **B — drift (baseline).** Ignore consensus; measure the first *k*-minute
  reaction after the release and enter in its direction.
- **Exit (both):** fixed horizon (e.g. session close or N hours) **or** a
  trailing stop, whichever first. Parameters (`threshold`, `Δ`, `k`, horizon,
  trail) are swept and chosen **only on the training window**, then evaluated
  out-of-sample.
- Backtest runs **A, B, and buy-and-hold side by side** so we can see whether the
  consensus signal actually earns its data dependency.

## 5. Data (and the landmines)

| Need | Source | Catch / mitigation |
|---|---|---|
| Release **actuals** | FRED / ALFRED | Must use **first-print / vintage** values (ALFRED), not FRED's revised series, or the backtest has look-ahead and is worthless. |
| **Consensus** forecast | Paid econ-calendar API (Trading Economics / Econoday) or scraped (Investing.com / ForexFactory) | Must be **point-in-time** (as known just before release). Assembling clean historical consensus is the biggest data risk; budget for a paid feed. |
| Release **timestamps** | BLS / Fed schedules | Datetime to the minute, including reschedules. |
| **Price bars** | Alpaca historical (IEX/SIP) or Polygon | Intraday lookback depth + feed cost; may need a paid bars feed for a long enough window. |

**Invariant:** a missing/low-quality data source **fails loudly** — never silently
fabricates. Every event records its data provenance. The signal sees **only data
known at `event_ts`** (no look-ahead, ever).

## 6. Cost model & backtest

- **Fill delay:** enter at the first bar `≥ event_ts + Δ` (Δ = realistic reaction,
  5–60s), never the print.
- **Slippage:** half-spread + a few bps of impact, configurable, default
  conservative. **Shorts:** model borrow.
- **Backtest:** one position at a time (or small concurrent cap), bankroll
  compounds; per-trade ledger with entry/exit/return/costs and provenance.

> **Brace for this:** with vintage actuals and pessimistic costs, the macro
> surprise edge may come out flat or negative — much published "edge" is
> gross-of-cost and uses revised data. That result, reported straight, is the
> system working.

## 7. Validation gate (before real money)

- **Walk-forward, out-of-sample:** tune on train, lock, evaluate on held-out test
  the params never saw. Large train→test gap ⇒ overfit ⇒ reject.
- **Multiple-comparisons honesty:** report how many configs were tried; penalize
  the best in-sample result; report `n`. A great Sharpe on a handful of events is
  luck, and the report says so.
- **Per-release-type breakdown:** edge may live in CPI but not FOMC, etc.
- **Gate:** OOS, after costs — positive Sharpe above bar, max-DD within limit,
  beats buy-and-hold, adequate `n`. All four hold → advance to paper. Else: stop,
  report "no edge."

## 8. Execution (deferred — built only after the gate passes)

- Paper on Alpaca via the **`alpaca-py` SDK** using **bracket orders** (entry +
  attached stop as ONE atomic server-side order). The exit lives at the broker,
  not in a client loop — the deliberate fix for the prior hand-rolled-execution
  failures (8 review rounds; do not repeat).
- **Phase-2 posts fast-path:** streaming ingest → classify → bracket order, with
  single-digit-second latency (warm LLM connection, pre-resolved instrument map,
  pre-staged order), idempotent `client_order_id`. **Honest floor:** we do not
  out-race HFT; the edge, if any, is in reading the post correctly, not speed.
- **Interlocks:** paper-by-default + acknowledgement file for live; kill switch;
  daily-loss + total-drawdown limits; one position at a time.
- **Paper gate:** a real paper run matching backtest expectations before real
  money.

## 9. Instruments & risk (Phase 1)

- **Instruments:** small, liquid set — SPY (equities), TLT/IEF (rates),
  optionally GLD/UUP — each release type mapped to the instrument its surprise
  most cleanly drives.
- **Sizing:** fraction of capital per event, scaled by `|z|`, capped; whole
  shares; no leverage beyond modeled shorts.
- **Risk limits:** per-trade cap, daily-loss limit, total-drawdown limit, one
  position at a time.

## 10. Out of scope (v1)

- Options / volatility-capture strategies (Approach C).
- Phase 2/3 sources (separate specs).
- Live real-money trading (gated on §7 + a paper run).
- Any promise of profitability. The backtest decides.

## 11. Open items to resolve during implementation

- Pick the consensus-data vendor (cost, history depth, licensing).
- Pick the price-bar vendor and confirm intraday history reaches a usable window.
- Set the concrete gate thresholds (Sharpe bar, max-DD limit, min `n`).
- Confirm ALFRED vintage coverage for each chosen release series.
