"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Link from "next/link";
import BlurSection from "@/components/BlurSection";
import PortfolioChart from "@/components/PortfolioChart";
import { useInput } from "@/context/InputContext";
import { requestPayment, confirmPayment } from "@/lib/api";

const RISK_GRADE_COLORS: Record<string, string> = {
  안정형: "bg-green-500",
  중립형: "bg-yellow-500",
  공격형: "bg-red-500",
};

export default function PreviewPage() {
  const router = useRouter();
  const { state, setOrderId } = useInput();
  const { previewResponse, portfolio, userProfile } = state;
  const [isGenerating, setIsGenerating] = useState(false);
  const [genError, setGenError] = useState("");

  useEffect(() => {
    if (!previewResponse) {
      router.replace("/input/step1");
    }
  }, [previewResponse, router]);

  if (!previewResponse) return null;

  const { risk_score, risk_grade, base_scenario_final, base_scenario_cagr, portfolio_summary } =
    previewResponse;
  const badgeColor = RISK_GRADE_COLORS[risk_grade] || "bg-gray-500";

  const handleGetReport = async () => {
    setIsGenerating(true);
    setGenError("");
    try {
      // 1. 주문 생성
      const payRes = await requestPayment({ user_profile: userProfile, portfolio });
      setOrderId(payRes.order_id);

      // 2. 자동 결제 승인 (무료 — 개발 모드)
      const confirmRes = await confirmPayment({
        payment_key: `dev_${Date.now()}`,
        order_id: payRes.order_id,
        amount: payRes.amount,
      });

      // 3. 리포트 생성 페이지로 이동
      router.push(
        `/payment/complete?paymentKey=dev_${Date.now()}&orderId=${payRes.order_id}&amount=${payRes.amount}&token=${confirmRes.report_token}`
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      if (msg.includes("fetch") || msg.includes("network") || msg.includes("connect")) {
        setGenError("백엔드 서버에 연결할 수 없습니다. 터미널에서 'python -m uvicorn main:app --reload' 를 먼저 실행해주세요.");
      } else {
        setGenError(msg || "오류가 발생했습니다. 다시 시도해주세요.");
      }
      setIsGenerating(false);
    }
  };

  const handleShare = () => {
    const text = `AI가 분석한 내 포트폴리오 리스크 등급: ${risk_grade} | 5년 뒤 기본 예상: ${base_scenario_final.toLocaleString()}만원`;
    if (navigator.share) {
      navigator.share({ title: "포트폴리오 AI 분석", text, url: window.location.href });
    } else {
      navigator.clipboard.writeText(text + "\n" + window.location.origin);
      alert("링크와 결과가 클립보드에 복사되었습니다!");
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-2xl mx-auto space-y-4">
        {/* 헤더 */}
        <div className="text-center">
          <h1 className="text-2xl font-bold text-navy mb-1">AI 분석 완료</h1>
          <p className="text-gray-500 text-sm">
            {userProfile.name ? `${userProfile.name}님의 ` : ""}포트폴리오 분석 결과입니다.
          </p>
        </div>

        {/* 리스크 등급 카드 */}
        <div className="card flex items-center gap-6">
          <div className={`w-20 h-20 rounded-2xl ${badgeColor} flex flex-col items-center justify-center`}>
            <span className="text-white text-xs">리스크</span>
            <span className="text-white font-bold text-lg">{risk_grade}</span>
          </div>
          <div>
            <p className="text-sm text-gray-500">리스크 점수</p>
            <p className="text-4xl font-bold text-navy">{risk_score}<span className="text-lg text-gray-400">/100</span></p>
            <div className="mt-2 w-48 bg-gray-200 rounded-full h-2">
              <div
                className={`h-2 rounded-full ${
                  risk_score <= 30 ? "bg-green-400" : risk_score <= 65 ? "bg-yellow-400" : "bg-red-400"
                }`}
                style={{ width: `${risk_score}%` }}
              />
            </div>
          </div>
        </div>

        {/* 포트폴리오 파이차트 */}
        <div className="card flex justify-center">
          <PortfolioChart allocations={portfolio.allocations} size={200} />
        </div>

        {/* 5년 후 기본 시나리오 (공개) */}
        <div className="card bg-navy text-white text-center">
          <p className="text-blue-200 text-sm mb-1">기본 시나리오 — 5년 후 예상 자산</p>
          <p className="text-5xl font-bold text-gold-400 mb-2">
            {base_scenario_final.toLocaleString()}
            <span className="text-2xl">만원</span>
          </p>
          <p className="text-blue-200 text-sm">연평균 수익률(CAGR) 예상: {base_scenario_cagr.toFixed(1)}%</p>
        </div>

        {/* AI 요약 미리보기 */}
        <div className="card">
          <h3 className="text-sm font-bold text-navy mb-2">AI 분석 요약</h3>
          <p className="text-gray-700 text-sm leading-relaxed">{portfolio_summary}</p>
        </div>

        {/* 블러 처리 — 비관/낙관 시나리오 */}
        <BlurSection label="비관/낙관 시나리오 + 리밸런싱 추천">
          <div className="card">
            <h3 className="font-bold text-navy mb-3">3개 시나리오 비교</h3>
            <div className="grid grid-cols-3 gap-3">
              {["비관", "기본", "낙관"].map((s) => (
                <div key={s} className="text-center p-3 bg-gray-50 rounded-xl">
                  <p className="text-xs text-gray-500">{s}</p>
                  <p className="text-xl font-bold text-navy mt-1">8,XXX만원</p>
                </div>
              ))}
            </div>
          </div>
        </BlurSection>

        {/* 블러 처리 — 리밸런싱 */}
        <BlurSection label="맞춤 리밸런싱 전략">
          <div className="card">
            <h3 className="font-bold text-navy mb-3">추천 포트폴리오</h3>
            <div className="space-y-2">
              {portfolio.allocations.slice(0, 3).map((a, i) => (
                <div key={i} className="flex justify-between items-center text-sm">
                  <span>{a.asset_name}</span>
                  <span className="text-gold-500">→ XX%</span>
                </div>
              ))}
            </div>
          </div>
        </BlurSection>

        {/* CTA */}
        <div className="card bg-gradient-to-br from-navy to-blue-900 text-white text-center py-8">
          <p className="text-blue-200 text-sm mb-2">전체 리포트에 포함된 내용</p>
          <ul className="text-sm text-blue-100 mb-5 space-y-1">
            <li>✓ 비관·기본·낙관 시나리오 상세 분석</li>
            <li>✓ 맞춤 리밸런싱 추천 (자산별 이유 포함)</li>
            <li>✓ 현재 시장 환경 분석 코멘트</li>
            <li>✓ 5페이지 전문 PDF 즉시 다운로드</li>
          </ul>
          {genError && (
            <div className="mb-4 px-4 py-3 bg-red-900/50 text-red-200 rounded-xl text-sm text-left">
              {genError}
            </div>
          )}
          <button
            onClick={handleGetReport}
            disabled={isGenerating}
            className="w-full px-8 py-4 bg-gold-500 text-white font-bold text-lg rounded-xl hover:bg-gold-600 transition-colors shadow-lg disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isGenerating ? "PDF 생성 중..." : "📥 전체 PDF 리포트 받기 (무료)"}
          </button>
          <p className="text-xs text-blue-300 mt-3">클릭 즉시 PDF 생성 시작 · 약 20~30초 소요</p>
        </div>

        {/* 공유하기 */}
        <div className="text-center">
          <button
            onClick={handleShare}
            className="text-sm text-gray-500 hover:text-navy underline"
          >
            📤 미리보기 결과 공유하기
          </button>
        </div>

        {/* 다시 분석 */}
        <div className="text-center pb-8">
          <Link href="/input/step1" className="text-sm text-gray-400 hover:text-gray-600 underline">
            다른 포트폴리오로 다시 분석하기
          </Link>
        </div>
      </div>
    </div>
  );
}
