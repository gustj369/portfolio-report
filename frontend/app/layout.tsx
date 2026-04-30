import type { Metadata } from "next";
import { Noto_Sans_KR } from "next/font/google";
import "./globals.css";
import { InputProvider } from "@/context/InputContext";
import BackendPing from "@/components/BackendPing";

const notoSansKR = Noto_Sans_KR({
  weight: ["400", "500", "700"],
  subsets: ["latin"],
  variable: "--font-noto-sans-kr",
  display: "swap",
});

export const metadata: Metadata = {
  title: "포트폴리오 AI 분석 리포트 | 5분 만에 받는 AI 재무 설계",
  description:
    "AI가 내 포트폴리오를 분석하고 5년 뒤 예상 자산과 맞춤 리밸런싱 전략을 담은 전문 리포트를 생성합니다. 단 4,900원.",
  openGraph: {
    title: "포트폴리오 AI 분석 리포트",
    description: "5분 만에 받는 AI 재무 설계 리포트",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" className={notoSansKR.variable}>
      <body className="font-sans bg-gray-50 text-gray-900 antialiased">
        <InputProvider>
          <BackendPing />
          {children}
        </InputProvider>
      </body>
    </html>
  );
}
