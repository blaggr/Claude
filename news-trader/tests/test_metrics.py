from metrics import summarize
from backtest import Result, Trade
import datetime as dt

def _t(ret):
    z = dt.datetime(2024,1,1,tzinfo=dt.timezone.utc)
    return Trade(z,"SPY","long",z,100,z,100*(1+ret),ret,"horizon",1.0)

def test_summary_keys_and_hit_rate():
    res = Result(trades=[_t(0.02), _t(-0.01), _t(0.03)], initial_capital=1000,
                 final_equity=1000*1.02*0.99*1.03)
    s = summarize(res)
    for k in ("total_return","sharpe","max_drawdown","hit_rate","n_trades"):
        assert k in s
    assert s["n_trades"] == 3
    assert abs(s["hit_rate"] - 2/3) < 1e-9

def test_benchmark_gives_vs_buyhold():
    res = Result(trades=[_t(0.02)], initial_capital=1000, final_equity=1020.0)
    s = summarize(res, benchmark_return=0.05)        # strategy +2% vs B&H +5%
    assert abs(s["buy_hold_return"] - 0.05) < 1e-9
    assert s["vs_buyhold"] < 0                        # underperformed B&H

def test_no_trades_is_safe():
    s = summarize(Result(trades=[], initial_capital=1000, final_equity=1000))
    assert s["n_trades"] == 0 and s["total_return"] == 0.0
