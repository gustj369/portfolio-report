"""market_data.py 단위 테스트

네트워크 호출 없이 핵심 분기를 검증한다.
외부 의존(yfinance)은 unittest.mock으로 격리한다.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from models.portfolio import AssetType, Allocation
from models.report import MarketSnapshot
from services.market_data import (
    MARKET_DEFAULTS,
    _HIGH_RATE_THRESHOLD,
    _HIGH_RATE_BOND_BOOST,
    _HIGH_RATE_STOCK_DRAG,
    _MIN_REAL_RETURN,
    _HIST_BLEND_RATIO,
    _adjust_return_for_market,
    get_asset_return,
)


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _snap(**overrides) -> MarketSnapshot:
    """MARKET_DEFAULTS 기반 MarketSnapshot 생성 (일부 필드만 덮어쓰기 가능)"""
    fields = dict(MARKET_DEFAULTS)
    fields["fetched_at"] = datetime.now(timezone.utc)
    fields.update(overrides)
    return MarketSnapshot(**fields)


def _alloc(asset_type: AssetType, ticker: str | None = None) -> Allocation:
    return Allocation(asset_name="테스트자산", asset_type=asset_type, weight=100.0, ticker=ticker)


# ── _adjust_return_for_market ─────────────────────────────────────────────────

class TestAdjustReturnForMarket:
    def test_high_rate_boosts_bond(self):
        """고금리 환경에서 채권 수익률이 상승해야 한다"""
        snap_high = _snap(us_10y_yield=_HIGH_RATE_THRESHOLD + 0.1, cpi_us=0.0)
        snap_low  = _snap(us_10y_yield=_HIGH_RATE_THRESHOLD - 0.1, cpi_us=0.0)
        assert _adjust_return_for_market(0.04, AssetType.BOND, snap_high) > \
               _adjust_return_for_market(0.04, AssetType.BOND, snap_low)

    def test_high_rate_drags_foreign_stock(self):
        """고금리 환경에서 해외주식 수익률이 하락해야 한다"""
        snap_high = _snap(us_10y_yield=_HIGH_RATE_THRESHOLD + 0.1)
        snap_low  = _snap(us_10y_yield=_HIGH_RATE_THRESHOLD - 0.1)
        assert _adjust_return_for_market(0.08, AssetType.FOREIGN_STOCK, snap_high) < \
               _adjust_return_for_market(0.08, AssetType.FOREIGN_STOCK, snap_low)

    def test_high_rate_adjustment_magnitude(self):
        """고금리 조정 크기가 상수와 일치해야 한다"""
        snap_high = _snap(us_10y_yield=_HIGH_RATE_THRESHOLD + 0.1, cpi_us=0.0)
        snap_low  = _snap(us_10y_yield=_HIGH_RATE_THRESHOLD - 0.1, cpi_us=0.0)
        bond_diff  = _adjust_return_for_market(0.04, AssetType.BOND, snap_high) - \
                     _adjust_return_for_market(0.04, AssetType.BOND, snap_low)
        stock_diff = _adjust_return_for_market(0.08, AssetType.FOREIGN_STOCK, snap_high) - \
                     _adjust_return_for_market(0.08, AssetType.FOREIGN_STOCK, snap_low)
        assert abs(bond_diff  - _HIGH_RATE_BOND_BOOST) < 1e-9
        assert abs(stock_diff + _HIGH_RATE_STOCK_DRAG) < 1e-9

    def test_cash_uses_kr_base_rate(self):
        """현금 수익률은 한국 기준금리로 결정되어야 한다"""
        snap = _snap(kr_base_rate=3.5, cpi_us=0.0)
        result = _adjust_return_for_market(0.02, AssetType.CASH, snap)
        assert abs(result - 0.035) < 1e-9

    def test_bond_floor_applied_on_high_inflation(self):
        """인플레이션이 극단적으로 높으면 채권 수익률이 최소값(_MIN_REAL_RETURN)으로 고정된다"""
        snap = _snap(us_10y_yield=3.0, cpi_us=99.0)
        result = _adjust_return_for_market(0.04, AssetType.BOND, snap)
        assert result == _MIN_REAL_RETURN

    def test_alternative_unaffected_by_rate(self):
        """대안자산은 금리 환경에 영향을 받지 않아야 한다"""
        snap_high = _snap(us_10y_yield=_HIGH_RATE_THRESHOLD + 1.0)
        snap_low  = _snap(us_10y_yield=_HIGH_RATE_THRESHOLD - 1.0)
        assert _adjust_return_for_market(0.05, AssetType.ALTERNATIVE, snap_high) == \
               _adjust_return_for_market(0.05, AssetType.ALTERNATIVE, snap_low)


# ── get_asset_return ──────────────────────────────────────────────────────────

class TestGetAssetReturn:
    def test_no_ticker_returns_valid_floats(self):
        """ticker 없으면 기본값 기반으로 유효한 수익률·변동성을 반환해야 한다"""
        snap = _snap()
        ret, vol = get_asset_return(_alloc(AssetType.FOREIGN_STOCK), snap)
        assert isinstance(ret, float)
        assert isinstance(vol, float)
        assert 0.0 < ret < 1.0
        assert 0.0 < vol < 2.0

    def test_ticker_blends_historical_return(self):
        """ticker 있으면 역사적 수익률과 블렌딩된 값을 반환해야 한다"""
        snap = _snap()
        hist_return, hist_vol = 0.30, 0.40
        with patch("services.market_data._fetch_historical_stats",
                   return_value=(hist_return, hist_vol)) as mock_fetch:
            ret, vol = get_asset_return(_alloc(AssetType.FOREIGN_STOCK, ticker="AAPL"), snap)
            mock_fetch.assert_called_once_with("AAPL")

        base_ret, base_vol = get_asset_return(_alloc(AssetType.FOREIGN_STOCK), snap)
        expected_ret = base_ret * (1 - _HIST_BLEND_RATIO) + hist_return * _HIST_BLEND_RATIO
        expected_vol = base_vol * (1 - _HIST_BLEND_RATIO) + hist_vol  * _HIST_BLEND_RATIO
        assert abs(ret - expected_ret) < 1e-9
        assert abs(vol - expected_vol) < 1e-9

    def test_ticker_fetch_failure_falls_back_to_base(self):
        """_fetch_historical_stats 실패 시 기본값으로 fallback해야 한다"""
        snap = _snap()
        with patch("services.market_data._fetch_historical_stats",
                   side_effect=ValueError("데이터 부족")):
            ret_with_ticker, vol_with_ticker = get_asset_return(
                _alloc(AssetType.FOREIGN_STOCK, ticker="INVALID"), snap
            )
        ret_no_ticker, vol_no_ticker = get_asset_return(_alloc(AssetType.FOREIGN_STOCK), snap)
        assert abs(ret_with_ticker - ret_no_ticker) < 1e-9
        assert abs(vol_with_ticker - vol_no_ticker) < 1e-9
