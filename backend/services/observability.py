"""
선택형 관측성 초기화.

SENTRY_DSN이 설정되어 있고 sentry-sdk가 설치된 환경에서만 Sentry를 활성화합니다.
패키지가 없으면 서버 실행을 막지 않고 로그만 남깁니다.
"""
import logging

logger = logging.getLogger(__name__)


def init_sentry(*, dsn: str, environment: str = "production") -> bool:
    if not dsn:
        logger.info("Sentry DSN 미설정 — 오류 보고 비활성화")
        return False

    try:
        import sentry_sdk
    except ImportError:
        logger.warning("SENTRY_DSN이 설정되었지만 sentry-sdk가 설치되어 있지 않아 오류 보고를 건너뜁니다.")
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=0.0,
    )
    logger.info("Sentry 오류 보고 활성화")
    return True
