# macOS Deployment Runbook — news-trader paper worker

## Read this first (no skipping)

**a) Paper trading only.** This worker places orders exclusively on Alpaca's paper
trading endpoint (`paper-api.alpaca.markets`). No real money is ever involved. The
code physically refuses any non-paper base URL.

**b) The signal has no demonstrated edge.** The drift signal failed its backtest gate:
it did not clear the minimum Sharpe / win-rate bar required to trade real capital. This
deployment is an operational and plumbing test — verifying that the pipeline (event
detection, bar fetch, signal, order placement, state persistence, email) works end to
end. Do not read any paper trading profits or losses as evidence of a real edge.

**c) FOMC happens ~8 times per year and almost never on a Monday.** The events CSV you
populate must come from the official Federal Reserve calendar. Most mornings the
summary email will say "Events scheduled today: none." Seeing a long stretch of
nothing is expected and correct — the worker is simply waiting for the next release.

**d) The Mac must be awake.** launchd keeps the worker running only while your machine
is on and awake. A 2 PM FOMC announcement will be missed if the Mac is asleep at
that time. No partial mitigation is applied — if you need reliability, run on a
remote server instead.

**e) You need two credentials before starting:**
  - An **Alpaca paper key pair** (Key ID + Secret Key). Create one at
    https://app.alpaca.markets under "Paper Trading" > "API Keys". Paper keys look
    identical to live keys but only work against the paper endpoint.
  - A **Gmail App Password** (or equivalent SMTP credential). This is a 16-character
    one-time code generated at https://myaccount.google.com/apppasswords — NOT your
    normal Google password. Two-factor authentication must be enabled on the Google
    account before App Passwords are available. The plist label says "App Password"
    as a reminder.

**f) Kill switch.** To stop the worker gracefully without touching launchd:

    touch /path/to/news-trader/KILL

The worker checks for this file at the start of each 30-second cycle and exits
cleanly. launchd will then restart it (KeepAlive=true), so if you want it to stay
stopped, also unload the plist (see step 8 below) or delete the plist from
`~/Library/LaunchAgents/`.

---

## Exact steps

### 1. Populate the events CSV from the official Fed schedule

The worker reads `news-trader/sample_data/events.csv`. The format is:

```
ts,type,symbol
2024-09-18T18:00:00+00:00,FOMC,SPY
2024-11-07T19:00:00+00:00,FOMC,SPY
```

**Do not guess at release times.** Get the exact UTC datetimes from the official
Federal Reserve calendar: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm

FOMC rate decisions are typically released at 2:00 PM ET (19:00 or 18:00 UTC,
depending on daylight saving time). Convert each date yourself; do not rely on
a tool or model to guess the time.

### 2. Fill the plist

Open `deploy/com.user.newstrader.plist` and replace every placeholder:

| Placeholder | What to put |
|---|---|
| `<ABSOLUTE PATH TO news-trader DIR>` | Full path, e.g. `/Users/rob/projects/news-trader` |
| `<FILL ME: your Alpaca paper key ID>` | Your Alpaca paper key ID |
| `<FILL ME: your Alpaca paper secret key>` | Your Alpaca paper secret key |
| `<FILL ME: your Gmail address>` | e.g. `rob@gmail.com` |
| `<FILL ME: your Gmail App Password>` | The 16-char App Password (no spaces) |
| `<FILL ME: sender address>` | Usually the same Gmail address |
| `<FILL ME: recipient address>` | Where you want the daily email |

Save the file.

### 3. Copy the plist to LaunchAgents

```bash
bash deploy/install_mac.sh
```

The script copies the plist but does NOT load it. It will warn you if any
placeholders are still unfilled.

### 4. Load the agent

```bash
launchctl load ~/Library/LaunchAgents/com.user.newstrader.plist
```

### 5. Verify it started

```bash
launchctl list | grep newstrader
tail -f /tmp/newstrader.log
```

The log should show a `worker_start` journal entry within a few seconds. If
the process exits immediately, check the log for a credential error (missing
`ALPACA_KEY_ID` / `SMTP_USER` etc.).

### 6. Check the daily summary email

The first summary email arrives at or after 9:35 AM ET on the next weekday.
Subject line: `[paper] news-trader summary YYYY-MM-DD`.
The body will list account equity, open positions (likely none), the last 10
journal entries, and any events scheduled that day.

### 7. Graceful stop (kill switch)

```bash
touch /path/to/news-trader/KILL
```

Remove the file if you want the worker to resume:

```bash
rm /path/to/news-trader/KILL
```

### 8. Permanent stop (unload the agent)

```bash
launchctl unload ~/Library/LaunchAgents/com.user.newstrader.plist
```

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Process exits immediately | `tail /tmp/newstrader.log` — usually a missing credential |
| "state_load_failed" in journal | `worker_state.json` is corrupt or missing — harmless, fresh state was used |
| No email arriving | Check `SMTP_USER`/`SMTP_PASS` in plist; confirm Gmail App Password (not normal password); check spam folder |
| "events_load_failed" in journal | The events CSV path is wrong or the CSV is malformed |
| "trade_error" in journal | Alpaca paper key may be wrong, or the market is closed (orders are rejected outside market hours) |
| Worker keeps restarting | Remove the KILL file if present; check the journal for `exit_too_many_failures` — this means 20 consecutive cycle errors |
