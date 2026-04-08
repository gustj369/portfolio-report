"use client";

import Link from "next/link";
import { useSearchParams, Suspense } from "react";

function FailContent() {
  const searchParams = useSearchParams();
  const message = searchParams.get("message") || "결제가 취소되었습니다.";
  const code = searchParams.get("code");

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="max-w-sm w-full card text-center">
        <div className="text-5xl mb-4">😞</div>
        <h1 className="text-xl font-bold text-navy mb-2">결제 실패</h1>
        <p className="text-gray-500 text-sm mb-2">{message}</p>
        {code && <p className="text-xs text-gray-400 mb-6">오류 코드: {code}</p>}

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
