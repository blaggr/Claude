"""Backtest: trading SPY/VIX around Trump's Truth Social posts.

Data
----
* Posts:  stiles/trump-truth-social-archive (GitHub) — 29k posts,
          Feb 2022 -> Oct 2025, UTC timestamps.
* Market: vivek-v-rao/Conditional-Skew vix_spy.csv — daily SPY (adj) and VIX
          close, 1993 -> 2026.

Timing model (no look-ahead)
----------------------------
For trading day T, the signal window is (close of T-1, close of T], i.e.
16:00 ET to 16:00 ET. A position is formed AT the close of day T using only
posts already published, and held close(T) -> close(T+1).

Signals tested
--------------
1. Post volume ("post storms"): days with unusually many posts.
2. Keyword baskets: tariffs/trade, Fed/rates, plus an "ALL-CAPS rage" meter.
Each is evaluated as an event study (mean next-day SPY return / VIX change)
and as a simple daily long/short/flat strategy vs buy & hold.

Sample splits: full window, and presidency-only (>= 2025-01-20) since posts
only carry policy weight once he's in office.
"""
import html
import io
import re
import urllib.request

import numpy as np
import pandas as pd

POSTS = "https://raw.githubusercontent.com/stiles/trump-truth-social-archive/main/data/truth_archive.csv"
MARKET = "https://raw.githubusercontent.com/vivek-v-rao/Conditional-Skew/main/vix_spy.csv"

TAG = re.compile(r"<[^>]+>")

def fetch(url):
    return urllib.request.urlopen(url, timeout=60).read().decode(errors="replace")


def load_posts() -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(fetch(POSTS)))
    ts = pd.to_datetime(df["created_at"], utc=True, format="mixed", errors="coerce")
    df = df.assign(ts=ts).dropna(subset=["ts"])
    df["ts_et"] = df["ts"].dt.tz_convert("America/New_York")
    txt = df["content"].fillna("").map(lambda s: html.unescape(TAG.sub(" ", s)))
    df["text"] = txt.str.replace(r"\s+", " ", regex=True).str.strip()
    return df[["ts_et", "text"]].sort_values("ts_et")


def load_market() -> pd.DataFrame:
    m = pd.read_csv(io.StringIO(fetch(MARKET)))
    m["Date"] = pd.to_datetime(m["Date"])
    m = m.set_index("Date").sort_index()
    m["spy_ret"] = m["SPY"].pct_change()
    m["vix_chg"] = m["VIX"].diff()
    return m


def words_features(posts: pd.DataFrame, market_days: pd.DatetimeIndex) -> pd.DataFrame:
    """Aggregate posts into per-trading-day signal windows ending at 16:00 ET."""
    closes = pd.DatetimeIndex(market_days).tz_localize("America/New_York") + pd.Timedelta(hours=16)
    idx = np.searchsorted(closes.asi8, pd.DatetimeIndex(posts["ts_et"]).asi8)
    # idx = first close AT/after the post -> that close's trading day owns the post
    posts = posts.assign(day_i=idx)
    posts = posts[posts["day_i"] < len(closes)]

    low = posts["text"].str.lower()
    KW = {
        "tariff": r"tariff|trade deal|trade war|china|import tax",
        "fed": r"\bfed\b|powell|interest rate|federal reserve",
    }
    feats = pd.DataFrame(index=range(len(closes)))
    grp = posts.groupby("day_i")
    feats["n_posts"] = grp.size()
    for name, pat in KW.items():
        posts[f"_{name}"] = low.str.contains(pat, regex=True)
        feats[name] = grp[f"_{name}"].sum()
    caps = posts["text"].map(lambda s: sum(1 for w in s.split() if len(w) >= 4 and w.isupper()))
    posts["_caps"] = caps
    feats["caps_words"] = grp["_caps"].sum()
    feats = feats.fillna(0)
    feats.index = market_days[: len(closes)]
    return feats


def perf(rets: pd.Series, label: str) -> dict:
    r = rets.dropna()
    if len(r) == 0:
        return {}
    eq = (1 + r).cumprod()
    yrs = len(r) / 252
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if yrs > 0 else np.nan
    vol = r.std() * np.sqrt(252)
    dd = (eq / eq.cummax() - 1).min()
    return {"label": label, "total_%": (eq.iloc[-1] - 1) * 100, "cagr_%": cagr * 100,
            "sharpe": (r.mean() * 252) / vol if vol > 0 else np.nan,
            "maxDD_%": dd * 100, "days_in_mkt_%": (rets.fillna(0) != 0).mean() * 100}


def tstat(x: pd.Series) -> float:
    x = x.dropna()
    return x.mean() / (x.std() / np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else np.nan


def event_study(sig: pd.Series, fwd_spy: pd.Series, fwd_vix: pd.Series, name: str):
    on, off = fwd_spy[sig], fwd_spy[~sig]
    von = fwd_vix[sig]
    print(f"  {name:<28} events={sig.sum():>4}  "
          f"next-day SPY: {on.mean()*100:+.3f}% (t={tstat(on):+.2f}) vs {off.mean()*100:+.3f}% other days | "
          f"next-day ΔVIX: {von.mean():+.3f} (t={tstat(von):+.2f})")


def run():
    posts = load_posts()
    mkt = load_market()
    lo, hi = posts["ts_et"].min().tz_localize(None), posts["ts_et"].max().tz_localize(None)
    mkt = mkt.loc[(mkt.index >= lo.normalize()) & (mkt.index <= hi.normalize() + pd.Timedelta(days=3))]
    # archive is continuous only through the scraper shutdown
    mkt = mkt.loc[mkt.index <= "2025-10-24"]

    feats = words_features(posts, mkt.index)
    fwd_spy = mkt["spy_ret"].shift(-1)   # return earned close(T)->close(T+1)
    fwd_vix = mkt["vix_chg"].shift(-1)

    # rolling 90d post-volume baseline (shifted so threshold itself isn't look-ahead)
    base = feats["n_posts"].rolling(90, min_periods=30).quantile(0.9).shift(1)
    storm = feats["n_posts"] > base

    for label, mask in [("FULL SAMPLE (Feb 2022 - Oct 2025)", mkt.index >= lo.normalize()),
                        ("PRESIDENCY ONLY (>= 2025-01-20)", mkt.index >= "2025-01-20")]:
        m = pd.Series(mask, index=mkt.index)
        f_spy, f_vix = fwd_spy[m], fwd_vix[m]
        fe = feats[m]
        print(f"\n=== {label} | {int(m.sum())} trading days | "
              f"baseline next-day SPY {f_spy.mean()*100:+.3f}%/day ===")
        event_study(storm[m].fillna(False), f_spy, f_vix, "Post storm (>90th pct, 90d)")
        event_study(fe["tariff"] >= 3, f_spy, f_vix, "Tariff/trade posts >= 3")
        event_study(fe["fed"] >= 2, f_spy, f_vix, "Fed/rates posts >= 2")
        event_study(fe["caps_words"] >= fe["caps_words"].quantile(0.9), f_spy, f_vix,
                    "ALL-CAPS top decile")
        event_study(fe["n_posts"] == 0, f_spy, f_vix, "Silent days (0 posts)")

        # --- simple strategies, close(T) -> close(T+1) ---
        rows = []
        sig_short_tariff = (fe["tariff"] >= 3)
        rows.append(perf(np.where(sig_short_tariff, -1, 1) * f_spy, "Long SPY, flip SHORT on tariff days"))
        rows.append(perf(np.where(sig_short_tariff, 0, 1) * f_spy, "Long SPY, FLAT on tariff days"))
        rows.append(perf(np.where(storm[m].fillna(False), 0, 1) * f_spy, "Long SPY, FLAT on post storms"))
        rows.append(perf(np.where(sig_short_tariff, 1, 0) * f_vix / mkt["VIX"][m], "Long VIX on tariff days (proxy)"))
        rows.append(perf(f_spy, "SPY buy & hold"))
        print(f"\n  {'strategy':<38} {'total%':>8} {'cagr%':>7} {'sharpe':>7} {'maxDD%':>8} {'in mkt%':>8}")
        for r in rows:
            if r:
                print(f"  {r['label']:<38} {r['total_%']:>8.2f} {r['cagr_%']:>7.2f} "
                      f"{r['sharpe']:>7.2f} {r['maxDD_%']:>8.2f} {r['days_in_mkt_%']:>8.0f}")


if __name__ == "__main__":
    run()
