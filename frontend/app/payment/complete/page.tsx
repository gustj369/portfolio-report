"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, Suspense } from "react";
import Link from "next/link";
import { useInput } from "@/context/InputContext";
import { confirmPayment, generateReport, getReportStatus } from "@/lib/api";
import type { ReportStatus } from "@/types/portfolio";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const STATUS_MESSAGES: Record<string, string> = {
  pending: "리포트 생성 준비 중...",
  generating: "AI 분석 및 PDF 생성 중...",
  ready: "리포트 준비 완료!",
  error: "오류가 발생했습니다",
};

const STATUS_STEPS = [
  "결제 확인",
  "시장 데이터 수집",
  "AI 분석 실행",
  "차트 생성",
  "PDF 빌드",
];

function CompletePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { state, setReportToken } = useInput();

  const [phase, setPhase] = useState<"confirming" | "generating" | "done" | "error">("confirming");
  const [reportToken, setLocalReportToken] = useState<string | null>(null);
  const [reportStatus, setReportStatus] = useState<ReportStatus>("pending");
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [currentStep, setCurrentStep] = useState(0);
  const [isDownloading, setIsDownloading] = useState(false);
  const [isSlowWarning, setIsSlowWarning] = useState(false);
  const [errorCode, setErrorCode] = useState<"timeout" | "server" | "network" | "payment" | "expired" | "">("");

  const handleDownload = async () => {
    if (!downloadUrl) return;
    setIsDownloading(true);
    try {
      const res = await fetch(downloadUrl);
      if (!res.ok) throw new Error("다운로드 실패");
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = "portfolio_report.pdf";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    } catch (e) {
      alert("다운로드에 실패했습니다. 다시 시도해주세요.");
    } finally {
      setIsDownloading(false);
    }
  };

  useEffect(() => {
    const paymentKey = searchParams.get("paymentKey");
    const orderId = searchParams.get("orderId");
    const amount = searchParams.get("amount");
    const preConfirmedToken = searchParams.get("token"); // 미리 확인된 토큰 (무료 플로우)

    if (!orderId || !amount) {
      setPhase("error");
      setErrorMsg("결제 정보가 올바르지 않습니다.");
      return;
    }

    (async () => {
      try {
        let token: string;
        let skipGenerate = false; // 새로고침 복구 시 generateReport 중복 호출 방지

        // 새로고침 복구: sessionStorage에 토큰이 남아있으면 confirm 단계 건너뜀
        const cachedToken = sessionStorage.getItem(`rpt_${orderId}`);

        if (cachedToken) {
          token = cachedToken;
          setLocalReportToken(token);
          setReportToken(token);
          setCurrentStep(1);
          skipGenerate = true; // 이전 세션에서 이미 generateReport 호출됨
        } else if (preConfirmedToken) {
          // 무료 플로우: 이미 confirm 완료된 토큰 사용
          setCurrentStep(0);
          token = preConfirmedToken;
          setLocalReportToken(token);
          setReportToken(token);
          sessionStorage.setItem(`rpt_${orderId}`, token);
        } else {
          // 유료 플로우: Toss 결제 승인
          if (!paymentKey) {
            setPhase("error");
            setErrorMsg("결제 정보가 올바르지 않습니다.");
            return;
          }
          setCurrentStep(0);
          try {
            const confirmResult = await confirmPayment({
              payment_key: paymentKey,
              order_id: orderId,
              amount: Number(amount),
            });
            token = confirmResult.report_token;
            setLocalReportToken(token);
            setReportToken(token);
            sessionStorage.setItem(`rpt_${orderId}`, token);
          } catch (e) {
            // 결제 확인 실패는 네트워크 오류와 구분 (만료·금액 불일치 등)
            setErrorCode("payment");
            setPhase("error");
            setErrorMsg(e instanceof Error ? e.message : "결제 확인 중 오류가 발생했습니다.");
            return;
          }
        }

        // 2. 리포트 생성 시작
        setCurrentStep(1);
        setPhase("generating");
        if (!skipGenerate) {
          await generateReport(token);
        }

        // 3. 상태 폴링
        let attempts = 0;
        const maxAttempts = 60; // 최대 3분

        const poll = async () => {
          if (attempts >= maxAttempts) {
            sessionStorage.removeItem(`rpt_${orderId}`);
            setErrorCode("timeout");
            setPhase("error");
            setErrorMsg("리포트 생성 시간이 초과되었습니다. 고객센터에 문의해주세요.");
            return;
          }
          attempts++;
          if (attempts === 20) setIsSlowWarning(true); // 약 60초 경과 시 안내

          let status;
          try {
            status = await getReportStatus(token);
          } catch (e) {
            // 404: 리포트 레코드 없음 → 토큰 만료(7일) 또는 잘못된 토큰
            if (e instanceof Error && (e as any).httpStatus === 404) {
              sessionStorage.removeItem(`rpt_${orderId}`);
              setErrorCode("expired");
              setPhase("error");
              setErrorMsg("리포트가 만료되었습니다. (리포트는 7일간 보관됩니다)");
              return;
            }
            throw e; // 그 외 네트워크 오류는 외부 catch로 전달
          }
          setReportStatus(status.status);

          if (status.status === "generating") setCurrentStep(Math.min(2 + Math.floor(attempts / 5), 4));

          if (status.status === "ready" && status.download_url) {
            // 백엔드가 상대 경로를 반환하는 경우 API_URL 접두어 추가
            const resolvedUrl = status.download_url.startsWith("/")
              ? `${API_URL}${status.download_url}`
              : status.download_url;
            setDownloadUrl(resolvedUrl);
            setPhase("done");
            setCurrentStep(5);
            sessionStorage.removeItem(`rpt_${orderId}`);
          } else if (status.status === "error") {
            sessionStorage.removeItem(`rpt_${orderId}`);
            setErrorCode("server");
            setPhase("error");
            setErrorMsg(status.error_message || "리포트 생성 중 오류가 발생했습니다.");
          } else {
            setTimeout(poll, 3000);
          }
        };

        setTimeout(poll, 2000);
      } catch (e) {
        sessionStorage.removeItem(`rpt_${orderId}`);
        setErrorCode("network");
        setPhase("error");
        setErrorMsg(e instanceof Error ? e.message : "처리 중 오류가 발생했습니다.");
      }
    })();
  }, [searchParams]);

  if (phase === "done" && downloadUrl) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4 py-8">
        <div className="max-w-md w-full card text-center">
          <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <span className="text-4xl">✅</span>
          </div>
          <h1 className="text-2xl font-bold text-navy mb-2">리포트가 준비되었습니다!</h1>
          <p className="text-gray-500 text-sm mb-6">AI 분석 리포트를 확인해보세요.</p>

          {/* 다운로드 버튼 */}
          <button
            onClick={handleDownload}
            disabled={isDownloading}
            className="block w-full py-4 bg-gold-500 text-white font-bold text-lg rounded-xl hover:bg-gold-600 transition-colors shadow-lg mb-3 disabled:opacity-50"
          >
            {isDownloading ? "다운로드 중..." : "📥 PDF 다운로드"}
          </button>

          {state.userProfile.email && (
            <div className="text-sm text-gray-500 mb-6">
              📧 <strong>{state.userProfile.email}</strong>으로 발송을 시도했습니다.
              <span className="block text-xs text-gray-400 mt-0.5">(이메일 미수신 시 PDF 다운로드를 이용해주세요)</span>
            </div>
          )}

          <div className="border-t border-gray-100 pt-4 space-y-2">
            <Link
              href="/input/step1"
              className="block text-sm text-navy hover:underline"
            >
              다른 포트폴리오로 다시 분석하기 →
            </Link>
            <Link href="/" className="block text-sm text-gray-400 hover:underline">
              홈으로 돌아가기
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (phase === "error") {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4 py-8">
        <div className="max-w-md w-full card text-center">
          <div className="text-5xl mb-4">❌</div>
          <h1 className="text-xl font-bold text-navy mb-2">오류가 발생했습니다</h1>
          <p className="text-gray-500 text-sm mb-4">{errorMsg}</p>
          {errorCode === "timeout" && (
            <p className="text-xs text-gray-400 mb-4">
              재시도 후에도 같은 문제가 반복되면 고객센터에 문의해주세요.
            </p>
          )}
          {errorCode === "server" && (
            <p className="text-xs text-gray-400 mb-4">
              잠시 후 다시 시도해주세요. 문제가 지속되면 고객센터에 문의해주세요.
            </p>
          )}
          {errorCode === "network" && (
            <p className="text-xs text-gray-400 mb-4">
              인터넷 연결을 확인하고 다시 시도해주세요.
            </p>
          )}
          {errorCode === "payment" && (
            <p className="text-xs text-gray-400 mb-4">
              결제 세션이 만료된 경우 처음부터 다시 진행해주세요.
            </p>
          )}
          {errorCode === "expired" && (
            <p className="text-xs text-gray-400 mb-4">
              리포트는 결제 후 7일간 보관됩니다. 기간이 지난 경우 새로 신청해주세요.
            </p>
          )}
          {errorCode === "payment" || errorCode === "expired" ? (
            <Link
              href="/input/step1"
              className="btn-gold block w-full py-3 text-center rounded-xl mb-3"
            >
              처음부터 시작하기
            </Link>
          ) : (
            <button
              onClick={() => window.location.reload()}
              className="btn-gold mb-3 w-full"
            >
              다시 시도
            </button>
          )}
          <Link href="/" className="block text-sm text-gray-400 hover:underline">
            홈으로 돌아가기
          </Link>
        </div>
      </div>
    );
  }

  // 로딩 (결제 확인 / 생성 중)
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4 py-8">
      <div className="max-w-md w-full card text-center">
        <div className="flex justify-center mb-6">
          <div className="w-16 h-16 border-4 border-gold-400 border-t-transparent rounded-full animate-spin" />
        </div>
        <h1 className="text-xl font-bold text-navy mb-2">
          {phase === "confirming" ? "결제 확인 중..." : "리포트 생성 중..."}
        </h1>
        <p className="text-gray-500 text-sm mb-6">
          {STATUS_MESSAGES[reportStatus] || "처리 중입니다..."}
        </p>

        {/* 단계 표시 */}
        <div className="text-left space-y-2">
          {STATUS_STEPS.map((step, i) => (
            <div
              key={i}
              className={`flex items-center gap-3 text-sm ${
                i < currentStep
                  ? "text-green-600 font-medium"
                  : i === currentStep
                  ? "text-navy font-semibold"
                  : "text-gray-400"
              }`}
            >
              <span className="w-5 text-center">
                {i < currentStep ? "✓" : i === currentStep ? "⟳" : "○"}
              </span>
              {step}
            </div>
          ))}
        </div>

        {isSlowWarning ? (
          <p className="text-xs text-amber-500 mt-6">
            AI 분석에 시간이 더 걸리고 있습니다 (최대 3분)
          </p>
        ) : (
          <p className="text-xs text-gray-400 mt-6">약 30초~1분 소요됩니다</p>
        )}
      </div>
    </div>
  );
}

export default function CompletePage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">로딩 중...</div>}>
      <CompletePageContent />
    </Suspense>
  );
}
