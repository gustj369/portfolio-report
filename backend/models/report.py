from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum


class ReportStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    ERROR = "error"


class ScenarioResult(BaseModel):
    name: str  # 비관 / 기본 / 낙관
    monthly_values: list[float]  # 60개월
    final_value: float  # 만원
    total_return_pct: float
    cagr: float
    max_drawdown: float


class SimulationResult(BaseModel):
    bear: ScenarioResult
    base: ScenarioResult
    bull: ScenarioResult
    initial_value: float
    monthly_contribution: float


class MarketSnapshot(BaseModel):
    sp500: float
    kospi: float
    us_10y_yield: float
    kr_base_rate: float
    usd_krw: float
    gold_price: float
    cpi_us: float
    fetched_at: datetime


class AIContent(BaseModel):
    portfolio_diagnosis: str
    strengths: list[str]
    weaknesses: list[str]
    risk_score: int  # 0~100
    risk_grade: str  # 안정형 / 중립형 / 공격형
    scenario_commentary: dict[str, str]  # bear/base/bull
    rebalancing_recommendations: list[dict]  # asset_name, current_weight, recommended_weight, reason
    market_commentary: str
    cautions: list[str]


class PreviewResponse(BaseModel):
    risk_score: int
    risk_grade: str
    base_scenario_final: float  # 만원
    base_scenario_cagr: float
    portfolio_summary: str  # AI 생성 요약 (앞 200자)
    simulation: SimulationResult
    market_data: MarketSnapshot


class ReportRecord(BaseModel):
    order_id: str
    report_token: str
    status: ReportStatus
    download_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
