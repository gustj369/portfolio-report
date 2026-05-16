"""ai_engine.py 단위 테스트

네트워크 호출(Gemini API) 없이 핵심 분기를 검증한다.
외부 의존(_call_gemini)은 unittest.mock으로 격리한다.
"""
import logging
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import httpx
from google.genai.errors import ClientError, APIError

from models.portfolio import (
    Portfolio, Allocation, AssetType,
    UserProfile, RiskTolerance, InvestmentGoal,
)
from models.report import SimulationResult, ScenarioResult, MarketSnapshot
from services.market_data import MARKET_DEFAULTS
from services.ai_engine import (
    _extract_json, _parse_ai_results,
    generate_preview_summary, generate_full_analysis,
    _call_gemini,
)


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _minimal_portfolio() -> Portfolio:
    return Portfolio(
        total_asset=1000,
        monthly_saving=50,
        allocations=[Allocation(asset_name="주식", asset_type=AssetType.DOMESTIC_STOCK, weight=100.0)],
    )


def _minimal_user_profile() -> UserProfile:
    return UserProfile(
        age=40,
        monthly_income=500,
        investment_goal=InvestmentGoal.WEALTH,
        investment_period=5,
        risk_tolerance=RiskTolerance.NEUTRAL,
    )


def _minimal_market_snapshot() -> MarketSnapshot:
    fields = dict(MARKET_DEFAULTS)
    fields["fetched_at"] = datetime.now(timezone.utc)
    return MarketSnapshot(**fields)


def _minimal_simulation() -> SimulationResult:
    scenario = ScenarioResult(
        name="기본",
        monthly_values=[1000.0] * 60,
        final_value=1000,
        total_return_pct=0.0,
        cagr=0.0,
        max_drawdown=0.0,
    )
    return SimulationResult(
        bear=scenario, base=scenario, bull=scenario,
        initial_value=1000, monthly_contribution=50,
    )


# ── _extract_json ─────────────────────────────────────────────────────────────

class TestExtractJson:
    def test_backtick_json_block(self):
        """```json ... ``` 블록에서 JSON 추출"""
        text = '```json\n{"key": "val"}\n```'
        assert _extract_json(text) == '{"key": "val"}'

    def test_plain_backtick_block(self):
        """``` ... ``` 블록(json 태그 없음)에서 JSON 추출"""
        text = '```\n{"key": "val"}\n```'
        assert _extract_json(text) == '{"key": "val"}'

    def test_raw_json_braces(self):
        """{ ... } 직접 포함된 경우 중괄호 범위로 추출"""
        text = '여기에 {"key": "val"} 있음'
        assert _extract_json(text) == '{"key": "val"}'

    def test_plain_text_returned_as_is(self):
        """JSON 패턴이 없으면 원문 그대로 반환"""
        text = "plain text without braces"
        assert _extract_json(text) == text


# ── _parse_ai_results fallback ────────────────────────────────────────────────

class TestParseAiResultsFallback:
    def test_broken_json_returns_default_content(self):
        """세 응답 모두 깨진 JSON이면 기본 fallback 값을 반환해야 한다"""
        portfolio = _minimal_portfolio()
        simulation = _minimal_simulation()

        result = _parse_ai_results("NOT JSON", "ALSO BROKEN", "BROKEN TOO", simulation, portfolio)

        assert isinstance(result.portfolio_diagnosis, str)
        assert len(result.portfolio_diagnosis) > 0
        assert result.risk_score == 50
        assert result.risk_grade == "중립형"
        assert len(result.cautions) > 0
        # 리밸런싱 추천이 없으면 현재 자산으로 채워야 한다
        assert len(result.rebalancing_recommendations) == len(portfolio.allocations)


# ── generate_preview_summary fallback ────────────────────────────────────────

class TestGeneratePreviewSummaryFallback:
    def test_malformed_api_response_falls_back_to_defaults(self):
        """Gemini가 JSON이 아닌 텍스트를 반환하면 fallback 기본값을 반환해야 한다"""
        raw_response = "이것은 JSON이 아닙니다"

        with patch("services.ai_engine._call_gemini", return_value=raw_response), \
             patch("services.ai_engine.genai.Client"):
            summary, risk_score, risk_grade = generate_preview_summary(
                user_profile=_minimal_user_profile(),
                portfolio=_minimal_portfolio(),
                market_snapshot=_minimal_market_snapshot(),
                api_key="dummy-key",
            )

        assert summary == raw_response[:150]
        assert risk_score == 50
        assert risk_grade == "중립형"

    def test_valid_api_response_parsed_correctly(self):
        """Gemini가 올바른 JSON을 반환하면 파싱된 값을 반환해야 한다"""
        raw_response = '{"summary": "양호한 포트폴리오", "risk_score": 42, "risk_grade": "중립형"}'

        with patch("services.ai_engine._call_gemini", return_value=raw_response), \
             patch("services.ai_engine.genai.Client"):
            summary, risk_score, risk_grade = generate_preview_summary(
                user_profile=_minimal_user_profile(),
                portfolio=_minimal_portfolio(),
                market_snapshot=_minimal_market_snapshot(),
                api_key="dummy-key",
            )

        assert summary == "양호한 포트폴리오"
        assert risk_score == 42
        assert risk_grade == "중립형"


# ── generate_full_analysis 통합 경로 ─────────────────────────────────────────

class TestGenerateFullAnalysis:
    def test_happy_path_returns_parsed_ai_content(self):
        """_call_gemini 3-call 시퀀스가 올바른 JSON을 반환하면 AIContent가 정상 파싱되어야 한다"""
        diagnosis_json = (
            '{"diagnosis": "분산이 잘 된 포트폴리오", '
            '"strengths": ["분산투자"], "weaknesses": ["암호화폐 과다"], '
            '"risk_score": 45, "risk_grade": "중립형", '
            '"bear_commentary": "경기침체", "base_commentary": "현상유지", "bull_commentary": "강세장"}'
        )
        rebalancing_json = (
            '{"recommendations": [{"asset_name": "주식", "current_weight": 100.0, '
            '"recommended_weight": 80.0, "direction": "감소", "reason": "분산 필요"}]}'
        )
        market_json = (
            '{"market_commentary": "고금리 지속", "cautions": ["원금 손실 가능", "정기 점검 권장"]}'
        )

        responses = iter([diagnosis_json, rebalancing_json, market_json])

        with patch("services.ai_engine._call_gemini", side_effect=lambda *a, **kw: next(responses)), \
             patch("services.ai_engine.genai.Client"):
            result = generate_full_analysis(
                user_profile=_minimal_user_profile(),
                portfolio=_minimal_portfolio(),
                simulation=_minimal_simulation(),
                market_snapshot=_minimal_market_snapshot(),
                api_key="dummy-key",
            )

        assert result.portfolio_diagnosis == "분산이 잘 된 포트폴리오"
        assert result.risk_score == 45
        assert result.risk_grade == "중립형"
        assert len(result.rebalancing_recommendations) == 1
        assert result.rebalancing_recommendations[0].asset_name == "주식"
        assert result.market_commentary == "고금리 지속"
        assert len(result.cautions) == 2


# ── _call_gemini 재시도 분기 ──────────────────────────────────────────────────

_RATE_LIMIT_EXC = ClientError(
    429,
    {"error": {"code": 429, "message": "quota exceeded", "status": "RESOURCE_EXHAUSTED"}},
)
_TIMEOUT_EXC = httpx.TimeoutException("read timed out")
_API_ERR_EXC = APIError(
    500,
    {"error": {"code": 500, "message": "internal error", "status": "INTERNAL"}},
)


class TestCallGemini:
    """_call_gemini의 재시도·예외 분기를 time.sleep mock으로 순간 실행"""

    def _make_client(self, side_effects: list):
        """generate_content가 순서대로 side_effect를 반환하는 mock client"""
        client = MagicMock()
        client.models.generate_content.side_effect = side_effects
        return client

    def test_rate_limit_exhausted_raises(self):
        """429 rate limit이 3회 연속으로 발생하면 예외를 전파해야 한다"""
        client = self._make_client([_RATE_LIMIT_EXC, _RATE_LIMIT_EXC, _RATE_LIMIT_EXC])

        with patch("services.ai_engine.time.sleep"), \
             pytest.raises(ClientError) as exc_info:
            _call_gemini(client, "test prompt")

        assert exc_info.value.code == 429

    def test_timeout_exhausted_raises(self):
        """timeout이 3회 연속으로 발생하면 예외를 전파해야 한다"""
        client = self._make_client([_TIMEOUT_EXC, _TIMEOUT_EXC, _TIMEOUT_EXC])

        with patch("services.ai_engine.time.sleep"), \
             pytest.raises(httpx.TimeoutException):
            _call_gemini(client, "test prompt")

    def test_api_error_then_success_returns_text(self):
        """일반 API 오류 1회 후 성공하면 응답 텍스트를 반환해야 한다"""
        ok_response = MagicMock()
        ok_response.text = "정상 응답"
        client = self._make_client([_API_ERR_EXC, ok_response])

        with patch("services.ai_engine.time.sleep"):
            result = _call_gemini(client, "test prompt")

        assert result == "정상 응답"

    def test_rate_limit_exhausted_logs_error_message(self, caplog):
        """rate limit 3회 소진 시 ERROR 레벨로 '3회 소진' 메시지가 기록되어야 한다"""
        client = self._make_client([_RATE_LIMIT_EXC, _RATE_LIMIT_EXC, _RATE_LIMIT_EXC])

        with patch("services.ai_engine.time.sleep"), \
             caplog.at_level(logging.ERROR, logger="services.ai_engine"), \
             pytest.raises(ClientError):
            _call_gemini(client, "test prompt", label="테스트")

        assert any("rate limit 3회 소진" in msg for msg in caplog.messages)

    def test_timeout_exhausted_logs_error_message(self, caplog):
        """timeout 3회 소진 시 ERROR 레벨로 'timeout 최종 실패' 메시지가 기록되어야 한다"""
        client = self._make_client([_TIMEOUT_EXC, _TIMEOUT_EXC, _TIMEOUT_EXC])

        with patch("services.ai_engine.time.sleep"), \
             caplog.at_level(logging.ERROR, logger="services.ai_engine"), \
             pytest.raises(httpx.TimeoutException):
            _call_gemini(client, "test prompt", label="테스트")

        assert any("timeout 최종 실패" in msg for msg in caplog.messages)
