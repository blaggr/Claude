# First real-data run — FOMC drift signal

**Date:** 2026-06-13. **Verdict: NO demonstrable edge. Do not deploy.**

## What was run
- Signal: drift (B) — ride the first 10-minute post-release reaction, exit by horizon/trail.
- Events: **21 real FOMC statement days**, 2022-06-15 → 2024-12-18 (2 PM ET, DST-correct UTC). FOMC only — see caveats.
- Bars: **real SPY 1-minute bars from Alpaca's free IEX feed** (2,854 bars across the event windows).
- Costs: pessimistic (2 bps half-spread + 1 bps impact, both sides).
- Validation: walk-forward, params tuned on train only, evaluated out-of-sample; 18 configs swept.

## Result

| split | n | total | Sharpe | maxDD | hit | vs buy-and-hold |
|---|--:|--:|--:|--:|--:|--:|
| train | 12 | +4.45% | 1.07 | −2.07% | 58% | **−50.4%** |
| test (OOS) | 9 | +2.94% | 1.28 | −0.75% | 67% | **−22.9%** |
| full sample | 21 | +7.52% | 1.16 | −2.07% | 62% | **−47.3%** |

**GATE: FAILED.** It fails on two independent counts:
1. **Insufficient n** — out-of-sample test had **9** events; the gate requires ≥ 20. A Sharpe on 9 trades is noise, not evidence.
2. **Loses to buy-and-hold by a mile** — the strategy is in the market ~2 hours per event (~21 times in 2.5 years), so it captures a small positive return with tiny drawdown but cannot compete with SPY's ~+54% over the window. `vs_buyhold` is deeply negative everywhere.

## Honest read
The headline Sharpe (~1.2) looks fine and is a trap: it rests on ~9–21 trades and a crude annualization, and the strategy's "low drawdown" is just an artifact of being in cash 99% of the time — the exact same mirage as the earlier trailing-stop work. After costs, on real data, the macro-FOMC drift signal shows **no edge worth trading**.

## Caveats (why this isn't even the final word — it's worse than it looks)
- **FOMC only.** CPI and jobs (8:30 ET, pre-market) are unmeasurable on the free IEX feed (no pre-market bars), so the events most likely to carry a surprise move were excluded.
- **IEX is partial-volume** — a fraction of true volume; real fills/spreads would differ (likely worse).
- **n = 21 is tiny.** No statistical power.
- **FOMC dates** assembled from public record — verify against federalreserve.gov before any use.
- A genuine test needs a **paid SIP feed** (full + pre-market), **many more years**, and **CPI/NFP** included — and would very plausibly still show no edge after costs.

## Bottom line
The harness did its job: it ran on real data and **refused to certify edge**. That negative result is the valuable output — it saved you from trading a thin/negative signal.
