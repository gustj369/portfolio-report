"""
models/portfolio.py field_validator 단위 테스트

외부 의존 없이 Pydantic 모델 직접 인스턴스화로 검증한다.

커버 범위:
  Allocation.weight_range     — 0~100 범위 검사
  Portfolio.weights_sum       — 비중 합계 100% 검사
  UserProfile.validate_email  — 이메일 형식 기본 검사
"""
import pytest
from pydantic import ValidationError

from models.portfolio import (
    Allocation,
    AssetType,
    Portfolio,
    UserProfile,
    InvestmentGoal,
    RiskTolerance,
)


# ──────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────

def _alloc(weight: float, asset_type: AssetType = AssetType.FOREIGN_STOCK) -> Allocation:
    """Allocation 생성 헬퍼 — 필수 필드 최소화"""
    return Allocation(asset_name="테스트자산", asset_type=asset_type, weight=weight)


def _portfolio(*weights: float) -> Portfolio:
    """가중치 목록으로 Portfolio 생성 헬퍼"""
    allocations = [_alloc(w) for w in weights]
    return Portfolio(total_asset=1000, monthly_saving=0, allocations=allocations)


def _user_profile(**kwargs) -> UserProfile:
    """UserProfile 생성 헬퍼 — 기본값 포함, kwargs로 필드 오버라이드"""
    defaults = dict(
        age=30,
        monthly_income=400,
        investment_goal=InvestmentGoal.WEALTH,
        risk_tolerance=RiskTolerance.NEUTRAL,
    )
    defaults.update(kwargs)
    return UserProfile(**defaults)


# ──────────────────────────────────────────────────────────────
# Allocation.weight_range
# ──────────────────────────────────────────────────────────────

class TestWeightRange:
    def test_weight_zero_is_valid(self):
        """경계값 0은 유효해야 한다"""
        alloc = _alloc(0.0)
        assert alloc.weight == 0.0

    def test_weight_100_is_valid(self):
        """경계값 100은 유효해야 한다"""
        alloc = _alloc(100.0)
        assert alloc.weight == 100.0

    def test_weight_midpoint_is_valid(self):
        """중간값 50은 유효해야 한다"""
        alloc = _alloc(50.0)
        assert alloc.weight == 50.0

    def test_weight_negative_raises(self):
        """음수 비중은 ValidationError를 발생시켜야 한다"""
        with pytest.raises(ValidationError) as exc_info:
            _alloc(-0.1)
        assert "비중은 0~100 사이여야 합니다" in str(exc_info.value)

    def test_weight_above_100_raises(self):
        """100 초과 비중은 ValidationError를 발생시켜야 한다"""
        with pytest.raises(ValidationError) as exc_info:
            _alloc(100.1)
        assert "비중은 0~100 사이여야 합니다" in str(exc_info.value)

    def test_weight_large_value_raises(self):
        """큰 값(200)도 ValidationError를 발생시켜야 한다"""
        with pytest.raises(ValidationError):
            _alloc(200.0)


# ──────────────────────────────────────────────────────────────
# Portfolio.weights_sum
# ──────────────────────────────────────────────────────────────

class TestWeightsSum:
    def test_exact_100_is_valid(self):
        """합계가 정확히 100이면 유효해야 한다"""
        ptf = _portfolio(60.0, 40.0)
        assert len(ptf.allocations) == 2

    def test_within_tolerance_is_valid(self):
        """허용 오차 1% 이내(99.5%)는 유효해야 한다"""
        ptf = _portfolio(60.0, 39.5)  # 합계 99.5
        assert len(ptf.allocations) == 2

    def test_single_asset_100_is_valid(self):
        """단일 자산 100%는 유효해야 한다"""
        ptf = _portfolio(100.0)
        assert ptf.allocations[0].weight == 100.0

    def test_sum_below_tolerance_raises(self):
        """합계가 98.9%이면 ValidationError를 발생시켜야 한다 (허용 오차 1% 초과)"""
        with pytest.raises(ValidationError) as exc_info:
            _portfolio(50.0, 48.9)  # 합계 98.9
        assert "비중 합계가 100%가 아닙니다" in str(exc_info.value)

    def test_sum_above_tolerance_raises(self):
        """합계가 101.1%이면 ValidationError를 발생시켜야 한다"""
        with pytest.raises(ValidationError) as exc_info:
            _portfolio(60.0, 41.1)  # 합계 101.1
        assert "비중 합계가 100%가 아닙니다" in str(exc_info.value)

    def test_error_message_includes_actual_total(self):
        """오류 메시지에 실제 합계값이 포함되어야 한다"""
        with pytest.raises(ValidationError) as exc_info:
            _portfolio(30.0, 30.0)  # 합계 60.0
        assert "60.0" in str(exc_info.value)

    def test_three_assets_summing_to_100(self):
        """자산 3개의 합계 100%는 유효해야 한다"""
        ptf = _portfolio(50.0, 30.0, 20.0)
        assert len(ptf.allocations) == 3


# ──────────────────────────────────────────────────────────────
# UserProfile.validate_email
# ──────────────────────────────────────────────────────────────

class TestValidateEmail:
    def test_empty_string_is_valid(self):
        """빈 문자열은 선택 입력이므로 유효해야 한다"""
        profile = _user_profile(email="")
        assert profile.email == ""

    def test_valid_email_is_accepted(self):
        """일반적인 이메일 형식은 유효해야 한다"""
        profile = _user_profile(email="user@example.com")
        assert profile.email == "user@example.com"

    def test_email_with_subdomain_is_accepted(self):
        """서브도메인 포함 이메일도 유효해야 한다"""
        profile = _user_profile(email="user@mail.example.co.kr")
        assert profile.email == "user@mail.example.co.kr"

    def test_missing_at_raises(self):
        """'@'가 없는 문자열은 ValidationError를 발생시켜야 한다"""
        with pytest.raises(ValidationError) as exc_info:
            _user_profile(email="notanemail")
        assert "@" in str(exc_info.value)

    def test_plain_domain_without_at_raises(self):
        """도메인만 있는 문자열도 ValidationError를 발생시켜야 한다"""
        with pytest.raises(ValidationError):
            _user_profile(email="example.com")

    def test_default_email_is_empty(self):
        """email 필드 미전달 시 기본값은 빈 문자열이어야 한다"""
        profile = _user_profile()
        assert profile.email == ""
