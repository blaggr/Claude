"""Fetch real historical minute bars from Alpaca into the harness CSV format.

This is the ONE piece that needs a credential: Alpaca market-data access. Paper
keys work for market data. Set ALPACA_KEY_ID / ALPACA_SECRET_KEY in the env, then:

    python fetch_bars.py --symbol SPY --start 2023-01-01 --end 2024-12-31 --out sample_data/SPY.csv

Writes `ts,open,high,low,close` (UTC) — exactly what prices.load_bars ingests.
Stdlib only (urllib); no SDK. Fails loud on auth/empty responses rather than
writing partial/garbage data.
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Optional

DATA_URL = "https://data.alpaca.markets/v2/stocks/{symbol}/bars"


class FetchError(RuntimeError):
    pass


def _get(url: str, key: str, secret: str) -> dict:
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise FetchError(f"{url} -> {e.code}: {detail}") from None


def fetch_bars(symbol: str, start: str, end: str, *, key: str, secret: str,
               feed: str = "iex", get=_get) -> list[dict]:
    """Return a list of {ts,open,high,low,close} dicts, paging through Alpaca.
    `get` is injectable for testing."""
    base = DATA_URL.format(symbol=symbol)
    rows: list[dict] = []
    page: Optional[str] = None
    while True:
        url = (f"{base}?timeframe=1Min&start={start}&end={end}&limit=10000&feed={feed}"
               + (f"&page_token={page}" if page else ""))
        data = get(url, key, secret)
        for b in (data.get("bars") or []):
            rows.append({"ts": b["t"], "open": b["o"], "high": b["h"],
                         "low": b["l"], "close": b["c"]})
        page = data.get("next_page_token")
        if not page:
            break
    if not rows:
        raise FetchError(f"no bars returned for {symbol} {start}..{end} "
                         f"(feed={feed}) — check symbol, dates, and data entitlement")
    return rows


def write_csv(rows: list[dict], out: str) -> None:
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ts", "open", "high", "low", "close"])
        w.writeheader()
        w.writerows(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--out", required=True)
    ap.add_argument("--feed", default="iex", help="iex (free) or sip (paid)")
    a = ap.parse_args(argv)
    key = os.environ.get("ALPACA_KEY_ID", "")
    secret = os.environ.get("ALPACA_SECRET_KEY", "")
    if not (key and secret):
        print("ERROR: set ALPACA_KEY_ID and ALPACA_SECRET_KEY in the environment.",
              file=sys.stderr)
        return 2
    rows = fetch_bars(a.symbol, a.start, a.end, key=key, secret=secret, feed=a.feed)
    write_csv(rows, a.out)
    print(f"wrote {len(rows)} bars for {a.symbol} -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
