"""Unit tests for worker.py pure helpers — no IO, no network."""
from __future__ import annotations
import datetime as dt
import zoneinfo
import pytest

from worker import due_event, should_send_summary, build_summary
from events import Event

ET = zoneinfo.ZoneInfo("America/New_York")
UTC = dt.timezone.utc


def _ev(ts_utc: dt.datetime, symbol: str = "SPY", etype: str = "FOMC") -> Event:
    return Event(ts=ts_utc, source="macro", type=etype, payload={"symbol": symbol})


# ---------------------------------------------------------------------------
# due_event
# ---------------------------------------------------------------------------

class TestDueEvent:
    def _now(self, offset_min: float, base: dt.datetime) -> dt.datetime:
        return base + dt.timedelta(minutes=offset_min)

    def test_returns_event_within_window(self):
        release = dt.datetime(2024, 6, 12, 14, 0, tzinfo=UTC)
        ev = _ev(release)
        # 5 min after release, inside 20-min window
        now = release + dt.timedelta(minutes=5)
        result = due_event(now, [ev], set())
        assert result is ev

    def test_returns_event_at_exact_release_time(self):
        release = dt.datetime(2024, 6, 12, 14, 0, tzinfo=UTC)
        ev = _ev(release)
        result = due_event(release, [ev], set())
        assert result is ev

    def test_returns_event_at_window_boundary(self):
        release = dt.datetime(2024, 6, 12, 14, 0, tzinfo=UTC)
        ev = _ev(release)
        # exactly at the window boundary (ts + 20 min)
        now = release + dt.timedelta(minutes=20)
        result = due_event(now, [ev], set())
        assert result is ev

    def test_ignores_event_before_release(self):
        release = dt.datetime(2024, 6, 12, 14, 0, tzinfo=UTC)
        ev = _ev(release)
        # 1 second before release
        now = release - dt.timedelta(seconds=1)
        result = due_event(now, [ev], set())
        assert result is None

    def test_ignores_event_after_window(self):
        release = dt.datetime(2024, 6, 12, 14, 0, tzinfo=UTC)
        ev = _ev(release)
        # 21 minutes after release
        now = release + dt.timedelta(minutes=21)
        result = due_event(now, [ev], set())
        assert result is None

    def test_ignores_already_acted_event(self):
        release = dt.datetime(2024, 6, 12, 14, 0, tzinfo=UTC)
        ev = _ev(release)
        now = release + dt.timedelta(minutes=5)
        acted = {release.isoformat()}
        result = due_event(now, [ev], acted)
        assert result is None

    def test_acts_only_once_within_window(self):
        release = dt.datetime(2024, 6, 12, 14, 0, tzinfo=UTC)
        ev = _ev(release)
        now = release + dt.timedelta(minutes=5)
        # First call — not yet acted
        r1 = due_event(now, [ev], set())
        assert r1 is ev
        # Simulate recording the action
        acted = {release.isoformat()}
        # Second call — already acted
        r2 = due_event(now, [ev], acted)
        assert r2 is None

    def test_returns_first_unacted_event(self):
        t1 = dt.datetime(2024, 6, 12, 14, 0, tzinfo=UTC)
        t2 = dt.datetime(2024, 6, 12, 15, 0, tzinfo=UTC)
        ev1 = _ev(t1, symbol="SPY")
        ev2 = _ev(t2, symbol="QQQ")
        now = t1 + dt.timedelta(minutes=5)
        # Only t1 is within window at this time
        result = due_event(now, [ev1, ev2], set())
        assert result is ev1

    def test_empty_events_list(self):
        now = dt.datetime(2024, 6, 12, 14, 0, tzinfo=UTC)
        assert due_event(now, [], set()) is None

    def test_custom_react_window(self):
        release = dt.datetime(2024, 6, 12, 14, 0, tzinfo=UTC)
        ev = _ev(release)
        # 25 min after release — outside default 20 min but inside 30 min
        now = release + dt.timedelta(minutes=25)
        assert due_event(now, [ev], set(), react_window_min=20) is None
        assert due_event(now, [ev], set(), react_window_min=30) is ev


# ---------------------------------------------------------------------------
# should_send_summary
# ---------------------------------------------------------------------------

class TestShouldSendSummary:
    def _et(self, year: int, month: int, day: int,
            hour: int, minute: int) -> dt.datetime:
        return dt.datetime(year, month, day, hour, minute,
                           tzinfo=ET)

    def test_weekday_after_time_no_prior_summary(self):
        # Wednesday 10:00 ET — should send
        now = self._et(2024, 6, 12, 10, 0)
        assert should_send_summary(now, None) is True

    def test_weekday_exactly_at_cutoff(self):
        now = self._et(2024, 6, 12, 9, 35)
        assert should_send_summary(now, None) is True

    def test_weekday_before_cutoff(self):
        now = self._et(2024, 6, 12, 9, 0)
        assert should_send_summary(now, None) is False

    def test_weekday_one_minute_before_cutoff(self):
        now = self._et(2024, 6, 12, 9, 34)
        assert should_send_summary(now, None) is False

    def test_already_sent_today(self):
        now = self._et(2024, 6, 12, 10, 0)
        assert should_send_summary(now, now.date()) is False

    def test_sent_yesterday_resends_today(self):
        now = self._et(2024, 6, 12, 10, 0)
        yesterday = (now - dt.timedelta(days=1)).date()
        assert should_send_summary(now, yesterday) is True

    def test_saturday_no_send(self):
        # 2024-06-15 is a Saturday
        now = self._et(2024, 6, 15, 10, 0)
        assert should_send_summary(now, None) is False

    def test_sunday_no_send(self):
        # 2024-06-16 is a Sunday
        now = self._et(2024, 6, 16, 10, 0)
        assert should_send_summary(now, None) is False

    def test_custom_after_time(self):
        now = self._et(2024, 6, 12, 9, 40)
        # 09:40 >= 09:35 -> True
        assert should_send_summary(now, None, after="09:35") is True
        # 09:40 < 10:00 -> False
        assert should_send_summary(now, None, after="10:00") is False


# ---------------------------------------------------------------------------
# build_summary
# ---------------------------------------------------------------------------

class TestBuildSummary:
    _ACCOUNT = {"equity": "100000.00", "cash": "99500.00"}
    _FOOTER_FRAGMENT = "Paper trading only"

    def test_subject_contains_paper_and_date(self):
        subject, _ = build_summary(self._ACCOUNT, [], [], [])
        assert "[paper]" in subject
        assert "news-trader" in subject

    def test_body_contains_equity(self):
        _, body = build_summary(self._ACCOUNT, [], [], [])
        assert "100000.00" in body

    def test_body_contains_footer(self):
        _, body = build_summary(self._ACCOUNT, [], [], [])
        assert self._FOOTER_FRAGMENT in body
        assert "no demonstrated edge" in body

    def test_body_no_real_money_disclaimer(self):
        _, body = build_summary(self._ACCOUNT, [], [], [])
        assert "no real money" in body

    def test_positions_listed(self):
        positions = [{"symbol": "SPY", "qty": "1", "side": "long",
                      "unrealized_pl": "25.50"}]
        _, body = build_summary(self._ACCOUNT, positions, [], [])
        assert "SPY" in body
        assert "25.50" in body

    def test_no_positions_message(self):
        _, body = build_summary(self._ACCOUNT, [], [], [])
        assert "none" in body.lower()

    def test_journal_entries_shown(self):
        journal = [{"ts": "2024-06-12T14:00:00+00:00", "event": "BUY",
                    "detail": "SPY entry"}]
        _, body = build_summary(self._ACCOUNT, [], journal, [])
        assert "BUY" in body

    def test_todays_events_listed(self):
        ev = _ev(dt.datetime(2024, 6, 12, 14, 0, tzinfo=UTC))
        _, body = build_summary(self._ACCOUNT, [], [], [ev])
        assert "FOMC" in body

    def test_no_events_message(self):
        _, body = build_summary(self._ACCOUNT, [], [], [])
        assert "none" in body.lower()

    def test_journal_limited_to_10(self):
        # Create 15 entries; only last 10 should appear
        journal = [{"ts": f"2024-06-12T{i:02d}:00:00+00:00", "event": f"EV{i}"}
                   for i in range(15)]
        _, body = build_summary(self._ACCOUNT, [], journal, [])
        # EV0..EV4 are dropped; EV5..EV14 appear
        assert "EV14" in body
        assert "EV4" not in body
