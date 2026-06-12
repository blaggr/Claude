# Historical backtest results

Tests of the trailing-stop / re-entry rule on **real daily OHLC data** for two
stocks. Reproduce with `python sample_data/run_examples.py`. Starting capital
$10,000, intrabar fill model, default initial entry on the first bar.

> Data note: this environment blocks live market feeds, so these use bundled
> CSVs from public datasets (~2–3 year windows). Results are **in-sample and
> illustrative** — they do not predict future returns, and fees, slippage and
> taxes are not modeled.

> These numbers were regenerated after fixing the fill model (the entry bar now
> extends the peak and can be stopped on the same bar it is opened; re-entry and
> the stop can fire within one bar). Earlier published figures were inflated by
> those bugs — most visibly on TSLA, where the trend-following edge largely
> disappears once the stop is no longer anchored too low on the entry bar.

## AAPL — 2015-02-17 → 2017-02-16 (choppy/flat market)

Buy & hold: **+6.17%**, max drawdown **-32.08%**.

| trail $ | reentry $ | return % | vs B&H | trades | win % | max DD % | time in mkt % |
|--------:|----------:|---------:|-------:|-------:|------:|---------:|--------------:|
| 1 | 1 |  +0.26 |  -5.91 |  6 | 33 |  -3.14 |  1 |
| 1 | 2 |  +0.69 |  -5.48 |  4 | 50 |  -1.67 |  1 |
| 2 | 1 |  -2.41 |  -8.58 | 10 | 20 | -10.72 |  5 |
| 2 | 2 |  +2.33 |  -3.84 |  2 | 50 |  -2.55 |  2 |
| 3 | 1 |  -7.44 | -13.61 |  9 | 22 | -16.73 |  7 |
| 3 | 2 |  -5.69 | -11.86 |  6 | 17 | -15.16 |  6 |
| 5 | 1 | -12.50 | -18.67 | 17 | 18 | -34.50 | 42 |
| 5 | 2 | -12.37 | -18.54 |  9 | 22 | -21.17 | 17 |

**Read:** in a flat, whippy market the rule **underperforms on return in every
config**. The tight $1–$2 trails keep it almost entirely in cash (1–5% time in
market), so they sidestep most of AAPL's -32% drawdown and lose only a little —
capital protection, not return. Wide trails ($5) just get whipsawed: 17 trades,
-34% drawdown, deep underperformance.

## TSLA — 2015-10-15 → 2018-10-15 (volatile, trending)

Buy & hold: **+19.94%**, max drawdown **-40.14%**.

| trail $ | reentry $ | return % | vs B&H | trades | win % | max DD % | time in mkt % |
|--------:|----------:|---------:|-------:|-------:|------:|---------:|--------------:|
|  5 | 1 |  -8.66 | -28.60 | 53 | 26 | -19.10 |  6 |
|  5 | 5 |  +1.22 | -18.72 | 28 | 32 |  -9.98 |  3 |
| 10 | 1 |  -3.03 | -22.97 | 40 | 38 | -21.14 | 17 |
| 10 | 5 |  -8.10 | -28.04 | 26 | 35 | -21.78 |  9 |
| 15 | 1 | +20.20 | **+0.26** | 27 | 37 | -20.35 | 21 |
| 15 | 5 | +21.68 | **+1.74** | 17 | 41 | -13.93 | 14 |
| 20 | 1 | +17.08 |  -2.86 | 29 | 41 | -33.73 | 45 |
| 20 | 5 | +12.18 |  -7.76 | 16 | 31 | -15.58 | 21 |

**Read:** on a volatile, trending name the picture is mixed. **Tight trails
($5–$10) lose heavily**: the stop is too close to the price's daily range, so the
rule gets chopped out (40–53 trades) and underperforms badly. Only a **wide,
range-aware trail ($15)** roughly matches buy-and-hold (+0.26% to +1.74%) while
holding the position ~14–21% of the time and cutting max drawdown from -40% to
-14% to -20%. The earlier claim that several configs *beat* buy-and-hold did not
survive the fill-model fix.

## Takeaways

1. **The rule is a risk-management overlay, not an alpha engine — and a weak
   one.** After the fill-model fix it does not beat buy-and-hold on return in any
   AAPL config and only ties it on TSLA at a single, well-sized trail. Its one
   consistent effect is low market exposure and (for tight trails) smaller
   drawdowns.
2. **Trail size must match the instrument's daily range.** A $1 trail is 0.8% on
   a $125 stock (constant whipsaw) and $5 is far too tight for TSLA's range; only
   the $15 TSLA trail is in the right ballpark. There is no universal dollar
   value. (A percent-based mode would make this portable; see "Possible
   extensions" in the PR.)
3. **Re-entry friction matters.** A larger re-entry trigger (e.g. `+$5`) trades
   less and avoids re-buying into noise, but can miss fast rebounds. `+$1`
   re-enters aggressively and, on a choppy name, bleeds.
4. **Drawdown comparisons are not apples-to-apples.** The strategy's max-DD is
   measured on total equity that is mostly *cash* (low time-in-market), so a
   smaller drawdown than fully-invested buy-and-hold is largely an artifact of
   being out of the market, not of superior stop placement. Read the DD column
   alongside the time-in-market column.
5. These are short, in-sample windows on free data. Treat the specific numbers
   as a demonstration of behavior, not as tuned parameters to deploy.
