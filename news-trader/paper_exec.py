"""Place orders on an Alpaca PAPER account — and ONLY paper.

The protective stop is attached to the entry as a single server-side OTO order
(one-triggers-other: market entry + a stop-loss leg). The broker manages the
stop atomically, so there is no hand-rolled poll/reconcile loop and no window
where the position is naked. (This is the deliberate fix for the prior
hand-rolled-execution failures — do not reintroduce a client-side exit loop.)

PAPER ONLY: refuses any base URL that is not the Alpaca paper endpoint. Reads
credentials from the gitignored `.alpaca_keys` file or the environment. Fails
loud; never places a partial/garbage order silently.

    python paper_exec.py --symbol SPY --qty 1 --stop-price 600.00
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

PAPER_URL = "https://paper-api.alpaca.markets"


class ExecError(RuntimeError):
    pass


def load_keys(path: str = ".alpaca_keys") -> tuple[str, str]:
    env = dict(os.environ)
    if os.path.exists(path):
        for line in open(path):
            k, _, v = line.strip().partition("=")
            if k:
                env.setdefault(k, v)
    kid, sec = env.get("ALPACA_KEY_ID"), env.get("ALPACA_SECRET_KEY")
    if not (kid and sec):
        raise ExecError("set ALPACA_KEY_ID / ALPACA_SECRET_KEY (env or .alpaca_keys)")
    return kid, sec


def _post(path: str, body: dict, kid: str, sec: str, base: str = PAPER_URL,
          _opener=urllib.request.urlopen) -> dict:
    if "paper" not in base:
        raise ExecError(f"refusing to POST to a non-paper endpoint: {base}")
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 method="POST", headers={
                                     "APCA-API-KEY-ID": kid,
                                     "APCA-API-SECRET-KEY": sec,
                                     "Content-Type": "application/json"})
    try:
        with _opener(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise ExecError(f"POST {path} -> {e.code}: "
                        f"{e.read().decode(errors='replace')[:300]}") from None


def place_oto_stop(symbol: str, qty: int, stop_price: float, *, side: str = "buy",
                   kid: str, sec: str, base: str = PAPER_URL, post=_post) -> dict:
    """Market entry + an attached stop-loss leg, atomic (order_class=oto)."""
    if "paper" not in base:
        raise ExecError(f"refusing non-paper base {base}")
    if int(qty) != qty or qty < 1:
        raise ExecError(f"qty must be a whole number >= 1, got {qty!r}")
    if not (stop_price and stop_price > 0):
        raise ExecError(f"stop_price must be > 0, got {stop_price!r}")
    body = {"symbol": symbol, "qty": str(int(qty)), "side": side, "type": "market",
            "time_in_force": "day", "order_class": "oto",
            "stop_loss": {"stop_price": f"{stop_price:.2f}"}}
    return post("/v2/orders", body, kid, sec, base)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--qty", type=int, default=1)
    ap.add_argument("--stop-price", type=float, required=True,
                    help="protective stop price for the attached leg")
    ap.add_argument("--side", default="buy", choices=["buy", "sell"])
    a = ap.parse_args(argv)
    try:
        kid, sec = load_keys()
        o = place_oto_stop(a.symbol, a.qty, a.stop_price, side=a.side, kid=kid, sec=sec)
    except ExecError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    legs = o.get("legs") or []
    print(f"[PAPER] {o.get('side')} {o.get('qty')} {o.get('symbol')} "
          f"id={o.get('id')} status={o.get('status')}")
    for leg in legs:
        print(f"  attached: {leg.get('type')} {leg.get('side')} "
              f"stop={leg.get('stop_price')} status={leg.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
