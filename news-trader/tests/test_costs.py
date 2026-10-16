from costs import CostModel

def test_buy_pays_up_sell_receives_less():
    cm = CostModel(half_spread_bps=2.0, impact_bps=1.0)   # 3 bps each side
    assert cm.fill_buy(100.0) == 100.03
    assert cm.fill_sell(100.0) == 99.97

def test_round_trip_cost_is_positive():
    cm = CostModel()
    buy, sell = cm.fill_buy(100.0), cm.fill_sell(100.0)
    assert buy > 100.0 > sell
