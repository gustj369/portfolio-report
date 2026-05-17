"""
services/simulator.py 단위 테스트

네트워크·외부 서비스 없이 핵심 경로 검증
커버 범위:
  run_simulation — monthly_saving=0, bear/base/bull 순서, monthly_values 길이,
                   initial_value 반영, 낙관 상한(cap), CAGR 공식
  calculate_risk_score — 안정형(≤30) / 공격형(>65) / 중립형 /
                         집중도 패널티 / 다양성 보너스 / 점수 클램핑
"""
import sys
import os
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from models.portfolio import AssetType, Allocation, Portfolio
from services.simulator import (
    run_simulation,
    calculate_risk_score,
    MONTHS,
    _BULL_RETURN_CAP,
    _STABLE_GRADE_MAX,
    _NEUTRAL_GRADE_MAX,
)
from conftest import make_market


# ──────────────────────────────────────────────────────────────
# 포트폴리오 생성 헬퍼
# ──────────────────────────────────────────────────────────────

def _portfolio(
    *assets: tuple[str, AssetType, float],
    total_asset: int = 5000,
    monthly_saving: int = 0,
) -> Portfolio:
    """포트폴리오 생성 헬퍼.

    args: (asset_name, asset_type, weight) 튜플 목록
    비중 합계는 100이어야 한다.
    """
    allocations = [
        Allocation(asset_name=name, asset_type=atype, weight=w)
        for name, atype, w in assets
    ]
    return Portfolio(
        total_asset=total_asset,
        monthly_saving=monthly_saving,
        allocations=allocations,
    )


# ──────────────────────────────────────────────────────────────
# run_simulation — 기본 동작
# ──────────────────────────────────────────────────────────────

class TestRunSimulation:
    def test_monthly_values_length_equals_months(self):
        """각 시나리오의 monthly_values 길이는 MONTHS(60)과 같아야 한다"""
        portfolio = _portfolio(("S&P500", AssetType.FOREIGN_STOCK, 100.0))
        snap = make_market()
        with patch("services.simulator.get_weighted_return_and_vol", return_value=(0.08, 0.15)):
            result = run_simulation(portfolio, snap)
        assert len(result.bear.monthly_values) == MONTHS
        assert len(result.base.monthly_values) == MONTHS
        assert len(result.bull.monthly_values) == MONTHS

    def test_bear_less_than_base_less_than_bull(self):
        """비관 < 기본 < 낙관 순서로 최종 자산이 증가해야 한다"""
        portfolio = _portfolio(("S&P500", AssetType.FOREIGN_STOCK, 100.0))
        snap = make_market()
        with patch("services.simulator.get_weighted_return_and_vol", return_value=(0.08, 0.15)):
            result = run_simulation(portfolio, snap)
        assert result.bear.final_value < result.base.final_value < result.bull.final_value

    def test_no_monthly_saving_contribution_is_zero(self):
        """monthly_saving=0이면 SimulationResult.monthly_contribution=0.0으로 저장된다"""
        portfolio = _portfolio(("국채", AssetType.BOND, 100.0), monthly_saving=0)
        snap = make_market()
        with patch("services.simulator.get_weighted_return_and_vol", return_value=(0.04, 0.07)):
            result = run_simulation(portfolio, snap)
        assert result.monthly_contribution == 0.0

    def test_initial_value_reflects_portfolio_total_asset(self):
        """SimulationResult.initial_value가 포트폴리오 total_asset와 일치해야 한다"""
        portfolio = _portfolio(("국채", AssetType.BOND, 100.0), total_asset=3000)
        snap = make_market()
        with patch("services.simulator.get_weighted_return_and_vol", return_value=(0.04, 0.07)):
            result = run_simulation(portfolio, snap)
        assert result.initial_value == 3000.0

    def test_bull_return_capped_at_bull_return_cap(self):
        """base_return × 1.4 > _BULL_RETURN_CAP 이면 낙관 CAGR이 cap 값(25.0%)으로 제한된다"""
        portfolio = _portfolio(("BTC", AssetType.BITCOIN, 100.0))
        snap = make_market()
        # base_return=0.25 → bull = 0.35 → cap at 0.25
        with patch("services.simulator.get_weighted_return_and_vol", return_value=(0.25, 0.80)):
            result = run_simulation(portfolio, snap)
        assert result.bull.cagr == round(_BULL_RETURN_CAP * 100, 2)

    def test_bull_not_capped_when_below_threshold(self):
        """base_return × 1.4 <= _BULL_RETURN_CAP 이면 캡이 적용되지 않는다"""
        portfolio = _portfolio(("국채", AssetType.BOND, 100.0))
        snap = make_market()
        # base_return=0.10 → bull = 0.14 < 0.25 → no cap
        with patch("services.simulator.get_weighted_return_and_vol", return_value=(0.10, 0.07)):
            result = run_simulation(portfolio, snap)
        assert result.bull.cagr == round(0.14 * 100, 2)

    def test_cagr_equals_annual_return_directly(self):
        """CAGR은 DCA 수식이 아닌 적용된 연수익률(annual_return) 그 자체여야 한다"""
        portfolio = _portfolio(("S&P500", AssetType.FOREIGN_STOCK, 100.0))
        snap = make_market()
        # base_return=0.08 → bear=0.048, base=0.08, bull=0.112
        with patch("services.simulator.get_weighted_return_and_vol", return_value=(0.08, 0.15)):
            result = run_simulation(portfolio, snap)
        assert result.base.cagr == round(0.08 * 100, 2)
        assert abs(result.bear.cagr - round(0.048 * 100, 2)) < 1e-6
        assert abs(result.bull.cagr - round(0.112 * 100, 2)) < 1e-6

    def test_monthly_saving_increases_final_value(self):
        """월 적립금이 있으면 없을 때보다 최종 자산이 커야 한다"""
        snap = make_market()
        with patch("services.simulator.get_weighted_return_and_vol", return_value=(0.06, 0.15)):
            result_no_saving  = run_simulation(
                _portfolio(("국채", AssetType.BOND, 100.0), monthly_saving=0), snap
            )
            result_with_saving = run_simulation(
                _portfolio(("국채", AssetType.BOND, 100.0), monthly_saving=100), snap
            )
        assert result_with_saving.base.final_value > result_no_saving.base.final_value


# ──────────────────────────────────────────────────────────────
# calculate_risk_score — 등급 분기 (lines 162-167)
# ──────────────────────────────────────────────────────────────

class TestCalculateRiskScore:
    def test_stable_grade_for_low_risk_portfolio(self):
        """단기채권·현금 분산 포트폴리오는 안정형 등급이어야 한다 (score ≤ 30)

        SHORT_BOND 50% + CASH 50%:
          weighted_vol = 0.5*0.02 + 0.5*0.01 = 0.015 → vol_score=4
          risky_w = 0 → risky_score=0
          max_weight=50 → concentration_penalty=5
          2 asset_types → diversity_bonus=4
          score = 4+0+5-4 = 5 ≤ 30 → 안정형
        """
        portfolio = _portfolio(
            ("단기채", AssetType.SHORT_BOND, 50.0),
            ("현금", AssetType.CASH, 50.0),
        )
        snap = make_market()
        score, grade = calculate_risk_score(portfolio, snap)
        assert score <= _STABLE_GRADE_MAX
        assert grade == "안정형"

    def test_aggressive_grade_for_bitcoin_portfolio(self):
        """비트코인 100% 포트폴리오는 공격형 등급이어야 한다 (score > 65)

        BITCOIN 100%:
          weighted_vol = 0.80 → vol_score = min(240, 80) = 80
          risky_w = 1.0 → risky_score = 30
          max_weight=100 → concentration_penalty = int(60*0.5) = 30
          1 asset_type → diversity_bonus = 2
          score = 80+30+30-2 = 138 → clamp → 100 → 공격형
        """
        portfolio = _portfolio(("BTC", AssetType.BITCOIN, 100.0))
        snap = make_market()
        score, grade = calculate_risk_score(portfolio, snap)
        assert score > _NEUTRAL_GRADE_MAX
        assert grade == "공격형"

    def test_neutral_grade_for_mixed_portfolio(self):
        """해외주식 50% + 채권 50% 혼합 포트폴리오는 중립형 등급이어야 한다

        FOREIGN_STOCK 50% + BOND 50%:
          weighted_vol = 0.5*0.18 + 0.5*0.07 = 0.125 → vol_score = min(37, 80) = 37
          risky_w = 0.5 → risky_score = 15
          max_weight=50 → concentration_penalty=5
          2 asset_types → diversity_bonus=4
          score = 37+15+5-4 = 53 → 중립형
        """
        portfolio = _portfolio(
            ("S&P500", AssetType.FOREIGN_STOCK, 50.0),
            ("국채", AssetType.BOND, 50.0),
        )
        snap = make_market()
        score, grade = calculate_risk_score(portfolio, snap)
        assert _STABLE_GRADE_MAX < score <= _NEUTRAL_GRADE_MAX
        assert grade == "중립형"

    def test_score_clamped_to_100(self):
        """극단 고위험 포트폴리오에서도 점수는 100을 초과하지 않는다"""
        portfolio = _portfolio(("BTC", AssetType.BITCOIN, 100.0))
        snap = make_market()
        score, _ = calculate_risk_score(portfolio, snap)
        assert score <= 100

    def test_score_not_below_zero(self):
        """점수는 0 미만이 되지 않는다 (하한선 클램핑 검증)"""
        portfolio = _portfolio(
            ("단기채", AssetType.SHORT_BOND, 20.0),
            ("국채", AssetType.BOND, 20.0),
            ("현금", AssetType.CASH, 20.0),
            ("해외주식", AssetType.FOREIGN_STOCK, 20.0),
            ("국내주식", AssetType.DOMESTIC_STOCK, 20.0),
        )
        snap = make_market()
        score, _ = calculate_risk_score(portfolio, snap)
        assert score >= 0

    def test_concentration_penalty_increases_score(self):
        """단일 자산 100% 집중 vs 동일 자산유형 분산 — 집중 시 점수가 더 높다

        BOND 100% → concentration_penalty = int((100-40)*0.5) = 30
        BOND 33.3% × 3 → concentration_penalty = 0 (max_weight ≤ 40)
        """
        portfolio_concentrated = _portfolio(("국채", AssetType.BOND, 100.0))
        portfolio_spread = _portfolio(
            ("국채A", AssetType.BOND, 33.3),
            ("국채B", AssetType.BOND, 33.3),
            ("국채C", AssetType.BOND, 33.4),
        )
        snap = make_market()
        score_c, _ = calculate_risk_score(portfolio_concentrated, snap)
        score_s, _ = calculate_risk_score(portfolio_spread, snap)
        assert score_c > score_s

    def test_diversity_bonus_reduces_score(self):
        """자산 유형 수가 많을수록 점수가 낮아진다 (다양성 보너스 효과)"""
        portfolio_single_type = _portfolio(
            ("국채A", AssetType.BOND, 33.3),
            ("국채B", AssetType.BOND, 33.3),
            ("국채C", AssetType.BOND, 33.4),
        )
        portfolio_two_types = _portfolio(
            ("국채", AssetType.BOND, 50.0),
            ("단기채", AssetType.SHORT_BOND, 50.0),
        )
        snap = make_market()
        score_single, _ = calculate_risk_score(portfolio_single_type, snap)
        score_diverse, _ = calculate_risk_score(portfolio_two_types, snap)
        # 두 유형은 diversity_bonus=4, 단일 유형은 diversity_bonus=2
        # 또한 집중도: 단일타입=33% (패널티없음), 두 타입=50% (패널티5) 이므로
        # 순수 다양성 효과를 확인하려면 vol 차이도 감안해야 함
        # SHORT_BOND(0.02)가 BOND(0.07)보다 낮으므로 두 타입이 vol도 낮음 → 더 낮은 점수
        assert score_diverse < score_single

    def test_risky_asset_weight_increases_score(self):
        """위험자산(해외주식) 비중이 높을수록 점수가 높아야 한다"""
        portfolio_risky = _portfolio(("S&P500", AssetType.FOREIGN_STOCK, 100.0))
        portfolio_safe  = _portfolio(("국채", AssetType.BOND, 100.0))
        snap = make_market()
        score_r, _ = calculate_risk_score(portfolio_risky, snap)
        score_s, _ = calculate_risk_score(portfolio_safe, snap)
        assert score_r > score_s
