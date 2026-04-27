"""
시장 데이터 수집 모듈
Yahoo Finance + FRED API 기반
"""
import yfinance as yf
import requests
from datetime import datetime, timedelta, timezone

# PDF에 표시되는 데이터 기준일은 KST(UTC+9)로 고정
KST = timezone(timedelta(hours=9))
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
    AssetType.SHORT_BOND: 0.04,  # 단기채권: T-bill/MMF 수준 (현재 금리 반영)
    AssetType.CASH: 0.025,
    AssetType.ALTERNATIVE: 0.05,
    AssetType.BITCOIN: 0.30,     # 연 30% (역사적 평균, 변동성 매우 높음)
    AssetType.CRYPTO: 0.25,      # ETH/SOL/XRP 등: BTC보다 약간 낮은 기대수익
    AssetType.GOLD: 0.07,        # 연 7% (인플레이션 헤지)
}

# 자산유형별 기본 변동성 (연간 표준편차)
BASE_VOLATILITY = {
    AssetType.FOREIGN_STOCK: 0.18,
    AssetType.DOMESTIC_STOCK: 0.20,
    AssetType.BOND: 0.07,
    AssetType.SHORT_BOND: 0.02,  # 단기채권: 매우 낮은 변동성
    AssetType.CASH: 0.01,
    AssetType.ALTERNATIVE: 0.15,
    AssetType.BITCOIN: 0.80,     # 변동성 80% (암호화폐 특성)
    AssetType.CRYPTO: 0.70,      # ETH/SOL/XRP: 비트코인보다 약간 낮은 변동성
    AssetType.GOLD: 0.15,        # 변동성 15%
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
            hist = t.history(period="1mo")
            if not hist.empty:
                close_data = hist["Close"].dropna()
                if close_data.empty:
                    continue
                price = float(close_data.iloc[-1])
                if key == "sp500":
                    # S&P 500: 합리적 범위 체크 (1000~10000)
                    if 1000 <= price <= 10000:
                        data["sp500"] = price
                elif key == "kospi":
                    # KOSPI: 합리적 범위 체크 (1000~5000)
                    if 1000 <= price <= 5000:
                        data["kospi"] = price
                    else:
                        # fast_info fallback
                        try:
                            fp = float(t.fast_info.last_price or 0)
                            if 1000 <= fp <= 5000:
                                data["kospi"] = fp
                        except Exception:
                            pass
                elif key == "gold":
                    data["gold_price"] = price
                elif key == "usd_krw":
                    # 환율: 합리적 범위 체크 (800~2000)
                    if 800 <= price <= 2000:
                        data["usd_krw"] = price
        except Exception as e:
            logger.warning(f"시장 데이터 수집 실패 ({ticker}): {e}")

    # KOSPI 다중 fallback (history가 비어있거나 환경 문제로 실패 시)
    if data["kospi"] == 2500.0:
        # fallback 1: fast_info
        try:
            t = yf.Ticker("^KS11")
            fp = float(t.fast_info.last_price or 0)
            if 1000 <= fp <= 5000:
                data["kospi"] = fp
        except Exception as e:
            logger.warning(f"KOSPI fast_info fallback 실패: {e}")

    if data["kospi"] == 2500.0:
        # fallback 2: yf.download (다른 내부 엔드포인트 사용)
        try:
            dl = yf.download("^KS11", period="5d", interval="1d", progress=False, auto_adjust=True)
            if not dl.empty:
                close = dl["Close"].dropna()
                if not close.empty:
                    fp = float(close.iloc[-1])
                    if 1000 <= fp <= 5000:
                        data["kospi"] = fp
        except Exception as e:
            logger.warning(f"KOSPI yf.download fallback 실패: {e}")

    if data["kospi"] == 2500.0:
        # fallback 3: Ticker.info regularMarketPrice
        try:
            info = yf.Ticker("^KS11").info
            fp = float(info.get("regularMarketPrice") or info.get("currentPrice") or 0)
            if 1000 <= fp <= 5000:
                data["kospi"] = fp
        except Exception as e:
            logger.warning(f"KOSPI info fallback 실패: {e}")

    if data["kospi"] == 2500.0:
        # fallback 4: Naver Finance (Yahoo Finance와 완전히 독립된 국내 소스 — 가장 안정적)
        # API 키 불필요 — 네이버 금융 모바일 앱이 사용하는 공개 JSON 엔드포인트
        try:
            resp = requests.get(
                "https://m.stock.naver.com/api/index/KOSPI/price",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://m.stock.naver.com/",
                },
                timeout=10,
            )
            if resp.ok:
                price_data = resp.json()
                # closePrice는 "2,547.42" 형식 (콤마 제거 필요)
                raw = (
                    price_data.get("closePrice")
                    or price_data.get("currentPrice")
                    or price_data.get("nv")
                    or "0"
                )
                fp = float(str(raw).replace(",", ""))
                if 1000 <= fp <= 5000:
                    data["kospi"] = fp
                    logger.info(f"KOSPI Naver Finance fallback 성공: {fp}")
                elif fp == 0:
                    # 필드명 불일치 진단 — Render 로그에서 실제 키 확인 가능
                    logger.warning(f"KOSPI Naver Finance 필드명 불일치 — 응답 키: {list(price_data.keys())[:8]}")
        except Exception as e:
            logger.warning(f"KOSPI Naver Finance fallback 실패: {e}")

    if data["kospi"] == 2500.0:
        # fallback 5: stooq.com CSV (Yahoo Finance·Naver와 완전히 독립적인 유럽 데이터 소스)
        try:
            resp = requests.get(
                "https://stooq.com/q/l/?s=%5eks11&f=sd2t2ohlcv&h&e=csv",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            if resp.ok and resp.text:
                lines = resp.text.strip().split("\n")
                if len(lines) >= 2:
                    cols = [c.strip() for c in lines[0].split(",")]
                    vals = [v.strip() for v in lines[1].split(",")]
                    close_idx = cols.index("Close") if "Close" in cols else 4
                    date_idx = cols.index("Date") if "Date" in cols else 1
                    # 열 수 부족 방어: 빈 행 or 컬럼 누락 시 IndexError 방지
                    if len(vals) <= max(close_idx, date_idx):
                        logger.warning("KOSPI stooq 열 수 부족 — 건너뜀")
                    elif vals[close_idx] in ("N/A", "-", "", "null"):
                        logger.warning("KOSPI stooq N/A 수신 — 건너뜀")
                    else:
                        fp = float(vals[close_idx])
                        raw_date = vals[date_idx]
                        if raw_date in ("N/A", "-", "", "null"):
                            logger.warning("KOSPI stooq 날짜 N/A — 건너뜀")
                        else:
                            stooq_date_str = raw_date
                            # 날짜 검증: 주말 포함 최대 5일 이내 데이터만 사용
                            stooq_date = datetime.strptime(stooq_date_str, "%Y-%m-%d").date()
                            days_old = (datetime.now(KST).date() - stooq_date).days
                            if days_old > 5:
                                logger.warning(f"KOSPI stooq 데이터 오래됨 ({days_old}일, {stooq_date_str}) — 건너뜀")
                            elif 1000 <= fp <= 5000:
                                data["kospi"] = fp
                                logger.info(f"KOSPI stooq fallback 성공: {fp} ({stooq_date_str})")
        except Exception as e:
            logger.warning(f"KOSPI stooq fallback 실패: {e}")

    # KOSPI 최종 상태 로그 (Render 로그에서 확인용)
    if data["kospi"] == 2500.0:
        logger.warning("KOSPI 전체 fallback 실패 — 기본값 2500 사용 중")
    else:
        logger.info(f"KOSPI 최종값: {data['kospi']:.2f}")

    # ── SP500 fallback + 최종 로그 ────────────────────────────
    if data["sp500"] == 5000.0:
        try:
            resp = requests.get(
                "https://stooq.com/q/l/?s=%5Espx&f=sd2t2ohlcv&h&e=csv",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            if resp.ok and resp.text:
                lines = resp.text.strip().split("\n")
                if len(lines) >= 2:
                    cols = [c.strip() for c in lines[0].split(",")]
                    vals = [v.strip() for v in lines[1].split(",")]
                    close_idx = cols.index("Close") if "Close" in cols else 4
                    date_idx = cols.index("Date") if "Date" in cols else 1
                    if len(vals) <= max(close_idx, date_idx):
                        logger.warning("SP500 stooq 열 수 부족 — 건너뜀")
                    elif vals[close_idx] in ("N/A", "-", "", "null"):
                        logger.warning("SP500 stooq N/A 수신 — 건너뜀")
                    else:
                        fp = float(vals[close_idx])
                        raw_date = vals[date_idx]
                        if raw_date in ("N/A", "-", "", "null"):
                            logger.warning("SP500 stooq 날짜 N/A — 건너뜀")
                        else:
                            stooq_date_str = raw_date
                            stooq_date = datetime.strptime(stooq_date_str, "%Y-%m-%d").date()
                            days_old = (datetime.now(KST).date() - stooq_date).days
                            if days_old > 5:
                                logger.warning(f"SP500 stooq 데이터 오래됨 ({days_old}일, {stooq_date_str}) — 건너뜀")
                            elif 1000 <= fp <= 10000:
                                data["sp500"] = fp
                                logger.info(f"SP500 stooq fallback 성공: {fp} ({stooq_date_str})")
        except Exception as e:
            logger.warning(f"SP500 stooq fallback 실패: {e}")

    if data["sp500"] == 5000.0:
        logger.warning("SP500 전체 fallback 실패 — 기본값 5000 사용 중")
    else:
        logger.info(f"SP500 최종값: {data['sp500']:.2f}")

    # ── USD/KRW fallback ──────────────────────────────────────
    if data["usd_krw"] == 1350.0:
        # fallback 1: stooq.com CSV — 장 마감 기준 최신 데이터 (open.er-api 24h 캐시보다 신선)
        try:
            resp = requests.get(
                "https://stooq.com/q/l/?s=usdkrw&f=sd2t2ohlcv&h&e=csv",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            if resp.ok and resp.text:
                lines = resp.text.strip().split("\n")
                if len(lines) >= 2:
                    cols = [c.strip() for c in lines[0].split(",")]
                    vals = [v.strip() for v in lines[1].split(",")]
                    close_idx = cols.index("Close") if "Close" in cols else 4
                    date_idx = cols.index("Date") if "Date" in cols else 1
                    if len(vals) <= max(close_idx, date_idx):
                        logger.warning("USD/KRW stooq 열 수 부족 — 건너뜀")
                    elif vals[close_idx] in ("N/A", "-", "", "null"):
                        logger.warning("USD/KRW stooq N/A 수신 — 건너뜀")
                    else:
                        krw = float(vals[close_idx])
                        # 역단위 자동 보정: stooq이 KRW/USD(≈0.00072) 대신 USD/KRW(≈1380) 반환 보장
                        if 0 < krw < 1:
                            krw = round(1 / krw, 2)
                            logger.info(f"USD/KRW stooq 역단위 감지 → 역수 보정: {krw}")
                        raw_date = vals[date_idx]
                        if raw_date in ("N/A", "-", "", "null"):
                            logger.warning("USD/KRW stooq 날짜 N/A — 건너뜀")
                        else:
                            stooq_date_str = raw_date
                            stooq_date = datetime.strptime(stooq_date_str, "%Y-%m-%d").date()
                            days_old = (datetime.now(KST).date() - stooq_date).days
                            if days_old > 5:
                                logger.warning(f"USD/KRW stooq 데이터 오래됨 ({days_old}일, {stooq_date_str}) — 건너뜀")
                            elif 800 <= krw <= 2000:
                                data["usd_krw"] = krw
                                logger.info(f"USD/KRW stooq fallback 성공: {krw} ({stooq_date_str})")
                            else:
                                # 보정 후에도 범위 밖이면 진단 로그
                                logger.warning(f"USD/KRW stooq 범위 밖 수신: {krw} (예상 800~2000) — 건너뜀")
        except Exception as e:
            logger.warning(f"USD/KRW stooq fallback 실패: {e}")

    if data["usd_krw"] == 1350.0:
        # fallback 2: open.er-api.com — 무료, 인증 불필요 (무료 플랜 24h 캐시)
        try:
            resp = requests.get(
                "https://open.er-api.com/v6/latest/USD",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            if resp.ok:
                krw = float(resp.json().get("rates", {}).get("KRW", 0))
                if 800 <= krw <= 2000:
                    data["usd_krw"] = krw
                    logger.info(f"USD/KRW open.er-api fallback 성공: {krw}")
        except Exception as e:
            logger.warning(f"USD/KRW open.er-api fallback 실패: {e}")

    # USD/KRW 최종 상태 로그 (Render 로그에서 확인용)
    if data["usd_krw"] == 1350.0:
        logger.warning("USD/KRW 전체 fallback 실패 — 기본값 1350 사용 중")
    else:
        logger.info(f"USD/KRW 최종값: {data['usd_krw']:.2f}")

    # ── 금값 fallback ─────────────────────────────────────────
    if data["gold_price"] == 2300.0:
        # stooq.com XAU/USD (트로이 온스 기준 달러 가격)
        try:
            resp = requests.get(
                "https://stooq.com/q/l/?s=xauusd&f=sd2t2ohlcv&h&e=csv",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            if resp.ok and resp.text:
                lines = resp.text.strip().split("\n")
                if len(lines) >= 2:
                    cols = [c.strip() for c in lines[0].split(",")]
                    vals = [v.strip() for v in lines[1].split(",")]
                    close_idx = cols.index("Close") if "Close" in cols else 4
                    date_idx = cols.index("Date") if "Date" in cols else 1
                    if len(vals) <= max(close_idx, date_idx):
                        logger.warning("금 stooq 열 수 부족 — 건너뜀")
                    elif vals[close_idx] in ("N/A", "-", "", "null"):
                        logger.warning("금 stooq N/A 수신 — 건너뜀")
                    else:
                        fp = float(vals[close_idx])
                        raw_date = vals[date_idx]
                        if raw_date in ("N/A", "-", "", "null"):
                            logger.warning("금 stooq 날짜 N/A — 건너뜀")
                        else:
                            stooq_date_str = raw_date
                            stooq_date = datetime.strptime(stooq_date_str, "%Y-%m-%d").date()
                            days_old = (datetime.now(KST).date() - stooq_date).days
                            if days_old > 5:
                                logger.warning(f"금 stooq 데이터 오래됨 ({days_old}일, {stooq_date_str}) — 건너뜀")
                            elif 500 <= fp <= 5000:
                                data["gold_price"] = fp
                                logger.info(f"금 stooq fallback 성공: {fp} ({stooq_date_str})")
        except Exception as e:
            logger.warning(f"금 stooq fallback 실패: {e}")

    if data["gold_price"] == 2300.0:
        logger.warning("금값 전체 fallback 실패 — 기본값 2300 사용 중")
    else:
        logger.info(f"금값 최종값: {data['gold_price']:.2f}")

    # 시장 데이터 수집 요약 — (기본) 표시는 fallback 전체 실패해 기본값 사용 중임을 의미
    def _mark(val: float, default: float) -> str:
        return "(기본)" if val == default else ""
    logger.info(
        f"시장 데이터 수집 완료 — "
        f"KOSPI:{data['kospi']:.0f}{_mark(data['kospi'], 2500.0)} "
        f"SP500:{data['sp500']:.0f}{_mark(data['sp500'], 5000.0)} "
        f"USD/KRW:{data['usd_krw']:.0f}{_mark(data['usd_krw'], 1350.0)} "
        f"금:{data['gold_price']:.0f}{_mark(data['gold_price'], 2300.0)}"
    )

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
        fetched_at=datetime.now(KST),
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
