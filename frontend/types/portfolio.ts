export type InvestmentGoal = "노후준비" | "주택구입" | "자산증식" | "기타";
export type RiskTolerance = "안정형" | "중립형" | "공격형";
export type AssetType = "국내주식" | "해외주식" | "채권" | "단기채권" | "현금" | "대안자산" | "비트코인" | "암호화폐" | "금";

export interface UserProfile {
  age: number;
  monthly_income: number;
  investment_goal: InvestmentGoal;
  investment_period: number;
  risk_tolerance: RiskTolerance;
  name?: string;
  email?: string;
}

export interface Allocation {
  asset_name: string;
  asset_type: AssetType;
  weight: number; // 0~100
  ticker?: string;
  amount?: number;
}

export interface Portfolio {
  total_asset: number;
  monthly_saving: number;
  allocations: Allocation[];
}

export interface AnalyzeRequest {
  user_profile: UserProfile;
  portfolio: Portfolio;
}

export interface ScenarioResult {
  name: string;
  monthly_values: number[];
  final_value: number;
  total_return_pct: number;
  cagr: number;
  max_drawdown: number;
}

export interface SimulationResult {
  bear: ScenarioResult;
  base: ScenarioResult;
  bull: ScenarioResult;
  initial_value: number;
  monthly_contribution: number;
}

export interface MarketSnapshot {
  sp500: number;
  kospi: number;
  us_10y_yield: number;
  kr_base_rate: number;
  usd_krw: number;
  gold_price: number;
  cpi_us: number;
  fetched_at: string;
}

export interface PreviewResponse {
  risk_score: number;
  risk_grade: string;
  base_scenario_final: number;
  base_scenario_cagr: number;
  portfolio_summary: string;
  simulation: SimulationResult;
  market_data: MarketSnapshot;
}

export type ReportStatus = "pending" | "generating" | "ready" | "error";

export interface ReportStatusResponse {
  report_token: string;
  status: ReportStatus;
  download_url?: string;
  error_message?: string;
}
