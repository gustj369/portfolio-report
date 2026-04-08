"""
Google Gemini API 연동 — 포트폴리오 분석 텍스트 생성
모델: gemini-1.5-flash (무료 티어: 1,500 req/day)
"""
import google.generativeai as genai
import json
import logging
import time
from models.portfolio import Portfolio, UserProfile
from models.report import AIContent, SimulationResult, MarketSnapshot

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 CFP(공인 재무설계사) 자격을 보유한 전문 투자 분석가입니다.
투자자의 포트폴리오를 분석하여 전문적이고 객관적인 의견을 제공합니다.

중요 원칙:
- 모든 응답은 한국어 리포트체로 작성 (구어체 금지)
- 수익률 보장 표현 절대 금지 — "예상", "시나리오", "가능성" 등 표현 사용
- 법적 리스크 방지를 위해 확정적 투자 권유 금지
- 간결하고 전문적인 문체 유지
- 반드시 지정된 JSON 형식으로만 응답"""

# 기본 모델 설정 — Flash는 무료, Pro는 품질 더 높음
DEFAULT_MODEL = "gemini-1.5-flash"  # 무료 티어 사용


def generate_full_analysis(
    user_profile: UserProfile,
    portfolio: Portfolio,
    simulation: SimulationResult,
    market_snapshot: MarketSnapshot,
    api_key: str,
) -> AIContent:
    """Gemini API를 호출하여 전체 분석 콘텐츠 생성"""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=DEFAULT_MODEL,
        system_instruction=SYSTEM_PROMPT,
    )

    portfolio_data = _build_portfolio_context(user_profile, portfolio, simulation, market_snapshot)

    # 1. 포트폴리오 종합 진단
    diagnosis_result = _call_gemini(model, _build_diagnosis_prompt(portfolio_data))

    # 2. 리밸런싱 추천
    rebalancing_result = _call_gemini(model, _build_rebalancing_prompt(portfolio_data, portfolio))

    # 3. 시장 코멘트 + 주의사항
    market_result = _call_gemini(model, _build_market_prompt(portfolio_data))

    return _parse_ai_results(diagnosis_result, rebalancing_result, market_result, simulation, portfolio)


def generate_preview_summary(
    user_profile: UserProfile,
    portfolio: Portfolio,
    market_snapshot: MarketSnapshot,
    api_key: str,
) -> tuple[str, int, str]:
    """
    미리보기용 간단 요약 생성 (결제 전)
    Returns: (summary_text, risk_score, risk_grade)
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=DEFAULT_MODEL,
        system_instruction=SYSTEM_PROMPT,
    )

    portfolio_data = _build_portfolio_context(user_profile, portfolio, None, market_snapshot)

    prompt = f"""다음 투자 포트폴리오를 분석하여 간결한 요약을 작성하세요.

{portfolio_data}

반드시 아래 JSON 형식으로만 응답하세요 (마크다운 코드블록 없이 순수 JSON):
{{
  "summary": "포트폴리오 전반적 평가 (150자 이내, 한국어)",
  "risk_score": 0에서 100 사이 정수,
  "risk_grade": "안정형" 또는 "중립형" 또는 "공격형"
}}"""

    result = _call_gemini(model, prompt)

    try:
        data = json.loads(_extract_json(result))
        return data["summary"], int(data["risk_score"]), data["risk_grade"]
    except Exception:
        return result[:150], 50, "중립형"


def _build_portfolio_context(
    user_profile: UserProfile,
    portfolio: Portfolio,
    simulation: SimulationResult | None,
    market_snapshot: MarketSnapshot,
) -> str:
    """프롬프트용 포트폴리오 컨텍스트 구성"""
    allocations_text = "\n".join([
        f"  - {a.asset_name} ({a.asset_type.value}): {a.weight:.1f}%"
        for a in portfolio.allocations
    ])

    sim_text = ""
    if simulation:
        sim_text = f"""
시뮬레이션 결과 (5년):
  - 비관 시나리오: {simulation.bear.final_value:,.0f}만원 (CAGR {simulation.bear.cagr:.1f}%)
  - 기본 시나리오: {simulation.base.final_value:,.0f}만원 (CAGR {simulation.base.cagr:.1f}%)
  - 낙관 시나리오: {simulation.bull.final_value:,.0f}만원 (CAGR {simulation.bull.cagr:.1f}%)"""

    return f"""투자자 정보:
  - 나이: {user_profile.age}세
  - 투자 목표: {user_profile.investment_goal.value}
  - 리스크 성향: {user_profile.risk_tolerance.value}
  - 투자 기간: {user_profile.investment_period}년

현재 포트폴리오:
  - 총 자산: {portfolio.total_asset:,}만원
  - 월 적립액: {portfolio.monthly_saving:,}만원
  - 자산 배분:
{allocations_text}
{sim_text}

현재 시장 상황:
  - S&P500: {market_snapshot.sp500:,.0f}
  - 코스피: {market_snapshot.kospi:,.0f}
  - 미국 10년 국채 금리: {market_snapshot.us_10y_yield:.2f}%
  - 한국 기준금리: {market_snapshot.kr_base_rate:.2f}%
  - 달러/원: {market_snapshot.usd_krw:,.0f}원
  - 금: ${market_snapshot.gold_price:,.0f}
  - 미국 CPI: {market_snapshot.cpi_us:.1f}%"""


def _build_diagnosis_prompt(portfolio_data: str) -> str:
    return f"""다음 투자 포트폴리오를 분석하세요.

{portfolio_data}

마크다운 코드블록 없이 순수 JSON으로만 응답하세요:
{{
  "diagnosis": "포트폴리오 종합 진단 (200자 이내)",
  "strengths": ["강점1 (50자 이내)", "강점2 (50자 이내)", "강점3 (50자 이내)"],
  "weaknesses": ["약점1 (50자 이내)", "약점2 (50자 이내)", "약점3 (50자 이내)"],
  "risk_score": 0에서 100 사이 정수,
  "risk_grade": "안정형" 또는 "중립형" 또는 "공격형",
  "bear_commentary": "비관 시나리오 발생 조건과 의미 (100자 이내)",
  "base_commentary": "기본 시나리오 발생 조건과 의미 (100자 이내)",
  "bull_commentary": "낙관 시나리오 발생 조건과 의미 (100자 이내)"
}}"""


def _build_rebalancing_prompt(portfolio_data: str, portfolio: Portfolio) -> str:
    asset_list = ", ".join([f'"{a.asset_name}"' for a in portfolio.allocations])
    return f"""다음 투자 포트폴리오의 리밸런싱 방안을 제시하세요.

{portfolio_data}

리밸런싱 원칙:
- 나이 기반 주식 비중 권장: 100 - 나이 = 주식 비중
- 고금리 국면: 채권/현금 비중 상향
- 단일 자산 60% 초과 시 분산 권고

반드시 아래 JSON 형식으로만 응답하세요 (마크다운 코드블록 없이 순수 JSON):
{{
  "recommendations": [
    {{
      "asset_name": "자산명 (반드시 다음 중 하나: {asset_list})",
      "current_weight": 현재 비중 숫자,
      "recommended_weight": 추천 비중 숫자,
      "direction": "증가" 또는 "감소" 또는 "유지",
      "reason": "조정 이유 (60자 이내)"
    }}
  ]
}}

위 자산 목록의 모든 자산에 대해 반드시 추천을 제공하세요."""


def _build_market_prompt(portfolio_data: str) -> str:
    return f"""다음 투자 포트폴리오에 대한 시장 환경 분석과 주의사항을 작성하세요.

{portfolio_data}

마크다운 코드블록 없이 순수 JSON으로만 응답하세요:
{{
  "market_commentary": "현재 시장이 이 포트폴리오에 미치는 영향 (200자 이내)",
  "cautions": [
    "주의사항1 (70자 이내)",
    "주의사항2 (70자 이내)",
    "주의사항3 (70자 이내)"
  ]
}}"""


def _call_gemini(model: genai.GenerativeModel, prompt: str) -> str:
    """Gemini API 호출 (최대 3회 재시도)"""
    config = genai.types.GenerationConfig(
        temperature=0.4,
        max_output_tokens=1500,
    )

    for attempt in range(3):
        try:
            response = model.generate_content(prompt, generation_config=config)
            return response.text
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "quota" in error_msg.lower():
                # Rate limit — 지수 백오프
                wait = 2 ** attempt * 5
                logger.warning(f"Gemini rate limit, {wait}초 대기 (시도 {attempt + 1})")
                time.sleep(wait)
            elif attempt < 2:
                logger.warning(f"Gemini API 오류 (시도 {attempt + 1}): {e}")
                time.sleep(1)
            else:
                logger.error(f"Gemini API 최종 실패: {e}")
                raise

    return ""


def _parse_ai_results(
    diagnosis_raw: str,
    rebalancing_raw: str,
    market_raw: str,
    simulation: SimulationResult,
    portfolio: Portfolio,
) -> AIContent:
    """Gemini 응답 파싱 → AIContent 객체 생성"""

    diagnosis = {}
    rebalancing = {"recommendations": []}
    market = {}

    try:
        diagnosis = json.loads(_extract_json(diagnosis_raw))
    except Exception as e:
        logger.warning(f"진단 파싱 실패: {e}\n원본: {diagnosis_raw[:200]}")

    try:
        rebalancing = json.loads(_extract_json(rebalancing_raw))
    except Exception as e:
        logger.warning(f"리밸런싱 파싱 실패: {e}\n원본: {rebalancing_raw[:200]}")

    try:
        market = json.loads(_extract_json(market_raw))
    except Exception as e:
        logger.warning(f"시장 파싱 실패: {e}\n원본: {market_raw[:200]}")

    if not rebalancing.get("recommendations"):
        rebalancing["recommendations"] = [
            {
                "asset_name": a.asset_name,
                "current_weight": a.weight,
                "recommended_weight": a.weight,
                "direction": "유지",
                "reason": "현재 비중 유지 권장",
            }
            for a in portfolio.allocations
        ]

    return AIContent(
        portfolio_diagnosis=diagnosis.get("diagnosis", "포트폴리오 분석을 완료하였습니다."),
        strengths=diagnosis.get("strengths", ["다양한 자산 보유", "꾸준한 적립 계획", "장기 투자 관점"]),
        weaknesses=diagnosis.get("weaknesses", ["집중도 점검 필요", "리밸런싱 주기 설정 권장", "인플레이션 대응 자산 검토"]),
        risk_score=int(diagnosis.get("risk_score", 50)),
        risk_grade=diagnosis.get("risk_grade", "중립형"),
        scenario_commentary={
            "bear": diagnosis.get("bear_commentary", "글로벌 경기 침체 또는 금리 급등 시 발생 가능한 시나리오입니다."),
            "base": diagnosis.get("base_commentary", "현재 시장 상황이 지속될 경우의 예상 결과입니다."),
            "bull": diagnosis.get("bull_commentary", "경기 회복 및 금리 인하 시 발생 가능한 긍정적 시나리오입니다."),
        },
        rebalancing_recommendations=rebalancing.get("recommendations", []),
        market_commentary=market.get("market_commentary", "현재 시장은 고금리 환경이 지속되고 있어 채권 및 현금성 자산의 매력도가 높아진 상황입니다."),
        cautions=market.get("cautions", [
            "투자는 원금 손실 가능성이 있습니다.",
            "과거 수익률이 미래를 보장하지 않습니다.",
            "정기적인 포트폴리오 점검을 권장합니다.",
        ]),
    )


def _extract_json(text: str) -> str:
    """텍스트에서 JSON 블록 추출"""
    # ```json ... ``` 블록 처리
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        return text[start:end].strip()
    if "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        return text[start:end].strip()
    # { ... } 직접 추출
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        return text[start:end]
    return text
