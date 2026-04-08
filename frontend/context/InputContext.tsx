"use client";

import React, { createContext, useContext, useState, ReactNode } from "react";
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

export function InputProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<InputState>(DEFAULT_STATE);

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

  const reset = () => setState(DEFAULT_STATE);

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
