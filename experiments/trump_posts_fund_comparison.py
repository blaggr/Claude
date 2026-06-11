"""Which FUND best fits the Truth Social tariff-post strategy?

Extends the SPY-only experiment to a basket of funds, on the thesis that a
concentrated, trade-war-exposed fund reacts harder to Trump's tariff posts
than broad SPY (which dilutes the effect). For each fund we measure, on days
with >= 3 tariff/trade/China posts:

  * SAME-day reaction  (close T-1 -> close T, the window the posts land in):
    a coincident, NOT-tradable diagnostic of how hard the fund moves.
  * NEXT-day reaction   (close T -> close T+1): the tradable horizon.

and run a simple "long the fund, flip SHORT on tariff-post days" strategy
(next-day) vs buy & hold.

Window: posts archive starts Feb 2022; price data (brownbear) ends 2025-05-02,
which includes the April 2025 "Liberation Day" tariff shock. Presidency split
at 2025-01-20.  Data fetched at runtime from public GitHub datasets.
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

# fund -> (url, description)
FUNDS = {
    "SPY": (BB.format("SPY"), "S&P 500 (broad baseline)"),
    "QQQ": (BB.format("QQQ"), "Nasdaq-100 / big tech"),
    "IWM": (BB.format("IWM"), "Small-cap US (domestic)"),
    "DIA": (BB.format("DIA"), "Dow 30 (industrials-heavy)"),
    "XLI": (BB.format("XLI"), "US industrials sector"),
    "XLK": (BB.format("XLK"), "US tech sector"),
    "SMH": (DAR.format("SMH"), "Semiconductors (China/Taiwan exposed)"),
    "FXI": (BB.format("FXI"), "China large-cap"),
    "KWEB": (DAR.format("KWEB"), "China internet"),
    "EEM": (BB.format("EEM"), "Emerging markets"),
    "EWZ": (BB.format("EWZ"), "Brazil"),
    "GLD": (BB.format("GLD"), "Gold (safe haven)"),
}
END = "2025-05-02"   # common price end across sources
TAG = re.compile(r"<[^>]+>")


def fetch(url):
    return urllib.request.urlopen(url, timeout=60).read().decode(errors="replace")


def load_posts():
    df = pd.read_csv(io.StringIO(fetch(POSTS)))
    ts = pd.to_datetime(df["created_at"], utc=True, format="mixed", errors="coerce")
    df = df.assign(ts=ts).dropna(subset=["ts"])
    df["ts_et"] = df["ts"].dt.tz_convert("America/New_York")
    txt = df["content"].fillna("").map(lambda s: html.unescape(TAG.sub(" ", s)))
    df["text"] = txt.str.replace(r"\s+", " ", regex=True).str.strip()
    return df[["ts_et", "text"]].sort_values("ts_et")


def load_close(url):
    df = pd.read_csv(io.StringIO(fetch(url)))
    df.columns = [c.lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    col = "close"
    if "adj close" in df.columns:
        adj = pd.to_numeric(df["adj close"], errors="coerce")
        if adj.notna().mean() > 0.98 and (adj > 0).all():
            col = "adj close"
    s = pd.to_numeric(df.set_index("date")[col], errors="coerce").dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s[s.index <= pd.Timestamp(END)]


def tariff_days(posts, trading_days):
    closes = pd.DatetimeIndex(trading_days).tz_localize("America/New_York") + pd.Timedelta(hours=16)
    idx = np.searchsorted(closes.asi8, pd.DatetimeIndex(posts["ts_et"]).asi8)
    p = posts.assign(day_i=idx)
    p = p[p["day_i"] < len(closes)]
    pat = r"tariff|trade deal|trade war|china|import tax|tariffs"
    p["hit"] = p["text"].str.lower().str.contains(pat, regex=True)
    cnt = p.groupby("day_i")["hit"].sum()
    out = pd.Series(0, index=range(len(closes)))
    out.update(cnt)
    out.index = trading_days[: len(closes)]
    return out


def tstat(x):
    x = x.dropna()
    return x.mean() / (x.std() / np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else np.nan


def sharpe(r):
    r = r.dropna()
    v = r.std() * np.sqrt(252)
    return (r.mean() * 252) / v if v > 0 else np.nan


def run():
    posts = load_posts()
    closes = {f: load_close(u) for f, (u, _) in FUNDS.items()}
    cal = closes["SPY"].index  # common trading calendar
    tcount = tariff_days(posts, cal)

    for label, start in [("PRESIDENCY (2025-01-20 -> 2025-05-02)", "2025-01-20"),
                        ("FULL (2022-02 -> 2025-05)", "2022-02-14")]:
        days = cal[(cal >= start)]
        sig = (tcount.reindex(days) >= 3)
        print(f"\n=== {label} | {len(days)} trading days | "
              f"tariff-post days (>=3): {int(sig.sum())} ===")
        print(f"{'fund':5} {'description':<34} | SAME-day |move| t/o | NEXT-day ret  t-stat | strat vs B&H (Sharpe)")
        print("-" * 116)
        rows = []
        for f, (_, desc) in FUNDS.items():
            px = closes[f].reindex(cal).ffill()
            ret = px.pct_change().reindex(days)
            same = ret                       # close T-1 -> T : window posts land in
            nxt = ret.shift(-1)              # close T -> T+1 : tradable
            s_on, s_off = same[sig].abs(), same[~sig].abs()
            n_on = nxt[sig]
            ratio = s_on.mean() / s_off.mean() if s_off.mean() else np.nan
            strat = np.where(sig.shift(1, fill_value=False), -1, 1) * ret  # act next day
            bh_sh, st_sh = sharpe(ret), sharpe(pd.Series(strat, index=days))
            rows.append((f, desc, s_on.mean()*100, ratio, n_on.mean()*100, tstat(n_on), st_sh, bh_sh,
                         same[sig].mean()*100))
            print(f"{f:5} {desc:<34} |  {s_on.mean()*100:5.2f}% {ratio:4.1f}x | "
                  f"{n_on.mean()*100:+6.2f}%  t={tstat(n_on):+5.2f} | "
                  f"{st_sh:+5.2f} vs {bh_sh:+5.2f}")
        if start == "2025-01-20":
            print("\n  Same-day DIRECTIONAL mean return on tariff-post days (diagnostic, not tradable):")
            for f, desc, son, ratio, non, tn, st, bh, dirret in sorted(rows, key=lambda r: r[8]):
                print(f"    {f:5} {dirret:+6.2f}%   ({desc})")


if __name__ == "__main__":
    run()
