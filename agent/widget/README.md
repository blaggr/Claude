# Menu-bar widget (SwiftBar)

A always-visible menu-bar readout of the live agent: equity, today's P&L, open
positions, whether it's running, and the last trade — with a dropdown for
details and quick actions (open the Alpaca dashboard, view the log, stop, KILL).

It's read-only: `status.py` reads your local state + the broker and prints
SwiftBar format; it never trades.

```
📈 $99,812  ▲0.21%        ← menu bar
├─ Mode: PAPER
├─ Equity: $99,812.40 · cash $90,011.02
├─ Today: +0.21%
├─ Running ✓ (last poll 12s ago)
├─ Open positions: 1
│   └ SPY -4 @ 600.00
├─ Last: exit GLD pnl 3.10 (trailing_stop)
├─ Open Alpaca paper dashboard
├─ View log
├─ Stop agent
└─ 🛑 KILL — flatten & halt
```

## Install (on your Mac)

1. Install SwiftBar:
   ```
   brew install --cask swiftbar
   ```
2. Launch **SwiftBar** → it asks for a **Plugin Folder**. Pick (or make) a
   dedicated one, e.g.:
   ```
   mkdir -p ~/SwiftBarPlugins
   ```
3. Symlink this plugin into that folder and make it executable:
   ```
   chmod +x ~/Claude/agent/widget/tradingagent.30s.sh
   ln -s ~/Claude/agent/widget/tradingagent.30s.sh ~/SwiftBarPlugins/
   ```
   (Symlink, don't copy — that way `git pull` updates keep it current.)
4. In SwiftBar, set the Plugin Folder to `~/SwiftBarPlugins` if you haven't, then
   **Refresh**. The status item appears in your menu bar and updates every 30s.

> Do **not** point SwiftBar's plugin folder directly at `agent/widget/` — it
> would also try to run `status.py`. Use a dedicated folder with just the
> symlink, as above.

## How it finds things

`tradingagent.30s.sh` sources `~/Claude/agent/deploy/agent.env` (for the Alpaca
keys) and runs `status.py` with `~/Claude/.venv`'s Python. If your repo or venv
lives elsewhere, set these in the plugin (or your shell):

```
TRADING_AGENT_REPO=/path/to/Claude
TRADING_AGENT_VENV=/path/to/venv
```

"Running" is driven by a `heartbeat` file the live driver touches every poll, so
the widget shows green only while `live_agent` is actually looping.

## Other front-ends

`status.py` (no flag) prints JSON, so the same data feeds Übersicht, a Stream
Deck button, a cron e-mail, etc. Run `python agent/widget/status.py` to see it.
