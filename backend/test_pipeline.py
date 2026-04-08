"""
포트폴리오 AI 리포트 — 직접 입력 테스트 스크립트
실행: python test_pipeline.py
"""
import os
import sys

os.environ.setdefault("ANTHROPIC_API_KEY", "")

from models.portfolio import (
    UserProfile, Portfolio, Allocation,
    InvestmentGoal, RiskTolerance, AssetType,
)
from services.market_data import fetch_market_snapshot
from services.simulator import run_simulation, calculate_risk_score
from services.chart_generator import (
    generate_portfolio_pie_chart,
    generate_projection_line_chart,
    generate_stacked_bar_chart,
    generate_rebalancing_comparison_chart,
)
from services.pdf_generator import build_report
from models.report import AIContent


# ─────────────────────────────────────────────
#  헬퍼
# ─────────────────────────────────────────────

def ask(prompt: str, default: str = "") -> str:
    val = input(f"{prompt} [{default}]: ").strip()
    return val if val else default


def ask_int(prompt: str, default: int) -> int:
    while True:
        try:
            return int(ask(prompt, str(default)))
        except ValueError:
            print("  숫자를 입력하세요.")


def ask_float(prompt: str, default: float) -> float:
    while True:
        try:
            return float(ask(prompt, str(default)))
        except ValueError:
            print("  숫자를 입력하세요.")


def choose(prompt: str, options: list[str]) -> str:
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    while True:
        try:
            idx = int(input(f"{prompt} (번호 입력): ").strip())
            if 1 <= idx <= len(options):
                return options[idx - 1]
        except ValueError:
            pass
        print(f"  1~{len(options)} 사이 번호를 입력하세요.")


# ─────────────────────────────────────────────
#  입력 수집
# ─────────────────────────────────────────────

def input_user_profile() -> UserProfile:
    print("\n" + "─" * 50)
    print("  1단계: 기본 정보")
    print("─" * 50)
    name = ask("이름", "투자자")
    age = ask_int("나이", 35)
    monthly_income = ask_int("월 소득 (만원)", 400)

    print("\n투자 목표:")
    goal_str = choose("선택", [g.value for g in InvestmentGoal])
    goal = InvestmentGoal(goal_str)

    investment_period = ask_int("목표 투자 기간 (년)", 5)

    print("\n리스크 성향:")
    risk_str = choose("선택", [r.value for r in RiskTolerance])
    risk = RiskTolerance(risk_str)

    email = ask("이메일 (선택, 엔터 스킵)", "")
    return UserProfile(
        age=age,
        monthly_income=monthly_income,
        investment_goal=goal,
        investment_period=investment_period,
        risk_tolerance=risk,
        name=name,
        email=email,
    )


def input_portfolio() -> Portfolio:
    print("\n" + "─" * 50)
    print("  2단계: 포트폴리오 입력")
    print("─" * 50)
    total_asset = ask_int("총 투자 자산 (만원)", 5000)
    monthly_saving = ask_int("월 추가 적립액 (만원, 없으면 0)", 0)

    allocations: list[Allocation] = []
    asset_types = [t.value for t in AssetType]

    print(f"\n자산을 입력하세요. 비중 합계가 100%%이 되어야 합니다.")
    print("(입력 완료 후 엔터만 누르면 종료)")

    while True:
        remaining = 100.0 - sum(a.weight for a in allocations)
        print(f"\n  현재 남은 비중: {remaining:.1f}%")
        if abs(remaining) < 0.1:
            print("  비중 합계 100% 도달!")
            break

        asset_name = input("  자산명 (엔터=완료): ").strip()
        if not asset_name:
            if not allocations:
                print("  최소 1개 이상 입력하세요.")
                continue
            break

        print("  자산 유형:")
        asset_type_str = choose("  선택", asset_types)
        asset_type = AssetType(asset_type_str)

        ticker = input("  티커 (없으면 엔터, 예: SPY): ").strip() or None

        while True:
            weight = ask_float(f"  비중 % (남은 비중 {remaining:.1f}%)", round(remaining, 1))
            if 0 < weight <= remaining + 0.1:
                break
            print(f"  0 초과 {remaining:.1f} 이하 값을 입력하세요.")

        allocations.append(Allocation(
            asset_name=asset_name,
            asset_type=asset_type,
            weight=weight,
            ticker=ticker,
        ))
        print(f"  ✓ 추가됨: {asset_name} {weight:.1f}%")

    # 비중 합계 보정 (부동소수점 오차)
    total_w = sum(a.weight for a in allocations)
    if abs(total_w - 100) > 0.1:
        print(f"\n  비중 합계 {total_w:.1f}% → 마지막 자산 비중을 자동 조정합니다.")
        last = allocations[-1]
        allocations[-1] = Allocation(
            asset_name=last.asset_name,
            asset_type=last.asset_type,
            weight=round(last.weight + (100 - total_w), 1),
            ticker=last.ticker,
        )

    return Portfolio(
        total_asset=total_asset,
        monthly_saving=monthly_saving,
        allocations=allocations,
    )


def make_dummy_ai_content(
    risk_score: int,
    risk_grade: str,
    portfolio: Portfolio,
) -> AIContent:
    """Gemini API 키 없을 때 사용하는 기본 콘텐츠"""
    return AIContent(
        portfolio_diagnosis=(
            f"현재 포트폴리오는 {len(portfolio.allocations)}개 자산으로 구성되어 있습니다. "
            "전반적으로 분산 투자가 이루어져 있으나, 시장 상황에 따른 정기적 리밸런싱을 권장합니다."
        ),
        strengths=[
            "다양한 자산군 보유로 리스크 분산",
            "꾸준한 적립식 투자 계획 유지",
            "장기 투자 관점으로 복리 효과 기대 가능",
        ],
        weaknesses=[
            "특정 자산 집중도 점검 필요",
            "정기 리밸런싱 주기 설정 권장",
            "인플레이션 대응 자산 비중 검토",
        ],
        risk_score=risk_score,
        risk_grade=risk_grade,
        scenario_commentary={
            "bear": "글로벌 경기 침체, 금리 급등, 지정학적 리스크 복합 발생 시 나타날 수 있는 시나리오입니다.",
            "base": "현재 시장 환경이 유지되고 인플레이션이 점진적으로 완화될 경우의 예상 결과입니다.",
            "bull": "경기 연착륙 성공, 금리 인하 가속화, 주요국 경기 부양 시 실현 가능한 낙관적 시나리오입니다.",
        },
        rebalancing_recommendations=[
            {
                "asset_name": a.asset_name,
                "current_weight": a.weight,
                "recommended_weight": a.weight,
                "direction": "유지",
                "reason": "현재 비중이 목표 범위 내에 있어 유지를 권장합니다.",
            }
            for a in portfolio.allocations
        ],
        market_commentary=(
            "현재 고금리 환경이 지속되고 있어 채권 및 현금성 자산의 실질 수익률이 상승한 상황입니다. "
            "주식 자산의 경우 밸류에이션 부담이 있으나 장기 성장 잠재력은 유효합니다."
        ),
        cautions=[
            "투자는 원금 손실 가능성이 있으며, 본 리포트는 투자 권유가 아닙니다.",
            "환율 변동이 해외 자산 수익률에 영향을 미칠 수 있습니다.",
            "분기별 포트폴리오 점검 및 리밸런싱을 권장합니다.",
        ],
    )


# ─────────────────────────────────────────────
#  Gemini AI 분석 (선택)
# ─────────────────────────────────────────────

def run_ai_analysis(
    user_profile: UserProfile,
    portfolio: Portfolio,
    simulation,
    market_snapshot,
    gemini_api_key: str,
    risk_score: int,
    risk_grade: str,
) -> AIContent:
    if not gemini_api_key:
        print("  (GEMINI_API_KEY 없음 — 기본 텍스트 사용)")
        return make_dummy_ai_content(risk_score, risk_grade, portfolio)

    try:
        from services.ai_engine import generate_full_analysis
        print("  Gemini AI 분석 중... (15~30초 소요)")
        return generate_full_analysis(
            user_profile, portfolio, simulation, market_snapshot, gemini_api_key
        )
    except Exception as e:
        print(f"  AI 분석 실패 ({e}) — 기본 텍스트 사용")
        return make_dummy_ai_content(risk_score, risk_grade, portfolio)


# ─────────────────────────────────────────────
#  메인
# ─────────────────────────────────────────────

def main():
    print("=" * 50)
    print("  포트폴리오 AI 리포트 생성기")
    print("=" * 50)

    # 실행 모드 선택
    print("\n실행 모드를 선택하세요:")
    print("  1. 직접 입력 (내 실제 포트폴리오)")
    print("  2. 샘플 데이터 (빠른 테스트)")
    mode = input("선택 (1/2) [1]: ").strip() or "1"

    if mode == "2":
        user_profile, portfolio = _sample_data()
    else:
        user_profile = input_user_profile()
        portfolio = input_portfolio()

    # 출력 파일명
    print()
    output_name = ask("저장할 파일명 (.pdf 제외)", "my_report")
    output_path = f"{output_name}.pdf"

    # Gemini API 키 확인
    gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
    if not gemini_api_key:
        # .env 파일 직접 읽기 시도
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_path):
            for line in open(env_path):
                if line.startswith("GEMINI_API_KEY="):
                    gemini_api_key = line.split("=", 1)[1].strip()
                    break

    print("\n" + "─" * 50)
    print("  분석 시작")
    print("─" * 50)

    print("\n[1/5] 시장 데이터 수집 중...")
    market_snapshot = fetch_market_snapshot()
    print(f"      S&P500: {market_snapshot.sp500:,.0f} | 코스피: {market_snapshot.kospi:,.0f} | 달러/원: {market_snapshot.usd_krw:,.0f}")

    print("\n[2/5] 5년 시뮬레이션 실행 중...")
    simulation = run_simulation(portfolio, market_snapshot)
    risk_score, risk_grade = calculate_risk_score(portfolio, market_snapshot)
    print(f"      리스크: {risk_grade} ({risk_score}점)")
    print(f"      비관: {simulation.bear.final_value:,.0f}만원 | 기본: {simulation.base.final_value:,.0f}만원 | 낙관: {simulation.bull.final_value:,.0f}만원")

    print("\n[3/5] AI 분석 중...")
    ai_content = run_ai_analysis(
        user_profile, portfolio, simulation, market_snapshot,
        gemini_api_key, risk_score, risk_grade,
    )

    print("\n[4/5] 차트 생성 중...")
    charts = {
        "pie": generate_portfolio_pie_chart(portfolio),
        "line": generate_projection_line_chart(simulation),
        "stacked_bar": generate_stacked_bar_chart(portfolio, simulation),
        "rebalancing": generate_rebalancing_comparison_chart(
            portfolio, ai_content.rebalancing_recommendations
        ),
    }
    print(f"      파이차트 {len(charts['pie'])//1024}KB | 꺾은선 {len(charts['line'])//1024}KB")

    print("\n[5/5] PDF 생성 중...")
    pdf_bytes = build_report(
        user_profile=user_profile,
        portfolio=portfolio,
        simulation=simulation,
        ai_content=ai_content,
        market_snapshot=market_snapshot,
        charts=charts,
    )

    with open(output_path, "wb") as f:
        f.write(pdf_bytes)

    print(f"\n{'=' * 50}")
    print(f"  ✅ 리포트 생성 완료!")
    print(f"  📄 파일: {os.path.abspath(output_path)}")
    print(f"  📦 크기: {len(pdf_bytes) / 1024:.1f} KB")
    print(f"{'=' * 50}")


def _sample_data():
    """빠른 테스트용 샘플 데이터"""
    user_profile = UserProfile(
        age=35, monthly_income=500,
        investment_goal=InvestmentGoal.WEALTH,
        investment_period=5,
        risk_tolerance=RiskTolerance.NEUTRAL,
        name="테스트 투자자", email="test@example.com",
    )
    portfolio = Portfolio(
        total_asset=5000, monthly_saving=100,
        allocations=[
            Allocation(asset_name="S&P500 ETF",  asset_type=AssetType.FOREIGN_STOCK, weight=40, ticker="SPY"),
            Allocation(asset_name="국내 주식",    asset_type=AssetType.DOMESTIC_STOCK, weight=20),
            Allocation(asset_name="채권 ETF",     asset_type=AssetType.BOND,           weight=25, ticker="TLT"),
            Allocation(asset_name="금 ETF",       asset_type=AssetType.ALTERNATIVE,    weight=10),
            Allocation(asset_name="예금",         asset_type=AssetType.CASH,           weight=5),
        ],
    )
    return user_profile, portfolio


if __name__ == "__main__":
    main()
