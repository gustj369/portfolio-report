from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from enum import Enum


class InvestmentGoal(str, Enum):
    RETIREMENT = "노후준비"
    HOUSING = "주택구입"
    WEALTH = "자산증식"
    OTHER = "기타"


class RiskTolerance(str, Enum):
    STABLE = "안정형"
    NEUTRAL = "중립형"
    AGGRESSIVE = "공격형"


class AssetType(str, Enum):
    DOMESTIC_STOCK = "국내주식"
    FOREIGN_STOCK = "해외주식"
    BOND = "채권"
    SHORT_BOND = "단기채권"    # T-bill, MMF, CD 등
    CASH = "현금"
    ALTERNATIVE = "대안자산"
    BITCOIN = "비트코인"
    CRYPTO = "암호화폐"        # ETH, SOL, XRP 등 비트코인 외 암호화폐
    GOLD = "금"


# 입력 상한 — 프론트 제한보다 넉넉하게 두어 정상 입력은 거절하지 않고, 비정상·남용 입력만 422로 차단
_MAX_AMOUNT_MANWON = 10_000_000   # 1,000억원 (만원 단위)
_MAX_ALLOCATIONS = 20              # 프론트 '자산 추가' 상한과 동일
_MAX_NAME_LEN = 50


class UserProfile(BaseModel):
    age: int = Field(ge=1, le=120)
    monthly_income: int = Field(ge=0, le=_MAX_AMOUNT_MANWON)  # 만원
    investment_goal: InvestmentGoal
    investment_period: int = Field(default=5, ge=1, le=50)  # 년
    risk_tolerance: RiskTolerance
    name: str = Field(default="", max_length=_MAX_NAME_LEN)
    email: str = Field(default="", max_length=254)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """이메일 형식 기본 검증 — 빈 문자열은 허용(선택 입력), 값이 있으면 '@' 포함 여부 확인."""
        if v and "@" not in v:
            raise ValueError("유효하지 않은 이메일 주소입니다 ('@' 가 포함되어야 합니다)")
        return v


class Allocation(BaseModel):
    asset_name: str = Field(max_length=_MAX_NAME_LEN)
    asset_type: AssetType
    weight: float  # 0~100
    ticker: Optional[str] = Field(default=None, max_length=20)
    amount: Optional[float] = Field(default=None, ge=0)  # 만원

    @field_validator("weight")
    @classmethod
    def weight_range(cls, v: float) -> float:
        if not 0 <= v <= 100:
            raise ValueError("비중은 0~100 사이여야 합니다")
        return v

    @model_validator(mode="after")
    def default_name_to_type(self) -> "Allocation":
        """자산명을 비워두면 자산 유형명으로 채움 — 차트 범례·PDF 표에 빈 라벨이 생기지 않도록"""
        if not self.asset_name.strip():
            self.asset_name = self.asset_type.value
        return self


class Portfolio(BaseModel):
    total_asset: int = Field(ge=0, le=_MAX_AMOUNT_MANWON)  # 만원
    monthly_saving: int = Field(ge=0, le=_MAX_AMOUNT_MANWON)  # 만원
    allocations: list[Allocation] = Field(min_length=1, max_length=_MAX_ALLOCATIONS)

    @field_validator("allocations")
    @classmethod
    def weights_sum(cls, v: list[Allocation]) -> list[Allocation]:
        total = sum(a.weight for a in v)
        if abs(total - 100) > 1:
            raise ValueError(f"비중 합계가 100%가 아닙니다 (현재: {total:.1f}%)")
        return v


class AnalyzeRequest(BaseModel):
    user_profile: UserProfile
    portfolio: Portfolio
