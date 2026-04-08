"use client";

import { useRouter } from "next/navigation";

interface BlurSectionProps {
  children: React.ReactNode;
  label?: string;
}

export default function BlurSection({
  children,
  label = "전체 리포트에서 확인 가능",
}: BlurSectionProps) {
  const router = useRouter();

  return (
    <div className="relative overflow-hidden rounded-xl">
      {/* 흐린 콘텐츠 */}
      <div className="blur-sm select-none pointer-events-none opacity-60">
        {children}
      </div>

      {/* 오버레이 */}
      <div className="absolute inset-0 flex flex-col items-center justify-center bg-white/60 backdrop-blur-[2px] rounded-xl">
        <div className="text-center px-4">
          <div className="w-10 h-10 bg-navy rounded-full flex items-center justify-center mx-auto mb-3">
            <svg
              className="w-5 h-5 text-gold-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
              />
            </svg>
          </div>
          <p className="text-sm font-semibold text-navy mb-1">{label}</p>
          <p className="text-xs text-gray-500 mb-3">전체 리포트를 구매하면 확인할 수 있습니다</p>
          <button
            onClick={() => router.push("/payment")}
            className="px-5 py-2 bg-gold-500 text-white text-sm font-bold rounded-lg hover:bg-gold-600 transition-colors shadow-sm"
          >
            전체 리포트 받기 — 4,900원
          </button>
        </div>
      </div>
    </div>
  );
}
