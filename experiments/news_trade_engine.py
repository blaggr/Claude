"""News-cycle trade engine: news in -> sized BUY/SELL order out.

Give it a Trump / White House / administration news item (and the quantity you
want to trade). It:
  1. classifies the item's TOPIC and VALENCE (risk-off escalation <-> risk-on
     de-escalation) from a transparent keyword model;
  2. looks up the empirically-calibrated market response for that topic and the
     current political REGIME (in office vs out — the sign flips, see below);
  3. emits a trade plan per instrument: SIDE (buy/sell), your QUANTITY (held as
     given, or scaled by edge), the probability the move goes the predicted way,
     the expected move size, and the entry + exit rule.

Trades the news cycle in EITHER direction: negative/escalation news -> the
risk-off response; positive/de-escalation news -> the same response flipped.

Calibration (baked from this repo's event studies; tiny samples — see caveats):
  IN OFFICE, escalation (negative valence), per instrument:
    SPY  sells, P(down overnight)=0.77, mean -0.88%   <- most reliable
    GLD  buys,  P(up   overnight)=0.69, mean +0.58%
    FXI  sells, P(down overnight)=0.62, mean -0.66%
    KWEB sells, P(down overnight)=0.46, mean -0.84%   <- ~coin flip, low conf
  OUT OF OFFICE, escalation: sign FLIPS (posts were rhetoric, market faded):
    FXI/KWEB buy, P(up open->close)=0.72, mean +0.6%/+0.75%
Positive/de-escalation news flips every sign (assumed symmetric -> lower conf).

Paper/planning tool only. Not investment advice; no orders are sent.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Callable

# ---------------------------------------------------------------- classifier

NEG_TERMS = [  # escalation / risk-off
    "tariff", "tariffs", "trade war", "sanction", "sanctions", "export control",
    "ban", "retaliat", "penalt", "no deal", "crack down", "crackdown",
    "100%", "200%", "additional tariff", "reciprocal tariff", "decoupl",
    "punish", "blacklist", "restrict", "levy", "duties",
]
POS_TERMS = [  # de-escalation / risk-on
    "deal", "agreement", "great call", "productive", "pause", "paused",
    "exempt", "exemption", "rolling back", "roll back", "truce", "breakthrough",
    "lower tariff", "cut tariff", "reduce tariff", "framework", "phase one",
    "constructive", "progress", "agreed",
]
TOPIC_TRADE = ["china", "tariff", "trade", "xi", "beijing", "import", "export", "duties"]
TOPIC_FED = ["fed", "powell", "interest rate", "rate cut", "federal reserve"]
MARKET_WORDS = TOPIC_TRADE + TOPIC_FED + ["market", "stock", "economy", "inflation", "deal"]


@dataclass
class Signal:
    topic: str            # "trade_china" | "fed" | "macro_generic" | "none"
    valence: float        # -1 (max escalation) .. +1 (max de-escalation)
    intensity: float      # 0..~3, headline forcefulness
    matched: list[str] = field(default_factory=list)


def classify(text: str) -> Signal:
    low = text.lower()
    neg = [t for t in NEG_TERMS if t in low]
    pos = [t for t in POS_TERMS if t in low]
    # topic
    if any(t in low for t in TOPIC_TRADE):
        topic = "trade_china"
    elif any(t in low for t in TOPIC_FED):
        topic = "fed"
    elif any(t in low for t in MARKET_WORDS):
        topic = "macro_generic"
    else:
        topic = "none"
    # valence: + for de-escalation, - for escalation
    nneg, npos = len(neg), len(pos)
    if nneg + npos == 0:
        valence = 0.0
    else:
        valence = (npos - nneg) / (nneg + npos)
    # a pure tariff/China mention with no positive cue reads as escalation
    if topic == "trade_china" and nneg + npos == 0:
        valence = -0.4
    # intensity: term hits + ALL-CAPS shouting + exclamation
    caps = sum(1 for w in text.split() if len(w) >= 4 and w.isupper())
    intensity = (nneg + npos) + 0.5 * min(caps, 6) + 0.3 * text.count("!")
    return Signal(topic, round(valence, 3), round(float(intensity), 2), neg + pos)


# ---- LLM-backed classifier (same Signal interface, optional) --------------
# Drop-in replacement for classify() that uses Claude to read nuance, sarcasm,
# and implicit valence the keyword model misses. Falls back to classify() when
# the anthropic SDK or an API key is unavailable, so the engine still runs
# offline. Requires: pip install anthropic  (+ ANTHROPIC_API_KEY in the env).

LLM_MODEL = "claude-opus-4-8"
_LLM_TOPICS = ["trade_china", "fed", "macro_generic", "none"]
_LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "enum": _LLM_TOPICS,
                  "description": "trade_china for US-China trade/tariffs; fed for monetary policy; "
                                 "macro_generic for other market-moving econ news; none if not market-relevant"},
        "valence": {"type": "number",
                    "description": "-1 = strong risk-off / escalation (e.g. new tariffs, sanctions), "
                                   "+1 = strong risk-on / de-escalation (e.g. trade deal, tariff pause), "
                                   "0 = neutral or not market-relevant"},
        "intensity": {"type": "number", "description": "0-3 forcefulness/specificity of the headline"},
        "matched": {"type": "array", "items": {"type": "string"},
                    "description": "key phrases that drove the classification"},
    },
    "required": ["topic", "valence", "intensity", "matched"],
    "additionalProperties": False,
}
_LLM_SYSTEM = (
    "You classify a single piece of news (a Trump/White House/administration post or headline) "
    "for an automated trading engine. Judge it from a markets standpoint: does it read as risk-off "
    "escalation (tariffs, sanctions, export bans, trade-war threats — negative valence) or risk-on "
    "de-escalation (deals, pauses, exemptions, productive talks — positive valence)? Account for "
    "sarcasm, negation, and conditional/hypothetical framing. If the item has no plausible market "
    "impact, set topic 'none' and valence 0. Respond only via the structured schema."
)


def classify_llm(text: str, model: str = LLM_MODEL, client=None, strict: bool = False) -> Signal:
    """LLM version of classify(). Returns the same Signal. Falls back to the
    keyword classifier (and warns on stderr) if the API is unavailable, unless
    ``strict`` is set."""
    try:
        import anthropic  # lazy: only needed for the LLM path
        if client is None:
            if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
                raise RuntimeError("no ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN in environment")
            client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model,
            max_tokens=512,
            system=_LLM_SYSTEM,
            output_config={"effort": "low",
                           "format": {"type": "json_schema", "schema": _LLM_SCHEMA}},
            messages=[{"role": "user", "content": text}],
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("model refused to classify")
        payload = next(b.text for b in resp.content if b.type == "text")
        data = json.loads(payload)
        topic = data["topic"] if data.get("topic") in _LLM_TOPICS else "none"
        valence = max(-1.0, min(1.0, float(data["valence"])))
        intensity = max(0.0, float(data.get("intensity", 0)))
        matched = [str(m) for m in data.get("matched", [])]
        return Signal(topic, round(valence, 3), round(intensity, 2), matched)
    except Exception as exc:  # any failure -> deterministic keyword fallback
        if strict:
            raise
        print(f"[classify_llm] falling back to keyword classifier: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return classify(text)


# ---------------------------------------------------------------- calibration

# response to NEGATIVE/escalation news: sign of expected return (+1 up / -1 down),
# probability that sign is realized, mean move %, and the capture window/exit.
CALIB = {
    "in_office": {
        "SPY":  dict(sign=-1, p=0.77, move=0.88, window="overnight", note="most reliable"),
        "GLD":  dict(sign=+1, p=0.69, move=0.58, window="overnight", note="safe-haven gap"),
        "FXI":  dict(sign=-1, p=0.62, move=0.66, window="overnight", note=""),
        "KWEB": dict(sign=-1, p=0.46, move=0.84, window="overnight", note="~coin flip, low conf"),
    },
    "out_office": {
        "FXI":  dict(sign=+1, p=0.72, move=0.59, window="intraday", note="rhetoric fade"),
        "KWEB": dict(sign=+1, p=0.72, move=0.75, window="intraday", note="rhetoric fade"),
        "GLD":  dict(sign=+1, p=0.66, move=0.23, window="intraday", note=""),
        "SPY":  dict(sign=+1, p=0.59, move=0.14, window="intraday", note="weak"),
    },
}
DEFAULT_BASKET = {
    "in_office": ["SPY", "GLD", "FXI"],   # sell broad + buy gold hedge + sell China
    "out_office": ["FXI", "KWEB"],
}
EXIT = {
    "overnight": ("Enter immediately in a venue open NOW (index/FX futures or "
                  "pre-market ETF). Exit on impulse-decay within ~the hour, and "
                  "no later than the next US cash open. Do NOT hold past that — "
                  "no continuation in the data."),
    "intraday": ("Enter at/just after the US cash open. Exit on impulse-decay "
                 "or by the session close. Flat end of day."),
}


@dataclass
class TradePlan:
    instrument: str
    side: str            # BUY | SELL
    quantity: int
    probability: float   # P(market moves the predicted way)
    expected_move_pct: float
    edge_score: float    # (2p-1) * expected_move, a rough $-per-unit-prob signal
    window: str
    entry_exit: str
    rationale: str
    confidence: str      # high | medium | low

    def to_dict(self):
        return dataclasses.asdict(self)


def _confidence(p: float, intensity: float, valence: float) -> str:
    if p >= 0.7 and intensity >= 1.5 and valence < 0:
        return "high"
    if p >= 0.6:
        return "medium"
    return "low"


def plan_trade(text: str, base_qty: int, regime: str = "in_office",
               instruments: list[str] | None = None, scale_by_prob: bool = False,
               classify_fn: Callable[[str], Signal] = classify) -> dict:
    sig = classify_fn(text)
    out = {"signal": dataclasses.asdict(sig), "regime": regime, "plans": []}

    if sig.topic == "none" or abs(sig.valence) < 1e-6:
        out["decision"] = "NO TRADE — no market-relevant valence detected."
        return out
    if sig.topic != "trade_china":
        out["decision"] = (f"NO CALIBRATED TRADE — topic '{sig.topic}' is not "
                           "empirically calibrated here; treat as discretionary.")
        return out

    table = CALIB[regime]
    picks = instruments or DEFAULT_BASKET[regime]
    # valence direction multiplier: escalation(-) uses calibrated sign as-is;
    # de-escalation(+) flips it.
    flip = 1 if sig.valence < 0 else -1
    # intensity scales expected move (and nudges probability toward calibrated)
    imult = min(1.0 + 0.25 * (sig.intensity - 1), 2.0)
    imult = max(imult, 0.6)

    for ins in picks:
        c = table.get(ins)
        if not c:
            continue
        exp_sign = c["sign"] * flip
        side = "BUY" if exp_sign > 0 else "SELL"
        p = c["p"]
        # positive/de-escalation news is assumed symmetric but less certain
        if sig.valence > 0:
            p = 0.5 + (p - 0.5) * 0.8
        exp_move = round(c["move"] * imult, 2) * (1 if exp_sign > 0 else -1)
        qty = base_qty
        if scale_by_prob:
            qty = int(round(base_qty * max(0.0, 2 * p - 1)))
        edge = round((2 * p - 1) * abs(exp_move), 3)
        conf = _confidence(p, sig.intensity, sig.valence)
        rationale = (f"{regime.replace('_', ' ')}, "
                     f"{'escalation' if sig.valence < 0 else 'de-escalation'} "
                     f"(valence {sig.valence:+.2f}); {ins} {c['window']} response "
                     f"{c['sign']:+d} historically, P={c['p']:.0%}"
                     + (f" — {c['note']}" if c['note'] else ""))
        out["plans"].append(TradePlan(
            instrument=ins, side=side, quantity=qty, probability=round(p, 3),
            expected_move_pct=exp_move, edge_score=edge, window=c["window"],
            entry_exit=EXIT[c["window"]], rationale=rationale, confidence=conf,
        ).to_dict())

    # order by edge_score so the strongest trade leads
    out["plans"].sort(key=lambda d: -d["edge_score"])
    out["decision"] = (f"{len(out['plans'])} trade leg(s) — lead: "
                       f"{out['plans'][0]['side']} {out['plans'][0]['quantity']} "
                       f"{out['plans'][0]['instrument']}" if out["plans"] else "NO TRADE")
    return out


# ---------------------------------------------------------------- CLI

EXAMPLES = [
    "BREAKING: I am imposing an ADDITIONAL 100% TARIFF on all Chinese imports, effective immediately!",
    "Just had a very productive call with President Xi. We have agreed to a framework deal and will pause tariffs.",
    "The Fed must CUT INTEREST RATES now. Powell is too late, as usual!",
    "Had a wonderful dinner at Mar-a-Lago last night. Thank you to everyone!",
]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--text", help="The news item / post text")
    ap.add_argument("--qty", type=int, default=100, help="Quantity YOU choose to trade (shares/contracts)")
    ap.add_argument("--out-office", action="store_true", help="Use the out-of-office regime (default: in office)")
    ap.add_argument("--instrument", action="append", help="Force instrument(s); repeatable. Default: calibrated basket")
    ap.add_argument("--scale", action="store_true", help="Scale quantity by edge ((2p-1)*qty) instead of using it as-is")
    ap.add_argument("--classifier", choices=["keyword", "llm"], default="keyword",
                    help="Valence classifier: 'keyword' (offline, default) or 'llm' (Claude; needs ANTHROPIC_API_KEY)")
    ap.add_argument("--json", action="store_true", help="Emit JSON")
    ap.add_argument("--demo", action="store_true", help="Run the built-in example posts")
    args = ap.parse_args(argv)

    regime = "out_office" if args.out_office else "in_office"
    classify_fn = classify_llm if args.classifier == "llm" else classify
    texts = EXAMPLES if args.demo else ([args.text] if args.text else None)
    if not texts:
        ap.error("provide --text \"...\" or --demo")

    for t in texts:
        res = plan_trade(t, args.qty, regime, args.instrument, args.scale, classify_fn)
        if args.json:
            print(json.dumps(res, indent=2))
            continue
        print("\n" + "=" * 78)
        print(f"NEWS: {t[:120]}")
        s = res["signal"]
        print(f"  topic={s['topic']}  valence={s['valence']:+.2f}  intensity={s['intensity']}  "
              f"matched={s['matched']}")
        print(f"  DECISION: {res['decision']}   (regime: {regime.replace('_',' ')})")
        for p in res["plans"]:
            print(f"   - {p['side']:4} {p['quantity']:>5} {p['instrument']:4} | "
                  f"P(move)={p['probability']:.0%}  exp {p['expected_move_pct']:+.2f}%  "
                  f"edge={p['edge_score']:+.3f}  [{p['confidence']}]")
            print(f"        why: {p['rationale']}")
            print(f"        plan: {p['entry_exit']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
