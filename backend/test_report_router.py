"""
routers/report.py 단위 테스트
네트워크·외부 서비스 없이 FastAPI TestClient + unittest.mock 으로 핵심 경로 검증

커버 범위:
  POST /report/generate  — 403 / 중복 GENERATING·READY 조기 반환 / 신규 PENDING
  GET  /report/status    — 404 / GENERATING / READY(download_url 포함) / ERROR(error_message 포함)
  GET  /report/download  — 404 / 409(미준비) / 429(횟수 초과) / 200(로컬 파일 서빙)
"""
import os
import sys
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(__file__))

from main import app
from models.report import ReportRecord, ReportStatus

# ──────────────────────────────────────────────────────────────
# 상수 · 헬퍼
# ──────────────────────────────────────────────────────────────

TOKEN = "rpt_testtoken"
GENERATE_URL = "/report/generate"
STATUS_URL = f"/report/status/{TOKEN}"
DOWNLOAD_URL = f"/report/download/{TOKEN}"


def _record(
    status: ReportStatus = ReportStatus.PENDING,
    download_url: str | None = None,
    download_count: int = 0,
    error_message: str | None = None,
) -> ReportRecord:
    """테스트용 ReportRecord 생성 헬퍼"""
    return ReportRecord(
        order_id="order_test",
        report_token=TOKEN,
        status=status,
        download_url=download_url,
        error_message=error_message,
        created_at=datetime.now(timezone.utc),
        download_count=download_count,
    )


def _payment() -> dict:
    """테스트용 결제 정보 헬퍼 (get_confirmed_payment 반환값 형태)"""
    return {
        "order_id": "order_test",
        "payment_key": "pk_test",
        "amount": 9900,
        "analyze_request": {
            "user_profile": {
                "age": 35,
                "monthly_income": 500,
                "investment_goal": "자산증식",
                "investment_period": 5,
                "risk_tolerance": "중립형",
                "name": "테스터",
                "email": None,
            },
            "portfolio": {
                "total_asset": 5000,
                "monthly_saving": 0,
                "allocations": [
                    {
                        "asset_name": "S&P500",
                        "asset_type": "해외주식",
                        "weight": 100.0,
                        "ticker": None,
                    }
                ],
            },
        },
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
    }


# ──────────────────────────────────────────────────────────────
# POST /report/generate
# ──────────────────────────────────────────────────────────────

def test_generate_no_payment_returns_403():
    """결제 정보 없음(미결제·만료) → 403 Forbidden"""
    with patch("routers.report.get_confirmed_payment", return_value=None):
        with TestClient(app) as c:
            resp = c.post(GENERATE_URL, json={"report_token": TOKEN})
    assert resp.status_code == 403


def test_generate_already_generating_skips_duplicate():
    """이미 GENERATING 상태 → 200 조기 반환, 중복 생성 차단"""
    with (
        patch("routers.report.get_confirmed_payment", return_value=_payment()),
        patch("routers.report._load_record", return_value=_record(ReportStatus.GENERATING)),
    ):
        with TestClient(app) as c:
            resp = c.post(GENERATE_URL, json={"report_token": TOKEN})
    assert resp.status_code == 200
    assert resp.json()["status"] == "generating"


def test_generate_already_ready_skips_duplicate():
    """이미 READY 상태 → 200 조기 반환, 중복 생성 차단"""
    with (
        patch("routers.report.get_confirmed_payment", return_value=_payment()),
        patch("routers.report._load_record", return_value=_record(ReportStatus.READY)),
    ):
        with TestClient(app) as c:
            resp = c.post(GENERATE_URL, json={"report_token": TOKEN})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_generate_new_token_returns_pending():
    """신규 토큰 → 200 PENDING 반환 + 백그라운드 태스크 등록"""
    with (
        patch("routers.report.get_confirmed_payment", return_value=_payment()),
        patch("routers.report._load_record", return_value=None),
        patch("routers.report._save_record"),
        # 실제 PDF 생성 차단 — TestClient는 background task를 동기 실행하므로 필수
        patch("routers.report._generate_report_background"),
    ):
        with TestClient(app) as c:
            resp = c.post(GENERATE_URL, json={"report_token": TOKEN})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["report_token"] == TOKEN


# ──────────────────────────────────────────────────────────────
# GET /report/status/{token}
# ──────────────────────────────────────────────────────────────

def test_status_unknown_token_returns_404():
    """레코드 없음(만료·잘못된 토큰) → 404 Not Found"""
    with patch("routers.report._load_record", return_value=None):
        with TestClient(app) as c:
            resp = c.get(STATUS_URL)
    assert resp.status_code == 404


def test_status_generating_has_no_download_url():
    """GENERATING 상태 → status 필드 정확, download_url 없음"""
    with patch("routers.report._load_record", return_value=_record(ReportStatus.GENERATING)):
        with TestClient(app) as c:
            resp = c.get(STATUS_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "generating"
    assert body["download_url"] is None


def test_status_ready_includes_download_url():
    """READY 상태 → download_url 포함"""
    url = f"/report/download/{TOKEN}"
    with patch("routers.report._load_record", return_value=_record(ReportStatus.READY, download_url=url)):
        with TestClient(app) as c:
            resp = c.get(STATUS_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["download_url"] == url


def test_status_error_includes_error_message():
    """ERROR 상태 → error_message 포함"""
    with patch("routers.report._load_record", return_value=_record(ReportStatus.ERROR, error_message="AI 분석 실패")):
        with TestClient(app) as c:
            resp = c.get(STATUS_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "error"
    assert body["error_message"] == "AI 분석 실패"


# ──────────────────────────────────────────────────────────────
# GET /report/download/{token}
# ──────────────────────────────────────────────────────────────

def test_download_unknown_token_returns_404():
    """레코드 없음 → 404 Not Found"""
    with patch("routers.report._load_record", return_value=None):
        with TestClient(app) as c:
            resp = c.get(DOWNLOAD_URL)
    assert resp.status_code == 404


def test_download_not_ready_returns_409():
    """GENERATING(미완료) 상태 → 409 Conflict"""
    with patch("routers.report._load_record", return_value=_record(ReportStatus.GENERATING)):
        with TestClient(app) as c:
            resp = c.get(DOWNLOAD_URL)
    assert resp.status_code == 409


def test_download_count_exceeded_returns_429():
    """다운로드 횟수 상한(10회) 도달 → 429 Too Many Requests"""
    with patch("routers.report._load_record", return_value=_record(ReportStatus.READY, download_count=10)):
        with TestClient(app) as c:
            resp = c.get(DOWNLOAD_URL)
    assert resp.status_code == 429


def test_download_local_file_served(tmp_path):
    """로컬 PDF 파일 존재 → 200 + application/pdf (R2·S3 미설정 환경 기본 경로)"""
    filename = f"report_{TOKEN}.pdf"
    (tmp_path / filename).write_bytes(b"%PDF-1.4 stub content")

    with (
        patch("routers.report._load_record", return_value=_record(ReportStatus.READY)),
        patch("routers.report._save_record"),           # 다운로드 카운트 저장 차단
        patch("routers.report.LOCAL_REPORTS_DIR", str(tmp_path)),
    ):
        with TestClient(app) as c:
            resp = c.get(DOWNLOAD_URL)

    assert resp.status_code == 200
    assert "application/pdf" in resp.headers["content-type"]


# ──────────────────────────────────────────────────────────────
# GET /report/file/{filename}  —  serve_local_file 경로 순회 방지
# ──────────────────────────────────────────────────────────────
# 방어 로직: filename 에 '/' '\\' '..' 포함 시 400 반환 (report.py 참고)

FILE_URL = "/report/file"


def test_serve_file_dotdot_prefix_returns_400():
    """파일명 선두 '..' → 400 (경로 순회 차단)"""
    with TestClient(app) as c:
        resp = c.get(f"{FILE_URL}/..secret.pdf")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "잘못된 파일명입니다."


def test_serve_file_dotdot_infix_returns_400():
    """파일명 중간 '..' → 400 (경로 순회 차단)"""
    with TestClient(app) as c:
        resp = c.get(f"{FILE_URL}/file..etc.pdf")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "잘못된 파일명입니다."


def test_serve_file_backslash_encoded_returns_400():
    """백슬래시 URL 인코딩(%5C) → FastAPI 디코딩 후 '\\' 감지 → 400"""
    with TestClient(app) as c:
        resp = c.get(f"{FILE_URL}/file%5Csecret.pdf")  # %5C == '\'
    assert resp.status_code == 400
    assert resp.json()["detail"] == "잘못된 파일명입니다."


def test_serve_file_missing_returns_404(tmp_path):
    """정상 파일명이지만 파일 없음 → 404"""
    with patch("routers.report.LOCAL_REPORTS_DIR", str(tmp_path)):
        with TestClient(app) as c:
            resp = c.get(f"{FILE_URL}/report_missing.pdf")
    assert resp.status_code == 404


def test_serve_file_valid_served(tmp_path):
    """정상 파일명 + 파일 존재 → 200 + application/pdf"""
    filename = "report_valid.pdf"
    (tmp_path / filename).write_bytes(b"%PDF-1.4 stub")
    with patch("routers.report.LOCAL_REPORTS_DIR", str(tmp_path)):
        with TestClient(app) as c:
            resp = c.get(f"{FILE_URL}/{filename}")
    assert resp.status_code == 200
    assert "application/pdf" in resp.headers["content-type"]
