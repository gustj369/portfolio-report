"""
결제 스토리지 조회 계층
라우터 간 직접 import 없이 결제 확인 데이터를 공유하기 위한 서비스 함수.
payment.py 라우터와 report.py 라우터 양쪽에서 사용한다.
"""
from services.storage import storage_get

# payment.py 의 _commit_payment 가 저장하는 키와 반드시 일치해야 함
_CONFIRMED_PFX = "pay:confirmed:"


def get_confirmed_payment(report_token: str) -> dict | None:
    """report_token 으로 승인 완료된 결제 데이터 조회. 없거나 만료되면 None 반환."""
    return storage_get(f"{_CONFIRMED_PFX}{report_token}")
