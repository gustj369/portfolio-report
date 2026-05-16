"""chart_generator.py 스모크 테스트

네트워크·외부 자원 없이 각 차트 함수가 비어 있지 않은 PNG bytes를 반환하는지 검증한다.
"""
from models.portfolio import Portfolio, Allocation, AssetType
from models.report import SimulationResult, ScenarioResult, RebalancingRecommendation
from services.chart_generator import (
    generate_portfolio_pie_chart,
    generate_projection_line_chart,
    generate_stacked_bar_chart,
    generate_rebalancing_comparison_chart,
)


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

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


def _recommendations() -> list[RebalancingRecommendation]:
    return [
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
    ]


# ── 스모크 테스트 ──────────────────────────────────────────────────────────────

class TestChartGeneratorSmoke:
    def test_pie_chart_returns_nonempty_bytes(self):
        """파이차트가 비어 있지 않은 bytes를 반환해야 한다"""
        result = generate_portfolio_pie_chart(_portfolio())

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_projection_line_chart_returns_nonempty_bytes(self):
        """꺾은선 차트가 비어 있지 않은 bytes를 반환해야 한다"""
        result = generate_projection_line_chart(_simulation())

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_stacked_bar_chart_returns_nonempty_bytes(self):
        """스택 바 차트가 비어 있지 않은 bytes를 반환해야 한다"""
        result = generate_stacked_bar_chart(_portfolio(), _simulation())

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_rebalancing_comparison_chart_returns_nonempty_bytes(self):
        """리밸런싱 비교 파이차트가 비어 있지 않은 bytes를 반환해야 한다"""
        result = generate_rebalancing_comparison_chart(_portfolio(), _recommendations())

        assert isinstance(result, bytes)
        assert len(result) > 0
