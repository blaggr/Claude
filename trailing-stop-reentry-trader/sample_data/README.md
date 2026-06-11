# Sample data

Real daily OHLC series used by `run_examples.py` and `../RESULTS.md`. They're
bundled so the strategy can be tested offline — this build environment blocks
live market feeds (Yahoo Finance / Stooq are not on the network allowlist), so
in normal use you'd pull fresh data with `--ticker` instead.

| File | Instrument | Window | Source |
|------|------------|--------|--------|
| `AAPL_daily.csv` | Apple, daily OHLCV | 2015-02-17 → 2017-02-16 (506 bars) | [plotly/datasets — finance-charts-apple.csv](https://raw.githubusercontent.com/plotly/datasets/master/finance-charts-apple.csv) |
| `TSLA_daily.csv` | Tesla, daily OHLCV (pre-2020-split nominal prices) | 2015-10-15 → 2018-10-15 (756 bars) | [plotly/datasets — tesla-stock-price.csv](https://raw.githubusercontent.com/plotly/datasets/master/tesla-stock-price.csv) |

Both were normalized to this project's `time,open,high,low,close,volume` schema.
One malformed trailing row was dropped from the Tesla file.

Reproduce the tables in `../RESULTS.md`:

```bash
python sample_data/run_examples.py
```
