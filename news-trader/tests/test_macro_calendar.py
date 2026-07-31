import os
import pytest
from macro_calendar import load_events
from events import Event

SAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")
EV = os.path.join(SAMPLE, "events.csv")

def test_loads_events_sorted_tz_aware():
    evs = load_events(EV)
    assert all(isinstance(e, Event) for e in evs)
    assert [e.type for e in evs] == ["CPI", "CPI", "CPI"]
    assert evs[0].ts.tzinfo is not None
    assert evs == sorted(evs, key=lambda e: e.ts)
    assert evs[0].payload["symbol"] == "SPY"

def test_bad_row_fails_loud(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("ts,type,symbol\nnot-a-date,CPI,SPY\n")
    with pytest.raises(ValueError):
        load_events(str(p))
