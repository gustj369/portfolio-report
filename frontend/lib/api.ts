import type {
  AnalyzeRequest,
  PreviewResponse,
  ReportStatusResponse,
} from "@/types/portfolio";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    const err = new Error(error.detail || `API 오류: ${res.status}`);
    (err as any).httpStatus = res.status;
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

export async function requestPayment(analyzeRequest: AnalyzeRequest): Promise<{
  order_id: string;
  amount: number;
  client_key: string;
  is_free: boolean;
}> {
  return apiFetch("/payment/request", {
    method: "POST",
    body: JSON.stringify({ analyze_request: analyzeRequest }),
  });
}

export async function confirmPayment(params: {
  payment_key: string;
  order_id: string;
  amount: number;
}): Promise<{
  success: boolean;
  report_token: string;
  message: string;
}> {
  return apiFetch("/payment/confirm", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function freeConfirmPayment(orderId: string): Promise<{
  success: boolean;
  report_token: string;
  message: string;
}> {
  return apiFetch("/payment/free-confirm", {
    method: "POST",
    body: JSON.stringify({ order_id: orderId }),
  });
}

export async function generateReport(reportToken: string): Promise<{
  report_token: string;
  status: string;
  message: string;
}> {
  return apiFetch("/report/generate", {
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
