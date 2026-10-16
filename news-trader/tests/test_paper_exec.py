import os, sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paper_exec import place_oto_stop, load_keys, ExecError, PAPER_URL


def test_oto_body_shape_is_paper_bracket():
    captured = {}
    def fake_post(path, body, kid, sec, base):
        captured.update(path=path, body=body, base=base)
        return {"id": "o1", "symbol": body["symbol"], "qty": body["qty"],
                "side": body["side"], "status": "accepted",
                "legs": [{"type": "stop", "side": "sell",
                          "stop_price": body["stop_loss"]["stop_price"], "status": "held"}]}
    o = place_oto_stop("SPY", 3, 600.0, kid="k", sec="s", post=fake_post)
    assert captured["path"] == "/v2/orders"
    assert captured["base"] == PAPER_URL
    b = captured["body"]
    assert b["order_class"] == "oto"                 # atomic entry + attached stop
    assert b["type"] == "market" and b["side"] == "buy" and b["qty"] == "3"
    assert b["stop_loss"]["stop_price"] == "600.00"  # protective leg present
    assert o["legs"][0]["type"] == "stop"


def test_refuses_non_paper_base():
    with pytest.raises(ExecError):
        place_oto_stop("SPY", 1, 600.0, kid="k", sec="s",
                       base="https://api.alpaca.markets", post=lambda *a, **k: {})


def test_validates_qty_and_stop():
    for qty, stop in [(0, 600.0), (2.5, 600.0), (1, 0.0), (1, -5.0)]:
        with pytest.raises(ExecError):
            place_oto_stop("SPY", qty, stop, kid="k", sec="s", post=lambda *a, **k: {})


def test_load_keys_from_file(tmp_path, monkeypatch):
    monkeypatch.delenv("ALPACA_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    p = tmp_path / ".alpaca_keys"
    p.write_text("ALPACA_KEY_ID=PKxxx\nALPACA_SECRET_KEY=sss\n")
    kid, sec = load_keys(str(p))
    assert kid == "PKxxx" and sec == "sss"
    with pytest.raises(ExecError):
        load_keys(str(tmp_path / "nope"))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
