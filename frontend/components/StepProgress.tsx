"use client";

interface StepProgressProps {
  currentStep: number;
  totalSteps?: number;
}

const STEP_LABELS = ["기본 정보", "포트폴리오", "확인 및 분석"];

export default function StepProgress({ currentStep, totalSteps = 3 }: StepProgressProps) {
  return (
    <div className="w-full mb-8">
      <div className="flex items-center justify-between mb-2">
        {STEP_LABELS.map((label, i) => {
          const step = i + 1;
          const isCompleted = step < currentStep;
          const isActive = step === currentStep;
          return (
            <div key={step} className="flex flex-col items-center flex-1">
              <div
                className={`w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold transition-colors
                  ${isCompleted ? "bg-gold-500 text-white" : ""}
                  ${isActive ? "bg-navy text-white ring-4 ring-gold-200" : ""}
                  ${!isCompleted && !isActive ? "bg-gray-200 text-gray-500" : ""}
                `}
              >
                {isCompleted ? "✓" : step}
              </div>
              <span
                className={`mt-1 text-xs font-medium ${
                  isActive ? "text-navy" : isCompleted ? "text-gold-500" : "text-gray-400"
                }`}
              >
                {label}
              </span>
            </div>
          );
        })}
      </div>
      {/* 진행 바 */}
      <div className="relative mt-2">
        <div className="h-1.5 bg-gray-200 rounded-full" />
        <div
          className="absolute top-0 left-0 h-1.5 bg-gold-500 rounded-full transition-all duration-500"
          style={{ width: `${((currentStep - 1) / (totalSteps - 1)) * 100}%` }}
        />
      </div>
      <p className="text-right text-xs text-gray-400 mt-1">
        {currentStep} / {totalSteps}
      </p>
    </div>
  );
}
