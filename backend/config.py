from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    gemini_api_key: str = ""
    fred_api_key: str = ""
    toss_client_key: str = ""
    toss_secret_key: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "ap-northeast-2"
    s3_bucket: str = "portfolio-reports"
    report_price_krw: int = 4900
    frontend_url: str = "http://localhost:3000"
    use_local_storage: bool = True  # S3 대신 로컬 저장 (개발용)

    # Redis (Upstash 등) — 미설정 시 인메모리 fallback (재시작하면 데이터 초기화)
    redis_url: str = ""           # redis://... 또는 rediss://...

    # Cloudflare R2 (S3 호환) — 미설정 시 로컬 저장
    r2_account_id: str = ""
    r2_access_key: str = ""
    r2_secret_key: str = ""
    r2_bucket: str = "portfolio-reports"

    # SMTP 이메일 설정 (선택 — 미설정 시 이메일 발송 건너뜀)
    smtp_host: str = ""
    smtp_port: int = 587          # 587=STARTTLS, 465=SSL
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""           # 발신자 주소 (미설정 시 smtp_user 사용)

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
