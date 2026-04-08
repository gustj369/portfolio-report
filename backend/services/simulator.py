"""
5년 복리 시뮬레이션 (3개 시나리오: 비관/기본/낙관)
"""
from models.portfolio import Portfolio
from models.report import SimulationResult, ScenarioResult
from services.market_data import get_weighted_return_and_vol, MarketSnapshot

SCENARIOS = {
    "bear": ("비관", 0.6),
    "base": ("기본", 1.0),
    "bull": ("낙관", 1.4),
}

INVESTMENT_YEARS = 5
MONTHS = INVESTMENT_YEARS * 12


def run_simulation(
    portfolio: Portfolio,
    market_snapshot: MarketSnapshot,
) -> SimulationResult:
    """
    포트폴리오 5년 시뮬레이션 실행
    Returns: SimulationResult (3개 시나리오)
    """
    base_return, base_vol = get_weighted_return_and_vol(
        portfolio.allocations, market_snapshot
    )

    initial_value = float(portfolio.total_asset)
    monthly_contribution = float(portfolio.monthly_saving)

    results = {}
    for scenario_key, (scenario_name, multiplier) in SCENARIOS.items():
        annual_return = base_return * multiplier
        scenario_result = _simulate_scenario(
            name=scenario_name,
            initial_value=initial_value,
            monthly_contribution=monthly_contribution,
            annual_return=annual_return,
            months=MONTHS,
        )
        results[scenario_key] = scenario_result

    return SimulationResult(
        bear=results["bear"],
        base=results["base"],
        bull=results["bull"],
        initial_value=initial_value,
        monthly_contribution=monthly_contribution,
    )


def _simulate_scenario(
    name: str,
    initial_value: float,
    monthly_contribution: float,
    annual_return: float,
    months: int,
) -> ScenarioResult:
    """단일 시나리오 월별 시뮬레이션"""
    monthly_return = (1 + annual_return) ** (1 / 12) - 1
    monthly_return = max(monthly_return, -0.05)  # 하한선

    values = []
    current_value = initial_value
    peak_value = initial_value
    max_drawdown = 0.0

    for _ in range(months):
        # 월 수익 적용
        current_value = current_value * (1 + monthly_return)
        # 월 적립금 추가
        current_value += monthly_contribution

        # 최대 낙폭 계산
        if current_value > peak_value:
            peak_value = current_value
        drawdown = (peak_value - current_value) / peak_value if peak_value > 0 else 0
        max_drawdown = max(max_drawdown, drawdown)

        values.append(round(current_value, 2))

    final_value = values[-1]
    total_invested = initial_value + monthly_contribution * months
    total_return_pct = (final_value - total_invested) / total_invested * 100 if total_invested > 0 else 0

    # CAGR = 실제 포트폴리오 연수익률 (DCA 기여분을 감안한 전체 투자 대비 성장률)
    years = months / 12
    cagr = (final_value / total_invested) ** (1 / years) - 1 if total_invested > 0 else 0

    return ScenarioResult(
        name=name,
        monthly_values=values,
        final_value=round(final_value, 0),
        total_return_pct=round(total_return_pct, 2),
        cagr=round(cagr * 100, 2),
        max_drawdown=round(max_drawdown * 100, 2),
    )


def calculate_risk_score(
    portfolio: Portfolio,
    market_snapshot: MarketSnapshot,
) -> tuple[int, str]:
    """
    포트폴리오 리스크 점수 계산 (0~100)
    Returns: (score, grade)
    """
    _, weighted_vol = get_weighted_return_and_vol(portfolio.allocations, market_snapshot)

    # 변동성 기반 기본 점수 (연 변동성 20% → 100점 기준)
    vol_score = min(int(weighted_vol * 500), 100)

    # 집중도 패널티 (단일 자산 60% 초과 시)
    max_weight = max(a.weight for a in portfolio.allocations)
    concentration_penalty = max(0, (max_weight - 60) * 0.5)

    # 자산군 다양성 보너스
    asset_types = set(a.asset_type for a in portfolio.allocations)
    diversity_bonus = len(asset_types) * 3

    score = int(vol_score + concentration_penalty - diversity_bonus)
    score = max(0, min(100, score))

    if score <= 30:
        grade = "안정형"
    elif score <= 65:
        grade = "중립형"
    else:
        grade = "공격형"

    return score, grade
