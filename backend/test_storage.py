"""
services/storage.py 단위 테스트

외부 의존(Redis) 없이 인메모리 경로와 Redis mock 경로를 모두 검증한다.

커버 범위:
  인메모리 — set/get/delete/exists, TTL 만료(lazy expiry), GC(_gc_local), 손상된 JSON
  Redis mock — set/get/delete/exists 정상 경로
  장애 처리 — Redis set/get/delete/exists 예외 → 인메모리 fallback 전환
"""
import sys
import os
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))

import services.storage as storage_mod
from services.storage import (
    storage_set,
    storage_get,
    storage_delete,
    storage_exists,
    _GC_INTERVAL,
)


# ──────────────────────────────────────────────────────────────
# 테스트 격리 fixture — 각 테스트 전 모듈 상태 초기화
# ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_storage():
    """테스트 간 인메모리 상태·Redis 캐시·GC 카운터를 초기화한다."""
    storage_mod._local.clear()
    storage_mod._redis_client_cache = None
    storage_mod._gc_counter = 0
    yield
    storage_mod._local.clear()
    storage_mod._redis_client_cache = None
    storage_mod._gc_counter = 0


# ──────────────────────────────────────────────────────────────
# 인메모리 경로 — 기본 CRUD
# ──────────────────────────────────────────────────────────────

class TestInMemoryBasic:
    def test_set_and_get_dict(self):
        """set 후 get 하면 동일한 dict를 반환해야 한다"""
        storage_set("k1", {"a": 1, "b": "hello"})
        result = storage_get("k1")
        assert result == {"a": 1, "b": "hello"}

    def test_get_missing_key_returns_none(self):
        """존재하지 않는 키는 None을 반환해야 한다"""
        assert storage_get("no_such_key") is None

    def test_delete_removes_key(self):
        """delete 후 get은 None을 반환해야 한다"""
        storage_set("k2", {"x": 42})
        storage_delete("k2")
        assert storage_get("k2") is None

    def test_delete_nonexistent_key_is_safe(self):
        """없는 키를 delete해도 예외가 발생하지 않아야 한다"""
        storage_delete("ghost")  # 예외 없이 통과해야 함

    def test_exists_true_for_stored_key(self):
        """저장된 키는 exists가 True여야 한다"""
        storage_set("k3", "value")
        assert storage_exists("k3") is True

    def test_exists_false_for_missing_key(self):
        """없는 키는 exists가 False여야 한다"""
        assert storage_exists("missing") is False

    def test_overwrite_returns_latest_value(self):
        """같은 키로 두 번 set하면 마지막 값을 반환해야 한다"""
        storage_set("k4", {"v": 1})
        storage_set("k4", {"v": 2})
        assert storage_get("k4") == {"v": 2}

    def test_set_list_value(self):
        """list 타입 값도 정확히 저장·반환되어야 한다"""
        storage_set("list_key", [1, 2, 3])
        assert storage_get("list_key") == [1, 2, 3]

    def test_set_string_value(self):
        """str 타입 값도 정확히 저장·반환되어야 한다"""
        storage_set("str_key", "hello")
        assert storage_get("str_key") == "hello"


# ──────────────────────────────────────────────────────────────
# 인메모리 경로 — TTL 만료 (lazy expiry)
# ──────────────────────────────────────────────────────────────

class TestInMemoryTTL:
    def test_key_expires_after_ttl(self):
        """TTL이 지난 키는 get 시 None을 반환하고 _local에서 삭제되어야 한다"""
        storage_set("expiring", {"data": "temp"}, ttl=1)
        # 만료 시각을 과거로 강제 조작 (실제 sleep 없이)
        key = "expiring"
        val, _ = storage_mod._local[key]
        storage_mod._local[key] = (val, time.time() - 1)

        assert storage_get(key) is None
        assert key not in storage_mod._local  # lazy expiry로 삭제 확인

    def test_exists_false_for_expired_key(self):
        """TTL이 지난 키는 exists가 False여야 한다"""
        storage_set("exp2", "data", ttl=1)
        val, _ = storage_mod._local["exp2"]
        storage_mod._local["exp2"] = (val, time.time() - 1)

        assert storage_exists("exp2") is False

    def test_non_expired_key_is_accessible(self):
        """TTL이 충분히 남은 키는 정상 반환되어야 한다"""
        storage_set("fresh", {"ok": True}, ttl=3600)
        assert storage_get("fresh") == {"ok": True}


# ──────────────────────────────────────────────────────────────
# 인메모리 경로 — GC (_gc_local)
# ──────────────────────────────────────────────────────────────

class TestInMemoryGC:
    def test_gc_removes_expired_keys_at_interval(self):
        """_GC_INTERVAL 번째 set 호출 시 만료 키가 _local에서 일괄 삭제되어야 한다"""
        # 만료된 키 1개 심기
        storage_mod._local["dead"] = ('{"x":1}', time.time() - 1)
        # GC 직전까지 카운터 채우기
        storage_mod._gc_counter = _GC_INTERVAL - 1

        # 이번 set이 GC를 트리거
        storage_set("trigger", {"t": 1})
        assert "dead" not in storage_mod._local

    def test_gc_does_not_remove_live_keys(self):
        """GC 실행 시 유효한 키는 삭제되지 않아야 한다"""
        storage_set("live", {"keep": True}, ttl=3600)
        storage_mod._gc_counter = _GC_INTERVAL - 1
        storage_set("trigger2", {"t": 2})
        assert storage_mod._local.get("live") is not None


# ──────────────────────────────────────────────────────────────
# 인메모리 경로 — 손상된 JSON
# ──────────────────────────────────────────────────────────────

class TestCorruptedData:
    def test_corrupted_json_returns_none(self):
        """_local에 손상된 JSON이 있으면 get은 None을 반환해야 한다"""
        storage_mod._local["bad"] = ("not-valid-json{{", None)
        assert storage_get("bad") is None


# ──────────────────────────────────────────────────────────────
# Redis mock 경로 — 정상 동작
# ──────────────────────────────────────────────────────────────

class TestRedisMockNormal:
    """_redis_client_cache에 MagicMock을 주입하여 Redis 정상 경로를 검증한다."""

    def _inject_redis(self) -> MagicMock:
        """가짜 Redis 클라이언트를 캐시에 주입하고 반환한다."""
        mock_r = MagicMock()
        storage_mod._redis_client_cache = mock_r
        return mock_r

    def test_set_calls_redis_set(self):
        """storage_set은 Redis client.set(key, serialized, ex=ttl)을 호출해야 한다"""
        mock_r = self._inject_redis()
        storage_set("rk1", {"a": 1}, ttl=60)
        mock_r.set.assert_called_once()
        args, kwargs = mock_r.set.call_args
        assert args[0] == "rk1"
        assert kwargs.get("ex") == 60

    def test_get_calls_redis_get_and_deserializes(self):
        """storage_get은 Redis client.get을 호출하고 JSON을 역직렬화해 반환해야 한다"""
        mock_r = self._inject_redis()
        mock_r.get.return_value = '{"b": 2}'
        result = storage_get("rk2")
        mock_r.get.assert_called_once_with("rk2")
        assert result == {"b": 2}

    def test_get_returns_none_when_redis_returns_none(self):
        """Redis get이 None 반환 시 storage_get도 None을 반환해야 한다"""
        mock_r = self._inject_redis()
        mock_r.get.return_value = None
        assert storage_get("rk3") is None

    def test_delete_calls_redis_delete(self):
        """storage_delete는 Redis client.delete를 호출해야 한다"""
        mock_r = self._inject_redis()
        storage_delete("rk4")
        mock_r.delete.assert_called_once_with("rk4")

    def test_exists_true_when_redis_returns_nonzero(self):
        """Redis exists가 1 반환 시 storage_exists는 True여야 한다"""
        mock_r = self._inject_redis()
        mock_r.exists.return_value = 1
        assert storage_exists("rk5") is True

    def test_exists_false_when_redis_returns_zero(self):
        """Redis exists가 0 반환 시 storage_exists는 False여야 한다"""
        mock_r = self._inject_redis()
        mock_r.exists.return_value = 0
        assert storage_exists("rk6") is False


# ──────────────────────────────────────────────────────────────
# Redis 장애 경로 — 인메모리 fallback 전환
# ──────────────────────────────────────────────────────────────

class TestRedisFallback:
    """Redis 각 operation 실패 시 인메모리 fallback으로 전환되는지 검증한다."""

    def _inject_failing_redis(self, method: str) -> MagicMock:
        """지정 method가 예외를 발생시키는 가짜 Redis 클라이언트를 주입한다."""
        mock_r = MagicMock()
        getattr(mock_r, method).side_effect = Exception("Redis 장애")
        storage_mod._redis_client_cache = mock_r
        return mock_r

    def test_set_failure_falls_back_to_local(self):
        """Redis set 실패 시 인메모리에 저장되어야 한다"""
        self._inject_failing_redis("set")
        storage_set("fb1", {"v": 99})
        # Redis 캐시가 무효화되어 None이어야 함
        assert storage_mod._redis_client_cache is None
        # 인메모리에 저장 확인
        assert storage_mod._local.get("fb1") is not None

    def test_get_failure_falls_back_to_local(self):
        """Redis get 실패 시 인메모리 값을 반환해야 한다"""
        storage_mod._local["fb2"] = ('{"local": true}', None)
        self._inject_failing_redis("get")
        result = storage_get("fb2")
        assert result == {"local": True}
        assert storage_mod._redis_client_cache is None

    def test_delete_failure_falls_back_to_local_delete(self):
        """Redis delete 실패 시 인메모리 키를 삭제해야 한다"""
        storage_mod._local["fb3"] = ('{"d": 1}', None)
        self._inject_failing_redis("delete")
        storage_delete("fb3")
        assert storage_mod._redis_client_cache is None
        assert "fb3" not in storage_mod._local

    def test_exists_failure_falls_back_to_local(self):
        """Redis exists 실패 시 인메모리 상태를 반환해야 한다"""
        storage_mod._local["fb4"] = ('{"e": 1}', None)
        self._inject_failing_redis("exists")
        assert storage_exists("fb4") is True
        assert storage_mod._redis_client_cache is None


# ──────────────────────────────────────────────────────────────
# 잠금 / 결제 복구 (storage_acquire_lock, storage_release_lock,
#                   storage_confirm_payment_recovery)
# ──────────────────────────────────────────────────────────────

class TestLockAndPaymentRecovery:
    """인메모리 환경에서 잠금과 결제 복구 원자적 처리를 검증한다."""

    def test_local_lock_acquire_blocks_duplicate_owner(self):
        """같은 키를 동일 소유자가 재획득 시도하면 False를 반환해야 한다"""
        assert storage_mod.storage_acquire_lock("lock:test", "owner-1", ttl=60) is True
        assert storage_mod.storage_acquire_lock("lock:test", "owner-1", ttl=60) is False

    def test_local_lock_release_requires_same_owner(self):
        """다른 소유자는 잠금을 해제할 수 없어야 한다"""
        storage_mod.storage_acquire_lock("lock:test", "owner-1", ttl=60)
        assert storage_mod.storage_release_lock("lock:test", "owner-2") is False
        assert storage_mod.storage_release_lock("lock:test", "owner-1") is True
        # 해제 후 다른 소유자가 획득 가능해야 한다
        assert storage_mod.storage_acquire_lock("lock:test", "owner-2", ttl=60) is True

    def test_local_payment_recovery_confirm_writes_in_safe_order(self):
        """결제 복구 확정이 올바른 순서로 저장되어야 한다"""
        storage_set("pay:pending:order_test", {"amount": 4900}, ttl=60)

        result = storage_mod.storage_confirm_payment_recovery(
            order_id="order_test",
            report_token="rpt_test",
            confirmed_record={"order_id": "order_test", "amount": 4900},
            idempotency_record={"report_token": "rpt_test"},
            ttl=60,
        )

        assert result["ok"] is True
        assert storage_get("pay:pending:order_test") is None
        assert storage_get("pay:idempotency:order_test")["report_token"] == "rpt_test"
        assert storage_get("pay:confirmed:rpt_test")["order_id"] == "order_test"

    def test_local_payment_recovery_confirm_blocks_duplicate(self):
        """이미 멱등성 키가 있으면 중복 결제 확정을 차단해야 한다"""
        storage_set("pay:pending:order_test", {"amount": 4900}, ttl=60)
        storage_set("pay:idempotency:order_test", {"report_token": "rpt_old"}, ttl=60)

        result = storage_mod.storage_confirm_payment_recovery(
            order_id="order_test",
            report_token="rpt_new",
            confirmed_record={"order_id": "order_test", "amount": 4900},
            idempotency_record={"report_token": "rpt_new"},
            ttl=60,
        )

        assert result["ok"] is False
        assert result["reason"] == "idempotency exists"
        assert storage_get("pay:confirmed:rpt_new") is None
