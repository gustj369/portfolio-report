"""
스토리지 추상화 레이어
- REDIS_URL 설정 시: Redis (Upstash 등) 사용
- 미설정 시: 인메모리 dict fallback (개발 환경)

사용법:
    from services.storage import storage_set, storage_get, storage_delete
    storage_set("key", {"foo": "bar"}, ttl=3600)
    data = storage_get("key")   # dict 또는 None
    storage_delete("key")
"""
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 인메모리 fallback (Redis 없을 때)
_local: dict[str, str] = {}


def _get_redis():
    """Redis 클라이언트 반환. 설정 없거나 연결 실패 시 None."""
    try:
        from config import get_settings
        settings = get_settings()
        if not settings.redis_url:
            return None
        import redis as redis_lib
        client = redis_lib.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        client.ping()  # 연결 확인
        return client
    except ImportError:
        logger.warning("redis 패키지 미설치 — 인메모리 fallback 사용")
        return None
    except Exception as e:
        logger.warning(f"Redis 연결 실패 — 인메모리 fallback 사용: {e}")
        return None


def storage_set(key: str, value: Any, ttl: int = 86400 * 7) -> None:
    """
    키-값 저장.
    ttl: 만료 시간(초), 기본 7일
    value: JSON-직렬화 가능한 dict/list/str/int
    """
    serialized = json.dumps(value, ensure_ascii=False, default=str)
    r = _get_redis()
    if r:
        r.set(key, serialized, ex=ttl)
    else:
        _local[key] = serialized


def storage_get(key: str) -> Optional[Any]:
    """키로 값 조회. 없으면 None."""
    r = _get_redis()
    raw = r.get(key) if r else _local.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def storage_delete(key: str) -> None:
    """키 삭제."""
    r = _get_redis()
    if r:
        r.delete(key)
    else:
        _local.pop(key, None)


def storage_exists(key: str) -> bool:
    """키 존재 여부 확인."""
    r = _get_redis()
    if r:
        return bool(r.exists(key))
    return key in _local
