"""Designing the 'perfect' trade on Trump / White House news — timing analysis.

Everything earlier showed the post reaction is SAME-DAY and gone by the next
close. The open question for a real trade is *within* the event day: how much
of the move happens OVERNIGHT / before the open (un-capturable — you can't
trade before the market opens) versus OPEN->CLOSE (capturable if you act at
the open)?

We split tariff/China posts by their ET timestamp relative to the session:
  * PRE-OPEN post: arrives after the prior close and before 09:30 ET of the
    event day  -> you can place a trade at the open.
  * INTRADAY post: arrives 09:30-16:00 -> coincident, only intraday execution
    could catch it.

For each fund we decompose the event-day return into:
  overnight = open_T / close_{T-1} - 1     (already moved by the time you trade)
  intraday  = close_T / open_T - 1         (the open->close leg you can capture)
and check T+1, T+2 for any continuation (drift) or reversal (priced-in test).

Prices: brownbear (SPY/FXI/GLD, with OHLC) + darischen (KWEB/SMH OHLC).
Window ends 2025-05-02 (includes April 2025 'Liberation Day' shock).
"""
import html
import io
import re
import urllib.request

import numpy as np
import pandas as pd

POSTS = "https://raw.githubusercontent.com/stiles/trump-truth-social-archive/main/data/truth_archive.csv"
BB = "https://raw.githubusercontent.com/fja05680/brownbear/master/symbol-cache/{}.csv"
DAR = "https://raw.githubusercontent.com/darischen/EEWS/main/data/etfs/{}.csv"
FUNDS = {
    "FXI": (BB.format("FXI"), "China large-cap"),
    "KWEB": (DAR.format("KWEB"), "China internet"),
    "SMH": (DAR.format("SMH"), "Semiconductors"),
    "SPY": (BB.format("SPY"), "S&P 500 (baseline)"),
    "GLD": (BB.format("GLD"), "Gold (safe haven)"),
}
END = "2025-05-02"
TAG = re.compile(r"<[^>]+>")
TARIFF = r"tariff|trade deal|trade war|china|import tax|tariffs"


def fetch(url):
    return urllib.request.urlopen(url, timeout=60).read().decode(errors="replace")


def load_posts():
    df = pd.read_csv(io.StringIO(fetch(POSTS)))
    ts = pd.to_datetime(df["created_at"], utc=True, format="mixed", errors="coerce")
    df = df.assign(ts=ts).dropna(subset=["ts"])
    df["ts_et"] = df["ts"].dt.tz_convert("America/New_York")
    txt = df["content"].fillna("").map(lambda s: html.unescape(TAG.sub(" ", s)))
    df["text"] = txt.str.replace(r"\s+", " ", regex=True).str.strip()
    df["tariff"] = df["text"].str.lower().str.contains(TARIFF, regex=True)
    return df[["ts_et", "tariff"]].sort_values("ts_et")


def load_ohlc(url):
    df = pd.read_csv(io.StringIO(fetch(url)))
    df.columns = [c.lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["open", "close"]).drop_duplicates("date", keep="last")
    df = df.set_index("date").sort_index()
    out = df[["open", "close"]].apply(pd.to_numeric, errors="coerce").dropna()
    return out[out.index <= pd.Timestamp(END)]


def classify_days(posts, cal):
    """Per trading day: count of tariff posts, and whether the FIRST tariff
    post in the (prevclose, close] window arrived before 09:30 ET (pre-open)."""
    closes = pd.DatetimeIndex(cal).tz_localize("America/New_York") + pd.Timedelta(hours=16)
    idx = np.searchsorted(closes.asi8, pd.DatetimeIndex(posts["ts_et"]).asi8)
    p = posts.assign(day_i=idx)
    p = p[(p["day_i"] < len(closes)) & p["tariff"]]
    open_thresh = (pd.DatetimeIndex(cal).tz_localize("America/New_York")
                   + pd.Timedelta(hours=9, minutes=30))
    p["preopen"] = p["ts_et"].values <= open_thresh[p["day_i"]].values
    p = p.sort_values("ts_et")
    g = p.groupby("day_i")
    n = g.size()
    first_preopen = g["preopen"].first()
    df = pd.DataFrame(index=range(len(cal)))
    df["n_tariff"] = n.reindex(df.index).fillna(0).astype(int)
    df["first_preopen"] = first_preopen.reindex(df.index).fillna(False).astype(bool)
    df.index = cal
    return df


def tstat(x):
    x = x.dropna()
    return x.mean() / (x.std() / np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else np.nan


def run():
    posts = load_posts()
    ohlc = {f: load_ohlc(u) for f, (u, _) in FUNDS.items()}
    cal = ohlc["SPY"].index
    days = classify_days(posts, cal)

    for label, start, thr in [("PRESIDENCY (2025-01-20 -> 2025-05-02)", "2025-01-20", 3),
                             ("FULL (2022-02 -> 2025-05)", "2022-02-14", 3)]:
        d = days.loc[cal >= start]
        heavy = d["n_tariff"] >= thr
        pre = (heavy & d["first_preopen"]).reindex(d.index, fill_value=False)
        print(f"\n=== {label} ===")
        print(f"tariff-heavy days (>={thr}): {int(heavy.sum())}  "
              f"[pre-open: {int(pre.sum())}, intraday-first: {int((heavy & ~d['first_preopen']).sum())}]")
        print(f"{'fund':5} {'desc':<20} | {'PRE-OPEN tariff days':^36} | {'next sess.':^12}")
        print(f"{'':5} {'':<20} | {'overngt':>8} {'opn>cls (t)':>15} {'whole':>8} | {'T+1 op>cl':>11}")
        print("-" * 88)
        pre_idx = pre.index[pre.values]
        for f, (_, desc) in FUNDS.items():
            o = ohlc[f].reindex(cal)
            overnight = (o["open"] / o["close"].shift(1) - 1)
            intraday = (o["close"] / o["open"] - 1)
            whole = (o["close"] / o["close"].shift(1) - 1)
            t1 = intraday.shift(-1)
            ov, ind = overnight.loc[pre_idx], intraday.loc[pre_idx]
            print(f"{f:5} {desc:<20} | {ov.mean()*100:+7.2f}% "
                  f"{ind.mean()*100:+7.2f}% (t={tstat(ind):+4.1f}) "
                  f"{whole.loc[pre_idx].mean()*100:+6.2f}% | {t1.loc[pre_idx].mean()*100:+8.2f}%")

    # share-of-move decomposition on China (FXI) over full sample
    o = ohlc["FXI"].reindex(cal)
    pre_all = (days["n_tariff"] >= 1) & days["first_preopen"]
    ov = (o["open"]/o["close"].shift(1)-1)[pre_all]
    ind = (o["close"]/o["open"]-1)[pre_all]
    tot = ov.abs().mean() + ind.abs().mean()
    print(f"\nFXI, all pre-open tariff days (n={int(pre_all.sum())}): "
          f"overnight = {ov.abs().mean()/tot*100:.0f}% of the move, "
          f"open->close = {ind.abs().mean()/tot*100:.0f}% "
          f"(mean overnight {ov.mean()*100:+.2f}%, open->close {ind.mean()*100:+.2f}%)")


if __name__ == "__main__":
    run()
