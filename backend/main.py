from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from config import get_settings
from routers import analyze, payment, report

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("포트폴리오 AI 리포트 서버 시작")
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
    return {"status": "ok", "service": "portfolio-ai-report"}


@app.get("/")
async def root():
    return {
        "message": "포트폴리오 AI 리포트 API",
        "docs": "/docs",
        "health": "/health",
    }
