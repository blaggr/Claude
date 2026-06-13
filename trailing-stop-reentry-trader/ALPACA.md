# Paper-trade the rule on Alpaca

`alpaca_trader.py` runs the **same** trailing-stop / re-entry engine as the
backtest and `paper.py`, but instead of simulating fills it places **real paper
orders** on an Alpaca paper account: Alpaca's price feed in, market orders out,
fills and positions reconciled against the broker. Money is fake; the order
plumbing is real, which is the point of testing here.

**Paper by default. Live trading is locked behind two interlocks** (see Risk
controls). Nothing here can place a real-money order unless you deliberately
enable it.

## Setup (paper — no money involved)

1. Free account at <https://alpaca.markets> → dashboard → **Paper Trading** →
   generate API keys (they start with `PK`).
2. Export the keys and run the preflight check:

   ```bash
   pip install -r requirements.txt          # no new deps; stdlib urllib only
   export ALPACA_KEY_ID="PK..."             # paper keys
   export ALPACA_SECRET_KEY="..."
   python alpaca_trader.py --symbol SPY --check
   ```

   `--check` verifies the keys, prints account equity/cash, market open/closed,
   and the latest price, then exits. If that works, you're wired up.

3. Run it:

   ```bash
   python alpaca_trader.py --symbol SPY --trail 1.5 --reentry 1 --poll 60
   ```

   Every poll, signal, order, skip, and halt is one JSON line in
   `alpaca_journal.jsonl`. Engine state is persisted to `alpaca_state.json`, so
   you can stop (Ctrl-C) and resume — on restart it **reconciles against
   Alpaca's actual position** rather than re-buying.

## How it maps the rule to orders

The strategy is all-in / all-out in one symbol, and **the stop lives at the
broker**:

| Step | Order |
|---|---|
| Entry | market buy a whole-share slice of **cash** (`BUDGET_PCT`, default 95%, never margin), then immediately attach a resting **server-side trailing-stop sell** (`type=trailing_stop`, `trail_price=$trail`, GTC) |
| Exit  | the **broker** fires the trailing stop when price falls `$trail` below its peak — no client action needed |
| Re-entry | when flat, the client buys again once price rises `$reentry` above the last exit, and attaches a fresh stop |

Why server-side: the exit no longer depends on this process being alive and
winning a race. If the worker crashes, lags, or the network drops, the
protective stop is still resting at Alpaca. If the stop can't be attached after
a buy, the trader **flattens immediately** rather than hold a naked position. A
lagging position read only delays re-entry; it can't cause a double-buy (entries
are gated on the broker showing truly flat) or abandon a position.

## Risk controls (`risk.py`)

| Control | Default | Behavior |
|---|---|---|
| Mode | **PAPER** | Live needs `ALPACA_LIVE=1` **and** the ack file below |
| Kill switch | — | `touch KILL` (next to `risk.py`) → flatten the position and halt |
| Daily loss limit | 5% | Equity dropping 5% below the day's start → flatten, write `KILL`, halt |
| Position sizing | 95% of cash | Whole shares, off cash only — a restart can't stack leverage |
| Concurrency | 1 position | Reconciles to the broker before acting; restart-safe, no double-buy |
| Repeated broker errors | 5 | Bails instead of looping forever on a bad symbol / outage |

Tune with env vars: `BUDGET_PCT`, `MAX_DAILY_LOSS_PCT`.

## Going live (only after a real paper gate)

Do not skip the gate. Promote only after a meaningful paper run you've actually
read in the journal, and after rehearsing the kill switch and a restart while
holding a position. Then, deliberately:

```bash
export ALPACA_KEY_ID="AK..." ALPACA_SECRET_KEY="..."   # LIVE dashboard keys
export ALPACA_LIVE=1
echo "I UNDERSTAND THIS PLACES REAL ORDERS WITH REAL MONEY" > LIVE_TRADING_ENABLED
export BUDGET_PCT=5                                     # start tiny
python alpaca_trader.py --symbol SPY --trail 1.5 --reentry 1 --poll 60
```

Deleting `LIVE_TRADING_ENABLED` is the permanent off switch.

## What this is not

This automates order placement; it does not make the strategy good — the
backtests in [`RESULTS.md`](RESULTS.md) show it is a weak risk overlay, not an
alpha engine. Slippage, fees, and partial fills are real on a live account and
are not modeled in the engine. Not financial advice.

## Tests

The whole trader is covered offline by a fake in-memory broker — no network, no
account needed:

```bash
python -m pytest tests/test_alpaca_trader.py -q
```
