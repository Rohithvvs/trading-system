"""Unit: platform regime → Bull/Sideways/Bear/UNKNOWN (FR-010, FR-025)."""

from app.services.re001.regime import is_regime_usable, map_market_regime


class _Obj:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def test_missing_all_is_unknown():
    assert map_market_regime(None) == "UNKNOWN"
    assert not is_regime_usable("UNKNOWN")


def test_favorable_maps_bull():
    assert map_market_regime(_Obj(market_state="FAVORABLE", trend_state="BULLISH", new_entry_allowed=True)) == "Bull"


def test_defensive_maps_bear():
    assert map_market_regime(_Obj(market_state="DEFENSIVE", new_entry_allowed=False)) == "Bear"


def test_entry_blocked_maps_bear():
    assert map_market_regime(_Obj(market_state="FAVORABLE", new_entry_allowed=False)) == "Bear"


def test_cautious_maps_sideways():
    assert map_market_regime(_Obj(market_state="CAUTIOUS", trend_state="UNKNOWN", new_entry_allowed=True)) == "Sideways"


def test_feat004_fav_maps_bull():
    assert map_market_regime(None, feat004_regime="FAV") == "Bull"


def test_dict_payload_supported():
    assert map_market_regime({"market_state": "HIGHRISK", "new_entry_allowed": True}) == "Bear"


def test_usable_buckets():
    for b in ("Bull", "Sideways", "Bear"):
        assert is_regime_usable(b)
