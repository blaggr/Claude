# Experiments

One-off strategy research scripts. Each fetches its data at runtime from
GitHub-hosted public datasets (the only network host allowed in this build
environment), so there are no bundled data files. Results below are from the
run dates noted; re-running may differ slightly as datasets update.

These are research notes, not financial advice. No fees/slippage modeled.

---

## `trump_truthsocial_strategy.py` — trading SPY/VIX around Trump's Truth Social posts

**Data:** 29,469 timestamped posts (Feb 2022 → Oct 2025) from
`stiles/trump-truth-social-archive`; daily SPY + VIX from
`vivek-v-rao/Conditional-Skew`.

**Timing model (no look-ahead):** posts are bucketed into windows ending at
each day's 16:00 ET close; a position formed at close T uses only posts
already published and earns the close(T)→close(T+1) return.

**Signals:** post-volume "storms" (>90th pct of trailing 90d), keyword
baskets (tariff/trade/China, Fed/rates), ALL-CAPS intensity, silent days.
Sample split at the 2025-01-20 inauguration.

**Findings (run 2026-06-11):**

- **No tradable next-day edge.** Across both samples, no signal's next-day
  SPY return is statistically distinguishable from baseline (all |t| < 1.5).
  Every post-conditioned strategy underperformed SPY buy-and-hold
  (e.g. presidency-only: flip-short-on-tariff-days Sharpe 0.42 vs 0.88 B&H).
- **But posts coincide with same-day turbulence.** During the presidency,
  days with ≥3 tariff/trade posts saw SPY move **1.27%** in absolute terms
  vs **0.69%** on other days (~1.8x), and post storms came with same-day
  VIX up +0.42 pts. The market reacts within hours; by the next close it is
  priced in.
- **Conclusion:** with daily bars, Truth Social posts are a *coincident
  volatility indicator*, not a directional alpha source. Any exploitable
  reaction would require intraday data and minute-level timestamps (which
  the archive has, but free intraday price history for the window does not
  exist on the allowed hosts).

Honest caveats: short presidency sample (193 trading days, 8–32 events per
signal), keyword signals are crude regex, archive has a gap after Oct 2025
(scraper shutdown), and multiple signals were tested on the same window —
treat any marginal t-stat as exploratory.

## `trump_posts_fund_comparison.py` — which FUND fits the strategy best?

Follow-up to the above: SPY is so diversified it may dilute the post reaction.
Tests 12 funds against the tariff-post signal (≥3 tariff/trade/China posts in
a day), separating the **same-day** move (coincident, the window posts land in)
from the **next-day** move (tradable). Prices from `fja05680/brownbear` and
`darischen/EEWS`; window Feb 2022 → 2025-05-02, which **includes the April 2025
"Liberation Day" tariff shock**.

**The thesis is half-right (run 2026-06-11):**

- **Concentration amplifies the reaction — exactly as predicted.** On tariff-post
  days during the presidency, China and semis move far more than SPY:
  SMH **3.15%**, KWEB 2.77%, XLK 2.71%, FXI 2.45% average absolute move, vs
  SPY 2.05% (and ~2x their own normal daily range). Same-day *direction* is
  cleanly negative for the trade-exposed names — FXI **−0.55%**, KWEB −0.54%
  — i.e. China funds drop hardest when Trump posts about tariffs. SPY (−0.09%)
  barely registers. **So yes, FXI/KWEB/SMH are "better" funds for capturing
  the signal.**
- **…but the edge is still same-day, not tradable next-day.** No fund has a
  statistically significant next-day return on tariff-post days (every |t| < 1.2
  in the presidency sample; EWZ's +1.89 over the full sample is the lone
  outlier and is *positive*, opposite the short thesis). The "long, flip short
  on tariff days" strategy beats buy-and-hold for almost no fund.

**Conclusion:** picking a concentrated, trade-war-exposed fund (FXI, KWEB, SMH)
makes the post reaction much larger and directionally clean — but it lands the
*same day* the posts are made. To monetize it you'd need to trade intraday,
within hours of the post; at daily close-to-close resolution it's already
priced in regardless of which fund you choose. Same caveats as above, plus an
even smaller event count per fund (13 tariff days in the presidency window).

## `trump_news_perfect_trade.py` + `PERFECT_TRADE.md` — the designed trade

Splits each tariff-post event-day move into **overnight** (prior close → open,
un-capturable) vs **open→close** (capturable at the open). Decisive finding
(presidency window): the directional China move is **entirely in the overnight
gap** — FXI −0.66% overnight, +0.09% (t=0.2) open→close, and T+1 flat. The edge
is priced **before the US cash open**, so it's zero at daily/ETF-open resolution.

`PERFECT_TRADE.md` is the full strategy write-up built on this: short China beta
(FXI/KWEB) and/or long gold via **futures/FX** the instant an escalation
headline hits, exit on impulse-decay within ~the hour and by the next cash open.
Includes the regime caveat — out of office (2022–24) the same posts had the
*opposite*, significant sign (FXI open→close +0.44%, t=2.4).

## `news_trade_engine.py` — news in → sized BUY/SELL order out

Operational engine that turns the research into a trade plan. Give it a news
item and the quantity you want to trade:

```bash
python news_trade_engine.py --qty 500 --text "ADDITIONAL 100% TARIFF on China, effective now!"
python news_trade_engine.py --demo                 # built-in example posts
python news_trade_engine.py --out-office --text "..."   # regime flip
python news_trade_engine.py --qty 1000 --scale --instrument FXI --text "..."  # size by edge
python news_trade_engine.py --json --text "..."    # machine-readable
```

It (1) classifies **topic** and **valence** (escalation ↔ de-escalation) from a
transparent keyword model, (2) looks up the **empirically-calibrated** response
for that topic + political **regime**, and (3) emits per-instrument legs with
**side, your quantity, P(move), expected move %, and the entry+exit rule**.
Trades either direction: escalation → the risk-off response; de-escalation →
the same legs flipped. `--scale` sizes each leg by edge ((2p−1)·qty).

Two calibrated topics:

- **`trade_china`** (US–China tariffs). In office: SPY-down 0.77, GLD-up 0.69,
  FXI-down 0.62, KWEB 0.46. Out of office the China sign flips to +0.72.
- **`geopolitics_conflict`** (Iran / Middle-East / war). Escalation → **BUY oil
  (USO), BUY gold (GLD), BUY defense (ITA), SELL SPY**; de-escalation/ceasefire
  flips all four. Calibrated from `iran_conflict_event_study.py` (6 escalation
  events, same-day reaction): oil +2.5% (83% up), gold +0.8% (83%), SPY −0.6%
  (83% down), defense +0.4%, Treasuries +0.3%. Regime-independent. The engine
  correctly flips on a *contained* strike read as de-escalation (cf. the
  2020-01-08 no-casualty event, where oil actually fell).

`fed` and `macro_generic` are recognized but **not** calibrated → "NO CALIBRATED
TRADE" (discretionary). **Small samples (6–29 events per topic) — planning
priors, not guarantees; the engine sends no orders.**

**Classifier (`--classifier keyword|llm|openai`).** The default keyword model
is transparent and offline. Two LLM options swap in behind the same
`classify() -> Signal` interface (they read sarcasm, negation, and implicit
valence the keyword model misses), both with structured JSON output and a
graceful fallback to the keyword model (warning on stderr) when the SDK or key
is missing:

- `--classifier openai` — needs `pip install openai` + `OPENAI_API_KEY`;
  model defaults to `gpt-4o-mini`, override with `OPENAI_MODEL`.
- `--classifier llm` — Claude (`claude-opus-4-8`); needs `pip install
  anthropic` + `ANTHROPIC_API_KEY`.

The daily simulation auto-picks: `OPENAI_API_KEY` → OpenAI, else
`ANTHROPIC_API_KEY` → Claude, else keyword. `plan_trade(..., classify_fn=...)`
accepts any `str -> Signal` callable.

Tested in `tests/test_news_engine.py` (12 cases — classification, side/quantity,
regime flip, edge sizing, NO-TRADE, and the offline LLM fallback):
`python -m pytest experiments/tests/test_news_engine.py -q`.

## `iran_conflict_event_study.py` — calibration for the conflict topic

Event study behind the `geopolitics_conflict` calibration. Measures the
same-day and next-day reaction of oil (USO), energy (XLE), gold (GLD), defense
(ITA), Treasuries (TLT), and SPY across six real Iran/Middle-East escalation
dates (Abqaiq 2019, Soleimani + Iran missile strikes Jan 2020, Iran↔Israel
Apr/Oct 2024). Reproduce: `python iran_conflict_event_study.py` (fetches public
data at runtime). Headline: oil is the strongest, most reliable leg; SPY sells
off but shallowly and tends to recover the next session — so this is a
same-day/overnight trade (crude & gold futures), not a multi-day hold.

## `simulation/` — daily forward sim ($100, compounding, morning reports)

Runs the engine **forward on live news** as a paper fund: starts at **$100**,
reinvests all P&L, no leverage. Each weekday at ~10:05–11:05 AM ET a GitHub
Actions job (`.github/workflows/news-sim.yml`):

1. **Scans** the last 24h of Truth Social posts (CNN mirror, GitHub fallback)
   and classifies them (OpenAI if `OPENAI_API_KEY` is set, else Claude if
   `ANTHROPIC_API_KEY`, else keyword).
2. **Fills at event time** (`simulation/intraday.py`): entry at the first
   1-minute bar ≥ post + 5 min (pre/post-market bars included), exit on
   **trailing-stop decay** (the repo's original strategy as the exit
   mechanism) or the calibrated hard boundary — next cash open for
   out-of-hours posts, session close for intraday posts. Posts whose venue
   was closed until the move was priced are honestly marked **MISSED**.
   Because yfinance keeps ~7 days of minute bars, the once-daily run
   reconstructs exact event-time fills retrospectively — no always-on
   poller needed. One position at a time; unresolved events carry to the
   next run; events stale after 3 days settle at the last bar.
3. **Reports**: commits `simulation/reports/YYYY-MM-DD.md`, `ledger.csv`, and
   `state.json`, and comments the report on the rolling issue
   **“📈 News-Trade Sim — Daily Reports”** (subscribe for email delivery).
4. **Alerts**: if the bankroll falls to ≤ $1 the sim halts and opens a
   **🚨 SIM FUND BUSTED** issue.

> Why event-time fills: the original close→open model entered *after* the
> move — our event studies show most posts land pre-open and the move
> completes in that morning's gap (event-day open→close t≈0.2). Event-time
> entry + decay exit is the fill model `PERFECT_TRADE.md` actually
> prescribes. (A legacy close→open settle remains only to close out any
> position opened under the old model.)

**Activation:** GitHub only fires `schedule` workflows from the repo's
**default branch** — merge the PR (or run it manually via the Actions tab →
`news-trade-sim` → *Run workflow*) to start the clock. To reset the fund,
delete `state.json`/`ledger.csv`/`BUSTED` and let the next run reseed $100.

Run a step locally: `python experiments/simulation/daily_sim.py --dry-run`.
Money math is tested in `tests/test_daily_sim.py` (settlement, compounding,
short legs, holiday carry-over, sizing, bust floor).

## `live/` — execution-grade trader (Alpaca, paper by default)

The real-money-shaped version: an always-on worker (`live/live_trader.py`)
that polls posts every 30s, classifies with an LLM, and places orders at
Alpaca — event-time entry, trailing-decay exit, boundary flatten, mirroring
the sim exactly. Paper trading by default; live requires `ALPACA_LIVE=1`
**and** an acknowledgement file (double interlock), with a kill-switch file,
a 5% daily-loss auto-kill, a 25%-of-equity per-event budget, idempotent
orders, and restart reconciliation. Without an LLM key it runs in SHADOW
mode (journals signals, places nothing). Full runbook incl. the paper→live
promotion gate and why TradingView cannot be the execution hub:
`live/README.md`. Risk interlocks tested in `tests/test_live.py`.

## `gold_vs_sentiment.py` *(removed; results preserved here)*

Tested trading gold inversely to the U. Michigan Consumer Sentiment index,
monthly, Dec 2019 → Nov 2024. Corr(Δsentiment, next-month gold return) was
−0.044 — no edge. All inverse-sentiment variants underperformed gold
buy-and-hold (+80%); long/short versions lost money outright. Related
correlations over 20 years (2004–2024, monthly changes): gold vs sentiment
−0.15, S&P 500 vs sentiment +0.31, 50/50 blend +0.11 — gold's negative
sentiment beta largely cancels equities' positive one.
