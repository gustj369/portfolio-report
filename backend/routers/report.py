"""
PDF 리포트 생성 라우터
결제 확인 → 전체 분석 → PDF 생성 → 저장 → 다운로드 링크 반환
"""
import os
import logging
import time
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
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
        # report_token TTL(7일) 만료 또는 미결제 — 스토리지 TTL 삭제로 두 경우 구분 불가
        raise HTTPException(
            status_code=403,
            detail="결제 정보를 찾을 수 없습니다. 결제 후 7일이 경과했거나 유효하지 않은 요청입니다.",
        )

    # 이미 생성 중/완료인 경우 — GENERATING/READY만 차단, ERROR/PENDING은 재시도 허용
    existing = _load_record(body.report_token)
    if existing and existing.status in (ReportStatus.GENERATING, ReportStatus.READY):
        logger.info(f"[{body.report_token}] {existing.status.value} 상태 — 중복 생성 건너뜀")
        return GenerateReportResponse(
            report_token=body.report_token,
            status=existing.status.value,
            message="이미 처리 중이거나 완료된 요청입니다.",
        )
    if existing and existing.status == ReportStatus.ERROR:
        logger.info(f"[{body.report_token}] 이전 실패({existing.error_message}) → 재생성 시작")

    # PENDING 중복 생성 방지: 5분 이내 PENDING 재요청은 건너뜀
    # 배경 태스크 첫 줄에서 즉시 GENERATING으로 전환하므로 PENDING 체류는 수초 이내가 정상.
    # 5분을 초과한 PENDING은 서버 재시작 등으로 태스크가 유실된 경우 → 재생성 허용.
    if existing and existing.status == ReportStatus.PENDING:
        try:
            now = datetime.now(KST)
            created = existing.created_at
            if created.tzinfo is None:          # naive datetime 안전 처리
                created = created.replace(tzinfo=KST)
            if (now - created).total_seconds() < 300:
                logger.warning(
                    f"[{body.report_token}] PENDING 중복 요청 "
                    f"({int((now - created).total_seconds())}초 경과) — 건너뜀"
                )
                return GenerateReportResponse(
                    report_token=body.report_token,
                    status=ReportStatus.PENDING.value,
                    message="이미 처리 중이거나 완료된 요청입니다.",
                )
        except Exception:
            pass  # 비교 실패 시 재생성 허용

    # 새 리포트 레코드 생성 (기존 ERROR 또는 5분 초과 PENDING 덮어쓰기)
    record = ReportRecord(
        order_id=payment["order_id"],
        report_token=body.report_token,
        status=ReportStatus.PENDING,
        created_at=datetime.now(KST),
    )
    _save_record(record)

    # 백그라운드에서 PDF 생성 (record를 직접 전달 — 재로드 시 스토리지 장애로 None이 되는 엣지케이스 방지)
    background_tasks.add_task(
        _generate_report_background,
        body.report_token,
        record,
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
async def download_report(report_token: str, settings: Settings = Depends(get_settings)):
    """리포트 다운로드 — R2/S3에서 읽어 직접 스트리밍 (CORS 우회)"""
    record = _load_record(report_token)
    if not record:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")

    if record.status != ReportStatus.READY:
        raise HTTPException(status_code=409, detail="리포트가 아직 준비되지 않았습니다.")

    filename = f"report_{report_token}.pdf"

    # R2에서 읽어 스트리밍
    if settings.r2_account_id and settings.r2_access_key and settings.r2_secret_key:
        import boto3
        from fastapi.responses import StreamingResponse
        import io
        s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.r2_access_key,
            aws_secret_access_key=settings.r2_secret_key,
            region_name="auto",
        )
        s3_key = f"reports/{report_token}/{filename}"
        obj = s3.get_object(Bucket=settings.r2_bucket, Key=s3_key)
        pdf_bytes = obj["Body"].read()
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    # 로컬 파일 서빙
    from fastapi.responses import FileResponse
    filepath = os.path.join(LOCAL_REPORTS_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return FileResponse(path=filepath, media_type="application/pdf", filename=filename)


async def _generate_report_background(
    report_token: str,
    record: ReportRecord,
    payment: dict,
    settings: Settings,
):
    """백그라운드 PDF 생성 태스크 (record는 호출부에서 직접 전달)"""
    try:
        t0 = time.perf_counter()  # 전체 소요시간 측정 기준점

        # 상태 업데이트: GENERATING
        record.status = ReportStatus.GENERATING
        _save_record(record)
        # 저장 검증: Redis↔인메모리 불일치 시 폴링이 PENDING을 반환할 수 있음을 조기 감지
        # 검증 실패 시에도 생성을 중단하지 않음 — 이미 결제 완료된 요청이므로 최선을 다해 완료 시도.
        # 완료 후 READY _save_record 가 성공하면 폴링은 최종적으로 READY를 읽으므로 무해.
        _saved = _load_record(report_token)
        if not _saved or _saved.status != ReportStatus.GENERATING:
            logger.warning(
                f"[{report_token}] GENERATING 상태 저장 확인 실패 "
                f"(읽힌 상태: {_saved.status.value if _saved else 'None'}) "
                f"— 폴링이 PENDING으로 응답할 수 있음. storage 로그를 확인해주세요."
            )

        # AnalyzeRequest 복원
        analyze_req = AnalyzeRequest.model_validate(payment["analyze_request"])

        # 1. 시장 데이터 수집
        logger.info(f"[{report_token}] 시장 데이터 수집 시작")
        market_snapshot = fetch_market_snapshot(settings.fred_api_key)
        logger.info(f"[{report_token}] 시장 데이터 수집 완료 ({time.perf_counter()-t0:.2f}s)")

        # 2. 시뮬레이션
        simulation = run_simulation(analyze_req.portfolio, market_snapshot)
        logger.info(f"[{report_token}] 시뮬레이션 완료 ({time.perf_counter()-t0:.2f}s)")

        # 3. 전체 AI 분석
        logger.info(f"[{report_token}] AI 분석 시작 ({time.perf_counter()-t0:.2f}s)")
        if settings.gemini_api_key:
            ai_content = generate_full_analysis(
                analyze_req.user_profile,
                analyze_req.portfolio,
                simulation,
                market_snapshot,
                settings.gemini_api_key,
            )
            logger.info(f"[{report_token}] Gemini AI 분석 사용 ({time.perf_counter()-t0:.2f}s)")
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
            logger.info(f"[{report_token}] Gemini 미설정 — fallback 분석 사용 ({time.perf_counter()-t0:.2f}s)")
        logger.info(f"[{report_token}] AI 분석 완료 ({time.perf_counter()-t0:.2f}s 누적)")

        # 4. 차트 생성 — 개별 실패 시 None 반환 (PDF는 해당 차트 없이 계속 생성)
        logger.info(f"[{report_token}] 차트 생성 시작 ({time.perf_counter()-t0:.2f}s)")
        def _safe_chart(fn, *args):
            try:
                return fn(*args)
            except Exception as e:
                logger.warning(f"차트 생성 실패 ({fn.__name__}): {e}")
                return None

        charts = {
            "pie":          _safe_chart(generate_portfolio_pie_chart, analyze_req.portfolio),
            "line":         _safe_chart(generate_projection_line_chart, simulation),
            "stacked_bar":  _safe_chart(generate_stacked_bar_chart, analyze_req.portfolio, simulation),
            "rebalancing":  _safe_chart(generate_rebalancing_comparison_chart,
                                        analyze_req.portfolio,
                                        ai_content.rebalancing_recommendations),
        }
        logger.info(f"[{report_token}] 차트 생성 완료 ({time.perf_counter()-t0:.2f}s 누적)")

        # 5. PDF 생성
        logger.info(f"[{report_token}] PDF 생성 시작 ({time.perf_counter()-t0:.2f}s)")
        pdf_bytes = build_report(
            user_profile=analyze_req.user_profile,
            portfolio=analyze_req.portfolio,
            simulation=simulation,
            ai_content=ai_content,
            market_snapshot=market_snapshot,
            charts=charts,
        )
        logger.info(f"[{report_token}] PDF 생성 완료 ({time.perf_counter()-t0:.2f}s 누적)")

        # 6. 저장 (로컬 / AWS S3 / Cloudflare R2)
        download_url = await _save_report(report_token, pdf_bytes, settings)
        logger.info(f"[{report_token}] 저장 완료 ({time.perf_counter()-t0:.2f}s 누적)")

        # 7. 완료 처리
        record.status = ReportStatus.READY
        record.download_url = download_url
        record.completed_at = datetime.now(KST)
        _save_record(record)
        logger.info(f"[{report_token}] 리포트 생성 완료 (총 {time.perf_counter()-t0:.2f}s): {download_url}")

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
                    # 발송 실패는 리포트 생성 자체에 영향 없음 — info 레벨로 기록
                    logger.info(f"[{report_token}] 이메일 발송 실패 (주소: {user_email})")
            except Exception as email_err:
                # 발송 예외도 치명적 아님 (PDF는 이미 완료) — info 레벨로 기록
                logger.info(f"[{report_token}] 이메일 발송 예외 (무시): {email_err}")
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

    # Cloudflare R2 우선 — 저장만 하고 백엔드 다운로드 URL 반환 (CORS 우회)
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
        # presigned URL 대신 백엔드 프록시 URL 반환 (CORS 문제 없음)
        return f"/report/download/{report_token}"

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
    # 반환 경로 "/report/file/{filename}" 는 이 파일 하단의 serve_local_file 라우트
    # (router prefix "/report" + "/file/{filename}") 와 정확히 일치해야 함.
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
