"""
스토리지 추상화 레이어
- REDIS_URL 설정 시: Redis (Upstash 등) 사용
- 미설정 시: 인메모리 dict fallback (개발 환경)

인메모리 fallback(_local) TTL 지원:
  (value, expire_ts) 튜플로 저장하며, get/exists 시 만료 여부를 지연 확인합니다.
  서버 재시작 시 초기화되므로 프로덕션에서는 반드시 REDIS_URL을 설정하세요.

사용법:
    from services.storage import storage_set, storage_get, storage_delete, storage_exists
    storage_set("key", {"foo": "bar"}, ttl=3600)
    data = storage_get("key")      # dict 또는 None
    storage_delete("key")
    exists = storage_exists("key") # bool
"""
import json
import time
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 인메모리 fallback (Redis 없을 때)
# 구조: {key: (serialized_json, expire_timestamp_or_None)}
# expire_timestamp가 None이면 만료 없음, float이면 time.time() 기준 만료 시각
_local: dict[str, tuple[str, float | None]] = {}

# Redis 클라이언트 캐시 — 최초 ping 성공 후 재사용 (매 호출 신규 연결·ping 방지)
# ping 실패 시 None 유지 → 다음 호출에서 재시도 / 각 operation의 try-except가 장애 처리
_redis_client_cache: Any = None

# 인메모리 GC 카운터 — storage_set N회마다 만료 키 일괄 삭제
_gc_counter: int = 0
_GC_INTERVAL: int = 100


def _gc_local() -> None:
    """인메모리 스토리지의 만료 키 주기적 일괄 삭제.

    lazy expiry(_local_get_raw)만으로는 접근이 없는 키가 메모리에 남을 수 있으므로,
    storage_set 호출 _GC_INTERVAL회마다 전체 스캔하여 만료 키를 정리한다.
    Redis 사용 환경에서는 _local이 비어 있어 사실상 no-op.
    """
    global _gc_counter
    _gc_counter += 1
    if _gc_counter < _GC_INTERVAL:
        return
    _gc_counter = 0
    now = time.time()
    expired = [k for k, (_, exp) in list(_local.items()) if exp is not None and now > exp]
    for k in expired:
        _local.pop(k, None)
    if expired:
        logger.debug(f"인메모리 GC: 만료 키 {len(expired)}개 삭제 (잔여 {len(_local)}개)")


def _reset_redis_cache() -> None:
    """Redis operation 실패 시 캐시 무효화 — 다음 호출에서 재연결 시도 (장기 장애 복구 지원)"""
    global _redis_client_cache
    _redis_client_cache = None


def _local_get_raw(key: str) -> Optional[str]:
    """인메모리 fallback에서 key의 값을 반환. 만료된 키는 삭제 후 None 반환 (lazy expiry)."""
    entry = _local.get(key)
    if entry is None:
        return None
    value, exp = entry
    if exp is not None and time.time() > exp:
        # 만료된 키 지연 삭제
        _local.pop(key, None)
        return None
    return value


def _get_redis():
    """Redis 클라이언트 반환. 캐시된 클라이언트 재사용. 설정 없거나 연결 실패 시 None.

    연결 성공 시 _redis_client_cache 에 저장 → 이후 호출은 ping 없이 재사용.
    연결 실패 시 _redis_client_cache 를 명시적으로 None 유지 → 다음 호출에서 재시도.
    (operation 실패 시에는 _reset_redis_cache() 가 None 으로 초기화하여 재연결 경로 열어둠)
    """
    global _redis_client_cache
    if _redis_client_cache is not None:
        return _redis_client_cache
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
        client.ping()  # 최초 연결 확인 — 성공해야 캐시에 저장
        _redis_client_cache = client
        return _redis_client_cache
    except ImportError:
        logger.warning("redis 패키지 미설치 — 인메모리 fallback 사용 (설치: pip install redis)")
        _redis_client_cache = None  # 명시적 미캐시: 다음 호출에서 재시도 가능
        return None
    except Exception as e:
        logger.warning(f"Redis 연결 실패 — 인메모리 fallback 사용: {e}")
        _redis_client_cache = None  # 명시적 미캐시: 다음 호출에서 재시도 가능
        return None


def storage_set(key: str, value: Any, ttl: int = 86400 * 7) -> None:
    """
    키-값 저장.
    ttl: 만료 시간(초), 기본 7일
    value: JSON-직렬화 가능한 dict/list/str/int
    """
    serialized = json.dumps(value, ensure_ascii=False, default=str)
    expire_ts = time.time() + ttl  # 인메모리 fallback용 만료 시각
    r = _get_redis()
    if r:
        try:
            r.set(key, serialized, ex=ttl)
        except Exception as e:
            logger.warning(f"Redis set 실패 — 캐시 무효화 후 인메모리 fallback 사용: {e}")
            _reset_redis_cache()
            _gc_local()  # Redis 장애 후 인메모리 사용 시에도 GC 실행
            _local[key] = (serialized, expire_ts)
            logger.debug(f"인메모리 fallback 저장 완료 (Redis 장애 후): key={key!r}")
    else:
        _gc_local()  # 인메모리 저장 시 주기적 GC 실행
        _local[key] = (serialized, expire_ts)
        logger.debug(f"인메모리 저장 완료 (Redis 미설정): key={key!r}")


def storage_get(key: str) -> Optional[Any]:
    """키로 값 조회. 없거나 만료된 경우 None."""
    r = _get_redis()
    try:
        if r:
            raw = r.get(key)
        else:
            raw = _local_get_raw(key)
            logger.debug(f"인메모리 get 완료 (Redis 미설정): key={key!r}")
    except Exception as e:
        logger.warning(f"Redis get 실패 — 캐시 무효화 후 인메모리 fallback 사용: {e}")
        _reset_redis_cache()
        raw = _local_get_raw(key)
        logger.debug(f"인메모리 fallback get 완료 (Redis 장애 후): key={key!r}")
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        # 스토리지에 손상된 값이 저장된 경우 — key와 raw 앞부분을 로그에 포함해 디버깅 용이하게 함
        preview = raw[:100] if isinstance(raw, str) else repr(raw)[:100]
        logger.warning(f"JSON 역직렬화 실패 (key={key!r}): {e} | raw 앞 100자: {preview!r}")
        return None


def storage_delete(key: str) -> None:
    """키 삭제."""
    r = _get_redis()
    if r:
        try:
            r.delete(key)
        except Exception as e:
            logger.warning(f"Redis delete 실패 — 캐시 무효화 후 인메모리에서만 삭제: {e}")
            _reset_redis_cache()
            _local.pop(key, None)
            logger.debug(f"인메모리 fallback 삭제 완료 (Redis 장애 후): key={key!r}")
    else:
        _local.pop(key, None)
        logger.debug(f"인메모리 삭제 완료 (Redis 미설정): key={key!r}")


def storage_exists(key: str) -> bool:
    """키 존재 여부 확인. 만료된 키는 존재하지 않는 것으로 처리."""
    r = _get_redis()
    if r:
        try:
            return bool(r.exists(key))
        except Exception as e:
            logger.warning(f"Redis exists 실패 — 캐시 무효화 후 인메모리 fallback 사용: {e}")
            _reset_redis_cache()
            result = _local_get_raw(key) is not None
            logger.debug(f"인메모리 fallback exists 확인 (Redis 장애 후): key={key!r} → {result}")
            return result
    result = _local_get_raw(key) is not None
    logger.debug(f"인메모리 exists 확인 (Redis 미설정): key={key!r} → {result}")
    return result
