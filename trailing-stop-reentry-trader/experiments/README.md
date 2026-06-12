# Experiments

Standalone strategy backtests that aren't part of the core trailing-stop
engine. Each is self-contained and pulls its own GitHub-hosted data (live
market feeds are blocked in the build environment).

## gold_vs_sentiment.py

Tests the idea: **trade gold opposite to U.S. consumer sentiment** — long gold
when sentiment falls, short/flat when it rises. Monthly, 5-year window.

```bash
python experiments/gold_vs_sentiment.py
```

**Finding (Dec 2019 → Nov 2024, 60 months):** the premise does not hold. The
correlation between the change in sentiment and gold's next-month return is
**−0.045** (directionally as predicted, but effectively zero). Every variant
underperformed simply holding gold (+80%, Sharpe 1.13); the long/short versions
lost money by shorting gold during a major bull market.

| strategy | total % | CAGR % | Sharpe | max DD % |
|----------|--------:|-------:|-------:|---------:|
| MoM long/short | -8.05 | -1.66 | -0.09 | -17.24 |
| MoM long/flat | 30.97 | 5.54 | 0.73 | -10.78 |
| vs-12m long/short | -13.62 | -2.89 | -0.20 | -33.41 |
| vs-12m long/flat | 26.37 | 4.79 | 0.57 | -18.63 |
| **Gold buy & hold** | **80.25** | **12.51** | **1.13** | **-15.45** |

The 12-month rolling mean is now computed on the full history before the 5-year
evaluation window is sliced off, so all five strategies are scored over the
**same** 60-month window. The previous table evaluated the vs-12m rows over a
shorter, non-overlapping period (the rolling mean burned the first 11 months as
NaN inside the truncated window), which is why those two numbers changed most.

Data: monthly LBMA gold (`datasets/gold-prices`) and University of Michigan
Consumer Sentiment / UMCSENT (FRED mirror). One window, monthly frequency, no
fees/slippage — illustrative, not a tuned or deployable signal.
