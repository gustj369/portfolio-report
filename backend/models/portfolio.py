from pydantic import BaseModel, field_validator
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


class UserProfile(BaseModel):
    age: int
    monthly_income: int  # 만원
    investment_goal: InvestmentGoal
    investment_period: int = 5  # 년
    risk_tolerance: RiskTolerance
    name: str = ""
    email: str = ""


class Allocation(BaseModel):
    asset_name: str
    asset_type: AssetType
    weight: float  # 0~100
    ticker: Optional[str] = None
    amount: Optional[float] = None  # 만원

    @field_validator("weight")
    @classmethod
    def weight_range(cls, v: float) -> float:
        if not 0 <= v <= 100:
            raise ValueError("비중은 0~100 사이여야 합니다")
        return v


class Portfolio(BaseModel):
    total_asset: int  # 만원
    monthly_saving: int  # 만원
    allocations: list[Allocation]

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
