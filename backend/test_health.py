"""/health 엔드포인트 — Redis 상태 표시 검증"""
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


def _redis_status(redis_url: str, client) -> str:
    with patch.object(main.settings, "redis_url", redis_url), \
         patch("services.storage._get_redis", return_value=client):
        return TestClient(main.app).get("/health").json()["redis"]


def test_redis_not_configured():
    assert _redis_status("", None) == "not_configured"


def test_redis_configured_but_unreachable():
    """REDIS_URL이 있는데 연결 실패 시 not_configured로 오인되지 않아야 한다"""
    assert _redis_status("rediss://default:x@deleted.upstash.io:6379", None) == "unreachable"


def test_redis_connected():
    assert _redis_status("rediss://default:x@ok.upstash.io:6379", object()) == "connected"
