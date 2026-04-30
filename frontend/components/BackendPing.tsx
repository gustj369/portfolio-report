"use client";

import { useEffect } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Render cold start 대응 — 앱 최초 마운트 시 /health 한 번 ping
 * 사용자가 폼을 작성하는 ~60초 동안 백엔드가 wake-up 완료됨
 */
export default function BackendPing() {
  useEffect(() => {
    fetch(`${API_URL}/health`).catch(() => {});
  }, []);

  return null;
}
