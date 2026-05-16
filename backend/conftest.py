import sys
import os
from datetime import datetime, timezone

import pytest

# backend/ 디렉터리를 sys.path에 추가
# 프로젝트 루트에서 pytest를 실행해도 from models.xxx, from services.xxx 등 import가 동작한다
sys.path.insert(0, os.path.dirname(__file__))

from models.report import MarketSnapshot
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
