import type {
  AnalyzeRequest,
  ApiError,
  GenerateReportResponse,
  PaymentConfirmParams,
  PaymentConfirmResponse,
  PaymentRequestResponse,
  PreviewResponse,
  ReportStatusResponse,
} from "@/types/portfolio";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// 개발 모드에서 환경변수 미설정 시 경고 — 프로덕션은 next.config.ts 빌드 가드가 차단
if (process.env.NODE_ENV === "development" && !process.env.NEXT_PUBLIC_API_URL) {
  console.warn(
    "[api] NEXT_PUBLIC_API_URL is not set. Falling back to http://localhost:8000.\n" +
      "Create frontend/.env.local and set NEXT_PUBLIC_API_URL to suppress this warning."
  );
}

/** 오류 응답의 detail을 문구로 변환 — 422 검증 오류는 문자열이 아닌 [{loc, msg}] 목록으로 옴 */
function formatErrorDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => String((d as { msg?: unknown })?.msg ?? "").replace(/^Value error, /, ""))
      .filter(Boolean);
    return msgs.length ? `입력값을 확인해주세요: ${msgs.join(" / ")}` : null;
  }
  return null;
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    // rate limit(429) 응답은 detail 필드가 없어 사용자용 문구로 대체
    const message =
      res.status === 429
        ? "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."
        : formatErrorDetail(error.detail) || `API 오류: ${res.status}`;
    const err = new Error(message) as ApiError;
    err.httpStatus = res.status;
    throw err;
  }

  return res.json();
}

export async function analyzePortfolio(req: AnalyzeRequest): Promise<PreviewResponse> {
  return apiFetch<PreviewResponse>("/analyze", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function requestPayment(analyzeRequest: AnalyzeRequest): Promise<PaymentRequestResponse> {
  return apiFetch<PaymentRequestResponse>("/payment/request", {
    method: "POST",
    body: JSON.stringify({ analyze_request: analyzeRequest }),
  });
}

export async function confirmPayment(params: PaymentConfirmParams): Promise<PaymentConfirmResponse> {
  return apiFetch<PaymentConfirmResponse>("/payment/confirm", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function freeConfirmPayment(orderId: string): Promise<PaymentConfirmResponse> {
  return apiFetch<PaymentConfirmResponse>("/payment/free-confirm", {
    method: "POST",
    body: JSON.stringify({ order_id: orderId }),
  });
}

export async function generateReport(reportToken: string): Promise<GenerateReportResponse> {
  return apiFetch<GenerateReportResponse>("/report/generate", {
    method: "POST",
    body: JSON.stringify({ report_token: reportToken }),
  });
}

export async function getReportStatus(reportToken: string): Promise<ReportStatusResponse> {
  return apiFetch<ReportStatusResponse>(`/report/status/${reportToken}`);
}

export function getDownloadUrl(reportToken: string): string {
  return `${API_URL}/report/download/${reportToken}`;
}

/**
 * 백엔드 download_url을 절대 URL로 변환.
 * - "http"로 시작하면 그대로 반환 (S3 presigned URL 등 외부 절대 URL)
 * - 상대 경로면 API_URL을 접두어로 추가 (R2 프록시 "/report/download/…", 로컬 "/report/file/…")
 */
export function resolveDownloadUrl(downloadUrl: string): string {
  return downloadUrl.startsWith("http") ? downloadUrl : `${API_URL}${downloadUrl}`;
}

/**
 * API 호출 실패를 사용자에게 보여줄 문구로 변환.
 * 연결 자체가 실패한 경우(브라우저별 "Failed to fetch" 등) 운영 환경에서는 Render 슬립 복귀 안내,
 * 개발 환경에서는 로컬 백엔드 실행 안내를 보여준다.
 */
export function describeApiError(e: unknown, fallback: string): string {
  const msg = e instanceof Error ? e.message : "";
  // fetch 연결 실패는 모든 브라우저에서 TypeError (Safari 문구는 "Load failed")
  if (e instanceof TypeError || msg.includes("fetch") || msg.includes("network") || msg.includes("connect")) {
    return process.env.NODE_ENV === "development"
      ? "백엔드 서버에 연결할 수 없습니다. 터미널에서 'python -m uvicorn main:app --reload' 를 먼저 실행해주세요."
      : "서버에 연결하지 못했습니다. 서버가 대기 상태에서 깨어나는 중일 수 있으니 30초쯤 뒤 다시 시도해주세요.";
  }
  return msg || fallback;
}
