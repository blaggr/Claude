import os, sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fetch_bars import fetch_bars, write_csv, FetchError


def _fake_get_factory(pages):
    """pages: list of API responses to return in order."""
    calls = {"i": 0}
    def get(url, key, secret):
        r = pages[calls["i"]]
        calls["i"] += 1
        return r
    return get


def test_paginates_and_maps_fields():
    pages = [
        {"bars": [{"t": "2024-01-11T13:30:00Z", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10}],
         "next_page_token": "p2"},
        {"bars": [{"t": "2024-01-11T13:31:00Z", "o": 1.5, "h": 2.5, "l": 1.0, "c": 2.0, "v": 11}],
         "next_page_token": None},
    ]
    rows = fetch_bars("SPY", "2024-01-01", "2024-02-01", key="k", secret="s",
                      get=_fake_get_factory(pages))
    assert len(rows) == 2                                  # followed the page token
    assert rows[0] == {"ts": "2024-01-11T13:30:00Z", "open": 1, "high": 2, "low": 0.5, "close": 1.5}
    assert rows[1]["ts"] == "2024-01-11T13:31:00Z"


def test_empty_response_fails_loud():
    with pytest.raises(FetchError):
        fetch_bars("SPY", "2024-01-01", "2024-02-01", key="k", secret="s",
                   get=_fake_get_factory([{"bars": [], "next_page_token": None}]))


def test_write_csv_roundtrips(tmp_path):
    import pandas as pd
    rows = [{"ts": "2024-01-11T13:30:00Z", "open": 470.0, "high": 470.1, "low": 469.9, "close": 470.0}]
    out = tmp_path / "X.csv"
    write_csv(rows, str(out))
    df = pd.read_csv(out)
    assert list(df.columns) == ["ts", "open", "high", "low", "close"]
    assert df.iloc[0]["close"] == 470.0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
