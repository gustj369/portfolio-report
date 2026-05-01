"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

// Toss Payments 주요 실패 코드 → 사용자 안내 힌트
const CODE_HINTS: Record<string, string> = {
  PAY_PROCESS_CANCELED: "결제창을 닫으셨나요? 아래 버튼으로 다시 시도할 수 있습니다.",
  REJECT_CARD_COMPANY: "카드사에서 결제를 거절했습니다. 다른 카드로 시도해보세요.",
  EXCEED_MAX_AMOUNT: "결제 금액이 카드 한도를 초과했습니다. 다른 카드로 시도해보세요.",
  LIMIT_EXCEEDED: "카드 한도를 초과했습니다. 다른 카드로 시도해보세요.",
  CARD_PROCESSING_ERROR: "카드 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해보세요.",
  INVALID_CARD_EXPIRATION: "카드 유효기간이 올바르지 않습니다. 카드 정보를 확인해주세요.",
  INVALID_STOPPED_CARD: "사용이 정지된 카드입니다. 다른 카드로 시도해보세요.",
  BELOW_MINIMUM_AMOUNT: "최소 결제 금액 미만입니다.",
  INVALID_CARD_NUMBER: "카드 번호가 올바르지 않습니다. 카드 정보를 다시 확인해주세요.",
  NOT_SUPPORTED_CARD_TYPE: "지원하지 않는 카드 종류입니다. 다른 카드로 시도해보세요.",
  BANK_SERVER_ERROR: "은행 서버 오류입니다. 잠시 후 다시 시도해보세요.",
  ACQUIRER_SERVER_ERROR: "카드사 서버 오류입니다. 잠시 후 다시 시도해보세요.",
};

function FailContent() {
  const searchParams = useSearchParams();
  const message = searchParams.get("message") || "결제가 취소되었습니다.";
  const code = searchParams.get("code");
  const codeHint = code ? CODE_HINTS[code] : null;

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="max-w-sm w-full card text-center">
        <div className="text-5xl mb-4">😞</div>
        <h1 className="text-xl font-bold text-navy mb-2">결제 실패</h1>
        <p className="text-gray-500 text-sm mb-2">{message}</p>
        {codeHint ? (
          <p className="text-xs text-blue-600 bg-blue-50 rounded-lg px-3 py-2 mb-6">{codeHint}</p>
        ) : (
          code && <p className="text-xs text-gray-400 mb-6">오류 코드: {code}</p>
        )}

        <div className="space-y-3">
          <Link href="/payment" className="btn-gold block w-full py-3 text-center rounded-xl">
            다시 결제하기
          </Link>
          <Link href="/preview" className="block text-sm text-gray-400 hover:underline">
            미리보기로 돌아가기
          </Link>
        </div>
      </div>
    </div>
  );
}

export default function FailPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">로딩 중...</div>}>
      <FailContent />
    </Suspense>
  );
}
