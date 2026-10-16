import os
from prices import load_bars
from macro_calendar import load_events
from costs import CostModel
from validate import walk_forward, gate

SAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")
SPY = os.path.join(SAMPLE, "SPY.csv")
EV = os.path.join(SAMPLE, "events.csv")

def test_walk_forward_reports_train_and_test_and_counts():
    events = load_events(EV)
    bars = {"SPY": load_bars(SPY)}
    grid = [{"delta_s":60,"measure_min":10,"horizon_min":30,"trail":None},
            {"delta_s":60,"measure_min":5,"horizon_min":60,"trail":None}]
    rep = walk_forward(events, bars, grid, CostModel(2,1), train_frac=0.66)
    assert rep["n_configs"] == 2
    assert rep["n_train"] >= 1 and rep["n_test"] >= 1
    assert "test" in rep and "sharpe" in rep["test"]
    assert "passed" in rep

def test_gate_requires_n_sharpe_dd_and_beating_buyhold():
    strong_small = {"sharpe":2.0,"max_drawdown":-0.05,"vs_buyhold":0.10,"n_trades":3}
    assert gate(strong_small, min_sharpe=0.8, max_dd=-0.25, min_n=20) is False   # n too small
    strong_big = {"sharpe":2.0,"max_drawdown":-0.05,"vs_buyhold":0.10,"n_trades":30}
    assert gate(strong_big, min_sharpe=0.8, max_dd=-0.25, min_n=20) is True
    loses = {"sharpe":2.0,"max_drawdown":-0.05,"vs_buyhold":-0.02,"n_trades":30}
    assert gate(loses, min_sharpe=0.8, max_dd=-0.25, min_n=20) is False           # lost to B&H
