"""Event study: market reaction to the administration's Fed / interest-rate posts.

Grounds the `fed` topic the same way tariffs and Iran were grounded. The read
is genuinely ambiguous a priori — "cut rates" pressure could be risk-on (easier
money) or risk-off (attacks on Fed independence → inflation/credibility premium)
— so this measures it rather than asserting it.

Escalation = the administration pressuring/attacking the Fed (the usual case).
Dates are the first US trading day reacting to a prominent Trump Fed/Powell post:

  2019-06-24  "Fed doesn't have a clue" ahead of the July cut
  2019-08-08  "our problem is the Fed — raised too much, too fast"
  2019-09-11  "Fed should get rates down to ZERO, or less"
  2019-10-08  renewed pressure to cut
  2025-04-17  "Powell's termination cannot come fast enough!"
  2025-04-21  "Mr. Too Late, a major loser" — Fed-independence selloff

Instruments: TLT (long bonds / long-end yield, inverse), UUP (US dollar),
SPY (broad equities), GLD (gold), IWM (rate-sensitive small caps),
XLF (financials). Prices: brownbear (2019 → 2025-05). Tiny, partly
tariff-confounded sample — directional prior, not a backtested edge.
"""
import io
import urllib.request

import numpy as np
import pandas as pd

BB = "https://raw.githubusercontent.com/fja05680/brownbear/master/symbol-cache/{}.csv"
FUNDS = {
    "TLT": "Long Treasuries (long-end yield, inverse)",
    "UUP": "US dollar",
    "SPY": "S&P 500 (broad)",
    "GLD": "Gold (safe haven)",
    "IWM": "Small caps (rate-sensitive)",
    "XLF": "Financials",
}
EVENTS = ["2019-06-24", "2019-08-08", "2019-09-11", "2019-10-08", "2025-04-17", "2025-04-21"]


def load_close(t):
    df = pd.read_csv(io.StringIO(urllib.request.urlopen(BB.format(t), timeout=60).read().decode()))
    df.columns = [c.lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    s = pd.to_numeric(df.set_index("date")["close"], errors="coerce").dropna()
    return s[~s.index.duplicated()].sort_index()


def run():
    closes = {t: load_close(t) for t in FUNDS}
    cal = closes["SPY"].index
    idx = [cal.searchsorted(pd.Timestamp(d)) for d in EVENTS]
    print(f"Administration Fed/rates-post event study | {len(EVENTS)} events\n")
    print(f"{'fund':5} {'description':<38} | {'same-day':>9} {'pos%':>5} | {'next-day':>9} {'pos%':>5}")
    print("-" * 80)
    for t, desc in FUNDS.items():
        ret = closes[t].reindex(cal).ffill().pct_change()
        same = np.array([ret.iloc[i] for i in idx if 0 < i < len(cal)])
        nxt = np.array([ret.iloc[i + 1] for i in idx if 0 < i + 1 < len(cal)])
        print(f"{t:5} {desc:<38} | {same.mean()*100:+8.2f}% {(same>0).mean()*100:4.0f}% "
              f"| {nxt.mean()*100:+8.2f}% {(nxt>0).mean()*100:4.0f}%")
    print("\nPer-event same-day move:")
    print(f"{'event':12} " + " ".join(f"{t:>7}" for t in FUNDS))
    for d, i in zip(EVENTS, idx):
        row = [f"{closes[t].reindex(cal).ffill().pct_change().iloc[i]*100:+6.2f}%" for t in FUNDS]
        print(f"{d:12} " + " ".join(f"{v:>7}" for v in row))


if __name__ == "__main__":
    run()
