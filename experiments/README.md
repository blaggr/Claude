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

## `gold_vs_sentiment.py` *(removed; results preserved here)*

Tested trading gold inversely to the U. Michigan Consumer Sentiment index,
monthly, Dec 2019 → Nov 2024. Corr(Δsentiment, next-month gold return) was
−0.044 — no edge. All inverse-sentiment variants underperformed gold
buy-and-hold (+80%); long/short versions lost money outright. Related
correlations over 20 years (2004–2024, monthly changes): gold vs sentiment
−0.15, S&P 500 vs sentiment +0.31, 50/50 blend +0.11 — gold's negative
sentiment beta largely cancels equities' positive one.
