"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Script from "next/script";
import { useInput } from "@/context/InputContext";
import { requestPayment, freeConfirmPayment } from "@/lib/api";

const TOSS_SDK_URL = "https://js.tosspayments.com/v1/payment";

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
  const [tossReady, setTossReady] = useState(false);
  const [isRetryingToss, setIsRetryingToss] = useState(false);
  const [tossRetryCount, setTossRetryCount] = useState(0);

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

  const getTossLoadError = (failedCount: number) => {
    if (typeof navigator !== "undefined" && !navigator.onLine) {
      return "현재 오프라인 상태로 보입니다. 인터넷 연결을 확인한 뒤 결제 모듈을 다시 불러와주세요.";
    }
    if (failedCount >= 2) {
      return "결제 모듈을 여러 번 불러오지 못했습니다. 광고 차단/보안 확장 프로그램을 잠시 끄거나 다른 네트워크에서 다시 시도해주세요. 문제가 계속되면 Toss CDN 접속이 차단되었을 수 있습니다.";
    }
    return "결제 모듈을 불러오지 못했습니다. 아래 버튼으로 다시 불러온 뒤 결제를 시도해주세요.";
  };

  useEffect(() => {
    if (!isRealTossKey || tossReady) return;

    const timeout = window.setTimeout(() => {
      setTossReady(true);
    }, 8000);

    return () => window.clearTimeout(timeout);
  }, [isRealTossKey, tossReady]);

  const reloadTossSdk = () => {
    if (typeof window.TossPayments !== "undefined") {
      setTossReady(true);
      setError("");
      setTossRetryCount(0);
      return;
    }

    setIsRetryingToss(true);
    setTossReady(false);
    setError("결제 모듈을 다시 불러오는 중입니다.");
    document.querySelectorAll("script[data-toss-sdk-retry='true']").forEach((script) => script.remove());

    const script = document.createElement("script");
    script.src = TOSS_SDK_URL;
    script.async = true;
    script.dataset.tossSdkRetry = "true";
    script.onload = () => {
      setIsRetryingToss(false);
      setTossReady(true);
      setError("");
      setTossRetryCount(0);
    };
    script.onerror = () => {
      const nextRetryCount = tossRetryCount + 1;
      setIsRetryingToss(false);
      setTossReady(true);
      setTossRetryCount(nextRetryCount);
      setError(getTossLoadError(nextRetryCount));
    };
    document.body.appendChild(script);
  };

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
          setError("결제 모듈을 불러오지 못했습니다. 아래 버튼으로 다시 불러온 뒤 결제를 시도해주세요.");
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

  const canRetryPage = !orderId || tossRetryCount > 0;
  const tossTroubleshootingItems =
    typeof navigator !== "undefined" && !navigator.onLine
      ? ["인터넷 연결이 온라인 상태인지 확인", "연결 복구 후 결제 모듈 다시 불러오기"]
      : tossRetryCount >= 2
      ? ["광고 차단 또는 보안 확장 프로그램 잠시 끄기", "회사/학교/공용 네트워크의 CDN 차단 여부 확인", "다른 브라우저나 다른 네트워크에서 다시 시도"]
      : ["잠시 후 결제 모듈 다시 불러오기", "계속 실패하면 네트워크 상태 확인"];

  return (
    <>
      <Script
        src={TOSS_SDK_URL}
        strategy="lazyOnload"
        onLoad={() => setTossReady(true)}
        onError={() => {
          const nextRetryCount = tossRetryCount + 1;
          setTossReady(true);
          setTossRetryCount(nextRetryCount);
          setError(getTossLoadError(nextRetryCount));
        }}
      />
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
                {canRetryPage && (
                  <div className="mt-3 space-y-2">
                    <div className="rounded-lg bg-white/70 p-2 text-xs text-red-700">
                      <p className="font-semibold mb-1">확인할 항목</p>
                      <ul className="space-y-1 text-left">
                        {tossTroubleshootingItems.map((item) => (
                          <li key={item} className="flex gap-1.5">
                            <span aria-hidden="true">-</span>
                            <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                    <button
                      onClick={reloadTossSdk}
                      disabled={isRetryingToss}
                      className="block w-full text-center text-xs text-red-500 hover:text-red-700 underline disabled:opacity-60"
                    >
                      {isRetryingToss ? "결제 모듈 불러오는 중..." : "결제 모듈 다시 불러오기"}
                    </button>
                  </div>
                )}
              </div>
            )}

            <button
              onClick={handlePayment}
              disabled={isLoading || !orderId || clientKey === "" || (isRealTossKey && !tossReady)}
              className="w-full py-4 bg-gold-500 text-white font-bold text-lg rounded-xl hover:bg-gold-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-lg"
            >
              {isLoading ? "처리 중..." : (!orderId || clientKey === "" || (isRealTossKey && !tossReady)) ? "초기화 중..." : isFree ? "무료로 받기" : `${amount.toLocaleString()}원 결제하기`}
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
