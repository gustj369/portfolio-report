from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from config import get_settings
from limiter import limiter  # 순환 import 방지 — 별도 모듈에서 인스턴스 공유
from routers import analyze, payment, report

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("포트폴리오 AI 리포트 서버 시작")

    # Sentry 오류 추적 초기화 (SENTRY_DSN 설정 시에만 활성화 — 미설정이면 no-op)
    if settings.sentry_dsn:
        try:
            import sentry_sdk
            sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.2)
            logger.info("Sentry 초기화 완료")
        except ImportError:
            logger.warning("sentry-sdk 미설치 — 오류 추적 비활성화 (pip install sentry-sdk)")

    logger.info(f"Gemini API: {'설정됨' if settings.gemini_api_key else '미설정 (더미 모드)'}")
    logger.info(f"Toss Payments: {'설정됨' if settings.toss_client_key else '미설정 (개발 모드)'}")
    if settings.use_local_storage:
        storage_label = "로컬 파일시스템"
    elif settings.r2_account_id and settings.r2_access_key:
        storage_label = "Cloudflare R2"
    elif settings.aws_access_key_id:
        storage_label = "AWS S3"
    else:
        storage_label = "로컬 파일시스템 (fallback)"
    logger.info(f"저장 방식: {storage_label}")
    yield
    logger.info("서버 종료")


app = FastAPI(
    title="포트폴리오 AI 리포트 API",
    description="AI 기반 자산 배분 분석 및 PDF 리포트 생성 서비스",
    version="1.0.0",
    lifespan=lifespan,
)

# Rate limiter 상태 주입 및 미들웨어·핸들러 등록
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

settings = get_settings()

# CORS 허용 오리진:
#   - 환경변수 FRONTEND_URL: 프로덕션·Vercel 배포 URL을 명시적으로 지정 (권장)
#     예) FRONTEND_URL=https://my-app.vercel.app
#   - 로컬 개발 주소는 항상 허용
#
# ※ 이전에 사용하던 allow_origin_regex=r"https://.*\.vercel\.app" 는 제거함.
#    임의의 Vercel 앱(.vercel.app)이 API에 접근할 수 있는 보안 위험이 있었음.
#    Vercel 프리뷰 URL이 필요하면 FRONTEND_URL 에 해당 URL을 명시적으로 추가할 것.
_cors_origins = list({
    settings.frontend_url,
    "http://localhost:3000",
    "http://localhost:3001",
} - {""})

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze.router)
app.include_router(payment.router)
app.include_router(report.router)


@app.get("/health")
async def health_check():
    # 스토리지 모드 판별 (lifespan 로그와 동일한 분기)
    if settings.use_local_storage:
        storage_mode = "local"
    elif settings.r2_account_id and settings.r2_access_key:
        storage_mode = "r2"
    elif settings.aws_access_key_id:
        storage_mode = "s3"
    else:
        storage_mode = "local"

    # Redis 연결 여부 — _get_redis() 재사용 (새 연결 없이 캐시 반환)
    from services.storage import _get_redis
    try:
        r = _get_redis()
        redis_status = "connected" if r is not None else "not_configured"
    except Exception:
        redis_status = "disconnected"

    return {
        "status": "ok",
        "service": "portfolio-ai-report",
        "version": app.version,
        "storage_mode": storage_mode,
        "redis": redis_status,
    }


@app.get("/")
async def root():
    return {
        "message": "포트폴리오 AI 리포트 API",
        "docs": "/docs",
        "health": "/health",
    }
