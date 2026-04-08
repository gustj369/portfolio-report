"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import StepProgress from "@/components/StepProgress";
import PortfolioChart from "@/components/PortfolioChart";
import { useInput } from "@/context/InputContext";
import { analyzePortfolio } from "@/lib/api";

const LOADING_MESSAGES = [
  "시장 데이터 수집 중...",
  "AI 분석 엔진 가동 중...",
  "포트폴리오 평가 중...",
  "리스크 점수 계산 중...",
  "시뮬레이션 실행 중...",
  "리포트 초안 작성 중...",
];

export default function Step3Page() {
  const router = useRouter();
  const { state, setPreviewResponse, setUserProfile } = useInput();
  const { userProfile, portfolio } = state;
  const [isLoading, setIsLoading] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState(LOADING_MESSAGES[0]);
  const [error, setError] = useState("");

  const handleAnalyze = async () => {
    setIsLoading(true);
    setError("");

    // 로딩 메시지 순환
    let msgIdx = 0;
    const interval = setInterval(() => {
      msgIdx = (msgIdx + 1) % LOADING_MESSAGES.length;
      setLoadingMsg(LOADING_MESSAGES[msgIdx]);
    }, 2500);

    try {
      const result = await analyzePortfolio({ user_profile: userProfile, portfolio });
      setPreviewResponse(result);
      router.push("/preview");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      if (msg.includes("fetch") || msg.includes("network") || msg.includes("connect")) {
        setError("백엔드 서버에 연결할 수 없습니다. 터미널에서 'python -m uvicorn main:app --reload' 를 먼저 실행해주세요.");
      } else {
        setError(msg || "분석 중 오류가 발생했습니다. 다시 시도해주세요.");
      }
    } finally {
      clearInterval(interval);
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-lg mx-auto">
        <StepProgress currentStep={3} />

        {isLoading ? (
          <div className="card text-center py-12">
            <div className="flex justify-center mb-6">
              <div className="w-16 h-16 border-4 border-gold-400 border-t-transparent rounded-full animate-spin" />
            </div>
            <h2 className="text-xl font-bold text-navy mb-2">AI 분석 중</h2>
            <p className="text-gray-500 text-sm mb-4">{loadingMsg}</p>
            <p className="text-xs text-gray-400">약 15~20초 소요됩니다</p>

            <div className="mt-6 space-y-1 text-left text-xs text-gray-400">
              {LOADING_MESSAGES.map((msg, i) => (
                <div
                  key={i}
                  className={`flex items-center gap-2 transition-colors ${
                    LOADING_MESSAGES.indexOf(loadingMsg) >= i ? "text-navy font-medium" : ""
                  }`}
                >
                  <span>{LOADING_MESSAGES.indexOf(loadingMsg) >= i ? "✓" : "○"}</span>
                  {msg}
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="card">
            <h1 className="section-title">입력 내용 확인</h1>
            <p className="text-gray-500 text-sm mb-6">아래 내용으로 AI 분석을 시작합니다.</p>

            {/* 기본 정보 요약 */}
            <div className="bg-gray-50 rounded-xl p-4 mb-4">
              <h3 className="text-sm font-bold text-navy mb-3">👤 기본 정보</h3>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-gray-500">나이</span>
                  <span className="ml-2 font-medium text-gray-800">{userProfile.age}세</span>
                </div>
                <div>
                  <span className="text-gray-500">월 소득</span>
                  <span className="ml-2 font-medium text-gray-800">{userProfile.monthly_income.toLocaleString()}만원</span>
                </div>
                <div>
                  <span className="text-gray-500">투자 목표</span>
                  <span className="ml-2 font-medium text-gray-800">{userProfile.investment_goal}</span>
                </div>
                <div>
                  <span className="text-gray-500">리스크 성향</span>
                  <span className="ml-2 font-medium text-gray-800">{userProfile.risk_tolerance}</span>
                </div>
              </div>
            </div>

            {/* 포트폴리오 요약 */}
            <div className="bg-gray-50 rounded-xl p-4 mb-4">
              <h3 className="text-sm font-bold text-navy mb-3">💼 포트폴리오</h3>
              <div className="grid grid-cols-2 gap-2 text-sm mb-3">
                <div>
                  <span className="text-gray-500">총 자산</span>
                  <span className="ml-2 font-medium text-gray-800">{portfolio.total_asset.toLocaleString()}만원</span>
                </div>
                <div>
                  <span className="text-gray-500">월 적립액</span>
                  <span className="ml-2 font-medium text-gray-800">{portfolio.monthly_saving.toLocaleString()}만원</span>
                </div>
              </div>
              <div className="space-y-1.5">
                {portfolio.allocations.map((a, i) => (
                  <div key={i} className="flex items-center justify-between">
                    <span className="text-gray-700 text-sm">{a.asset_name || a.asset_type}</span>
                    <div className="flex items-center gap-3">
                      <div className="w-24 bg-gray-200 rounded-full h-1.5">
                        <div
                          className="h-1.5 rounded-full bg-gold-500"
                          style={{ width: `${a.weight}%` }}
                        />
                      </div>
                      <span className="text-sm font-medium text-navy w-10 text-right">{a.weight}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* 미리보기 차트 */}
            <div className="flex justify-center py-2 mb-4">
              <PortfolioChart allocations={portfolio.allocations} size={150} />
            </div>

            {/* 이메일 입력 */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                이메일 <span className="text-gray-400">(선택 — 리포트 발송용)</span>
              </label>
              <input
                type="email"
                className="input-field"
                placeholder="example@email.com"
                value={userProfile.email || ""}
                onChange={(e) => setUserProfile({ email: e.target.value })}
              />
            </div>

            {error && (
              <div className="mb-4 p-3 bg-red-50 text-red-600 rounded-xl text-sm">{error}</div>
            )}

            <div className="flex justify-between mt-6">
              <button
                onClick={() => router.push("/input/step2")}
                className="px-5 py-2 text-gray-500 hover:text-gray-700 text-sm"
              >
                ← 수정하기
              </button>
              <button onClick={handleAnalyze} className="btn-gold text-base px-8 py-3">
                🔍 AI 분석 시작
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
