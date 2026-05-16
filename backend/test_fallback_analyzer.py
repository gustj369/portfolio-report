"""fallback_analyzer.py 단위 테스트

네트워크·AI API 없이 핵심 분기를 검증한다.
"""
import pytest

from models.portfolio import Portfolio, Allocation, AssetType
from services.fallback_analyzer import (
    _group_weights,
    _generate_rebalancing,
    _TARGET_ALLOC,
    _DIRECTION_THRESHOLD,
)


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _alloc(name: str, asset_type: AssetType, weight: float) -> Allocation:
    return Allocation(asset_name=name, asset_type=asset_type, weight=weight)


def _portfolio(*allocations: Allocation) -> Portfolio:
    return Portfolio(total_asset=1000, monthly_saving=50, allocations=list(allocations))


# ── _group_weights ────────────────────────────────────────────────────────────

class TestGroupWeights:
    def test_equity_bond_cash_classified_correctly(self):
        """주식·채권·현금이 올바른 그룹에 집계되어야 한다"""
        portfolio = _portfolio(
            _alloc("국내주식", AssetType.DOMESTIC_STOCK, 60.0),
            _alloc("채권", AssetType.BOND, 30.0),
            _alloc("현금", AssetType.CASH, 10.0),
        )
        g = _group_weights(portfolio)

        assert g["equity"] == pytest.approx(60.0)
        assert g["bond"] == pytest.approx(30.0)
        assert g["cash"] == pytest.approx(10.0)
        assert g["alt"] == pytest.approx(0.0)

    def test_alt_types_grouped_together(self):
        """비트코인·금·대안자산이 모두 alt 그룹으로 집계되어야 한다"""
        portfolio = _portfolio(
            _alloc("비트코인", AssetType.BITCOIN, 30.0),
            _alloc("금", AssetType.GOLD, 20.0),
            _alloc("현금", AssetType.CASH, 50.0),
        )
        g = _group_weights(portfolio)

        assert g["alt"] == pytest.approx(50.0)
        assert g["equity"] == pytest.approx(0.0)


# ── _generate_rebalancing ─────────────────────────────────────────────────────

class TestGenerateRebalancing:
    def test_recommended_weights_sum_to_100(self):
        """추천 비중 합계는 항상 100이어야 한다 (전형적인 3-자산 포트폴리오)"""
        portfolio = _portfolio(
            _alloc("국내주식", AssetType.DOMESTIC_STOCK, 60.0),
            _alloc("채권", AssetType.BOND, 30.0),
            _alloc("현금", AssetType.CASH, 10.0),
        )
        g = _group_weights(portfolio)
        target = _TARGET_ALLOC["중립형"]

        recs = _generate_rebalancing(portfolio, g, target, "중립형")
        total = sum(r.recommended_weight for r in recs)

        assert total == pytest.approx(100.0, abs=0.2)

    def test_no_bond_portfolio_gets_add_recommendation(self):
        """채권이 없는 포트폴리오는 채권 신규 편입('추가') 추천을 받아야 한다"""
        portfolio = _portfolio(
            _alloc("국내주식", AssetType.DOMESTIC_STOCK, 80.0),
            _alloc("현금", AssetType.CASH, 20.0),
        )
        g = _group_weights(portfolio)
        target = _TARGET_ALLOC["중립형"]  # bond 목표 20% > 0

        recs = _generate_rebalancing(portfolio, g, target, "중립형")
        directions = [r.direction for r in recs]

        assert "추가" in directions

    def test_small_adjustment_gives_direction_유지(self):
        """목표 비중과의 차이가 _DIRECTION_THRESHOLD 미만이면 '유지'로 분류되어야 한다"""
        # 중립형 채권 목표 20% — 현재 20% (차이 0, 임계값 0.5 미만)
        portfolio = _portfolio(
            _alloc("국내주식", AssetType.DOMESTIC_STOCK, 65.0),
            _alloc("채권", AssetType.BOND, 20.0),
            _alloc("현금", AssetType.CASH, 15.0),
        )
        g = _group_weights(portfolio)
        target = _TARGET_ALLOC["중립형"]

        recs = _generate_rebalancing(portfolio, g, target, "중립형")
        bond_rec = next(r for r in recs if r.asset_name == "채권")

        assert bond_rec.direction == "유지"

    def test_excess_equity_gets_direction_감소(self):
        """주식 비중이 목표를 크게 초과하면 '감소' 방향을 받아야 한다"""
        # 안정형 주식 목표 35% — 현재 90% (차이 55%, 임계값 0.5 초과)
        portfolio = _portfolio(
            _alloc("국내주식", AssetType.DOMESTIC_STOCK, 90.0),
            _alloc("현금", AssetType.CASH, 10.0),
        )
        g = _group_weights(portfolio)
        target = _TARGET_ALLOC["안정형"]

        recs = _generate_rebalancing(portfolio, g, target, "안정형")
        equity_rec = next(r for r in recs if r.asset_name == "국내주식")

        assert equity_rec.direction == "감소"
        assert equity_rec.recommended_weight < equity_rec.current_weight
