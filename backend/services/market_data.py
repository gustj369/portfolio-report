"""
시장 데이터 수집 모듈
Yahoo Finance + FRED API 기반
"""
import yfinance as yf
import requests
from datetime import datetime, timedelta
from typing import Optional
import logging

from models.portfolio import Allocation, AssetType
from models.report import MarketSnapshot

logger = logging.getLogger(__name__)

# 자산유형별 기본 연평균 수익률 (역사적 평균)
BASE_RETURNS = {
    AssetType.FOREIGN_STOCK: 0.08,
    AssetType.DOMESTIC_STOCK: 0.06,
    AssetType.BOND: 0.04,
    AssetType.CASH: 0.035,
    AssetType.ALTERNATIVE: 0.05,
    AssetType.BITCOIN: 0.30,   # 연 30% (역사적 평균, 변동성 매우 높음)
    AssetType.GOLD: 0.07,      # 연 7% (인플레이션 헤지)
}

# 자산유형별 기본 변동성 (연간 표준편차)
BASE_VOLATILITY = {
    AssetType.FOREIGN_STOCK: 0.18,
    AssetType.DOMESTIC_STOCK: 0.20,
    AssetType.BOND: 0.07,
    AssetType.CASH: 0.01,
    AssetType.ALTERNATIVE: 0.15,
    AssetType.BITCOIN: 0.80,   # 변동성 80% (암호화폐 특성)
    AssetType.GOLD: 0.15,      # 변동성 15%
}

# 주요 시장 지수 티커
MARKET_TICKERS = {
    "sp500": "^GSPC",
    "kospi": "^KS11",
    "gold": "GC=F",
    "usd_krw": "KRW=X",
}

# FRED API 시리즈 ID
FRED_SERIES = {
    "us_10y_yield": "DGS10",
    "cpi_us": "CPIAUCSL",
}

# 한국 기준금리 (FRED에 없을 경우 기본값)
KR_BASE_RATE_DEFAULT = 3.5


def fetch_market_snapshot(fred_api_key: str = "") -> MarketSnapshot:
    """현재 시장 데이터 스냅샷 수집"""
    data = {
        "sp500": 5000.0,
        "kospi": 2500.0,
        "us_10y_yield": 4.3,
        "kr_base_rate": 3.5,
        "usd_krw": 1350.0,
        "gold_price": 2300.0,
        "cpi_us": 3.2,
    }

    # Yahoo Finance에서 시장 지수 수집
    for key, ticker in MARKET_TICKERS.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
                if key == "sp500":
                    # S&P 500: 합리적 범위 체크 (1000~10000)
                    if 1000 <= price <= 10000:
                        data["sp500"] = price
                elif key == "kospi":
                    # KOSPI: 합리적 범위 체크 (1000~5000)
                    if 1000 <= price <= 5000:
                        data["kospi"] = price
                elif key == "gold":
                    data["gold_price"] = price
                elif key == "usd_krw":
                    # 환율: 합리적 범위 체크 (800~2000)
                    if 800 <= price <= 2000:
                        data["usd_krw"] = price
        except Exception as e:
            logger.warning(f"시장 데이터 수집 실패 ({ticker}): {e}")

    # FRED API에서 금리/CPI 수집
    if fred_api_key:
        for key, series_id in FRED_SERIES.items():
            try:
                url = f"https://api.stlouisfed.org/fred/series/observations"
                params = {
                    "series_id": series_id,
                    "api_key": fred_api_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": 1,
                }
                resp = requests.get(url, params=params, timeout=10)
                if resp.status_code == 200:
                    obs = resp.json().get("observations", [])
                    if obs and obs[0]["value"] != ".":
                        data[key] = float(obs[0]["value"])
            except Exception as e:
                logger.warning(f"FRED 데이터 수집 실패 ({series_id}): {e}")

    return MarketSnapshot(
        sp500=data["sp500"],
        kospi=data["kospi"],
        us_10y_yield=data["us_10y_yield"],
        kr_base_rate=data["kr_base_rate"],
        usd_krw=data["usd_krw"],
        gold_price=data["gold_price"],
        cpi_us=data["cpi_us"],
        fetched_at=datetime.now(),
    )


def get_asset_return(
    allocation: Allocation,
    market_snapshot: MarketSnapshot,
) -> tuple[float, float]:
    """
    자산의 예상 연수익률과 변동성 반환 (연율화)
    ticker가 있으면 과거 데이터 기반, 없으면 자산유형 기본값 사용
    Returns: (annual_return, annual_volatility)
    """
    base_return = BASE_RETURNS.get(allocation.asset_type, 0.05)
    base_vol = BASE_VOLATILITY.get(allocation.asset_type, 0.15)

    # 현재 시장 상황 반영 조정
    adjusted_return = _adjust_return_for_market(base_return, allocation.asset_type, market_snapshot)

    # ticker가 있으면 과거 5년 실제 수익률 참고
    if allocation.ticker:
        try:
            hist_return, hist_vol = _fetch_historical_stats(allocation.ticker)
            # 역사적 수익률과 기본값 50:50 블렌딩
            adjusted_return = (adjusted_return + hist_return) / 2
            base_vol = (base_vol + hist_vol) / 2
        except Exception as e:
            logger.warning(f"티커 {allocation.ticker} 과거 데이터 조회 실패: {e}")

    return adjusted_return, base_vol


def _adjust_return_for_market(
    base_return: float,
    asset_type: AssetType,
    market: MarketSnapshot,
) -> float:
    """시장 상황에 따른 수익률 조정"""
    adjusted = base_return

    # 고금리 환경 (US 10Y > 4.5%): 채권/현금 상향, 주식 소폭 하향
    if market.us_10y_yield > 4.5:
        if asset_type in (AssetType.BOND, AssetType.CASH):
            adjusted += 0.01
        elif asset_type in (AssetType.FOREIGN_STOCK, AssetType.DOMESTIC_STOCK):
            adjusted -= 0.005

    # 현금 수익률 = 한국 기준금리 연동
    if asset_type == AssetType.CASH:
        adjusted = market.kr_base_rate / 100

    # 인플레이션 조정 (실질 수익률)
    inflation_rate = market.cpi_us / 100
    if asset_type in (AssetType.BOND, AssetType.CASH):
        adjusted = max(adjusted - inflation_rate * 0.3, 0.01)

    return adjusted


def _fetch_historical_stats(ticker: str) -> tuple[float, float]:
    """티커의 과거 5년 연평균 수익률과 변동성 계산"""
    t = yf.Ticker(ticker)
    end = datetime.now()
    start = end - timedelta(days=365 * 5)
    hist = t.history(start=start, end=end, interval="1mo")

    if hist.empty or len(hist) < 12:
        raise ValueError(f"데이터 부족: {ticker}")

    monthly_returns = hist["Close"].pct_change().dropna()
    annual_return = float((1 + monthly_returns.mean()) ** 12 - 1)
    annual_vol = float(monthly_returns.std() * (12 ** 0.5))

    return annual_return, annual_vol


def get_weighted_return_and_vol(
    allocations: list[Allocation],
    market_snapshot: MarketSnapshot,
) -> tuple[float, float]:
    """
    포트폴리오 가중평균 수익률과 변동성 계산
    Returns: (weighted_return, weighted_vol)
    """
    weighted_return = 0.0
    weighted_vol_sq = 0.0

    for alloc in allocations:
        weight = alloc.weight / 100
        ret, vol = get_asset_return(alloc, market_snapshot)
        weighted_return += weight * ret
        weighted_vol_sq += (weight * vol) ** 2  # 단순화 (상관관계 무시)

    return weighted_return, weighted_vol_sq ** 0.5
