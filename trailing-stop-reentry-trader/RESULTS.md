# Historical backtest results

Tests of the trailing-stop / re-entry rule on **real daily OHLC data** for two
stocks. Reproduce with `python sample_data/run_examples.py`. Starting capital
$10,000, intrabar fill model, default initial entry on the first bar.

> Data note: this environment blocks live market feeds, so these use bundled
> CSVs from public datasets (~2–3 year windows). Results are **in-sample and
> illustrative** — they do not predict future returns, and fees, slippage and
> taxes are not modeled.

## AAPL — 2015-02-17 → 2017-02-16 (choppy/flat market)

Buy & hold: **+5.88%**, max drawdown **-32.08%**.

| trail $ | reentry $ | return % | vs B&H | trades | win % | max DD % | time in mkt % |
|--------:|----------:|---------:|-------:|-------:|------:|---------:|--------------:|
| 1 | 1 | +4.45 | -1.43 | 3 | 67 | -1.50 | 2 |
| 1 | 2 | +1.04 | -4.84 | 4 | 50 | -4.65 | 2 |
| 2 | 1 | -1.70 | -7.58 | 10 | 30 | -10.07 | 7 |
| 3 | 1 | -5.58 | -11.46 | 8 | 12 | -15.06 | 9 |
| 5 | 1 | -19.93 | -25.81 | 23 | 22 | -40.06 | 51 |

**Read:** in a flat, whippy market the rule *underperforms on return* across the
board — but the tight $1 trail also kept it almost entirely in cash, so it
sidestepped AAPL's -32% drawdown and lost almost nothing (-1.5% max DD). Wider
trails ($5) just got whipsawed: 23 trades, -40% drawdown. Capital protection,
not return, is what shows up here.

## TSLA — 2015-10-15 → 2018-10-15 (volatile, trending)

Buy & hold: **+17.30%**, max drawdown **-40.14%**.

| trail $ | reentry $ | return % | vs B&H | trades | win % | max DD % | time in mkt % |
|--------:|----------:|---------:|-------:|-------:|------:|---------:|--------------:|
| 5 | 1 | +22.32 | **+5.02** | 38 | 42 | -12.10 | 10 |
| 10 | 1 | +19.19 | **+1.89** | 29 | 52 | -13.65 | 14 |
| 15 | 5 | +23.35 | **+6.05** | 16 | 44 | -13.93 | 14 |
| 20 | 1 | +10.81 | -6.49 | 29 | 45 | -36.72 | 45 |

**Read:** on a volatile name with sharp pullbacks, several configs **beat
buy-and-hold** *and* cut max drawdown from -40% to roughly -12% to -14% — while
holding the position only ~10–14% of the time. That is the trailing stop doing
its job: capturing up-moves, cutting losers fast, sitting out the chop.

## Takeaways

1. **The rule is a risk-management overlay, not an alpha engine.** Its
   consistent effect is much smaller drawdowns and low market exposure. Whether
   it beats buy-and-hold on *return* depends entirely on the instrument's
   behavior: it helps on volatile/trending names (TSLA), hurts in flat chop
   (AAPL).
2. **Dollar stops are price-level sensitive.** A `$1` trail is 0.8% on a $125
   stock (constant whipsaw) but 0.5% on a $220 stock. Size the trail to the
   instrument's price and typical daily range — there is no universal dollar
   value. (A percent-based mode would make this portable; see "Possible
   extensions" in the PR.)
3. **Re-entry friction matters.** A larger re-entry trigger (e.g. `+$5`) trades
   less and avoids re-buying into noise, but can miss fast rebounds. `+$1`
   re-enters aggressively.
4. These are short, in-sample windows on free data. Treat the specific numbers
   as a demonstration of behavior, not as tuned parameters to deploy.
