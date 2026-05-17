import type { NextConfig } from "next";

// 프로덕션 빌드 시 필수 환경변수 누락을 조기에 포착
// (NEXT_PUBLIC_ 변수는 빌드 타임에 번들에 인라인되므로 런타임에서는 수정 불가)
if (process.env.NODE_ENV === "production") {
  const missing = [
    !process.env.NEXT_PUBLIC_API_URL && "NEXT_PUBLIC_API_URL",
    !process.env.NEXT_PUBLIC_TOSS_CLIENT_KEY && "NEXT_PUBLIC_TOSS_CLIENT_KEY",
  ].filter(Boolean);

  if (missing.length > 0) {
    throw new Error(
      `[next.config] Missing required environment variables: ${missing.join(", ")}\n` +
        "Set them before building for production (see frontend/.env.local.example)."
    );
  }
}

const nextConfig: NextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
    NEXT_PUBLIC_TOSS_CLIENT_KEY: process.env.NEXT_PUBLIC_TOSS_CLIENT_KEY || "",
  },
};

export default nextConfig;
