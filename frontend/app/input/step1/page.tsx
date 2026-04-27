"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import StepProgress from "@/components/StepProgress";
import { useInput } from "@/context/InputContext";
import type { InvestmentGoal, RiskTolerance } from "@/types/portfolio";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const GOALS: { value: InvestmentGoal; label: string; emoji: string }[] = [
  { value: "노후준비", label: "노후 준비", emoji: "🏖️" },
  { value: "주택구입", label: "주택 구입", emoji: "🏠" },
  { value: "자산증식", label: "자산 증식", emoji: "📈" },
  { value: "기타", label: "기타", emoji: "💡" },
];

const RISK_LEVELS: { value: RiskTolerance; label: string; desc: string; color: string }[] = [
  { value: "안정형", label: "안정형", desc: "원금 보존 중시, 낮은 변동성 선호", color: "blue" },
  { value: "중립형", label: "중립형", desc: "적정 수익과 리스크 균형 추구", color: "yellow" },
  { value: "공격형", label: "공격형", desc: "높은 수익 추구, 변동성 감수", color: "red" },
];

export default function Step1Page() {
  const router = useRouter();
  const { state, setUserProfile } = useInput();
  const { userProfile } = state;

  // Render cold start 대응: 폼 작성 중(~60초) 백엔드가 wake-up 완료되도록 fire-and-forget ping
  useEffect(() => {
    fetch(`${API_URL}/health`).catch(() => {});
  }, []);

  const handleNext = () => {
    if (!userProfile.age || !userProfile.monthly_income) {
      alert("나이와 월 소득을 입력해주세요.");
      return;
    }
    router.push("/input/step2");
  };

  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-lg mx-auto">
        <StepProgress currentStep={1} />

        <div className="card">
          <h1 className="section-title">기본 정보 입력</h1>
          <p className="text-gray-500 text-sm mb-6">맞춤 분석을 위해 기본 정보를 입력해주세요.</p>

          <div className="space-y-5">
            {/* 이름 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                이름 <span className="text-gray-400">(선택)</span>
              </label>
              <input
                type="text"
                className="input-field"
                placeholder="홍길동"
                value={userProfile.name || ""}
                onChange={(e) => setUserProfile({ name: e.target.value })}
              />
            </div>

            {/* 나이 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                나이 <span className="text-red-400">*</span>
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  className="input-field w-28"
                  min={18}
                  max={80}
                  value={userProfile.age}
                  onChange={(e) => setUserProfile({ age: Number(e.target.value) })}
                />
                <span className="text-gray-600">세</span>
              </div>
            </div>

            {/* 월 소득 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                월 소득 <span className="text-red-400">*</span>
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  className="input-field w-36"
                  min={0}
                  step={10}
                  value={userProfile.monthly_income}
                  onChange={(e) => setUserProfile({ monthly_income: Number(e.target.value) })}
                />
                <span className="text-gray-600">만원</span>
              </div>
            </div>

            {/* 투자 목표 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">투자 목표</label>
              <div className="grid grid-cols-2 gap-2">
                {GOALS.map((g) => (
                  <button
                    key={g.value}
                    onClick={() => setUserProfile({ investment_goal: g.value })}
                    className={`flex items-center gap-2 px-4 py-3 rounded-xl border-2 text-sm font-medium transition-all
                      ${
                        userProfile.investment_goal === g.value
                          ? "border-gold-500 bg-gold-50 text-navy"
                          : "border-gray-200 hover:border-gray-300 text-gray-600"
                      }`}
                  >
                    <span>{g.emoji}</span> {g.label}
                  </button>
                ))}
              </div>
            </div>

            {/* 투자 기간 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                목표 투자 기간
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min={1}
                  max={30}
                  value={userProfile.investment_period}
                  onChange={(e) => setUserProfile({ investment_period: Number(e.target.value) })}
                  className="flex-1 accent-yellow-500"
                />
                <span className="text-navy font-bold w-16 text-right">
                  {userProfile.investment_period}년
                </span>
              </div>
            </div>

            {/* 리스크 성향 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">리스크 성향</label>
              <div className="space-y-2">
                {RISK_LEVELS.map((r) => (
                  <button
                    key={r.value}
                    onClick={() => setUserProfile({ risk_tolerance: r.value })}
                    className={`w-full flex items-center justify-between px-4 py-3 rounded-xl border-2 text-sm transition-all
                      ${
                        userProfile.risk_tolerance === r.value
                          ? "border-gold-500 bg-gold-50"
                          : "border-gray-200 hover:border-gray-300"
                      }`}
                  >
                    <span className="font-medium text-navy">{r.label}</span>
                    <span className="text-gray-500 text-xs">{r.desc}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="flex justify-between mt-8">
            <button
              onClick={() => router.push("/")}
              className="px-5 py-2 text-gray-500 hover:text-gray-700 text-sm"
            >
              ← 처음으로
            </button>
            <button onClick={handleNext} className="btn-gold">
              다음 단계 →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
