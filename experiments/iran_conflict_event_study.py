"""Event study: how markets react to Iran / Middle-East war escalation.

Grounds the geopolitics_conflict calibration in the news_trade_engine the same
way the tariff numbers were grounded — measuring real reactions rather than
asserting priors. Escalation dates (first US trading day that reacts):

  2019-09-16  Abqaiq: drone strike on Saudi oil facility (blamed on Iran)
  2020-01-03  US strike kills IRGC's Soleimani
  2020-01-08  Iran missile strike on US bases in Iraq
  2024-04-15  first session after Iran's 4/13 direct drone/missile attack on Israel
  2024-04-19  Israeli retaliatory strike on Iran
  2024-10-01  Iran ballistic-missile barrage on Israel

Instruments: USO (oil), XLE (energy), GLD (gold), ITA (defense), TLT (long
Treasuries / flight-to-safety), SPY (broad equities). Prices: brownbear +
darischen (2019 -> 2025-05). Small sample (6 events) — directional prior, not
a backtested edge.
"""
import io
import urllib.request

import numpy as np
import pandas as pd

BB = "https://raw.githubusercontent.com/fja05680/brownbear/master/symbol-cache/{}.csv"
DAR = "https://raw.githubusercontent.com/darischen/EEWS/main/data/etfs/{}.csv"
FUNDS = {
    "USO": (BB.format("USO"), "Oil"),
    "XLE": (BB.format("XLE"), "Energy sector"),
    "GLD": (BB.format("GLD"), "Gold (safe haven)"),
    "ITA": (DAR.format("ITA"), "Defense/aerospace"),
    "TLT": (BB.format("TLT"), "Long Treasuries (flight to safety)"),
    "SPY": (BB.format("SPY"), "S&P 500 (broad)"),
}
EVENTS = ["2019-09-16", "2020-01-03", "2020-01-08", "2024-04-15", "2024-04-19", "2024-10-01"]


def load_close(url):
    df = pd.read_csv(io.StringIO(urllib.request.urlopen(url, timeout=60).read().decode(errors="replace")))
    df.columns = [c.lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    col = "close"
    if "adj close" in df.columns:
        adj = pd.to_numeric(df["adj close"], errors="coerce")
        if adj.notna().mean() > 0.98 and (adj > 0).all():
            col = "adj close"
    s = pd.to_numeric(df.set_index("date")[col], errors="coerce").dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


def run():
    closes = {f: load_close(u) for f, (u, _) in FUNDS.items()}
    cal = closes["SPY"].index
    event_idx = [cal.searchsorted(pd.Timestamp(d)) for d in EVENTS]  # first trading day >= date

    print(f"Iran / Middle-East escalation event study | {len(EVENTS)} events\n")
    print(f"{'fund':5} {'description':<34} | {'same-day mean':>13} {'pos%':>5} | {'next-day mean':>13} {'pos%':>5}")
    print("-" * 86)
    for f, (_, desc) in FUNDS.items():
        px = closes[f].reindex(cal).ffill()
        ret = px.pct_change()
        same = np.array([ret.iloc[i] for i in event_idx if 0 < i < len(cal)])
        nxt = np.array([ret.iloc[i + 1] for i in event_idx if 0 < i + 1 < len(cal)])
        print(f"{f:5} {desc:<34} | {same.mean()*100:+11.2f}% {(same>0).mean()*100:4.0f}% "
              f"| {nxt.mean()*100:+11.2f}% {(nxt>0).mean()*100:4.0f}%")

    # per-event detail for the headline instruments
    print("\nPer-event same-day move:")
    print(f"{'event':12} " + " ".join(f"{f:>7}" for f in FUNDS))
    for d, i in zip(EVENTS, event_idx):
        row = []
        for f in FUNDS:
            r = closes[f].reindex(cal).ffill().pct_change().iloc[i]
            row.append(f"{r*100:+6.2f}%")
        print(f"{d:12} " + " ".join(f"{v:>7}" for v in row))


if __name__ == "__main__":
    run()
