"""Backtest: trade gold inversely to U.S. consumer sentiment (5 years, monthly).

Premise to test: when consumer sentiment falls, gold (a fear/safe-haven asset)
tends to rise, and vice versa. So position gold OPPOSITE to the change in
sentiment.

Data (GitHub-hosted, since live feeds are blocked here):
  * Gold:      monthly LBMA USD price  (datasets/gold-prices)
  * Sentiment: University of Michigan Consumer Sentiment, UMCSENT, monthly
               (mirror of the FRED series)

Signal (no look-ahead): at the end of month t we know sentiment_t. We form the
position for month t+1 and earn gold's month t+1 return.

Two signal definitions are tested:
  A) MoM change:  position = -sign(sentiment_t - sentiment_{t-1})
  B) vs 12m mean: position = -sign(sentiment_t - mean(last 12 sentiments))

Two position styles:
  * long/short (+1 / -1)   * long/flat (+1 / 0, no shorting gold)
"""
import io
import urllib.request

import numpy as np
import pandas as pd

GOLD_URL = "https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv"
UMCSENT_URL = ("https://raw.githubusercontent.com/Duzzuti/fear-and-greed/"
               "0a02043706b707df7025b048807829c689b8d4e3/"
               "data/2000-01-01_2025-01-15_UMCSENT.csv")
YEARS = 5


def _get(url):
    return urllib.request.urlopen(url, timeout=30).read().decode()


def load_data():
    g = pd.read_csv(io.StringIO(_get(GOLD_URL)))
    g["m"] = pd.PeriodIndex(g["Date"], freq="M")
    gold = g.set_index("m")["Price"].astype(float).rename("gold")

    s = pd.read_csv(io.StringIO(_get(UMCSENT_URL)))
    s.columns = [c.lower() for c in s.columns]
    s["m"] = pd.PeriodIndex(pd.to_datetime(s["date"]), freq="M")
    sent = pd.to_numeric(s["umcsent"], errors="coerce")
    sent.index = s["m"]
    sent = sent.rename("sent").dropna()

    # Return the FULL overlapping history. Truncating to the evaluation window
    # here would make rolling(12) burn the first 11 months as NaN and silently
    # evaluate the vs-12m strategies over a shorter, different window than the
    # others. run() slices to the shared window AFTER computing the signals.
    return pd.concat([gold, sent], axis=1).dropna().sort_index()


def metrics(monthly_ret: pd.Series) -> dict:
    r = monthly_ret.dropna()
    equity = (1 + r).cumprod()
    total = equity.iloc[-1] - 1
    yrs = len(r) / 12
    cagr = equity.iloc[-1] ** (1 / yrs) - 1
    vol = r.std() * np.sqrt(12)
    sharpe = (r.mean() * 12) / vol if vol > 0 else float("nan")
    dd = (equity / equity.cummax() - 1).min()
    return {
        "total_%": total * 100,
        "cagr_%": cagr * 100,
        "vol_%": vol * 100,
        "sharpe": sharpe,
        "maxDD_%": dd * 100,
        "hit_%": (r > 0).mean() * 100,
        "months": len(r),
    }


def run():
    df = load_data()
    gold_ret = df["gold"].pct_change()          # month t return
    fwd_ret = gold_ret.shift(-1)                 # month t+1 return (what we earn)
    sent = df["sent"]

    # Signals computed on the FULL history so the 12-month mean has its lookback.
    sig_mom = -np.sign(sent.diff())
    sig_ma = -np.sign(sent - sent.rolling(12).mean())

    strategies = {
        "MoM long/short": sig_mom * fwd_ret,
        "MoM long/flat": sig_mom.clip(lower=0) * fwd_ret,
        "vs12m long/short": sig_ma * fwd_ret,
        "vs12m long/flat": sig_ma.clip(lower=0) * fwd_ret,
        "Gold buy & hold": fwd_ret,
    }

    # Restrict EVERY strategy to the same evaluation window (last YEARS*12+1
    # months), so the table compares like with like.
    win = df.index[-(YEARS * 12 + 1):]
    strategies = {name: r.reindex(win) for name, r in strategies.items()}

    print(f"Window: {win[1]} -> {win[-1]}  ({len(win)-1} months of returns)")
    print(f"Gold:  ${df['gold'].reindex(win).iloc[0]:.0f} -> ${df['gold'].iloc[-1]:.0f}")
    print(f"Sentiment: {sent.reindex(win).iloc[0]:.1f} -> {sent.iloc[-1]:.1f}")

    # premise check: correlation of gold's fwd return with the sentiment change,
    # over the same evaluation window as the table.
    valid = pd.concat([sent.diff(), fwd_ret], axis=1).reindex(win).dropna()
    corr = valid.iloc[:, 0].corr(valid.iloc[:, 1])
    print(f"\nCorr(Δsentiment, next-month gold return) = {corr:+.3f}  "
          f"(premise wants this NEGATIVE)\n")

    hdr = ("strategy", "total_%", "cagr_%", "vol_%", "sharpe", "maxDD_%", "hit_%")
    print("{:>17} {:>8} {:>7} {:>6} {:>7} {:>8} {:>6}".format(*hdr))
    print("-" * 66)
    for name, r in strategies.items():
        m = metrics(r)
        print("{:>17} {:>8.2f} {:>7.2f} {:>6.2f} {:>7.2f} {:>8.2f} {:>6.0f}".format(
            name, m["total_%"], m["cagr_%"], m["vol_%"], m["sharpe"], m["maxDD_%"], m["hit_%"]))


if __name__ == "__main__":
    run()
