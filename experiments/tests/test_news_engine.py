"""Tests that lock the news-cycle trade engine's behavior.

Run from the repo root:  python -m pytest experiments/tests/test_news_engine.py -q
These are pure-Python (no network): the LLM-classifier test exercises only the
offline fallback path, so it never calls the Anthropic API.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import news_trade_engine as nte  # noqa: E402


# ---- classifier -----------------------------------------------------------

def test_classify_escalation_is_negative():
    s = nte.classify("BREAKING: ADDITIONAL 100% TARIFF on all Chinese imports!")
    assert s.topic == "trade_china"
    assert s.valence < 0
    assert s.intensity > 1  # caps + "!" + multiple terms

def test_classify_deescalation_is_positive():
    s = nte.classify("Great call with President Xi — we agreed to a deal and will pause tariffs.")
    assert s.topic == "trade_china"
    assert s.valence > 0

def test_classify_bare_tariff_mention_reads_as_escalation():
    s = nte.classify("More tariffs on China are coming.")
    assert s.topic == "trade_china"
    assert s.valence < 0

def test_classify_offtopic_is_none():
    s = nte.classify("Had a wonderful dinner at Mar-a-Lago. Thank you all!")
    assert s.topic == "none"
    assert s.valence == 0


# ---- trade planning -------------------------------------------------------

def test_escalation_in_office_leads_short_spy_and_buys_gold():
    res = nte.plan_trade("ADDITIONAL 100% TARIFF on China, effective now!", base_qty=500)
    legs = {p["instrument"]: p for p in res["plans"]}
    assert res["plans"][0]["instrument"] == "SPY"      # highest edge leads
    assert legs["SPY"]["side"] == "SELL"
    assert legs["SPY"]["quantity"] == 500
    assert legs["SPY"]["probability"] == 0.77
    assert legs["GLD"]["side"] == "BUY"                # safe-haven leg
    assert legs["FXI"]["side"] == "SELL"

def test_deescalation_flips_every_leg():
    res = nte.plan_trade("Productive call with Xi; framework deal reached, tariffs paused.",
                         base_qty=100)
    legs = {p["instrument"]: p for p in res["plans"]}
    assert legs["SPY"]["side"] == "BUY"
    assert legs["GLD"]["side"] == "SELL"
    assert legs["FXI"]["side"] == "BUY"

def test_out_of_office_flips_china_to_buy_the_fade():
    res = nte.plan_trade("Massive new tariffs on China and export controls!",
                         base_qty=100, regime="out_office")
    legs = {p["instrument"]: p for p in res["plans"]}
    assert "FXI" in legs and legs["FXI"]["side"] == "BUY"
    assert legs["FXI"]["window"] == "intraday"

def test_scale_by_prob_sizes_to_edge():
    res = nte.plan_trade("ADDITIONAL 100% TARIFF on China!", base_qty=1000,
                         instruments=["SPY", "FXI"], scale_by_prob=True)
    legs = {p["instrument"]: p for p in res["plans"]}
    assert legs["SPY"]["quantity"] == round(1000 * (2 * 0.77 - 1))   # 540
    assert legs["FXI"]["quantity"] == round(1000 * (2 * 0.62 - 1))   # 240

def test_offtopic_returns_no_trade():
    res = nte.plan_trade("Beautiful weather in Florida today!", base_qty=100)
    assert res["plans"] == []
    assert "NO TRADE" in res["decision"]

def test_forced_single_instrument():
    res = nte.plan_trade("New tariffs on China!", base_qty=50, instruments=["GLD"])
    assert [p["instrument"] for p in res["plans"]] == ["GLD"]
    assert res["plans"][0]["side"] == "BUY"


# ---- LLM classifier interface (offline fallback only) ---------------------

def test_classify_llm_falls_back_without_api_key(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    text = "ADDITIONAL 100% TARIFF on China!"
    s = nte.classify_llm(text)               # must not hit the network
    assert isinstance(s, nte.Signal)
    assert s.topic == nte.classify(text).topic   # matches keyword fallback
    assert "falling back" in capsys.readouterr().err

def test_plan_trade_accepts_a_custom_classifier():
    # inject a stub classifier to prove the seam works without the LLM
    stub = lambda _t: nte.Signal(topic="trade_china", valence=-1.0, intensity=2.0, matched=["stub"])
    res = nte.plan_trade("anything", base_qty=10, classify_fn=stub)
    assert res["plans"][0]["instrument"] == "SPY"
    assert res["plans"][0]["side"] == "SELL"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn) and "monkeypatch" not in fn.__code__.co_varnames:
            fn()
            print(f"ok  {name}")
    print("(run via pytest for the monkeypatch-based tests)")
