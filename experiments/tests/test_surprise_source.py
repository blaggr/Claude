"""Tests for surprise_source (pure stdlib; NO pandas, macro_events, daily_sim).

Verifies the consensus/surprise data sources used to gate macro-event trading:
FileSurpriseSource (JSON + CSV), ManualSurpriseSource, sign convention for hot
vs cool CPI, and graceful None on missing entries / files.
"""
import json
import os
import sys
import tempfile

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "simulation"),
)

import surprise_source as ss  # noqa: E402


def _write(tmpdir, name, text):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


# ---------------------------------------------------------------- sanity guards

def test_no_pandas_imported():
    assert "pandas" not in sys.modules


def test_interface_method_present():
    # Mirrors macro_events.SurpriseSource: get_surprise(kind, date) -> float|None
    for cls in (ss.FileSurpriseSource, ss.ManualSurpriseSource):
        assert hasattr(cls, "get_surprise")


# ---------------------------------------------------------------- compute logic

def test_compute_surprise_hot_cpi_positive():
    # actual above consensus -> hawkish/hot -> positive
    s = ss.compute_surprise("CPI", consensus=3.2, actual=3.5)
    assert s > 0


def test_compute_surprise_cool_cpi_negative():
    s = ss.compute_surprise("CPI", consensus=3.4, actual=3.1)
    assert s < 0


def test_compute_surprise_inline_zero():
    assert ss.compute_surprise("CPI", 3.0, 3.0) == 0.0


def test_compute_surprise_magnitude_normalized():
    # diff 0.4 / scale 0.2 == 2.0
    s = ss.compute_surprise("CPI", consensus=3.0, actual=3.4)
    assert abs(s - 2.0) < 1e-9


def test_compute_surprise_magnitude_capped():
    s = ss.compute_surprise("CPI", consensus=0.0, actual=100.0)
    assert s == ss._MAX_MAGNITUDE


# ------------------------------------------------------- FileSurpriseSource JSON

def test_file_json_hot_and_cool_cpi():
    with tempfile.TemporaryDirectory() as d:
        data = {
            "2025-06-11": {"CPI": {"consensus": 3.2, "actual": 3.5}},
            "2025-05-13": {"CPI": {"consensus": 3.4, "actual": 3.1}},
        }
        path = _write(d, "surprises.json", json.dumps(data))
        src = ss.FileSurpriseSource(path)

        hot = src.get_surprise("CPI", "2025-06-11")
        cool = src.get_surprise("CPI", "2025-05-13")

        assert hot is not None and hot > 0
        assert cool is not None and cool < 0
        # hot diff 0.3/0.2 = 1.5 ; cool diff -0.3/0.2 = -1.5
        assert abs(hot - 1.5) < 1e-9
        assert abs(cool + 1.5) < 1e-9


def test_file_json_terse_shape():
    with tempfile.TemporaryDirectory() as d:
        path = _write(d, "t.json", json.dumps({"2025-06-11": {"CPI": -0.5}}))
        src = ss.FileSurpriseSource(path)
        assert src.get_surprise("CPI", "2025-06-11") == -0.5


def test_file_json_fomc():
    with tempfile.TemporaryDirectory() as d:
        path = _write(
            d, "f.json",
            json.dumps({"2025-06-18": {"FOMC": {"consensus": 5.25, "actual": 5.50}}}),
        )
        src = ss.FileSurpriseSource(path)
        s = src.get_surprise("FOMC", "2025-06-18")
        assert s is not None and s > 0  # higher rate than expected -> hawkish


def test_file_missing_date_returns_none():
    with tempfile.TemporaryDirectory() as d:
        path = _write(d, "x.json", json.dumps({"2025-06-11": {"CPI": 1.0}}))
        src = ss.FileSurpriseSource(path)
        assert src.get_surprise("CPI", "2099-01-01") is None


def test_file_missing_kind_returns_none():
    with tempfile.TemporaryDirectory() as d:
        path = _write(d, "x.json", json.dumps({"2025-06-11": {"CPI": 1.0}}))
        src = ss.FileSurpriseSource(path)
        assert src.get_surprise("FOMC", "2025-06-11") is None


def test_file_missing_file_returns_none():
    src = ss.FileSurpriseSource("/nonexistent/path/to/nothing.json")
    assert src.get_surprise("CPI", "2025-06-11") is None


def test_file_corrupt_json_returns_none():
    with tempfile.TemporaryDirectory() as d:
        path = _write(d, "bad.json", "{not valid json")
        src = ss.FileSurpriseSource(path)
        assert src.get_surprise("CPI", "2025-06-11") is None


# -------------------------------------------------------- FileSurpriseSource CSV

def test_file_csv_rich_hot_and_cool():
    with tempfile.TemporaryDirectory() as d:
        text = (
            "date,kind,consensus,actual,surprise\n"
            "2025-06-11,CPI,3.2,3.5,\n"
            "2025-05-13,CPI,3.4,3.1,\n"
        )
        path = _write(d, "s.csv", text)
        src = ss.FileSurpriseSource(path)
        hot = src.get_surprise("CPI", "2025-06-11")
        cool = src.get_surprise("CPI", "2025-05-13")
        assert hot is not None and hot > 0
        assert cool is not None and cool < 0


def test_file_csv_terse_surprise_column():
    with tempfile.TemporaryDirectory() as d:
        text = (
            "date,kind,consensus,actual,surprise\n"
            "2025-06-11,CPI,,,-0.5\n"
        )
        path = _write(d, "t.csv", text)
        src = ss.FileSurpriseSource(path)
        assert src.get_surprise("CPI", "2025-06-11") == -0.5


def test_file_csv_missing_entry_none():
    with tempfile.TemporaryDirectory() as d:
        text = "date,kind,consensus,actual,surprise\n2025-06-11,CPI,3.2,3.5,\n"
        path = _write(d, "s.csv", text)
        src = ss.FileSurpriseSource(path)
        assert src.get_surprise("FOMC", "2025-06-11") is None


# ----------------------------------------------------------- ManualSurpriseSource

def test_manual_roundtrip_terse():
    src = ss.ManualSurpriseSource({"2025-06-11": {"CPI": 1.0, "FOMC": -1.0}})
    assert src.get_surprise("CPI", "2025-06-11") == 1.0
    assert src.get_surprise("FOMC", "2025-06-11") == -1.0


def test_manual_roundtrip_rich():
    src = ss.ManualSurpriseSource(
        {"2025-06-11": {"CPI": {"consensus": 3.2, "actual": 3.5}}}
    )
    s = src.get_surprise("CPI", "2025-06-11")
    assert s is not None and s > 0


def test_manual_missing_returns_none():
    src = ss.ManualSurpriseSource({"2025-06-11": {"CPI": 1.0}})
    assert src.get_surprise("CPI", "2030-01-01") is None
    assert src.get_surprise("FOMC", "2025-06-11") is None


def test_manual_empty_is_shadow():
    src = ss.ManualSurpriseSource()
    assert src.get_surprise("CPI", "2025-06-11") is None


# -------------------------------------------------------------- default_source

def test_default_source_null_without_env(monkeypatch):
    monkeypatch.delenv("MACRO_SURPRISE_FILE", raising=False)
    src = ss.default_source()
    assert src.get_surprise("CPI", "2025-06-11") is None


def test_default_source_uses_file_with_env(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        path = _write(d, "e.json", json.dumps({"2025-06-11": {"CPI": 1.0}}))
        monkeypatch.setenv("MACRO_SURPRISE_FILE", path)
        src = ss.default_source()
        assert isinstance(src, ss.FileSurpriseSource)
        assert src.get_surprise("CPI", "2025-06-11") == 1.0
