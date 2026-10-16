import os, datetime as dt
import pytest
from prices import load_bars, first_at_or_after, PriceError

SAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")
SPY = os.path.join(SAMPLE, "SPY.csv")

def _ts(s): return dt.datetime.fromisoformat(s)

def test_first_at_or_after_returns_first_bar_not_before():
    bars = load_bars(SPY)
    # 2024-01-11T13:31:00Z exists in fixture (close 470.20); querying at exactly
    # that timestamp returns it — "at or after" includes the boundary.
    ts, px = first_at_or_after(bars, _ts("2024-01-11T13:31:00+00:00"))
    assert ts == _ts("2024-01-11T13:31:00+00:00")
    assert px == 470.20

def test_missing_window_fails_loud():
    bars = load_bars(SPY)
    with pytest.raises(PriceError):
        first_at_or_after(bars, _ts("2099-01-01T00:00:00+00:00"))
