"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";
import type { UserProfile, Portfolio, PreviewResponse, Allocation, AssetType } from "@/types/portfolio";

interface InputState {
  userProfile: UserProfile;
  portfolio: Portfolio;
  previewResponse: PreviewResponse | null;
  orderId: string | null;
  reportToken: string | null;
}

interface InputContextType {
  state: InputState;
  setUserProfile: (profile: Partial<UserProfile>) => void;
  setPortfolio: (portfolio: Partial<Portfolio>) => void;
  setPreviewResponse: (response: PreviewResponse) => void;
  setOrderId: (id: string) => void;
  setReportToken: (token: string) => void;
  addAllocation: () => void;
  updateAllocation: (index: number, update: Partial<Allocation>) => void;
  removeAllocation: (index: number) => void;
  reset: () => void;
}

const DEFAULT_STATE: InputState = {
  userProfile: {
    age: 30,
    monthly_income: 400,
    investment_goal: "자산증식",
    investment_period: 5,
    risk_tolerance: "중립형",
    name: "",
    email: "",
  },
  portfolio: {
    total_asset: 1000,
    monthly_saving: 50,
    allocations: [
      { asset_name: "S&P500 ETF", asset_type: "해외주식" as AssetType, weight: 50 },
      { asset_name: "국내 주식", asset_type: "국내주식" as AssetType, weight: 30 },
      { asset_name: "예금/채권", asset_type: "채권" as AssetType, weight: 20 },
    ],
  },
  previewResponse: null,
  orderId: null,
  reportToken: null,
};

const InputContext = createContext<InputContextType | null>(null);

// 새로고침 복구용 sessionStorage 키 (previewResponse·orderId·reportToken은 제외 — 세션 파생 데이터)
const _STORAGE_KEY = "ptf_input";

/** sessionStorage에서 userProfile·portfolio를 읽어 반환. SSR/파싱 오류 시 null. */
function _loadFromStorage(): { userProfile: UserProfile; portfolio: Portfolio } | null {
  if (typeof window === "undefined") return null; // SSR 안전 처리
  try {
    const raw = sessionStorage.getItem(_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as { userProfile: UserProfile; portfolio: Portfolio };
  } catch {
    return null; // JSON 파싱 오류 or sessionStorage 사용 불가 (private mode 등)
  }
}

export function InputProvider({ children }: { children: ReactNode }) {
  // 새로고침 복구: sessionStorage에 저장된 값이 있으면 복원 (없으면 DEFAULT_STATE)
  const [state, setState] = useState<InputState>(() => {
    const saved = _loadFromStorage();
    if (!saved) return DEFAULT_STATE;
    return { ...DEFAULT_STATE, userProfile: saved.userProfile, portfolio: saved.portfolio };
  });

  // userProfile·portfolio 변경 시 sessionStorage에 자동 저장 (새로고침 복구)
  useEffect(() => {
    try {
      sessionStorage.setItem(_STORAGE_KEY, JSON.stringify({
        userProfile: state.userProfile,
        portfolio: state.portfolio,
      }));
    } catch {
      // sessionStorage 사용 불가 시 (private mode, storage full 등) 조용히 무시
    }
  }, [state.userProfile, state.portfolio]);

  const setUserProfile = (profile: Partial<UserProfile>) => {
    setState((prev) => ({
      ...prev,
      userProfile: { ...prev.userProfile, ...profile },
    }));
  };

  const setPortfolio = (portfolio: Partial<Portfolio>) => {
    setState((prev) => ({
      ...prev,
      portfolio: { ...prev.portfolio, ...portfolio },
    }));
  };

  const setPreviewResponse = (response: PreviewResponse) => {
    setState((prev) => ({ ...prev, previewResponse: response }));
  };

  const setOrderId = (id: string) => {
    setState((prev) => ({ ...prev, orderId: id }));
  };

  const setReportToken = (token: string) => {
    setState((prev) => ({ ...prev, reportToken: token }));
  };

  const addAllocation = () => {
    const defaultTypes: AssetType[] = ["해외주식", "국내주식", "채권", "현금", "대안자산"];
    const usedTypes = state.portfolio.allocations.map((a) => a.asset_type);
    const nextType = defaultTypes.find((t) => !usedTypes.includes(t)) || "현금";
    setState((prev) => ({
      ...prev,
      portfolio: {
        ...prev.portfolio,
        allocations: [
          ...prev.portfolio.allocations,
          { asset_name: "", asset_type: nextType, weight: 0 },
        ],
      },
    }));
  };

  const updateAllocation = (index: number, update: Partial<Allocation>) => {
    setState((prev) => {
      const allocations = [...prev.portfolio.allocations];
      allocations[index] = { ...allocations[index], ...update };
      return { ...prev, portfolio: { ...prev.portfolio, allocations } };
    });
  };

  const removeAllocation = (index: number) => {
    setState((prev) => ({
      ...prev,
      portfolio: {
        ...prev.portfolio,
        allocations: prev.portfolio.allocations.filter((_, i) => i !== index),
      },
    }));
  };

  const reset = () => {
    try { sessionStorage.removeItem(_STORAGE_KEY); } catch {}
    setState(DEFAULT_STATE);
  };

  return (
    <InputContext.Provider
      value={{
        state,
        setUserProfile,
        setPortfolio,
        setPreviewResponse,
        setOrderId,
        setReportToken,
        addAllocation,
        updateAllocation,
        removeAllocation,
        reset,
      }}
    >
      {children}
    </InputContext.Provider>
  );
}

export function useInput(): InputContextType {
  const ctx = useContext(InputContext);
  if (!ctx) throw new Error("useInput must be used within InputProvider");
  return ctx;
}
