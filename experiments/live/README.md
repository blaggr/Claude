# Live news trader — runbook

The execution-grade version of the news strategy: an always-on worker that
polls Truth Social every 30s, classifies new posts with an LLM, and places
orders at **Alpaca** — entry ASAP after the post, trailing-stop decay exit,
flat by the calibrated boundary. **Paper trading by default**; real money only
behind deliberate interlocks.

## Why Alpaca and not TradingView

TradingView's automation only flows *out* of its charts (Pine alerts →
webhooks). There is no public API to push an external signal (a classified
news post) *into* TradingView and have it execute. Since this strategy's
signal originates from news, the executing connection must be a broker API.
Alpaca is the standard fit: free paper tier with the identical API as live,
REST, extended-hours orders, shorting. **TradingView's role here is the
monitoring cockpit** — make a watchlist of `USO GLD ITA SPY FXI KWEB` and
watch the same tape the worker trades; it is not the order router.

## Setup (paper — do this first, no money involved)

1. Create a free account at https://alpaca.markets → dashboard → **Paper
   Trading** → generate API keys.
2. On the machine that will run the worker (your Mac, or any small VPS):

   ```bash
   git clone https://github.com/blaggr/Claude.git && cd Claude
   python3 -m venv .venv && source .venv/bin/activate
   pip install pandas openai            # openai optional but strongly advised
   export ALPACA_KEY_ID="PK..."         # paper keys
   export ALPACA_SECRET_KEY="..."
   export OPENAI_API_KEY="sk-..."       # without an LLM key the worker runs
                                        # in SHADOW mode (signals, no orders)
   python experiments/live/live_trader.py
   ```

3. Watch `experiments/live/journal.jsonl` — every signal, entry, exit, skip,
   and alert is a JSON line. Optional push alerts: set `ALERT_WEBHOOK_URL`
   to a Slack/Discord webhook.

### Keep it running (your Mac)

`launchd` example — save as `~/Library/LaunchAgents/com.user.newstrader.plist`,
fill in paths/keys, then `launchctl load` it:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.user.newstrader</string>
  <key>ProgramArguments</key><array>
    <string>/PATH/TO/Claude/.venv/bin/python</string>
    <string>/PATH/TO/Claude/experiments/live/live_trader.py</string>
  </array>
  <key>EnvironmentVariables</key><dict>
    <key>ALPACA_KEY_ID</key><string>PK...</string>
    <key>ALPACA_SECRET_KEY</key><string>...</string>
    <key>OPENAI_API_KEY</key><string>sk-...</string>
  </dict>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/newstrader.log</string>
  <key>StandardErrorPath</key><string>/tmp/newstrader.log</string>
</dict></plist>
```

On a Linux VPS, the equivalent systemd unit: `ExecStart` the same command,
`Restart=always`, environment in an `EnvironmentFile`. **Do not run the
execution worker on GitHub Actions** — cron latency (5–30 min) destroys an
edge that decays in minutes, runners are ephemeral, and broker keys don't
belong in repo secrets. The daily-sim workflow stays as the benchmark; this
worker is a separate, always-on process.

## Risk controls (built in — `risk.py`)

| Control | Default | Behavior |
|---|---|---|
| Mode | **PAPER** | Live needs `ALPACA_LIVE=1` **and** the ack file (below) |
| Kill switch | — | `touch experiments/live/KILL` → flattens everything, halts |
| Daily loss limit | 5% | Breach → auto-flatten, kill switch trips, human must reset |
| Per-event budget | 25% of equity | Split across legs by edge weight, whole shares |
| Concurrency | 1 event | No stacking; idempotent client order ids; restart-safe reconcile |
| Classifier | LLM required | Keyword-only → SHADOW mode (no orders) unless `ALLOW_KEYWORD_CLASSIFIER=1` |
| Unknown positions | halt entries | Worker won't trade blind over positions it didn't open |

Entries are market orders in regular hours and marketable DAY limit orders in
extended hours (4:00–9:30 / 16:00–20:00 ET, per Alpaca's rules). Posts landing
while the venue is fully closed arm and enter at the next session — or expire
as MISSED if the calibrated boundary passes first, exactly like the sim.

## Going live (only after the paper gate)

Do not skip the gate. Promote only when **all** of these hold over ≥ 4 weeks
of paper trading:

- [ ] ≥ 10 settled events; win rate and average P&L in line with the sim
- [ ] Zero misclassified trades (read every SIGNAL line in the journal —
      day one of the sim bought oil on a military-*budget* post)
- [ ] Fill quality acceptable (compare journal entry prices to the post-time
      quotes; extended-hours spreads are wide)
- [ ] You've rehearsed the kill switch and a restart while a position was open

Then, deliberately:

```bash
# 1. Real-money keys from the live (not paper) dashboard
export ALPACA_KEY_ID="AK..." ALPACA_SECRET_KEY="..."
# 2. Both interlocks
export ALPACA_LIVE=1
echo "I UNDERSTAND THIS PLACES REAL ORDERS WITH REAL MONEY" \
  > experiments/live/LIVE_TRADING_ENABLED
# 3. Start small: cap the budget
export EVENT_BUDGET_PCT=5
python experiments/live/live_trader.py
```

Funding note: legs are whole shares (SPY ≈ $700+), so a live account under
roughly $2–5k will see legs skipped as dust. The worker logs every skip.

## What this is not

This automates order placement; it does not make the strategy good. The
calibration rests on 6–29 historical events, headline slippage is real, a
follow-up "ceasefire/deal" post can reverse a position violently, and the
live classifier has already misfired once. Expect losses; size accordingly.
Not financial advice.
