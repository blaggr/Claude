"""Tests for the scheduled FOMC/CPI module (no network)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "simulation"))

import macro_events as me  # noqa: E402


def test_event_kind_recognizes_fomc_and_cpi():
    assert me.event_kind("2025-06-18") == "FOMC"
    assert me.event_kind("2025-06-11") == "CPI"
    assert me.event_kind("2025-06-12") is None


def test_no_feed_is_shadow():
    out = me.check_today("2025-06-18", me.NullSurpriseSource())
    assert out["kind"] == "FOMC" and out["status"] == "shadow"
    assert "not traded" in out["note"]


def test_non_event_day_returns_none():
    assert me.check_today("2025-06-12", me.NullSurpriseSource()) is None


def test_hot_cpi_sells_risk_buys_dollar():
    out = me.check_today("2025-06-11", _FixedSource(+1))   # hot CPI
    assert out["status"] == "traded-ready" and out["label"] == "hawkish/hot"
    by = {l["instrument"]: l for l in out["legs"]}
    assert by["SPY"]["side"] == "SELL"     # hot -> equities down
    assert by["TLT"]["side"] == "SELL"     # hot -> yields up, bonds down
    assert by["UUP"]["side"] == "BUY"      # hot -> dollar up
    assert by["GLD"]["side"] == "SELL"


def test_dovish_fomc_flips_every_leg():
    hot = {l["instrument"]: l["side"] for l in me.plan_for_event("FOMC", +1)["legs"]}
    cool = {l["instrument"]: l["side"] for l in me.plan_for_event("FOMC", -1)["legs"]}
    assert all(hot[i] != cool[i] for i in hot)


def test_weights_normalize_and_sort_by_conviction():
    legs = me.plan_for_event("CPI", +1)["legs"]
    assert abs(sum(l["weight"] for l in legs) - 1.0) < 1e-6
    convict = [abs(l["expected_move_pct"]) * l["probability"] for l in legs]
    assert convict == sorted(convict, reverse=True)


def test_file_surprise_source(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"2025-06-11": {"CPI": -1}}))
    src = me.FileSurpriseSource(str(p))
    assert src.get_surprise("CPI", "2025-06-11") == -1.0
    assert src.get_surprise("CPI", "2025-06-12") is None
    out = me.check_today("2025-06-11", src)
    assert out["status"] == "traded-ready" and out["label"] == "dovish/cool"


def test_release_timestamps():
    assert str(me.release_timestamp("CPI", "2025-06-11")).startswith("2025-06-11 08:30")
    assert str(me.release_timestamp("FOMC", "2025-06-18")).startswith("2025-06-18 14:00")


class _FixedSource:
    def __init__(self, v): self.v = v
    def get_surprise(self, kind, date): return self.v
