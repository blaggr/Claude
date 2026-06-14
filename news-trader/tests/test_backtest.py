import os
from prices import load_bars
from macro_calendar import load_events
from signals import drift_signal
from costs import CostModel
from backtest import run_backtest

SAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")
SPY = os.path.join(SAMPLE, "SPY.csv")
EV = os.path.join(SAMPLE, "events.csv")

def test_backtest_produces_trades_and_costs_reduce_return():
    events = load_events(EV)
    bars = {"SPY": load_bars(SPY)}
    classify = lambda ev, b: drift_signal(ev, b, delta_s=60, measure_min=10,
                                           horizon_min=30, trail=None)
    res_free = run_backtest(events, bars, classify, CostModel(0, 0), capital=1000.0)
    res_cost = run_backtest(events, bars, classify, CostModel(5, 5), capital=1000.0)
    assert len(res_free.trades) >= 1
    assert res_cost.final_equity <= res_free.final_equity
