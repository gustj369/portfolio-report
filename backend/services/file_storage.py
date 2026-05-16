"""
PDF 파일 스토리지 추상화 — Cloudflare R2 / AWS S3 / 로컬 파일시스템

백엔드 선택 분기를 이 모듈에 집중하여 routers/report.py 에서 스토리지 세부 구현을 격리.

우선순위:
  1. Cloudflare R2 (r2_account_id + r2_access_key + r2_secret_key 설정 시)
  2. AWS S3 (use_local_storage=False + aws_access_key_id 설정 시)
  3. 로컬 파일시스템 (개발 환경 기본값)

공개 API:
  save_pdf(report_token, pdf_bytes, settings)  → download_url (str)
  load_pdf_bytes(report_token, settings)       → bytes | None  (None = R2 미설정)
  LOCAL_REPORTS_DIR                            → 로컬 저장 경로 (serve_local_file 공유)
"""
import asyncio
import logging
import os

from config import Settings

logger = logging.getLogger(__name__)

# 로컬 저장 디렉토리 (개발용) — routers/report.py의 serve_local_file 과 경로 공유
LOCAL_REPORTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "generated_reports"
)
os.makedirs(LOCAL_REPORTS_DIR, exist_ok=True)


async def save_pdf(report_token: str, pdf_bytes: bytes, settings: Settings) -> str:
    """
    PDF 저장 — 환경변수에 따라 R2 / S3 / 로컬 파일시스템 선택.
    Returns: download URL
      - R2·로컬: 백엔드 프록시 경로 ("/report/download/…" 또는 "/report/file/…")
      - S3: presigned URL (브라우저가 S3에서 직접 다운로드)
    """
    filename = f"report_{report_token}.pdf"

    # ── 1순위: Cloudflare R2 ──────────────────────────────────
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
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: s3.put_object(
                Bucket=settings.r2_bucket,
                Key=s3_key,
                Body=pdf_bytes,
                ContentType="application/pdf",
            ),
        )
        logger.info(f"[{report_token}] R2 저장 완료: {s3_key}")
        # presigned URL 대신 백엔드 프록시 URL 반환 (CORS 문제 없음)
        return f"/report/download/{report_token}"

    # ── 2순위: AWS S3 ─────────────────────────────────────────
    if not settings.use_local_storage and settings.aws_access_key_id:
        import boto3
        s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
        s3_key = f"reports/{report_token}/{filename}"
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: s3.put_object(
                Bucket=settings.s3_bucket,
                Key=s3_key,
                Body=pdf_bytes,
                ContentType="application/pdf",
            ),
        )
        presigned_url = await loop.run_in_executor(
            None,
            lambda: s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.s3_bucket, "Key": s3_key},
                ExpiresIn=86400,
            ),
        )
        logger.info(f"[{report_token}] S3 저장 완료: {s3_key}")
        return presigned_url

    # ── 3순위: 로컬 파일시스템 (개발 환경 기본값) ─────────────
    filepath = os.path.join(LOCAL_REPORTS_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(pdf_bytes)
    logger.info(f"[{report_token}] 로컬 저장 완료: {filepath}")
    # serve_local_file 라우트("/report/file/{filename}")와 일치하는 경로 반환
    return f"/report/file/{filename}"


async def load_pdf_bytes(report_token: str, settings: Settings) -> bytes | None:
    """
    R2에서 PDF 바이트 읽기 — download_report 프록시 엔드포인트 전용.
    R2 미설정 시 None 반환 (호출부에서 로컬 파일 경로로 폴백).
    """
    if not (settings.r2_account_id and settings.r2_access_key and settings.r2_secret_key):
        return None

    import boto3
    filename = f"report_{report_token}.pdf"
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key,
        aws_secret_access_key=settings.r2_secret_key,
        region_name="auto",
    )
    s3_key = f"reports/{report_token}/{filename}"
    loop = asyncio.get_running_loop()
    obj = await loop.run_in_executor(
        None, lambda: s3.get_object(Bucket=settings.r2_bucket, Key=s3_key)
    )
    return obj["Body"].read()
