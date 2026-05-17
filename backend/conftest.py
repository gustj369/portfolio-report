import sys
import os
from datetime import datetime, timezone

import pytest

# backend/ 디렉터리를 sys.path에 추가
# 프로젝트 루트에서 pytest를 실행해도 from models.xxx, from services.xxx 등 import가 동작한다
sys.path.insert(0, os.path.dirname(__file__))

from models.report import MarketSnapshot, ScenarioResult, SimulationResult
from services.market_data import MARKET_DEFAULTS
from test_pipeline import _sample_data


@pytest.fixture
def sample():
    """샘플 포트폴리오 + 기본값 MarketSnapshot 묶음 — 네트워크 없이 생성.
    test_market_data.py, test_pipeline.py 양쪽에서 공유 가능.
    """
    user_profile, portfolio = _sample_data()
    fields = dict(MARKET_DEFAULTS)
    fields["fetched_at"] = datetime.now(timezone.utc)
    market_snapshot = MarketSnapshot(**fields)
    return user_profile, portfolio, market_snapshot


# ──────────────────────────────────────────────────────────────
# 공용 헬퍼 함수 — 여러 test_*.py 에서 import 하여 재사용
# (pytest fixture 가 아닌 일반 함수 — 기존 테스트 호출 방식 유지)
# ──────────────────────────────────────────────────────────────

# MarketSnapshot 기본값 (MARKET_DEFAULTS 와 동일하되 fetched_at 고정)
_MARKET_SNAPSHOT_DEFAULTS: dict = {
    **{k: v for k, v in MARKET_DEFAULTS.items()},
    "fetched_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
}


def make_market(**overrides) -> MarketSnapshot:
    """MarketSnapshot 생성 — 기본값에 overrides 필드만 덮어씀.

    대체 대상:
      test_market_data._snap(**overrides)
      test_analyze_router._market()
      test_ai_engine._minimal_market_snapshot()
    """
    return MarketSnapshot(**{**_MARKET_SNAPSHOT_DEFAULTS, **overrides})


def make_scenario(
    name: str = "기본",
    final_value: float = 6000.0,
    cagr: float = 3.7,
) -> ScenarioResult:
    """ScenarioResult 생성 헬퍼 (test_analyze_router._scenario 대체)."""
    return ScenarioResult(
        name=name,
        monthly_values=[1000.0] * 60,
        final_value=final_value,
        total_return_pct=20.0,
        cagr=cagr,
        max_drawdown=10.0,
    )


def make_simulation(
    bear_final: float = 4000.0,
    base_final: float = 6000.0,
    bull_final: float = 8000.0,
    initial_value: float = 5000.0,
    monthly_contribution: float = 0.0,
) -> SimulationResult:
    """SimulationResult 생성 헬퍼 (test_analyze_router._simulation 대체).

    각 시나리오의 cagr 기본값: 비관 -2.0 / 기본 3.7 / 낙관 9.0
    """
    return SimulationResult(
        bear=make_scenario("비관", bear_final, -2.0),
        base=make_scenario("기본", base_final, 3.7),
        bull=make_scenario("낙관", bull_final, 9.0),
        initial_value=initial_value,
        monthly_contribution=monthly_contribution,
    )
