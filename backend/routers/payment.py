"""
토스페이먼츠 결제 처리 라우터
"""
import uuid
import base64
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import httpx

from config import get_settings, Settings
from models.portfolio import AnalyzeRequest
from services.storage import storage_set, storage_get, storage_delete

router = APIRouter(prefix="/payment", tags=["payment"])
logger = logging.getLogger(__name__)

TOSS_CONFIRM_URL = "https://api.tosspayments.com/v1/payments/confirm"

# 스토리지 키 접두사
_PENDING_PFX = "pay:pending:"
_CONFIRMED_PFX = "pay:confirmed:"
_IDEMPOTENCY_PFX = "pay:idempotency:"  # 중복 confirm 방지 (order_id → report_token)


class PaymentRequestInput(BaseModel):
    analyze_request: AnalyzeRequest


class PaymentRequestResponse(BaseModel):
    order_id: str
    amount: int
    client_key: str


class PaymentConfirmInput(BaseModel):
    payment_key: str
    order_id: str
    amount: int


class PaymentConfirmResponse(BaseModel):
    success: bool
    report_token: str
    message: str


class PaymentStatusResponse(BaseModel):
    order_id: str
    status: str  # pending / unknown (confirmed 이후엔 report_token 기준으로 관리되므로 order_id로 조회 불가)


@router.post("/request", response_model=PaymentRequestResponse)
async def request_payment(
    body: PaymentRequestInput,
    settings: Settings = Depends(get_settings),
) -> PaymentRequestResponse:
    """결제 요청 초기화 — orderId 생성 및 포트폴리오 데이터 임시 저장"""
    order_id = f"order_{uuid.uuid4().hex[:16]}"

    storage_set(
        f"{_PENDING_PFX}{order_id}",
        {
            "status": "pending",
            "amount": settings.report_price_krw,
            "analyze_request": body.analyze_request.model_dump(mode="json"),
            "created_at": datetime.now().isoformat(),
        },
        ttl=3600,  # 1시간 후 자동 만료
    )

    logger.info(f"결제 요청 생성: {order_id}")

    return PaymentRequestResponse(
        order_id=order_id,
        amount=settings.report_price_krw,
        client_key=settings.toss_client_key,
    )


@router.post("/confirm", response_model=PaymentConfirmResponse)
async def confirm_payment(
    body: PaymentConfirmInput,
    settings: Settings = Depends(get_settings),
) -> PaymentConfirmResponse:
    """토스페이먼츠 결제 승인 처리"""

    # 대기 중인 결제 확인
    pending = storage_get(f"{_PENDING_PFX}{body.order_id}")
    if not pending:
        # 이미 처리된 주문인지 확인 (네트워크 재시도·이중 요청 멱등성)
        cached = storage_get(f"{_IDEMPOTENCY_PFX}{body.order_id}")
        if cached:
            logger.info(f"중복 confirm 요청 — 캐시된 토큰 반환: {body.order_id}")
            return PaymentConfirmResponse(
                success=True,
                report_token=cached["report_token"],
                message="이미 처리된 결제입니다.",
            )
        raise HTTPException(
            status_code=404,
            detail="결제 세션이 만료되었거나 존재하지 않는 주문입니다. (결제 요청 후 1시간 이내에 완료해주세요)",
        )

    if pending["amount"] != body.amount:
        raise HTTPException(status_code=400, detail="결제 금액이 일치하지 않습니다.")

    # 토스페이먼츠 서버 결제 승인 호출
    if settings.toss_secret_key:
        try:
            auth_str = base64.b64encode(f"{settings.toss_secret_key}:".encode()).decode()
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    TOSS_CONFIRM_URL,
                    headers={
                        "Authorization": f"Basic {auth_str}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "paymentKey": body.payment_key,
                        "orderId": body.order_id,
                        "amount": body.amount,
                    },
                )
                if response.status_code != 200:
                    toss_error = response.json()
                    logger.error(f"토스페이먼츠 승인 실패: {toss_error}")
                    raise HTTPException(
                        status_code=400,
                        detail=f"결제 승인 실패: {toss_error.get('message', '알 수 없는 오류')}",
                    )
        except httpx.RequestError as e:
            logger.error(f"토스페이먼츠 API 연결 오류: {e}")
            raise HTTPException(status_code=503, detail="결제 서버 연결 오류")
    else:
        # 개발 모드: 토스 키 없으면 승인 통과
        logger.warning(f"토스 시크릿 키 없음 — 개발 모드로 결제 승인: {body.order_id}")

    # 결제 확인 완료 처리
    report_token = f"rpt_{uuid.uuid4().hex}"
    storage_delete(f"{_PENDING_PFX}{body.order_id}")
    storage_set(
        f"{_CONFIRMED_PFX}{report_token}",
        {
            "order_id": body.order_id,
            "payment_key": body.payment_key,
            "amount": body.amount,
            "analyze_request": pending["analyze_request"],
            "confirmed_at": datetime.now().isoformat(),
        },
        ttl=86400 * 7,  # 7일 보관
    )
    # 멱등성 키 저장 — 7일 동안 동일 order_id로 재요청 시 같은 토큰 반환
    storage_set(
        f"{_IDEMPOTENCY_PFX}{body.order_id}",
        {"report_token": report_token},
        ttl=86400 * 7,
    )

    logger.info(f"결제 승인 완료: {body.order_id} → {report_token}")

    return PaymentConfirmResponse(
        success=True,
        report_token=report_token,
        message="결제가 완료되었습니다.",
    )


@router.get("/status/{order_id}", response_model=PaymentStatusResponse)
async def get_payment_status(order_id: str) -> PaymentStatusResponse:
    """결제 상태 조회"""
    if storage_get(f"{_PENDING_PFX}{order_id}"):
        return PaymentStatusResponse(order_id=order_id, status="pending")

    # confirmed 상태는 report_token 기준으로 저장되므로 order_id로 역조회 불가
    # pending이 없으면 만료·미존재·승인완료 중 구분할 수 없어 unknown 반환
    return PaymentStatusResponse(order_id=order_id, status="unknown")


def get_confirmed_payment(report_token: str) -> dict | None:
    """report_token으로 승인된 결제 조회 (내부 서비스 함수)"""
    return storage_get(f"{_CONFIRMED_PFX}{report_token}")
