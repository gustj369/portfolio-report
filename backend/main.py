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
    logger.info(f"저장 방식: {'로컬' if settings.use_local_storage else 'AWS S3'}")
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
#   - 환경변수 FRONTEND_URL (Vercel 배포 URL 등)
#   - 로컬 개발 주소
#   - Vercel 프리뷰 도메인 (*vercel.app) 은 allow_origin_regex로 처리
_cors_origins = list({
    settings.frontend_url,
    "http://localhost:3000",
    "http://localhost:3001",
} - {""})

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",  # Vercel 프리뷰 URL 자동 허용
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
