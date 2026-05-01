"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useInput } from "@/context/InputContext";
import { requestPayment, freeConfirmPayment } from "@/lib/api";

declare global {
  interface Window {
    TossPayments: (clientKey: string) => {
      requestPayment: (method: string, options: Record<string, unknown>) => Promise<void>;
    };
  }
}

export default function PaymentPage() {
  const router = useRouter();
  const { state, setOrderId } = useInput();
  const { previewResponse, userProfile, portfolio } = state;

  const [isLoading, setIsLoading] = useState(false);
  const [orderId, setLocalOrderId] = useState<string | null>(null);
  const [amount, setAmount] = useState(4900);
  const [clientKey, setClientKey] = useState("");
  const [isFree, setIsFree] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!previewResponse) {
      router.replace("/input/step1");
      return;
    }
    // 결제 요청 초기화
    (async () => {
      try {
        const res = await requestPayment({ user_profile: userProfile, portfolio });
        setLocalOrderId(res.order_id);
        setOrderId(res.order_id);
        setAmount(res.amount);
        setIsFree(res.is_free);
        setClientKey(res.client_key || process.env.NEXT_PUBLIC_TOSS_CLIENT_KEY || "test_ck_dummy");
      } catch (e) {
        setError(e instanceof Error ? e.message : "결제 초기화 실패");
      }
    })();
  }, [previewResponse, router]);

  // 실제 Toss 키인지 확인 (live_ck_ 또는 test_ck_ 로 시작하는 실제 키)
  const isRealTossKey = clientKey.startsWith("live_ck_") || clientKey.startsWith("test_ck_D") || clientKey.startsWith("test_ck_O");

  const handlePayment = async () => {
    if (!orderId) {
      setError("결제 초기화가 완료되지 않았습니다. 잠시 후 다시 시도해주세요.");
      return;
    }

    setIsLoading(true);
    setError("");

    try {
      if (isFree) {
        // 무료 플로우: Toss 완전 우회 → /payment/free-confirm → token 발급
        const result = await freeConfirmPayment(orderId);
        router.push(
          `/payment/complete?token=${result.report_token}&orderId=${orderId}&amount=0`
        );
      } else if (isRealTossKey) {
        // 실제 Toss 키인데 SDK가 로드되지 않은 경우 → 오류 표시 (개발 모드로 우회하지 않음)
        if (typeof window.TossPayments === "undefined") {
          setError("결제 모듈을 불러오지 못했습니다. 페이지를 새로고침 후 다시 시도해주세요.");
          setIsLoading(false);
          return;
        }
        const toss = window.TossPayments(clientKey);
        await toss.requestPayment("카드", {
          amount,
          orderId,
          orderName: "포트폴리오 AI 분석 리포트",
          customerName: userProfile.name || "고객",
          customerEmail: userProfile.email || undefined,
          successUrl: `${window.location.origin}/payment/complete`,
          failUrl: `${window.location.origin}/payment/fail`,
        });
      } else {
        // 개발 모드: 토스 SDK 없이 직접 결제 완료 페이지로 이동
        console.log("개발 모드 결제 처리:", orderId);
        router.push(
          `/payment/complete?paymentKey=dev_${Date.now()}&orderId=${orderId}&amount=${amount}`
        );
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "처리 중 오류가 발생했습니다.";
      setError(isFree ? `리포트 발급에 실패했습니다. ${msg}` : `결제 처리 중 오류가 발생했습니다. ${msg}`);
      setIsLoading(false);
    }
  };

  if (!previewResponse) return null;

  return (
    <>
      <div className="min-h-screen bg-gray-50 py-8 px-4 flex items-center justify-center">
        <div className="w-full max-w-md">
          <div className="card">
            <h1 className="section-title text-center mb-6">결제</h1>

            {/* 주문 요약 */}
            <div className="bg-navy text-white rounded-xl p-5 mb-6">
              <p className="text-blue-200 text-sm mb-1">주문 내역</p>
              <p className="text-lg font-bold">포트폴리오 AI 분석 리포트</p>
              <div className="mt-3 pt-3 border-t border-blue-700 flex justify-between items-center">
                <span className="text-blue-200 text-sm">{isFree ? "무료 제공" : "결제 금액"}</span>
                <span className="text-gold-400 text-2xl font-bold">
                  {isFree ? "무료" : `${amount.toLocaleString()}원`}
                </span>
              </div>
            </div>

            {/* 포함 내용 */}
            <div className="bg-gray-50 rounded-xl p-4 mb-5 text-sm">
              <p className="font-medium text-navy mb-2">포함 내용</p>
              <ul className="space-y-1.5 text-gray-600">
                <li className="flex gap-2"><span className="text-gold-500">✓</span>5페이지 전문 PDF 리포트</li>
                <li className="flex gap-2"><span className="text-gold-500">✓</span>AI 포트폴리오 종합 진단</li>
                <li className="flex gap-2"><span className="text-gold-500">✓</span>3개 시나리오 5년 시뮬레이션</li>
                <li className="flex gap-2"><span className="text-gold-500">✓</span>맞춤 리밸런싱 추천</li>
                <li className="flex gap-2"><span className="text-gold-500">✓</span>즉시 다운로드 + 이메일 발송</li>
              </ul>
            </div>

            {/* 이메일 확인 */}
            {userProfile.email && (
              <div className="text-sm text-gray-600 mb-4 flex gap-2 items-center">
                <span>📧</span>
                <span><strong>{userProfile.email}</strong>로 리포트가 발송됩니다.</span>
              </div>
            )}

            {error && (
              <div className="mb-4 p-3 bg-red-50 text-red-600 rounded-xl text-sm">
                {error}
                {!orderId && (
                  <div className="mt-2 text-center">
                    <button
                      onClick={() => window.location.reload()}
                      className="text-xs text-red-500 hover:text-red-700 underline"
                    >
                      새로고침 후 다시 시도
                    </button>
                  </div>
                )}
              </div>
            )}

            <button
              onClick={handlePayment}
              disabled={isLoading || !orderId || clientKey === ""}
              className="w-full py-4 bg-gold-500 text-white font-bold text-lg rounded-xl hover:bg-gold-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-lg"
            >
              {isLoading ? "처리 중..." : (!orderId || clientKey === "") ? "초기화 중..." : isFree ? "무료로 받기" : `${amount.toLocaleString()}원 결제하기`}
            </button>

            <div className="text-center mt-4">
              <button
                onClick={() => router.back()}
                className="text-sm text-gray-400 hover:text-gray-600 underline"
              >
                ← 미리보기로 돌아가기
              </button>
            </div>

            <p className="text-xs text-gray-400 text-center mt-4">
              토스페이먼츠 보안 결제 · SSL 암호화
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
