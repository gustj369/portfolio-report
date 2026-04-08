"""
이메일 발송 서비스 — smtplib 기반 (외부 패키지 불필요)
PDF 리포트 완성 후 사용자 이메일로 첨부 발송
"""
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

logger = logging.getLogger(__name__)


def send_report_email(
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    from_address: str,
    to_address: str,
    user_name: str,
    pdf_bytes: bytes,
) -> bool:
    """
    PDF 리포트를 이메일로 발송합니다.
    Returns True on success, False on failure (exceptions are caught internally).
    """
    if not to_address or "@" not in to_address:
        logger.warning(f"유효하지 않은 이메일 주소: {to_address!r}")
        return False

    display_name = user_name.strip() if user_name.strip() else "고객"

    msg = MIMEMultipart()
    msg["Subject"] = f"[자산 배분 AI 리포트] {display_name}님의 포트폴리오 분석 결과"
    msg["From"] = from_address
    msg["To"] = to_address

    body_html = f"""
<html>
<body style="font-family: Arial, sans-serif; color: #1a1a2e; background: #f8f8f8; padding: 20px;">
  <div style="max-width: 560px; margin: 0 auto; background: white; border-radius: 12px; padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
    <h2 style="color: #1a1a2e; margin-bottom: 4px;">📊 AI 포트폴리오 분석 리포트</h2>
    <p style="color: #888; font-size: 13px; margin-top: 0;">자산 배분 AI 리포트 생성기</p>
    <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
    <p style="font-size: 15px;">안녕하세요, <strong>{display_name}</strong>님.</p>
    <p style="font-size: 14px; color: #444; line-height: 1.6;">
      요청하신 <strong>포트폴리오 AI 분석 리포트</strong>가 완성되었습니다.<br>
      첨부된 PDF 파일을 열어 자세한 분석 내용을 확인해보세요.
    </p>
    <div style="background: #fffbea; border-left: 4px solid #f5a623; padding: 12px 16px; border-radius: 4px; margin: 20px 0; font-size: 13px; color: #555;">
      💡 리포트에는 5년 시뮬레이션, 리밸런싱 제안, 시장 코멘터리가 포함되어 있습니다.
    </div>
    <p style="font-size: 12px; color: #aaa; margin-top: 24px;">
      본 리포트는 투자 권유가 아닌 정보 제공 목적으로만 활용해주세요.<br>
      투자 결정은 본인의 판단과 책임하에 이루어져야 합니다.
    </p>
  </div>
</body>
</html>
"""
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
    attachment.add_header(
        "Content-Disposition",
        "attachment",
        filename=f"portfolio_report_{display_name}.pdf",
    )
    msg.attach(attachment)

    try:
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
                server.login(smtp_user, smtp_password)
                server.sendmail(from_address, to_address, msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_user, smtp_password)
                server.sendmail(from_address, to_address, msg.as_string())

        logger.info(f"리포트 이메일 발송 성공: {to_address}")
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(f"SMTP 인증 실패 (user={smtp_user})")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP 오류: {e}")
        return False
    except Exception as e:
        logger.error(f"이메일 발송 중 예외: {e}")
        return False
