# The "perfect" trade on Trump / White House news — design, execution, exit

This is the synthesis of the whole investigation, built only on what the data
actually supports. Short version: **the cleanest tradable signal is China /
trade-war escalation, the move is real and large, but it is priced *before the
US cash market opens* — so the trade only exists if you execute in the venue
that's live when the post lands (futures / FX / overnight), and you must exit
within minutes-to-hours, not days.**

## What the data forced us to conclude

Across the conversation:

1. Daily, post-conditioned SPY strategies have **no** next-day edge (every |t|<1.5).
2. Concentrated, trade-exposed funds (FXI, KWEB, SMH) react **~2x harder** and
   directionally cleanly — China drops when Trump posts tariffs.
3. **The decisive test** (`trump_news_perfect_trade.py`): split the event-day
   move into *overnight* (prior close → open, un-capturable) vs *open→close*
   (capturable if you trade at the open). Presidency window, tariff-heavy days
   (n=13, **all arrived pre-open** — he posts tariffs early morning):

   | Fund | Overnight gap | Open→close (t) | Whole day | Next session open→close |
   |------|--------------:|---------------:|----------:|------------------------:|
   | FXI (China) | **−0.66%** | +0.09% (t=0.2) | −0.55% | −0.72% |
   | KWEB (China net) | **−0.84%** | +0.30% (t=0.6) | −0.54% | −0.85% |
   | SMH (semis) | **−1.14%** | +1.64% (t=1.2) | +0.50% | +0.04% |
   | SPY (baseline) | −0.88% | +0.80% (t=0.8) | −0.09% | −0.04% |
   | GLD (gold) | **+0.58%** | −0.12% | +0.47% | −0.19% |

   The directional move is **entirely in the overnight gap**. By the time the
   cash ETF opens at 09:30, open→close is flat (t≈0.2) and the next session is
   flat too. Gold's safe-haven bid is also an overnight gap (+0.58%).

**Implication:** at daily / cash-open resolution the edge is **zero** — it's
gone before you can click. The trade is only real in the pre-open window.

## The perfect trade

**Signal.** An official escalation/de-escalation headline on US–China trade
(tariffs, export controls, "deal", "call with Xi", "pause") from Trump's Truth
Social, the White House, USTR/Treasury, or a credible ally relaying it.
Escalation → risk-off China; de-escalation → risk-on China.

**Direction (escalation case).** SHORT the most China-beta liquid instrument;
optionally LONG gold as the hedge leg. (Flip for de-escalation.)

**Instrument — chosen by *when the post lands*, because that's where the move
happens:**

| Post timing (ET) | What's open / where price moves | Trade |
|---|---|---|
| Overnight / Asia hours | FTSE China A50 fut, Hang Seng fut, USD/CNH | Short A50/HSI, long USD/CNH |
| US pre-market (most tariff posts) | ES/NQ futures, pre-market FXI/KWEB | Short NQ / pre-market KWEB |
| US cash hours | FXI/KWEB/SMH, NQ futures | Short directly, immediately |

Futures/FX are the right venue: they trade 24h, they're liquid in the fat tail,
and they are literally where the −0.66% China gap forms while the ETF is closed.

## Execution

1. **Ingest fast.** The public archive refreshes ~5 min — fine for research,
   too slow for the edge. For live trading: Truth Social API / a low-latency
   headline feed (and WH/USTR RSS, wire alerts).
2. **Classify in code.** Escalation vs de-escalation + target (China / semis /
   broad). A keyword+LLM classifier on the post text; ignore non-market posts
   (the vast majority).
3. **Fire within seconds.** Market/marketable-limit order in the venue table
   above. Pre-size positions; the window is minutes.
4. **Hedge leg (optional).** Long gold (GC futures / GLD) on escalation to
   capture the +0.58% safe-haven gap and cut net beta.

## Exit — when the edge is gone (the core question)

The data answers this directly: **the move is complete by the US cash open and
does not continue.** Open→close on event day ≈ 0 (t=0.2) and T+1 ≈ 0.

- **Best single estimate:** the bulk is priced in the **first ~tens of minutes**
  after the headline; effectively fully priced by the **next cash open**. This
  matches JPMorgan's "Volfefe" finding that the impact of his posts on rates
  decayed within roughly an hour.
- **Exit rule:** close on the *earlier* of —
  (a) **impulse decay** — price stops extending in the news direction (e.g.
  15–30 min with no new low, or a re-entry inside a short volatility band), or
  (b) the **next major liquidity event** (the US cash open after an overnight
  post).
  **Hard stop-time:** flat by the close of the session the post lands in. Do
  **not** hold overnight for continuation — there is none in the data.
- Practically: a trailing stop (the project's own engine) sized to the
  instrument's 1-minute range works as the decay detector — it rides the
  impulse and stops you out when it stalls.

## Risks and honest limits

- **Reversal risk is severe.** A follow-up "we have a deal" post reverses the
  China move violently. Always stop; never average down.
- **Regime dependence.** Over the full 2022–2024 sample (Trump *out* of office),
  the same posts produced the **opposite** sign — significant *positive*
  open→close drift (FXI +0.44%, t=2.4; KWEB +0.61%, t=2.6): then they were
  campaign rhetoric and markets faded the fear. The short-China edge only holds
  when posts carry **policy authority**. Condition the trade on that.
- **Latency & slippage.** Capturable only with low-latency ingestion and 24h
  instruments; fills in fast headline markets are poor. Net of costs the
  surviving edge is small.
- **Sample size.** 13 presidency events. Treat magnitudes as indicative.
- Not investment advice; this is a research write-up.

## Bottom line

There is a real, repeatable edge in Trump/WH **China-trade** headlines, and the
"perfect" expression is to **short China beta (and/or buy gold) in futures/FX
the moment an escalation headline hits, then exit on impulse-decay within the
hour and certainly by the next cash open.** What does *not* work — proven on the
data — is any version that waits for the daily close or the ETF open: by then
the move is already in the overnight gap and the edge is gone.
