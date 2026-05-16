"""pdf_generator.py 스모크 테스트

외부 의존 없이 build_report()가 유효한 PDF bytes(%PDF 헤더)를 반환하는지 검증한다.
"""
from datetime import datetime, timezone

from models.portfolio import Portfolio, Allocation, AssetType, UserProfile, RiskTolerance, InvestmentGoal
from models.report import (
    SimulationResult, ScenarioResult, AIContent,
    RebalancingRecommendation, MarketSnapshot,
)
from services.market_data import MARKET_DEFAULTS
from services.pdf_generator import build_report


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _user_profile() -> UserProfile:
    return UserProfile(
        age=40, monthly_income=500,
        investment_goal=InvestmentGoal.WEALTH,
        investment_period=5,
        risk_tolerance=RiskTolerance.NEUTRAL,
    )


def _portfolio() -> Portfolio:
    return Portfolio(
        total_asset=1000,
        monthly_saving=50,
        allocations=[
            Allocation(asset_name="국내주식", asset_type=AssetType.DOMESTIC_STOCK, weight=60.0),
            Allocation(asset_name="채권",   asset_type=AssetType.BOND,           weight=30.0),
            Allocation(asset_name="현금",   asset_type=AssetType.CASH,           weight=10.0),
        ],
    )


def _simulation() -> SimulationResult:
    def _scenario(name: str, final: float, cagr: float) -> ScenarioResult:
        return ScenarioResult(
            name=name,
            monthly_values=[final * (i / 60) for i in range(1, 61)],
            final_value=final,
            total_return_pct=(final - 1000) / 1000 * 100,
            cagr=cagr,
            max_drawdown=5.0,
        )

    return SimulationResult(
        bear=_scenario("비관", 900.0, -2.1),
        base=_scenario("기본", 1200.0, 3.7),
        bull=_scenario("낙관", 1600.0, 9.9),
        initial_value=1000.0,
        monthly_contribution=50.0,
    )


def _ai_content() -> AIContent:
    return AIContent(
        portfolio_diagnosis="균형 잡힌 포트폴리오입니다.",
        strengths=["분산 투자", "꾸준한 적립", "채권 방어막"],
        weaknesses=["주식 집중도 높음"],
        risk_score=50,
        risk_grade="중립형",
        scenario_commentary={
            "bear": "경기침체 시 손실 발생 가능",
            "base": "현 시장 지속 시 안정적 성장",
            "bull": "강세장에서 높은 수익 기대",
        },
        rebalancing_recommendations=[
            RebalancingRecommendation(
                asset_name="국내주식", current_weight=60.0, recommended_weight=55.0,
                direction="감소", reason="분산 필요",
            ),
            RebalancingRecommendation(
                asset_name="채권", current_weight=30.0, recommended_weight=35.0,
                direction="증가", reason="방어력 보강",
            ),
            RebalancingRecommendation(
                asset_name="현금", current_weight=10.0, recommended_weight=10.0,
                direction="유지", reason="유동성 유지",
            ),
        ],
        market_commentary="고금리 환경이 지속되고 있습니다.",
        cautions=["원금 손실 가능성이 있습니다.", "정기적인 리밸런싱을 권장합니다."],
    )


def _market_snapshot() -> MarketSnapshot:
    fields = dict(MARKET_DEFAULTS)
    fields["fetched_at"] = datetime.now(timezone.utc)
    return MarketSnapshot(**fields)


# ── 스모크 테스트 ──────────────────────────────────────────────────────────────

class TestBuildReportSmoke:
    def test_build_report_returns_valid_pdf_bytes(self):
        """build_report()가 %PDF 헤더로 시작하는 유효한 PDF bytes를 반환해야 한다"""
        result = build_report(
            user_profile=_user_profile(),
            portfolio=_portfolio(),
            simulation=_simulation(),
            ai_content=_ai_content(),
            market_snapshot=_market_snapshot(),
            charts={},  # 차트 없이도 PDF가 생성되어야 한다
        )

        assert isinstance(result, bytes)
        assert len(result) > 0
        assert result[:4] == b"%PDF"
