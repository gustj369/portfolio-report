"""
PDF 리포트 생성 라우터
결제 확인 → 전체 분석 → PDF 생성 → 저장 → 다운로드 링크 반환
"""
import uuid
import os
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from config import get_settings, Settings
from models.portfolio import AnalyzeRequest
from models.report import ReportRecord, ReportStatus
from services.storage import storage_set, storage_get
from services.market_data import fetch_market_snapshot
from services.simulator import run_simulation, calculate_risk_score
from services.ai_engine import generate_full_analysis
from services.chart_generator import (
    generate_portfolio_pie_chart,
    generate_projection_line_chart,
    generate_stacked_bar_chart,
    generate_rebalancing_comparison_chart,
)
from services.pdf_generator import build_report
from routers.payment import get_confirmed_payment

router = APIRouter(prefix="/report", tags=["report"])
logger = logging.getLogger(__name__)

# 스토리지 키 접두사
_RECORD_PFX = "report:record:"

# 로컬 저장 디렉토리 (개발용)
LOCAL_REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "generated_reports")
os.makedirs(LOCAL_REPORTS_DIR, exist_ok=True)


def _save_record(record: ReportRecord) -> None:
    storage_set(
        f"{_RECORD_PFX}{record.report_token}",
        record.model_dump(mode="json"),
        ttl=86400 * 7,
    )


def _load_record(report_token: str) -> ReportRecord | None:
    data = storage_get(f"{_RECORD_PFX}{report_token}")
    if data is None:
        return None
    return ReportRecord.model_validate(data)


class GenerateReportRequest(BaseModel):
    report_token: str


class GenerateReportResponse(BaseModel):
    report_token: str
    status: str
    message: str


class ReportStatusResponse(BaseModel):
    report_token: str
    status: str
    download_url: str | None = None
    error_message: str | None = None


@router.post("/generate", response_model=GenerateReportResponse)
async def generate_report(
    body: GenerateReportRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
) -> GenerateReportResponse:
    """
    PDF 리포트 생성 시작 (백그라운드 태스크)
    결제 확인 후 전체 분석 + PDF 생성 비동기 처리
    """
    # 결제 확인
    payment = get_confirmed_payment(body.report_token)
    if not payment:
        raise HTTPException(status_code=403, detail="유효하지 않은 리포트 토큰입니다.")

    # 이미 생성 중/완료인 경우
    existing = _load_record(body.report_token)
    if existing and existing.status in (ReportStatus.GENERATING, ReportStatus.READY):
        return GenerateReportResponse(
            report_token=body.report_token,
            status=existing.status.value,
            message="이미 처리 중이거나 완료된 요청입니다.",
        )

    # 새 리포트 레코드 생성
    record = ReportRecord(
        order_id=payment["order_id"],
        report_token=body.report_token,
        status=ReportStatus.PENDING,
        created_at=datetime.now(),
    )
    _save_record(record)

    # 백그라운드에서 PDF 생성
    background_tasks.add_task(
        _generate_report_background,
        body.report_token,
        payment,
        settings,
    )

    return GenerateReportResponse(
        report_token=body.report_token,
        status=ReportStatus.PENDING.value,
        message="리포트 생성을 시작했습니다.",
    )


@router.get("/status/{report_token}", response_model=ReportStatusResponse)
async def get_report_status(report_token: str) -> ReportStatusResponse:
    """리포트 생성 상태 조회"""
    record = _load_record(report_token)
    if not record:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")

    return ReportStatusResponse(
        report_token=record.report_token,
        status=record.status.value,
        download_url=record.download_url,
        error_message=record.error_message,
    )


@router.get("/download/{report_token}")
async def download_report(report_token: str):
    """리포트 다운로드 — S3/R2 URL로 리다이렉트 또는 직접 반환"""
    record = _load_record(report_token)
    if not record:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")

    if record.status != ReportStatus.READY:
        raise HTTPException(status_code=409, detail="리포트가 아직 준비되지 않았습니다.")

    if not record.download_url:
        raise HTTPException(status_code=500, detail="다운로드 URL을 찾을 수 없습니다.")

    return RedirectResponse(url=record.download_url, status_code=302)


async def _generate_report_background(
    report_token: str,
    payment: dict,
    settings: Settings,
):
    """백그라운드 PDF 생성 태스크"""
    record = _load_record(report_token)
    if not record:
        logger.error(f"[{report_token}] 레코드 없음 — 생성 불가")
        return

    try:
        # 상태 업데이트: GENERATING
        record.status = ReportStatus.GENERATING
        _save_record(record)

        # AnalyzeRequest 복원
        analyze_req = AnalyzeRequest.model_validate(payment["analyze_request"])

        # 1. 시장 데이터 수집
        logger.info(f"[{report_token}] 시장 데이터 수집")
        market_snapshot = fetch_market_snapshot(settings.fred_api_key)

        # 2. 시뮬레이션
        logger.info(f"[{report_token}] 시뮬레이션 실행")
        simulation = run_simulation(analyze_req.portfolio, market_snapshot)

        # 3. 전체 AI 분석
        logger.info(f"[{report_token}] AI 분석 시작")
        if settings.gemini_api_key:
            ai_content = generate_full_analysis(
                analyze_req.user_profile,
                analyze_req.portfolio,
                simulation,
                market_snapshot,
                settings.gemini_api_key,
            )
        else:
            from services.fallback_analyzer import generate_personalized_content
            risk_score, risk_grade = calculate_risk_score(analyze_req.portfolio, market_snapshot)
            ai_content = generate_personalized_content(
                analyze_req.user_profile,
                analyze_req.portfolio,
                simulation,
                market_snapshot,
                risk_score,
                risk_grade,
            )

        # 4. 차트 생성
        logger.info(f"[{report_token}] 차트 생성")
        charts = {
            "pie": generate_portfolio_pie_chart(analyze_req.portfolio),
            "line": generate_projection_line_chart(simulation),
            "stacked_bar": generate_stacked_bar_chart(analyze_req.portfolio, simulation),
            "rebalancing": generate_rebalancing_comparison_chart(
                analyze_req.portfolio,
                ai_content.rebalancing_recommendations,
            ),
        }

        # 5. PDF 생성
        logger.info(f"[{report_token}] PDF 생성")
        pdf_bytes = build_report(
            user_profile=analyze_req.user_profile,
            portfolio=analyze_req.portfolio,
            simulation=simulation,
            ai_content=ai_content,
            market_snapshot=market_snapshot,
            charts=charts,
        )

        # 6. 저장 (로컬 / AWS S3 / Cloudflare R2)
        download_url = await _save_report(report_token, pdf_bytes, settings)

        # 7. 완료 처리
        record.status = ReportStatus.READY
        record.download_url = download_url
        record.completed_at = datetime.now()
        _save_record(record)
        logger.info(f"[{report_token}] 리포트 생성 완료: {download_url}")

        # 8. 이메일 발송 (SMTP 설정 + 사용자 이메일 있는 경우)
        user_email = analyze_req.user_profile.email
        if user_email and settings.smtp_host and settings.smtp_user and settings.smtp_password:
            try:
                from services.email_service import send_report_email
                from_addr = settings.smtp_from or settings.smtp_user
                sent = send_report_email(
                    smtp_host=settings.smtp_host,
                    smtp_port=settings.smtp_port,
                    smtp_user=settings.smtp_user,
                    smtp_password=settings.smtp_password,
                    from_address=from_addr,
                    to_address=user_email,
                    user_name=analyze_req.user_profile.name,
                    pdf_bytes=pdf_bytes,
                )
                if sent:
                    logger.info(f"[{report_token}] 이메일 발송 완료: {user_email}")
                else:
                    logger.warning(f"[{report_token}] 이메일 발송 실패 (주소: {user_email})")
            except Exception as email_err:
                logger.warning(f"[{report_token}] 이메일 발송 예외 (무시): {email_err}")
        elif user_email:
            logger.info(f"[{report_token}] SMTP 미설정 — 이메일 발송 건너뜀 (주소: {user_email})")

    except Exception as e:
        logger.error(f"[{report_token}] 리포트 생성 실패: {e}", exc_info=True)
        record.status = ReportStatus.ERROR
        record.error_message = str(e)
        _save_record(record)


async def _save_report(report_token: str, pdf_bytes: bytes, settings: Settings) -> str:
    """PDF 저장 — 로컬(개발) / Cloudflare R2 / AWS S3"""
    filename = f"report_{report_token}.pdf"

    # Cloudflare R2 우선
    if settings.r2_account_id and settings.r2_access_key and settings.r2_secret_key:
        import boto3
        s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.r2_access_key,
            aws_secret_access_key=settings.r2_secret_key,
            region_name="auto",
        )
        s3_key = f"reports/{report_token}/{filename}"
        s3.put_object(
            Bucket=settings.r2_bucket,
            Key=s3_key,
            Body=pdf_bytes,
            ContentType="application/pdf",
        )
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.r2_bucket, "Key": s3_key},
            ExpiresIn=86400,  # 24시간
        )
        return presigned_url

    # AWS S3
    if not settings.use_local_storage and settings.aws_access_key_id:
        import boto3
        s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
        s3_key = f"reports/{report_token}/{filename}"
        s3.put_object(
            Bucket=settings.s3_bucket,
            Key=s3_key,
            Body=pdf_bytes,
            ContentType="application/pdf",
        )
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": s3_key},
            ExpiresIn=86400,
        )
        return presigned_url

    # 로컬 저장 (개발 환경)
    filepath = os.path.join(LOCAL_REPORTS_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(pdf_bytes)
    return f"/report/file/{filename}"


@router.get("/file/{filename}")
async def serve_local_file(filename: str):
    """개발용 로컬 PDF 파일 서빙"""
    from fastapi.responses import FileResponse
    # 경로 순회 공격 방지: 파일명에 경로 구분자 금지
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="잘못된 파일명입니다.")
    filepath = os.path.join(LOCAL_REPORTS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return FileResponse(
        path=filepath,
        media_type="application/pdf",
        filename=filename,
    )
