"""
운영 알림 서비스 — Slack Incoming Webhook 등 JSON {"text": "..."} 수신 URL 호환
ADMIN_ALERT_WEBHOOK_URL 미설정 시 no-op.
"""
import logging
import requests

logger = logging.getLogger(__name__)


def send_alert(webhook_url: str, message: str) -> None:
    """
    webhook_url 로 {"text": message} 를 POST 전송한다.
    실패해도 예외를 전파하지 않으며, 결과는 로그로만 기록한다.
    """
    if not webhook_url:
        return
    try:
        resp = requests.post(
            webhook_url,
            json={"text": message},
            timeout=5,
        )
        if not resp.ok:
            logger.warning(f"알림 전송 실패 (HTTP {resp.status_code}): {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"알림 전송 예외 (무시): {e}")
