"""
분석 API 라우터 — 미리보기용 분석 (결제 전)
"""
from fastapi import APIRouter, HTTPException, Depends
import logging
import time

from config import get_settings, Settings
from models.portfolio import AnalyzeRequest
from models.report import PreviewResponse
from services.market_data import fetch_market_snapshot
from services.simulator import run_simulation, calculate_risk_score
from services.ai_engine import generate_preview_summary

router = APIRouter(prefix="/analyze", tags=["analyze"])
logger = logging.getLogger(__name__)


@router.post("", response_model=PreviewResponse)
async def analyze_portfolio(
    request: AnalyzeRequest,
    settings: Settings = Depends(get_settings),
) -> PreviewResponse:
    """
    포트폴리오 분석 엔드포인트 (미리보기)
    - 시장 데이터 수집
    - 5년 시뮬레이션 실행
    - AI 요약 생성 (간략 버전)
    """
    try:
        t0 = time.perf_counter()

        # 1. 시장 데이터 수집
        logger.info("시장 데이터 수집 시작")
        market_snapshot = fetch_market_snapshot(settings.fred_api_key)
        t1 = time.perf_counter()
        logger.info(f"시장 데이터 수집 완료 ({t1 - t0:.2f}s 누적)")

        # 2. 5년 시뮬레이션
        simulation = run_simulation(request.portfolio, market_snapshot)
        t2 = time.perf_counter()
        logger.info(f"시뮬레이션 완료 ({t2 - t1:.2f}s 스테이지, {t2 - t0:.2f}s 누적)")

        # 3. 리스크 점수 계산
        risk_score, risk_grade = calculate_risk_score(request.portfolio, market_snapshot)
        logger.info(f"리스크 점수: {risk_score} ({risk_grade})")

        # 4. AI 간략 요약 생성
        from services.fallback_analyzer import generate_personalized_preview_summary
        summary = generate_personalized_preview_summary(
            request.user_profile, request.portfolio, market_snapshot, risk_score, risk_grade, simulation
        )
        ai_risk_score = risk_score
        ai_risk_grade = risk_grade

        if settings.gemini_api_key:
            try:
                logger.info("AI 분석 시작 (미리보기)")
                summary, ai_risk_score, ai_risk_grade = generate_preview_summary(
                    request.user_profile,
                    request.portfolio,
                    market_snapshot,
                    settings.gemini_api_key,
                )
                elapsed = time.perf_counter()
                logger.info(f"AI 분석 완료 ({elapsed - t2:.2f}s 스테이지, {elapsed - t0:.2f}s 누적)")
            except Exception as e:
                elapsed = time.perf_counter()
                logger.warning(f"AI 분석 실패 — fallback 사용 ({elapsed - t2:.2f}s 스테이지, {elapsed - t0:.2f}s 누적): {e}")
        else:
            elapsed = time.perf_counter()
            logger.info(f"Gemini 미설정 — fallback 분석 사용 ({elapsed - t2:.2f}s 스테이지, {elapsed - t0:.2f}s 누적)")

        logger.info(f"미리보기 분석 완료 (총 {time.perf_counter() - t0:.2f}s)")
        return PreviewResponse(
            risk_score=ai_risk_score,
            risk_grade=ai_risk_grade,
            base_scenario_final=simulation.base.final_value,
            base_scenario_cagr=simulation.base.cagr,
            portfolio_summary=summary[:200] + ("..." if len(summary) > 200 else ""),
            simulation=simulation,
            market_data=market_snapshot,
        )

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"분석 처리 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="분석 처리 중 오류가 발생했습니다.")
