"""Streamlit UI for the trailing-stop / re-entry strategy.

    streamlit run app.py

Pick any stock or index-fund ticker, set the trailing-stop distance and the
re-entry trigger (in dollars), and backtest the rule over historical data. The
app charts price with the live stop / re-entry lines, marks every buy and sell,
plots the equity curve against buy-and-hold, and lists each trade. A second tab
explains how to leave the rule running live in paper-sim mode.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import data as data_mod
from strategy import StrategyParams, run_backtest

st.set_page_config(page_title="Trailing-Stop / Re-entry Trader", page_icon=":chart_with_upwards_trend:", layout="wide")


@st.cache_data(show_spinner=False)
def _fetch(ticker: str, period: str, interval: str) -> pd.DataFrame:
    return data_mod.fetch_ohlcv(ticker, period=period, interval=interval)


@st.cache_data(show_spinner=False)
def _synthetic() -> pd.DataFrame:
    return data_mod.synthetic_ohlcv()


def price_chart(result, df: pd.DataFrame):
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=result.price.index, y=result.price.values,
                             name="Close", line=dict(color="#3b6ea5", width=1.5)))
    fig.add_trace(go.Scatter(x=result.stop_line.index, y=result.stop_line.values,
                             name="Trailing stop", line=dict(color="#d1495b", width=1, dash="dot")))
    fig.add_trace(go.Scatter(x=result.trigger_line.index, y=result.trigger_line.values,
                             name="Re-entry trigger", line=dict(color="#2a9d8f", width=1, dash="dot")))

    fig.add_trace(go.Scatter(
        x=[t.entry_time for t in result.trades], y=[t.entry_price for t in result.trades],
        mode="markers", name="Buy", marker=dict(symbol="triangle-up", size=11, color="#2a9d8f"),
    ))
    sells = [t for t in result.trades if t.exit_time is not None]
    fig.add_trace(go.Scatter(
        x=[t.exit_time for t in sells], y=[t.exit_price for t in sells],
        mode="markers", name="Sell (stopped)", marker=dict(symbol="triangle-down", size=11, color="#d1495b"),
    ))
    fig.update_layout(height=460, margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02))
    return fig


def equity_chart(result):
    import plotly.graph_objects as go

    bh = result.initial_capital * (result.price / result.price.iloc[0])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=result.equity.index, y=result.equity.values,
                             name="Strategy", line=dict(color="#264653", width=2)))
    fig.add_trace(go.Scatter(x=bh.index, y=bh.values,
                             name="Buy & hold", line=dict(color="#9aa0a6", width=1.5, dash="dash")))
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02))
    return fig


# ---------------- Sidebar: instrument + parameters ----------------
with st.sidebar:
    st.markdown("### Instrument")
    source = st.radio("Data source", ["Yahoo Finance", "Synthetic (offline demo)"], index=0)
    ticker = st.text_input("Ticker", value="SPY", help="Any stock, ETF or index fund — e.g. AAPL, SPY, VTI, ^GSPC")
    colp = st.columns(2)
    with colp[0]:
        period = st.selectbox("Period", ["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"], index=3)
    with colp[1]:
        interval = st.selectbox("Interval", ["1d", "1h", "30m", "15m", "5m", "1wk"], index=0)

    st.markdown("### Strategy")
    trail = st.number_input("Trailing stop ($)", min_value=0.01, value=2.0, step=0.25,
                            help="Sell when price falls this many dollars below its peak since entry.")
    reentry = st.number_input("Re-entry trigger ($ up)", min_value=0.0, value=1.0, step=0.25,
                              help="After a stop-out, buy back when price rises this many dollars above the exit price.")
    capital = st.number_input("Starting capital ($)", min_value=100.0, value=10_000.0, step=1000.0)
    close_only = st.checkbox("Decide on close only", value=False,
                             help="Off = use intrabar highs/lows (more realistic). On = close-to-close.")
    no_start_entry = st.checkbox("Wait for first trigger", value=False,
                                 help="Don't buy on the first bar; wait for a re-entry trigger.")

st.title("Trailing-Stop / Re-entry Trader")
st.caption("Backtest a trailing stop-loss with an automatic re-entry rule on any stock or index fund. "
           "Paper/simulation only — no real orders are placed.")

tab_bt, tab_live = st.tabs(["Backtest", "Live paper sim"])

with tab_bt:
    run = st.button("Run backtest", type="primary")
    if run:
        try:
            df = _synthetic() if source.startswith("Synthetic") else _fetch(ticker.strip(), period, interval)
        except Exception as exc:
            st.error(f"Could not load data: {exc}")
            st.stop()

        params = StrategyParams(trail=trail, reentry=reentry,
                                use_intrabar=not close_only, enter_at_start=not no_start_entry)
        try:
            result = run_backtest(df, params, initial_capital=capital)
        except Exception as exc:
            st.error(f"Backtest failed: {exc}")
            st.stop()

        s = result.summary()
        label = "Synthetic series" if source.startswith("Synthetic") else ticker.upper()
        st.markdown(f"#### {label} — {len(df)} bars")

        c = st.columns(4)
        delta = s["total_return_pct"] - s["buy_hold_return_pct"]
        c[0].metric("Strategy return", f"{s['total_return_pct']:.2f}%", f"{delta:+.2f}% vs B&H")
        c[1].metric("Final equity", f"${s['final_equity']:,.0f}")
        c[2].metric("Trades", s["num_trades"])
        c[3].metric("Win rate", f"{s['win_rate_pct']:.0f}%")
        c2 = st.columns(4)
        c2[0].metric("Buy & hold", f"{s['buy_hold_return_pct']:.2f}%")
        c2[1].metric("Max drawdown", f"{s['max_drawdown_pct']:.2f}%")
        c2[2].metric("Avg trade", f"{s['avg_trade_return_pct']:.2f}%")
        c2[3].metric("Time in market", f"{s['exposure_pct']:.0f}%")

        try:
            st.plotly_chart(price_chart(result, df), use_container_width=True)
            st.plotly_chart(equity_chart(result), use_container_width=True)
        except ImportError:
            st.line_chart(result.price)
            st.line_chart(result.equity)
            st.info("Install plotly for the richer chart with buy/sell markers.")

        st.markdown("#### Trades")
        rows = []
        for t in result.trades:
            rows.append({
                "Entry": str(t.entry_time),
                "Entry $": round(t.entry_price, 2),
                "Exit": "open" if t.exit_time is None else str(t.exit_time),
                "Exit $": None if t.exit_price is None else round(t.exit_price, 2),
                "Return %": round(t.return_pct * 100, 2),
                "P&L $": round(t.pnl, 2),
                "Bars": t.bars_held,
                "Reason": t.exit_reason,
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No trades were generated for these parameters.")
    else:
        st.info("Set your instrument and parameters in the sidebar, then click **Run backtest**.")

with tab_live:
    st.markdown("#### Leave the rule running live (paper)")
    st.write(
        "The live loop runs as a standalone script so it can poll prices for hours "
        "without tying up the browser. It uses the **same** trailing-stop / re-entry "
        "engine and logs simulated fills — it never places a real order."
    )
    st.code(
        f"python paper.py --ticker {ticker.strip() or 'SPY'} "
        f"--trail {trail:g} --reentry {reentry:g} --poll 60",
        language="bash",
    )
    st.caption(
        "Fills are appended to `paper_trades.csv` and engine state is saved to "
        "`paper_state.json` so you can stop (Ctrl-C) and resume without losing the position. "
        "Markets must be open for live prices to update."
    )
    st.warning(
        "This is a simulation for learning and strategy validation. Wiring it to a real "
        "brokerage to trade actual money is a separate, deliberate step with real financial "
        "risk — not enabled here."
    )
