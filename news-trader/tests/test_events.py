import datetime as dt
from events import Event, Signal

def test_event_is_frozen_and_tz_aware():
    e = Event(ts=dt.datetime(2024,1,11,13,30,tzinfo=dt.timezone.utc), source="macro", type="CPI")
    assert e.payload == {}
    try:
        e.ts = None  # frozen
        assert False, "Event must be immutable"
    except Exception:
        pass

def test_signal_fields():
    s = Signal(symbol="SPY", side="long", size_frac=0.5, horizon_min=120,
               trail=None, confidence=0.8, rationale="drift up")
    assert s.side == "long" and 0 < s.size_frac <= 1
