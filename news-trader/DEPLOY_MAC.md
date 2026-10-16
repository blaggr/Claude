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
    account before App Passwords are available.

  Both go in `news-trader/.env.local` — a `chmod 600`, gitignored file read at launch.
  Credentials never go in the plist and never go in git.

**f) Kill switch.** To stop the worker gracefully without touching launchd:

    touch /path/to/news-trader/KILL

The worker checks for this file at the start of each 30-second cycle and exits
cleanly. launchd will then restart it (KeepAlive=true), so if you want it to stay
stopped, also unload the plist (see step 8 below) or delete the plist from
`~/Library/LaunchAgents/`.

**g) No horizon exit — protective stop only.** When an event fires, the worker places
a market entry plus a single 0.5% protective stop (server-side, atomic OTO). It does
NOT place a time-based exit at the 30-minute horizon, unlike the backtest. The stop is
a day order, so a position that never hits its stop is held to market close and may
carry **overnight with no stop attached**. This is a deliberate Phase-1 simplification
— server-side execution only, no hand-rolled client-side exit loop (that loop was the
source of the earlier execution failures). The morning email lists any open position;
flatten it manually in the Alpaca paper dashboard if you don't want it held. At ~8
paper trades a year, this is a known low-stakes limitation, not a silent gap.

---

## Prerequisite: code, a venv with pandas, and a credentials file

This package currently lives on the `claude/admin-news-trader` branch of
`github.com/blaggr/Claude`. On your Mac:

```bash
git clone --branch claude/admin-news-trader --single-branch \
  https://github.com/blaggr/Claude.git ~/Claude
cd ~/Claude/news-trader
```

The worker imports **pandas**. The system `/usr/bin/python3` may or may not have it,
so create an isolated virtualenv and install pandas there (run.sh points at this venv):

```bash
/usr/bin/python3 -m venv .venv
.venv/bin/pip install pandas
```

Create your credentials file from the template and lock it down:

```bash
cp .env.local.example .env.local
chmod 600 .env.local
# then edit .env.local and fill in the 4 secret/email values (see step 2)
```

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
a tool or model to guess the time. Without this file the worker still runs — it
just never trades and the email says "Events scheduled today: none."

### 2. Put your credentials in `.env.local`

Edit `~/Claude/news-trader/.env.local` and fill in:

```
ALPACA_KEY_ID=PKyourPaperKeyID
ALPACA_SECRET_KEY=yourPaperSecret
SMTP_USER=youremail@gmail.com
SMTP_PASS=your16charAppPassword
MAIL_FROM=youremail@gmail.com
MAIL_TO=where-you-want-the-summary@example.com
```

`SMTP_USER`/`SMTP_PASS`/`MAIL_FROM` are the Gmail you send *from* plus its App
Password (UCLA Workspace often blocks App Passwords — use a personal Gmail there).
`MAIL_TO` is where the daily summary lands. Save the file.

### 3. Fill the plist paths

Open `deploy/com.user.newstrader.plist` and replace both occurrences of
`/ABSOLUTE/PATH/TO/news-trader` with the real path, e.g.
`/Users/you/Claude/news-trader`. (No credentials go here — they're in `.env.local`.)

### 4. Install and load

```bash
bash deploy/install_mac.sh        # copies the plist to ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.user.newstrader.plist
```

If `launchctl load` errors on your macOS version, use:
`launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.user.newstrader.plist`

### 5. Verify it started

```bash
launchctl list | grep newstrader
tail -f /tmp/newstrader.log
```

The log should show a `worker_start` journal entry within a few seconds. If the
process exits immediately, check the log for a credential error (missing
`ALPACA_KEY_ID` / `SMTP_USER` etc. means `.env.local` isn't filled or isn't found).

### 6. Check the daily summary email

The first summary email arrives at or after 9:35 AM ET on the next weekday.
Subject line: `[paper] news-trader summary YYYY-MM-DD`.
The body lists account equity, open positions (likely none), the last 10 journal
entries, and any events scheduled that day.

### 7. Graceful stop (kill switch)

```bash
touch ~/Claude/news-trader/KILL    # worker exits at the next cycle
rm ~/Claude/news-trader/KILL       # allow it to resume
```

### 8. Permanent stop (unload the agent)

```bash
launchctl unload ~/Library/LaunchAgents/com.user.newstrader.plist
```

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Process exits immediately | `tail /tmp/newstrader.log` — usually missing creds in `.env.local`, or `.venv` has no pandas |
| `ModuleNotFoundError: pandas` | The venv lacks pandas — `~/Claude/news-trader/.venv/bin/pip install pandas` |
| "state_load_failed" in journal | `worker_state.json` corrupt/missing — harmless, fresh state was used |
| No email arriving | Check `SMTP_USER`/`SMTP_PASS` in `.env.local`; confirm a Gmail App Password (not normal password); check spam folder |
| "events_load_failed" in journal | The events CSV path is wrong or the CSV is malformed |
| "trade_error" in journal | Alpaca paper key may be wrong, or the market is closed (orders rejected outside market hours) |
| Worker keeps restarting | Remove the KILL file if present; check the journal for `exit_too_many_failures` (20 consecutive cycle errors) |
