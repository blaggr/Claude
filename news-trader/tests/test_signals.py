import os
from prices import load_bars
from macro_calendar import load_events
from signals import drift_signal

SAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")
SPY = os.path.join(SAMPLE, "SPY.csv")
EV = os.path.join(SAMPLE, "events.csv")

def test_up_reaction_gives_long():
    bars = load_bars(SPY)
    ev = load_events(EV)[0]               # 2024-01-11, up-drift fixture
    sig = drift_signal(ev, bars, delta_s=60, measure_min=10, horizon_min=30, trail=None)
    assert sig is not None
    assert sig.side == "long"
    assert sig.symbol == "SPY"
    assert sig.entry_ts is not None

def test_zero_reaction_returns_none():
    import pandas as pd
    flat = pd.DataFrame({"ts": pd.to_datetime(
        ["2024-01-11T13:30Z","2024-01-11T13:31Z","2024-01-11T13:45Z"], utc=True),
        "close": [470.0, 470.0, 470.0]})
    ev = load_events(EV)[0]
    assert drift_signal(ev, flat, delta_s=60, measure_min=10, horizon_min=30, trail=None) is None
