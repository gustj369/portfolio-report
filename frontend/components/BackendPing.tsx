"use client";

import { useEffect } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Render cold start 대응 — 앱 최초 마운트 시 /health 한 번 ping
 * 사용자가 폼을 작성하는 ~60초 동안 백엔드가 wake-up 완료됨
 */
export default function BackendPing() {
  useEffect(() => {
    // 같은 브라우저 세션 내 중복 ping 방지 (hard reload 반복 요청 억제)
    if (sessionStorage.getItem("backend_pinged")) return;
    sessionStorage.setItem("backend_pinged", "1");
    fetch(`${API_URL}/health`).catch((err) => {
      // 개발 모드에서는 백엔드 미연결 상황을 콘솔에 노출
      if (process.env.NODE_ENV === "development") {
        console.warn(`[BackendPing] 백엔드 연결 실패 (${API_URL}/health):`, err);
      }
    });
  }, []);

  return null;
}
