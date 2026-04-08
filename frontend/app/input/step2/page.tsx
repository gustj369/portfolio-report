"use client";

import { useRouter } from "next/navigation";
import StepProgress from "@/components/StepProgress";
import PortfolioChart from "@/components/PortfolioChart";
import { useInput } from "@/context/InputContext";
import type { AssetType } from "@/types/portfolio";

const ASSET_TYPES: AssetType[] = ["해외주식", "국내주식", "채권", "현금", "대안자산", "비트코인", "금"];

const ASSET_TYPE_COLORS: Record<AssetType, string> = {
  해외주식: "bg-blue-100 text-blue-700",
  국내주식: "bg-green-100 text-green-700",
  채권: "bg-yellow-100 text-yellow-700",
  현금: "bg-gray-100 text-gray-700",
  대안자산: "bg-purple-100 text-purple-700",
  비트코인: "bg-orange-100 text-orange-700",
  금: "bg-yellow-100 text-yellow-800",
};

export default function Step2Page() {
  const router = useRouter();
  const { state, setPortfolio, addAllocation, updateAllocation, removeAllocation } = useInput();
  const { portfolio } = state;

  const totalWeight = portfolio.allocations.reduce((sum, a) => sum + a.weight, 0);
  const isWeightValid = Math.abs(totalWeight - 100) <= 1;

  const handleNext = () => {
    if (portfolio.allocations.length === 0) {
      alert("최소 1개 이상의 자산을 입력해주세요.");
      return;
    }
    if (!isWeightValid) {
      alert(`비중 합계가 100%가 되어야 합니다. (현재: ${totalWeight.toFixed(1)}%)`);
      return;
    }
    router.push("/input/step3");
  };

  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-2xl mx-auto">
        <StepProgress currentStep={2} />

        <div className="card">
          <h1 className="section-title">포트폴리오 입력</h1>
          <p className="text-gray-500 text-sm mb-6">현재 투자하고 있는 자산을 입력해주세요.</p>

          {/* 기본 정보 */}
          <div className="grid sm:grid-cols-2 gap-4 mb-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                총 투자 자산 <span className="text-red-400">*</span>
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  className="input-field"
                  min={0}
                  step={100}
                  value={portfolio.total_asset}
                  onChange={(e) => setPortfolio({ total_asset: Number(e.target.value) })}
                />
                <span className="text-gray-600 whitespace-nowrap">만원</span>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                월 추가 적립액
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  className="input-field"
                  min={0}
                  step={10}
                  value={portfolio.monthly_saving}
                  onChange={(e) => setPortfolio({ monthly_saving: Number(e.target.value) })}
                />
                <span className="text-gray-600 whitespace-nowrap">만원</span>
              </div>
            </div>
          </div>

          {/* 비중 합계 표시 */}
          <div
            className={`flex items-center justify-between p-3 rounded-xl mb-4 text-sm font-medium
              ${isWeightValid ? "bg-green-50 text-green-700" : "bg-red-50 text-red-600"}`}
          >
            <span>자산 비중 합계</span>
            <span>
              {totalWeight.toFixed(1)}% {isWeightValid ? "✓ 완성" : `(${100 - totalWeight > 0 ? "+" : ""}${(100 - totalWeight).toFixed(1)}% 남음)`}
            </span>
          </div>

          {/* 자산 목록 */}
          <div className="space-y-3 mb-4">
            {portfolio.allocations.map((alloc, i) => (
              <div key={i} className="flex gap-2 items-start p-3 bg-gray-50 rounded-xl">
                <div className="flex-1 grid sm:grid-cols-3 gap-2">
                  {/* 자산명 */}
                  <input
                    type="text"
                    className="input-field text-sm"
                    placeholder="자산명 (예: S&P500 ETF)"
                    value={alloc.asset_name}
                    onChange={(e) => updateAllocation(i, { asset_name: e.target.value })}
                  />
                  {/* 자산 유형 */}
                  <select
                    className="input-field text-sm"
                    value={alloc.asset_type}
                    onChange={(e) => updateAllocation(i, { asset_type: e.target.value as AssetType })}
                  >
                    {ASSET_TYPES.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                  {/* 비중 */}
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      className="input-field text-sm w-20"
                      min={0}
                      max={100}
                      step={1}
                      value={alloc.weight}
                      onChange={(e) => updateAllocation(i, { weight: Number(e.target.value) })}
                    />
                    <span className="text-sm text-gray-500">%</span>
                  </div>
                </div>
                <button
                  onClick={() => removeAllocation(i)}
                  disabled={portfolio.allocations.length <= 1}
                  className="text-red-400 hover:text-red-600 disabled:opacity-30 mt-2 p-1"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>

          {/* 자산 추가 버튼 */}
          {portfolio.allocations.length < 20 && (
            <button
              onClick={addAllocation}
              className="w-full py-2 border-2 border-dashed border-gray-300 text-gray-500 rounded-xl hover:border-gold-400 hover:text-gold-500 transition-colors text-sm font-medium mb-6"
            >
              + 자산 추가
            </button>
          )}

          {/* 미리보기 차트 */}
          {portfolio.allocations.length > 0 && isWeightValid && (
            <div className="flex justify-center py-4 border-t border-gray-100">
              <PortfolioChart allocations={portfolio.allocations} size={160} />
            </div>
          )}

          <div className="flex justify-between mt-6">
            <button
              onClick={() => router.push("/input/step1")}
              className="px-5 py-2 text-gray-500 hover:text-gray-700 text-sm"
            >
              ← 이전
            </button>
            <button onClick={handleNext} className="btn-gold" disabled={!isWeightValid}>
              다음 단계 →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
