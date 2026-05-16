"""
routers/analyze.py 단위 테스트
네트워크·외부 서비스 없이 FastAPI TestClient + unittest.mock 으로 핵심 경로 검증

커버 범위:
  POST /analyze — Gemini 키 미설정(fallback 경로) / Gemini 키 설정(AI 호출 경로) /
                  AI 호출 실패 → fallback 전환 / ValueError → 422 / 서버 오류 → 500
"""
import os
import sys
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(__file__))

from config import Settings, get_settings
from main import app
from models.report import MarketSnapshot, ScenarioResult, SimulationResult
from conftest import make_market, make_scenario, make_simulation

ANALYZE_URL = "/analyze"

# 최소 유효 AnalyzeRequest JSON
_REQ = {
    "user_profile": {
        "age": 35,
        "monthly_income": 500,
        "investment_goal": "자산증식",
        "investment_period": 5,
        "risk_tolerance": "중립형",
        "name": "테스터",
        "email": "",
    },
    "portfolio": {
        "total_asset": 5000,
        "monthly_saving": 0,
        "allocations": [
            {"asset_name": "S&P500", "asset_type": "해외주식", "weight": 100.0},
        ],
    },
}


# ──────────────────────────────────────────────────────────────
# 공통 mock 반환값 헬퍼 — conftest 공용 함수로 위임
# ──────────────────────────────────────────────────────────────

def _market() -> MarketSnapshot:
    return make_market()


def _simulation() -> SimulationResult:
    return make_simulation()  # bear=4000 / base=6000(cagr 3.7) / bull=8000


# ──────────────────────────────────────────────────────────────
# 테스트 실행 헬퍼 — ExitStack 으로 다중 패치 적용
# ──────────────────────────────────────────────────────────────

def _post(extra_patches: dict, settings: Settings | None = None) -> object:
    """
    extra_patches: {patch_target: mock_object} 딕셔너리
    settings: 주입할 Settings 인스턴스 (None 이면 기본값 사용)
    """
    # 외부 I/O 기본 격리 패치 (모든 테스트 공통)
    base = {
        "routers.analyze.fetch_market_snapshot": MagicMock(return_value=_market()),
        "routers.analyze.run_simulation": MagicMock(return_value=_simulation()),
        "routers.analyze.calculate_risk_score": MagicMock(return_value=(50, "중립형")),
        "services.fallback_analyzer.generate_personalized_preview_summary": MagicMock(
            return_value="fallback 요약 텍스트"
        ),
    }
    base.update(extra_patches)  # 테스트별 오버라이드 적용

    if settings:
        app.dependency_overrides[get_settings] = lambda: settings
    try:
        with ExitStack() as stack:
            for target, mock in base.items():
                stack.enter_context(patch(target, mock))
            with TestClient(app) as c:
                return c.post(ANALYZE_URL, json=_REQ)
    finally:
        app.dependency_overrides.pop(get_settings, None)


# ──────────────────────────────────────────────────────────────
# POST /analyze — Gemini 키 미설정 (fallback 경로)
# ──────────────────────────────────────────────────────────────

def test_analyze_no_gemini_key_uses_fallback():
    """gemini_api_key 미설정 → fallback 요약 사용, 200 반환"""
    resp = _post({}, settings=Settings(gemini_api_key=""))

    assert resp.status_code == 200
    body = resp.json()
    assert "fallback" in body["portfolio_summary"]


def test_analyze_no_gemini_key_returns_simulation_fields():
    """gemini_api_key 미설정 → 시뮬레이션 수치가 응답에 포함"""
    resp = _post({}, settings=Settings(gemini_api_key=""))

    body = resp.json()
    assert body["base_scenario_final"] == 6000.0
    assert abs(body["base_scenario_cagr"] - 3.7) < 1e-6
    assert body["risk_score"] == 50
    assert body["risk_grade"] == "중립형"


# ──────────────────────────────────────────────────────────────
# POST /analyze — Gemini 키 설정 (AI 호출 경로)
# ──────────────────────────────────────────────────────────────

def test_analyze_with_gemini_key_uses_ai_result():
    """gemini_api_key 설정 → AI 요약·점수·등급이 응답에 반영"""
    ai_mock = MagicMock(return_value=("AI 요약 텍스트", 72, "공격형"))
    resp = _post(
        {"routers.analyze.generate_preview_summary": ai_mock},
        settings=Settings(gemini_api_key="sk_test"),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert "AI 요약" in body["portfolio_summary"]
    assert body["risk_score"] == 72
    assert body["risk_grade"] == "공격형"


def test_analyze_summary_truncated_at_200_chars():
    """AI 요약이 200자 초과면 말줄임표(...) 처리"""
    long_summary = "A" * 300
    ai_mock = MagicMock(return_value=(long_summary, 50, "중립형"))
    resp = _post(
        {"routers.analyze.generate_preview_summary": ai_mock},
        settings=Settings(gemini_api_key="sk_test"),
    )

    body = resp.json()
    assert body["portfolio_summary"].endswith("...")
    # 200자 본문 + "..." = 203자
    assert len(body["portfolio_summary"]) == 203


def test_analyze_summary_not_truncated_when_short():
    """AI 요약이 200자 이하면 말줄임표 없음"""
    short_summary = "짧은 요약"
    ai_mock = MagicMock(return_value=(short_summary, 50, "중립형"))
    resp = _post(
        {"routers.analyze.generate_preview_summary": ai_mock},
        settings=Settings(gemini_api_key="sk_test"),
    )

    body = resp.json()
    assert body["portfolio_summary"] == short_summary
    assert not body["portfolio_summary"].endswith("...")


# ──────────────────────────────────────────────────────────────
# POST /analyze — AI 호출 실패 → fallback 전환
# ──────────────────────────────────────────────────────────────

def test_analyze_ai_failure_falls_back_to_rule_based():
    """AI 호출 중 예외 발생 → fallback 요약·점수·등급으로 200 반환 (503 아님)"""
    ai_mock = MagicMock(side_effect=Exception("Gemini quota exceeded"))
    resp = _post(
        {"routers.analyze.generate_preview_summary": ai_mock},
        settings=Settings(gemini_api_key="sk_test"),
    )

    assert resp.status_code == 200
    body = resp.json()
    # fallback 요약이 사용되어야 함
    assert "fallback" in body["portfolio_summary"]
    # calculate_risk_score 값(50, 중립형)이 유지되어야 함
    assert body["risk_score"] == 50
    assert body["risk_grade"] == "중립형"


# ──────────────────────────────────────────────────────────────
# POST /analyze — 오류 경로
# ──────────────────────────────────────────────────────────────

def test_analyze_simulation_value_error_returns_422():
    """run_simulation이 ValueError 발생 → 422 반환"""
    resp = _post(
        {"routers.analyze.run_simulation": MagicMock(side_effect=ValueError("비중 합계 오류"))},
        settings=Settings(gemini_api_key=""),
    )
    assert resp.status_code == 422
    assert "비중 합계 오류" in resp.json()["detail"]


def test_analyze_market_fetch_error_returns_500():
    """fetch_market_snapshot 에서 예기치 않은 예외 → 500 반환"""
    resp = _post(
        {"routers.analyze.fetch_market_snapshot": MagicMock(side_effect=RuntimeError("네트워크 오류"))},
        settings=Settings(gemini_api_key=""),
    )
    assert resp.status_code == 500
    assert "오류" in resp.json()["detail"]


def test_analyze_invalid_request_body_returns_422():
    """필수 필드 누락 요청 → Pydantic 검증 실패로 422 반환"""
    with TestClient(app) as c:
        resp = c.post(ANALYZE_URL, json={"user_profile": {}, "portfolio": {}})
    assert resp.status_code == 422
