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

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    const err = new Error(error.detail || `API 오류: ${res.status}`) as ApiError;
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
