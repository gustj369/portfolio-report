"""
Rate limiter 인스턴스 — 순환 import 방지를 위해 main.py에서 분리.

main.py 와 routers/analyze.py 양쪽에서 동일 인스턴스를 참조한다.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# IP 기반 rate limiter (slowapi)
# key_func: 클라이언트 IP를 식별 함수로 사용
limiter = Limiter(key_func=get_remote_address)

# 무료 리포트 발급 경로(결제 요청·무료 확인·PDF 생성) 공통 제한 — AI·PDF 생성과 메일 발송 남용 방지
REPORT_ISSUE_LIMIT = "3/minute;20/day"
