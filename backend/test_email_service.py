"""email_service — 사용자 입력(이름)이 메일 HTML에 그대로 삽입되지 않는지 검증"""
from email import message_from_string
from unittest.mock import patch

from services.email_service import send_report_email


def test_user_name_is_html_escaped_in_body():
    with patch("services.email_service.smtplib.SMTP") as smtp:
        ok = send_report_email(
            smtp_host="smtp.example.com", smtp_port=587, smtp_user="u", smtp_password="p",
            from_address="from@example.com", to_address="to@example.com",
            user_name='<a href="https://evil.example">클릭</a>', pdf_bytes=b"%PDF-1.4",
        )
    assert ok
    raw = smtp.return_value.__enter__.return_value.sendmail.call_args.args[2]
    html_part = next(p for p in message_from_string(raw).walk() if p.get_content_type() == "text/html")
    body = html_part.get_payload(decode=True).decode("utf-8")
    assert '<a href="https://evil.example">' not in body
    assert "&lt;a href=" in body


def test_email_quota_allows_three_per_address_per_day():
    """같은 주소(대소문자·공백 무시)는 하루 3통까지만 허용되고, 다른 주소는 별도 집계"""
    from services import storage
    from services.email_service import reserve_email_quota
    storage._local.clear()
    results = [reserve_email_quota(addr) for addr in
               ["a@example.com", " A@Example.com", "a@example.com", "a@example.com"]]
    assert results == [True, True, True, False]
    assert reserve_email_quota("b@example.com") is True
    # 저장소에는 주소 원문이 남지 않아야 한다
    assert not any("example.com" in k for k in storage._local)


def test_email_quota_denies_when_storage_unavailable():
    """한도를 확인할 수 없으면(저장소 장애) 발송하지 않는다"""
    from services.email_service import reserve_email_quota
    with patch("services.storage.storage_get", side_effect=RuntimeError("redis down")):
        assert reserve_email_quota("a@example.com") is False
