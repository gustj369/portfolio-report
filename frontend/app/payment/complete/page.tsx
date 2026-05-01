"use client";

import { useSearchParams } from "next/navigation";
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
  const [isRetrying, setIsRetrying] = useState(false);
  const [errorCode, setErrorCode] = useState<"timeout" | "server" | "network" | "payment" | "expired" | "">("");
  const [downloadError, setDownloadError] = useState("");

  const handleDownload = async () => {
    if (!downloadUrl) return;
    setIsDownloading(true);
    setDownloadError(""); // 이전 오류 초기화
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
      // alert 대신 인라인 상태 메시지 — UX 흐름 유지 (페이지 이탈 없음)
      setDownloadError("다운로드에 실패했습니다. 다시 시도해주세요.");
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

    // 언마운트 후 poll 상태 업데이트 방지
    let isCancelled = false;

    (async () => {
      try {
        let token: string;

        // 새로고침 복구: sessionStorage에 토큰이 남아있으면 confirm 단계 건너뜀
        const cachedToken = sessionStorage.getItem(`rpt_${orderId}`);

        if (cachedToken) {
          token = cachedToken;
          setLocalReportToken(token);
          setReportToken(token);
          setCurrentStep(1);
          if (isCancelled) return; // 상태 설정 후 언마운트 방어
          // generateReport는 항상 호출 — 백엔드가 GENERATING/READY이면 조기 반환으로 중복 방지
          // skipGenerate 제거: 백엔드 PENDING 태스크 유실 시 재시도 없이 3분 타임아웃 되는 엣지 케이스 해소
        } else if (preConfirmedToken) {
          // 무료 플로우: 이미 confirm 완료된 토큰 사용
          setCurrentStep(0);
          token = preConfirmedToken;
          setLocalReportToken(token);
          setReportToken(token);
          sessionStorage.setItem(`rpt_${orderId}`, token);
          if (isCancelled) return; // 상태 설정 후 언마운트 방어
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
            if (isCancelled) return; // confirm 완료 전 언마운트 방어
            token = confirmResult.report_token;
            setLocalReportToken(token);
            setReportToken(token);
            sessionStorage.setItem(`rpt_${orderId}`, token);
          } catch (e) {
            if (isCancelled) return; // confirm 실패 전 언마운트 방어
            // 결제 확인 실패: HTTP 상태에 따라 errorCode 분기
            // 503(Toss 서버 연결 오류)은 재시도 안내, 그 외(만료·금액 불일치 등)는 처음부터 안내
            const httpStatus = (e as any).httpStatus;
            setPhase("error");
            setErrorCode(httpStatus === 503 ? "server" : "payment");
            setErrorMsg(e instanceof Error ? e.message : "결제 확인 중 오류가 발생했습니다.");
            return;
          }
        }

        // 2. 리포트 생성 시작
        setCurrentStep(1);
        setPhase("generating");
        // 네트워크 오류 시 2초 대기 후 1회 재시도 (토큰은 유효, 백엔드 idempotent)
        try {
          await generateReport(token).catch(async () => {
            setIsRetrying(true);
            await new Promise(r => setTimeout(r, 2000));
            setIsRetrying(false);
            await generateReport(token);
          });
        } catch (e) {
          if (isCancelled) return; // generateReport 실패 전 언마운트 방어
          // 결제는 완료됐으나 리포트 생성 API 요청 실패
          // sessionStorage 토큰을 보존해 "다시 시도"(새로고침) 시 confirm 단계 건너뜀
          setErrorCode("server");
          setPhase("error");
          setErrorMsg("리포트 발급 요청에 실패했습니다. 결제는 정상 처리됐으니 잠시 후 다시 시도해주세요.");
          return;
        }

        // 3. 상태 폴링
        let attempts = 0;
        const maxAttempts = 60; // 최대 3분

        const poll = async () => {
          if (isCancelled) return; // 언마운트 후 실행 중단
          if (attempts >= maxAttempts) {
            sessionStorage.removeItem(`rpt_${orderId}`);
            setErrorCode("timeout");
            setPhase("error");
            setErrorMsg("리포트 생성 시간이 초과되었습니다. 고객센터에 문의해주세요.");
            return;
          }
          attempts++;
          if (attempts === 10) setIsSlowWarning(true); // 약 30초 경과 시 안내 (isCancelled 가드가 상단에서 언마운트 시나리오를 방어함)

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
            // 그 외 네트워크 오류: poll은 setTimeout 콜백이므로 외부 try-catch에 걸리지 않음
            // → unhandled rejection 방지를 위해 직접 처리
            sessionStorage.removeItem(`rpt_${orderId}`);
            setErrorCode("network");
            setPhase("error");
            setErrorMsg(e instanceof Error ? e.message : "네트워크 오류가 발생했습니다.");
            return;
          }
          setReportStatus(status.status);

          if (status.status === "generating") setCurrentStep(Math.min(2 + Math.floor(attempts / 5), 4));

          if (status.status === "ready" && status.download_url) {
            // 백엔드가 상대 경로를 반환하는 경우 API_URL 접두어 추가
            const resolvedUrl = status.download_url.startsWith("/")
              ? `${API_URL}${status.download_url}`
              : status.download_url;
            sessionStorage.removeItem(`rpt_${orderId}`);
            if (isCancelled) return; // 언마운트 후 상태 업데이트 방어
            setDownloadUrl(resolvedUrl);
            setPhase("done");
            setCurrentStep(5);
          } else if (status.status === "error") {
            sessionStorage.removeItem(`rpt_${orderId}`);
            if (isCancelled) return; // 언마운트 후 상태 업데이트 방어
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

    return () => { isCancelled = true; }; // 언마운트 시 poll 루프 중단
  // setReportToken 을 deps에 추가하면 InputContext spread 업데이트로 매 렌더마다
  // 새 참조가 생성되어 effect 재실행 무한 루프 발생 → 의도적으로 제외
  // eslint-disable-next-line react-hooks/exhaustive-deps
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

          {/* 다운로드 실패 인라인 메시지 + 재시도 버튼 */}
          {downloadError && (
            <div className="mb-3">
              <p className="text-sm text-red-500 mb-2">{downloadError}</p>
              <button
                onClick={handleDownload}
                disabled={isDownloading}
                className="text-sm text-navy underline hover:no-underline disabled:opacity-50"
              >
                다시 시도
              </button>
            </div>
          )}

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
          {isRetrying ? "연결 재시도 중..." : phase === "confirming" ? "결제 확인 중..." : "리포트 생성 중..."}
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
