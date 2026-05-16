"""
routers/payment.py 단위 테스트
결제 요청·승인·멱등성·금액 불일치·Toss API 실패·free-confirm·상태 조회 핵심 경로 검증

커버 범위:
  POST /payment/request      — order_id 생성, is_free 분기
  POST /payment/confirm      — 404 / 멱등성 / 금액 불일치 / 개발 모드 성공 / Toss 4xx·5xx·네트워크 오류
  POST /payment/free-confirm — 404 / 멱등성 / 유료 주문 차단 / 정상 성공
  GET  /payment/status       — pending / confirmed / unknown
"""
import os
import sys
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(__file__))

from main import app
from config import get_settings, Settings

ORDER_ID = "order_test123"
REQUEST_URL = "/payment/request"
CONFIRM_URL = "/payment/confirm"
FREE_CONFIRM_URL = "/payment/free-confirm"
STATUS_URL = f"/payment/status/{ORDER_ID}"

# 최소 유효 AnalyzeRequest JSON (request 엔드포인트 body 용)
_ANALYZE_REQ = {
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
            {"asset_name": "S&P500", "asset_type": "해외주식", "weight": 100.0, "ticker": None},
        ],
    },
}

# storage_get 이 반환할 pending 레코드 (유료)
_PENDING = {
    "status": "pending",
    "amount": 9900,
    "analyze_request": _ANALYZE_REQ,
    "created_at": "2024-01-01T00:00:00+09:00",
}

# storage_get 이 반환할 pending 레코드 (무료)
_FREE_PENDING = {**_PENDING, "amount": 0}


# ──────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────

def _storage_get_factory(pending=None, idempotency=None):
    """key 별로 다른 값을 반환하는 storage_get side_effect 생성"""
    store = {}
    if pending is not None:
        store[f"pay:pending:{ORDER_ID}"] = pending
    if idempotency is not None:
        store[f"pay:idempotency:{ORDER_ID}"] = idempotency
    return lambda key: store.get(key)


def _mock_toss_client(status_code: int, body: dict):
    """httpx.AsyncClient async context manager + POST mock 생성"""
    mock_resp = MagicMock(status_code=status_code)
    mock_resp.json.return_value = body
    mc = AsyncMock()
    mc.post = AsyncMock(return_value=mock_resp)
    mc.__aenter__ = AsyncMock(return_value=mc)
    mc.__aexit__ = AsyncMock(return_value=False)
    return mc


# ──────────────────────────────────────────────────────────────
# POST /payment/request
# ──────────────────────────────────────────────────────────────

def test_request_returns_order_id_and_fields():
    """기본 요청 → order_id·amount·client_key·is_free 반환"""
    app.dependency_overrides[get_settings] = lambda: Settings(
        report_price_krw=9900, toss_client_key="test_ck"
    )
    try:
        with patch("routers.payment.storage_set"):
            with TestClient(app) as c:
                resp = c.post(REQUEST_URL, json={"analyze_request": _ANALYZE_REQ})
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["order_id"].startswith("order_")
    assert body["amount"] == 9900
    assert body["client_key"] == "test_ck"
    assert body["is_free"] is False


def test_request_is_free_when_price_zero():
    """report_price_krw=0 → is_free=True, amount=0"""
    app.dependency_overrides[get_settings] = lambda: Settings(report_price_krw=0)
    try:
        with patch("routers.payment.storage_set"):
            with TestClient(app) as c:
                resp = c.post(REQUEST_URL, json={"analyze_request": _ANALYZE_REQ})
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_free"] is True
    assert body["amount"] == 0


# ──────────────────────────────────────────────────────────────
# POST /payment/confirm
# ──────────────────────────────────────────────────────────────

def test_confirm_no_pending_returns_404():
    """pending·idempotency 모두 없음 → 404"""
    with patch("routers.payment.storage_get", return_value=None):
        with TestClient(app) as c:
            resp = c.post(CONFIRM_URL, json={
                "payment_key": "pk", "order_id": ORDER_ID, "amount": 9900,
            })
    assert resp.status_code == 404


def test_confirm_idempotency_returns_cached_token():
    """pending 없음 + idempotency 있음 → 200 + 캐시된 토큰 (멱등성 보장)"""
    sg = _storage_get_factory(pending=None, idempotency={"report_token": "rpt_cached"})
    with patch("routers.payment.storage_get", side_effect=sg):
        with TestClient(app) as c:
            resp = c.post(CONFIRM_URL, json={
                "payment_key": "pk", "order_id": ORDER_ID, "amount": 9900,
            })
    assert resp.status_code == 200
    body = resp.json()
    assert body["report_token"] == "rpt_cached"
    assert body["success"] is True


def test_confirm_amount_mismatch_returns_400():
    """pending 금액(9900)과 요청 금액(1000) 불일치 → 400"""
    sg = _storage_get_factory(pending=_PENDING)
    with patch("routers.payment.storage_get", side_effect=sg):
        with TestClient(app) as c:
            resp = c.post(CONFIRM_URL, json={
                "payment_key": "pk", "order_id": ORDER_ID, "amount": 1000,
            })
    assert resp.status_code == 400
    assert "금액" in resp.json()["detail"]


def test_confirm_dev_mode_no_toss_key_succeeds():
    """toss_secret_key=''(개발 모드) → Toss 건너뜀, 200 + report_token"""
    sg = _storage_get_factory(pending=_PENDING)
    with (
        patch("routers.payment.storage_get", side_effect=sg),
        patch("routers.payment._commit_payment", return_value="rpt_dev"),
    ):
        with TestClient(app) as c:
            resp = c.post(CONFIRM_URL, json={
                "payment_key": "pk", "order_id": ORDER_ID, "amount": 9900,
            })
    assert resp.status_code == 200
    body = resp.json()
    assert body["report_token"] == "rpt_dev"
    assert body["success"] is True


def test_confirm_toss_4xx_returns_400():
    """Toss 4xx 응답(결제 데이터 문제) → 400"""
    mc = _mock_toss_client(400, {"code": "INVALID_CARD", "message": "카드 한도 초과"})
    sg = _storage_get_factory(pending=_PENDING)
    app.dependency_overrides[get_settings] = lambda: Settings(
        toss_secret_key="sk_test_xxx", report_price_krw=9900
    )
    try:
        with (
            patch("routers.payment.storage_get", side_effect=sg),
            patch("routers.payment.httpx.AsyncClient", return_value=mc),
        ):
            with TestClient(app) as c:
                resp = c.post(CONFIRM_URL, json={
                    "payment_key": "pk", "order_id": ORDER_ID, "amount": 9900,
                })
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert resp.status_code == 400


def test_confirm_toss_5xx_returns_503():
    """Toss 5xx 응답(서버 오류) → 503"""
    mc = _mock_toss_client(500, {"code": "INTERNAL_ERROR", "message": "토스 서버 오류"})
    sg = _storage_get_factory(pending=_PENDING)
    app.dependency_overrides[get_settings] = lambda: Settings(
        toss_secret_key="sk_test_xxx", report_price_krw=9900
    )
    try:
        with (
            patch("routers.payment.storage_get", side_effect=sg),
            patch("routers.payment.httpx.AsyncClient", return_value=mc),
        ):
            with TestClient(app) as c:
                resp = c.post(CONFIRM_URL, json={
                    "payment_key": "pk", "order_id": ORDER_ID, "amount": 9900,
                })
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert resp.status_code == 503


def test_confirm_toss_network_error_returns_503():
    """Toss 연결 실패(httpx.RequestError) → 503"""
    import httpx as _httpx
    mc = AsyncMock()
    mc.__aenter__ = AsyncMock(return_value=mc)
    mc.__aexit__ = AsyncMock(return_value=False)
    mc.post = AsyncMock(side_effect=_httpx.RequestError("연결 실패"))

    sg = _storage_get_factory(pending=_PENDING)
    app.dependency_overrides[get_settings] = lambda: Settings(
        toss_secret_key="sk_test_xxx", report_price_krw=9900
    )
    try:
        with (
            patch("routers.payment.storage_get", side_effect=sg),
            patch("routers.payment.httpx.AsyncClient", return_value=mc),
        ):
            with TestClient(app) as c:
                resp = c.post(CONFIRM_URL, json={
                    "payment_key": "pk", "order_id": ORDER_ID, "amount": 9900,
                })
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert resp.status_code == 503


# ──────────────────────────────────────────────────────────────
# POST /payment/free-confirm
# ──────────────────────────────────────────────────────────────

def test_free_confirm_no_pending_returns_404():
    """pending·idempotency 모두 없음 → 404"""
    with patch("routers.payment.storage_get", return_value=None):
        with TestClient(app) as c:
            resp = c.post(FREE_CONFIRM_URL, json={"order_id": ORDER_ID})
    assert resp.status_code == 404


def test_free_confirm_idempotency_returns_cached_token():
    """pending 없음 + idempotency 있음 → 200 + 캐시된 토큰 (멱등성 보장)"""
    sg = _storage_get_factory(pending=None, idempotency={"report_token": "rpt_free_cached"})
    with patch("routers.payment.storage_get", side_effect=sg):
        with TestClient(app) as c:
            resp = c.post(FREE_CONFIRM_URL, json={"order_id": ORDER_ID})
    assert resp.status_code == 200
    assert resp.json()["report_token"] == "rpt_free_cached"


def test_free_confirm_paid_order_returns_400():
    """유료 주문(amount=9900)에 free-confirm 시도 → 400"""
    sg = _storage_get_factory(pending=_PENDING)  # amount=9900
    with patch("routers.payment.storage_get", side_effect=sg):
        with TestClient(app) as c:
            resp = c.post(FREE_CONFIRM_URL, json={"order_id": ORDER_ID})
    assert resp.status_code == 400
    assert "무료" in resp.json()["detail"]


def test_free_confirm_success():
    """무료(amount=0) 정상 요청 → 200 + report_token"""
    sg = _storage_get_factory(pending=_FREE_PENDING)
    with (
        patch("routers.payment.storage_get", side_effect=sg),
        patch("routers.payment._commit_payment", return_value="rpt_free"),
    ):
        with TestClient(app) as c:
            resp = c.post(FREE_CONFIRM_URL, json={"order_id": ORDER_ID})
    assert resp.status_code == 200
    body = resp.json()
    assert body["report_token"] == "rpt_free"
    assert body["success"] is True


# ──────────────────────────────────────────────────────────────
# GET /payment/status/{order_id}
# ──────────────────────────────────────────────────────────────

def test_status_pending():
    """pending 키 존재 → status='pending'"""
    sg = _storage_get_factory(pending=_PENDING)
    with patch("routers.payment.storage_get", side_effect=sg):
        with TestClient(app) as c:
            resp = c.get(STATUS_URL)
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


def test_status_confirmed():
    """pending 없음 + idempotency 있음 → status='confirmed'"""
    sg = _storage_get_factory(pending=None, idempotency={"report_token": "rpt_x"})
    with patch("routers.payment.storage_get", side_effect=sg):
        with TestClient(app) as c:
            resp = c.get(STATUS_URL)
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"


def test_status_unknown():
    """pending·idempotency 모두 없음 → status='unknown'"""
    with patch("routers.payment.storage_get", return_value=None):
        with TestClient(app) as c:
            resp = c.get(STATUS_URL)
    assert resp.status_code == 200
    assert resp.json()["status"] == "unknown"
