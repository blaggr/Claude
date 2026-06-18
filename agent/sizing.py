"""Risk-based position sizing with correlation-aware portfolio caps.

This module turns a calibrated trade *leg* (the dict produced by
``experiments/news_trade_engine.plan_trade``) into a whole-share quantity that
respects three independent risk limits, in increasing order of authority:

  1. Fractional-Kelly cap.  The leg carries an edge (probability ``p`` and an
     ``expected_move_pct``).  We size the *bet fraction* with a fractional
     Kelly (default a quarter Kelly) so that a string of correlated misses
     can't blow up the book.  Kelly is 0 for ``p <= 0.5`` (no edge -> no bet).

  2. Volatility targeting.  Independently we ask "how many shares put roughly
     ``risk_pct`` of equity at risk for a one-sigma daily move in this name?"
     A higher-vol instrument therefore earns *fewer* shares for the same
     dollar risk budget.  We take the *smaller* of the Kelly and vol-target
     share counts -- whichever risk lens is tighter wins.

  3. Absolute notional cap.  Regardless of the above, a single leg may never
     commit more than ``max_notional_pct`` of equity (mirrors the flat
     per-event budget that ``Toolbox.place_order`` enforces today).

On top of per-leg sizing, :class:`PortfolioSizer` applies a *correlation-aware*
exposure check so that a basket of legs that are really the same bet
(e.g. SELL SPY + SELL FXI + BUY GLD on a risk-off headline) is not waved
through as three independent positions.  See :meth:`PortfolioSizer.size`.

Pure standard library: no numpy/pandas, offline, paper-only -- matching the
rest of the ``agent`` package.  The vol and correlation tables follow the same
static offline-stub pattern as ``agent/marketdata.py``'s ``_REF``; both are
overridable via the constructor or environment so they never have to be true,
only plausible and deterministic.
"""
from __future__ import annotations

import json
import os

# --------------------------------------------------------------------------
# Static reference tables (offline stubs, a la marketdata._REF).
#
# Annualised volatility, as a fraction (0.15 == 15%/yr).  Estimates only:
#   * Broad US equity index ETFs (SPY) ~15%.
#   * Tech-tilted / sector ETFs (QQQ, XLK, SMH) a bit higher, ~20-28%.
#   * Single names (AAPL, TSLA) higher still; TSLA notoriously so.
#   * China / single-country / commodity ETFs (FXI, KWEB, USO, EWZ) high.
#   * Defensive duration / gold (TLT, GLD) modest.
#   * ITA (defence) ~ broad-equity-ish.
# --------------------------------------------------------------------------
_VOL = {
    "SPY": 0.15, "QQQ": 0.20, "XLK": 0.22, "SMH": 0.28,
    "FXI": 0.28, "KWEB": 0.38, "EWZ": 0.32,
    "USO": 0.35, "GLD": 0.14, "TLT": 0.14, "ITA": 0.18,
    "AAPL": 0.27, "TSLA": 0.55,
}
_DEFAULT_VOL = 0.30  # unknown symbol: assume a fairly jumpy single name

# Pairwise correlation.  We store only the upper-triangle / notable pairs and
# symmetrise on lookup; the diagonal is 1.0 and any unlisted pair falls back to
# _DEFAULT_CORR.  The structure we want to capture:
#   * SPY/QQQ/XLK/SMH are the same risk-on equity bet (strongly +).
#   * AAPL/TSLA load on that same tech/beta complex (+, a bit looser).
#   * FXI/KWEB are one China bet (strongly +), partially correlated to global
#     risk-on (mild + to SPY) and to EWZ (other EM/risk-on, mild +).
#   * GLD and TLT are defensive: low-to-negative vs equities, mildly + together.
#   * USO (oil) is its own thing: low/mild correlation to equities.
#   * ITA (defence) tracks broad equities moderately.
_CORR = {
    ("SPY", "QQQ"): 0.92, ("SPY", "XLK"): 0.88, ("SPY", "SMH"): 0.80,
    ("SPY", "AAPL"): 0.72, ("SPY", "TSLA"): 0.55, ("SPY", "ITA"): 0.70,
    ("SPY", "FXI"): 0.45, ("SPY", "KWEB"): 0.42, ("SPY", "EWZ"): 0.55,
    ("SPY", "USO"): 0.25, ("SPY", "GLD"): -0.10, ("SPY", "TLT"): -0.35,
    ("QQQ", "XLK"): 0.94, ("QQQ", "SMH"): 0.88, ("QQQ", "AAPL"): 0.80,
    ("QQQ", "TSLA"): 0.62, ("QQQ", "GLD"): -0.08, ("QQQ", "TLT"): -0.32,
    ("QQQ", "FXI"): 0.42, ("QQQ", "KWEB"): 0.45,
    ("XLK", "SMH"): 0.90, ("XLK", "AAPL"): 0.82, ("XLK", "TSLA"): 0.60,
    ("SMH", "AAPL"): 0.70, ("SMH", "TSLA"): 0.58,
    ("AAPL", "TSLA"): 0.50,
    ("FXI", "KWEB"): 0.90, ("FXI", "EWZ"): 0.55, ("KWEB", "EWZ"): 0.48,
    ("FXI", "GLD"): 0.00, ("KWEB", "GLD"): 0.00,
    ("GLD", "TLT"): 0.30,
    ("TLT", "USO"): -0.10, ("GLD", "USO"): 0.20,
    ("USO", "EWZ"): 0.30,
    ("ITA", "QQQ"): 0.66, ("ITA", "XLK"): 0.62,
    ("EWZ", "GLD"): 0.15,
}
_DEFAULT_CORR = 0.20  # unlisted pair: assume a mild common-market component

# Trading days per year, for de-annualising vol into a daily sigma.
_TRADING_DAYS = 252


def _load_override(env_name: str):
    """Parse a JSON object from an env var, or return None.  Lets a caller do
    e.g. ``AGENT_VOL_OVERRIDE='{"TSLA": 0.7}'`` without touching code."""
    raw = os.environ.get(env_name)
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------
# Pure sizing math
# --------------------------------------------------------------------------
def fractional_kelly_fraction(p: float, win: float, loss: float,
                              fraction: float = 0.25) -> float:
    """Return the fraction of equity to stake, as a *fractional* Kelly bet.

    Classic Kelly for a bet that wins ``win`` (>0) with probability ``p`` and
    loses ``loss`` (>0, magnitude) with probability ``1-p`` is::

        f* = (b*p - (1-p)) / b,   where b = win / loss   (payoff odds)

    We then multiply by ``fraction`` (default 0.25 -> quarter Kelly) for
    robustness to mis-estimated edge.  The result is clamped to ``[0, 1]`` and
    is exactly 0 whenever ``p <= 0.5`` or there is no favourable payoff (no
    edge -> no bet).
    """
    if p <= 0.5 or win <= 0 or loss <= 0:
        return 0.0
    b = win / loss
    f_star = (b * p - (1.0 - p)) / b
    if f_star <= 0.0:
        return 0.0
    return max(0.0, min(1.0, f_star * fraction))


def daily_sigma(vol_annual: float) -> float:
    """De-annualise an annualised vol into a one-day sigma (fraction)."""
    return vol_annual / (_TRADING_DAYS ** 0.5)


def vol_target_qty(equity: float, price: float, p: float, expected_move_pct: float,
                   vol_annual: float, *, risk_pct: float = 1.0,
                   kelly_fraction: float = 0.25, max_notional_pct: float = 25.0) -> int:
    """Whole-share quantity for one leg, the *smaller* of a fractional-Kelly
    stake and a vol-targeted stake, hard-capped by an absolute notional limit.

    Parameters
    ----------
    equity, price : account equity and the instrument's price.
    p : calibrated probability the move goes the predicted way.
    expected_move_pct : the leg's expected move, in percent (sign ignored).
    vol_annual : the instrument's annualised volatility (fraction).
    risk_pct : per-trade risk budget as a percent of equity (default ~1%).
    kelly_fraction : Kelly multiplier (default 0.25 -> quarter Kelly).
    max_notional_pct : absolute notional ceiling as a percent of equity.

    The two lenses:

    * *Kelly*: treat the expected move as the win and a symmetric adverse move
      as the loss, giving payoff odds ~1:1, so the Kelly fraction is driven by
      the edge ``2p-1``.  ``kelly_notional = f_kelly * equity``.

    * *Vol target*: choose notional so that a one-day sigma move risks about
      ``risk_pct`` of equity: ``vol_notional = (risk_pct/100 * equity) / sigma_d``.

    We size on ``min(kelly_notional, vol_notional)`` then clamp to the absolute
    notional cap, and floor to whole shares.
    """
    if equity <= 0 or price <= 0:
        return 0
    move = abs(expected_move_pct) / 100.0
    if move <= 0:
        return 0

    # Kelly lens: win/loss are the favourable/adverse move of equal magnitude.
    f_kelly = fractional_kelly_fraction(p, move, move, fraction=kelly_fraction)
    kelly_notional = f_kelly * equity

    # Vol-target lens: notional s.t. a 1-sigma daily move ~ risk_pct of equity.
    sigma_d = daily_sigma(vol_annual)
    risk_budget = (risk_pct / 100.0) * equity
    vol_notional = (risk_budget / sigma_d) if sigma_d > 0 else 0.0

    notional = min(kelly_notional, vol_notional)

    # Absolute notional ceiling (mirrors the flat per-event budget).
    notional = min(notional, (max_notional_pct / 100.0) * equity)

    return int(notional // price)


# --------------------------------------------------------------------------
# Portfolio-level sizer
# --------------------------------------------------------------------------
class PortfolioSizer:
    """Size a leg against equity *and* against existing correlated exposure.

    Public API
    ----------
    ``PortfolioSizer(vol=None, corr=None, *, risk_pct=1.0, kelly_fraction=0.25,
                     max_notional_pct=25.0, gross_corr_cap_pct=60.0)``
        ``vol`` / ``corr`` optionally override the built-in tables (merged over
        the defaults).  Env overrides ``AGENT_VOL_OVERRIDE`` /
        ``AGENT_CORR_OVERRIDE`` (JSON objects) are also merged in.

    ``vol_for(symbol) -> float``
        Annualised vol for a symbol (default for unknowns).

    ``correlation(a, b) -> float``
        Symmetric pairwise correlation (1.0 on the diagonal, default for
        unlisted pairs).

    ``size(leg, equity, price, current_positions) -> int``
        Signed-aware share count for ``leg``, after the correlation check.

    Correlation-aware exposure heuristic
    ------------------------------------
    We model a single scalar "net correlated exposure" for the book.  Each
    existing position contributes a *signed dollar beta to SPY*::

        beta_to_spy(sym) = correlation(sym, "SPY")
        signed_exposure(sym) = sign(qty) * |qty * price| * beta_to_spy(sym)

    Summing over the book gives ``net`` -- a single number whose magnitude is
    how net-long (or, if negative, net-short) the book is *to the common
    risk-on factor*.  A risk-off basket (SELL SPY + SELL FXI + BUY GLD) all
    pushes ``net`` in the same (negative) direction even though the tickers
    differ, which is exactly the concentration we want to catch.

    A candidate leg's own signed SPY-exposure is computed the same way.  We
    allow the book's net correlated exposure to reach at most
    ``gross_corr_cap_pct`` of equity *in either direction*.  If a leg would
    push ``|net|`` past that cap **and** it is adding to the already-dominant
    direction, we shrink the leg's notional to just fill the remaining room
    (and reject it outright if there is no room).  A leg that *reduces* net
    exposure (a diversifier / hedge) is never shrunk by this check.

    The price for existing positions is approximated from
    ``current_positions[sym]['price']`` (or ``'avg'``) if present, else from
    the leg's own price as a last resort -- the sizer stays fully offline and
    never fetches quotes itself.
    """

    def __init__(self, vol: dict | None = None, corr: dict | None = None, *,
                 risk_pct: float = 1.0, kelly_fraction: float = 0.25,
                 max_notional_pct: float = 25.0, gross_corr_cap_pct: float = 60.0):
        self.vol = dict(_VOL)
        env_vol = _load_override("AGENT_VOL_OVERRIDE")
        if env_vol:
            self.vol.update({k.upper(): float(v) for k, v in env_vol.items()})
        if vol:
            self.vol.update({k.upper(): float(v) for k, v in vol.items()})
        self.default_vol = _DEFAULT_VOL

        # store correlations as a frozen-key dict, symmetric on lookup
        self.corr = {self._key(a, b): float(c) for (a, b), c in _CORR.items()}
        env_corr = _load_override("AGENT_CORR_OVERRIDE")
        if env_corr:
            self._merge_corr(env_corr)
        if corr:
            self._merge_corr(corr)
        self.default_corr = _DEFAULT_CORR

        self.risk_pct = risk_pct
        self.kelly_fraction = kelly_fraction
        self.max_notional_pct = max_notional_pct
        self.gross_corr_cap_pct = gross_corr_cap_pct

    # -- table accessors ---------------------------------------------------
    @staticmethod
    def _key(a: str, b: str):
        a, b = a.upper(), b.upper()
        return (a, b) if a <= b else (b, a)

    def _merge_corr(self, mapping: dict) -> None:
        """Accept either {"SPY,QQQ": 0.9} or {("SPY","QQQ"): 0.9} forms."""
        for k, v in mapping.items():
            if isinstance(k, str):
                parts = [p.strip() for p in k.split(",")]
                if len(parts) != 2:
                    continue
                a, b = parts
            else:
                a, b = k
            self.corr[self._key(a, b)] = float(v)

    def vol_for(self, symbol: str) -> float:
        return self.vol.get(symbol.upper(), self.default_vol)

    def correlation(self, a: str, b: str) -> float:
        if a.upper() == b.upper():
            return 1.0
        return self.corr.get(self._key(a, b), self.default_corr)

    # -- exposure heuristic ------------------------------------------------
    def _beta(self, symbol: str) -> float:
        """Signed loading on the common risk-on factor (proxied by SPY)."""
        return self.correlation(symbol, "SPY")

    def _net_exposure(self, current_positions: dict, fallback_price: float) -> float:
        """Net signed correlated (SPY-beta-weighted) dollar exposure of the book."""
        net = 0.0
        for sym, info in (current_positions or {}).items():
            if isinstance(info, dict):
                qty = info.get("qty", 0)
                px = info.get("price", info.get("avg", fallback_price)) or fallback_price
            else:  # plain signed quantity
                qty, px = info, fallback_price
            if not qty:
                continue
            sign = 1.0 if qty > 0 else -1.0
            net += sign * abs(qty * px) * self._beta(sym)
        return net

    # -- public sizing -----------------------------------------------------
    def size(self, leg: dict, equity: float, price: float,
             current_positions: dict | None = None) -> int:
        """Whole-share quantity for ``leg`` after per-leg risk sizing and the
        correlation-aware exposure check.  ``leg`` is a plan-leg dict with at
        least ``instrument``, ``side``, ``probability`` and
        ``expected_move_pct``.  ``current_positions`` maps symbol -> signed qty
        (or symbol -> {"qty", "price"/"avg"})."""
        symbol = str(leg.get("instrument", "")).upper()
        side = str(leg.get("side", "BUY")).upper()
        p = float(leg.get("probability", leg.get("p", 0.0)) or 0.0)
        move = float(leg.get("expected_move_pct", 0.0) or 0.0)

        # 1) standalone per-leg size
        qty = vol_target_qty(equity, price, p, move, self.vol_for(symbol),
                             risk_pct=self.risk_pct,
                             kelly_fraction=self.kelly_fraction,
                             max_notional_pct=self.max_notional_pct)
        if qty <= 0:
            return 0

        # 2) correlation-aware exposure check
        if equity > 0:
            cap = (self.gross_corr_cap_pct / 100.0) * equity
            net = self._net_exposure(current_positions or {}, price)
            beta = self._beta(symbol)
            leg_sign = 1.0 if side == "BUY" else -1.0
            # signed correlated exposure this leg *adds* per share
            per_share = leg_sign * abs(price) * beta
            if per_share != 0.0:
                projected = net + qty * per_share
                # only constrain if the leg pushes |net| past the cap while
                # adding to the direction it is (or becomes) dominant in
                if abs(projected) > cap and (projected * per_share) > 0:
                    # |added exposure| we can still take in this direction
                    room = cap - abs(net) if (net * per_share) >= 0 else cap + abs(net)
                    allowed_shares = int(max(0.0, room) // abs(per_share))
                    qty = min(qty, allowed_shares)

        return max(0, int(qty))
