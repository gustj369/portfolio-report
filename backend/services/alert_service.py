"""
운영 알림 서비스.

외부 의존성 없이 Slack Incoming Webhook처럼 JSON 요청을 받는 웹훅으로
중요한 운영 이벤트를 전달합니다.
"""
import json
import logging
from urllib import request, error

logger = logging.getLogger(__name__)


def _build_slack_payload(title: str, message: str) -> dict:
    text = f"{title}\n{message}"
    return {
        "text": text,
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": title,
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message,
                },
            },
        ],
    }


def send_admin_alert(*, webhook_url: str, title: str, message: str) -> bool:
    """운영 알림을 전송한다. 웹훅 미설정 또는 실패 시 False를 반환한다."""
    if not webhook_url:
        logger.info(f"운영 알림 웹훅 미설정 — 로그로만 기록: {title}")
        return False

    payload = json.dumps(_build_slack_payload(title, message), ensure_ascii=False).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=10) as response:
            if 200 <= response.status < 300:
                logger.info(f"운영 알림 전송 완료: {title}")
                return True
            logger.warning(f"운영 알림 전송 실패: status={response.status}, title={title}")
            return False
    except (error.URLError, TimeoutError, Exception) as e:
        logger.warning(f"운영 알림 전송 중 예외: {e}")
        return False
