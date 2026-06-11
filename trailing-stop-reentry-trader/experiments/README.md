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

**Finding (Dec 2019 → Nov 2024):** the premise does not hold. The correlation
between the change in sentiment and gold's next-month return is **−0.044**
(directionally as predicted, but effectively zero). Every variant
underperformed simply holding gold (+80%, Sharpe 1.13); the long/short versions
lost money by shorting gold during a major bull market.

| strategy | total % | CAGR % | Sharpe | max DD % |
|----------|--------:|-------:|-------:|---------:|
| MoM long/short | -7.53 | -1.58 | -0.08 | -17.24 |
| MoM long/flat | 30.97 | 5.64 | 0.73 | -10.78 |
| vs-12m long/short | -21.39 | -5.72 | -0.48 | -29.79 |
| vs-12m long/flat | 5.87 | 1.41 | 0.21 | -14.55 |
| **Gold buy & hold** | **80.25** | **12.51** | **1.13** | **-15.45** |

Data: monthly LBMA gold (`datasets/gold-prices`) and University of Michigan
Consumer Sentiment / UMCSENT (FRED mirror). One window, monthly frequency, no
fees/slippage — illustrative, not a tuned or deployable signal.
