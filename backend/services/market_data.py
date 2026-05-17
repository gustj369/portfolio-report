"""
시장 데이터 수집 모듈
Yahoo Finance + FRED API 기반
"""
import yfinance as yf
import requests
from concurrent.futures import ThreadPoolExecutor
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

# 수익률 조정 계수 (_adjust_return_for_market 사용)
_HIGH_RATE_THRESHOLD = 4.5      # US 10Y 수익률이 이 값 초과 시 고금리 환경으로 판단
_HIGH_RATE_BOND_BOOST = 0.01    # 고금리 환경에서 채권/현금 수익률 가산
_HIGH_RATE_STOCK_DRAG = 0.005   # 고금리 환경에서 주식 수익률 차감
_INFLATION_IMPACT_FACTOR = 0.3  # 인플레이션이 채권/현금 실질 수익률에 미치는 비율
_MIN_REAL_RETURN = 0.01         # 채권/현금 실질 수익률 하한
_HIST_BLEND_RATIO = 0.5         # 역사적 수익률 블렌딩 비율 (0=기본값만, 1=역사적값만)

# BASE_RETURNS / BASE_VOLATILITY에 없는 미등록 자산유형의 fallback 기본값
_DEFAULT_RETURN = 0.05
_DEFAULT_VOLATILITY = 0.15


def _parse_stooq_close(
    csv_text: str,
    *,
    label: str,
    min_value: float,
    max_value: float,
    max_days_old: int = 5,
    invert_if_fraction: bool = False,
    today=None,
) -> float | None:
    """stooq CSV 응답에서 최신 Close 값을 안전하게 추출한다."""
    if not csv_text:
        return None

    lines = csv_text.strip().split("\n")
    if len(lines) < 2:
        return None

    cols = [c.strip() for c in lines[0].split(",")]
    vals = [v.strip() for v in lines[1].split(",")]
    close_idx = cols.index("Close") if "Close" in cols else 6
    date_idx = cols.index("Date") if "Date" in cols else 1

    if "Close" not in cols or "Date" not in cols:
        logger.warning(f"{label} stooq 예상치 못한 헤더 (fallback 인덱스 사용): {cols[:8]}")

    if len(vals) <= max(close_idx, date_idx):
        logger.warning(f"{label} stooq 열 수 부족 — 건너뜀")
        return None

    if vals[close_idx] in ("N/A", "-", "", "null"):
        logger.warning(f"{label} stooq N/A 수신 — 건너뜀")
        return None

    raw_date = vals[date_idx]
    if raw_date in ("N/A", "-", "", "null"):
        logger.warning(f"{label} stooq 날짜 N/A — 건너뜀")
        return None

    value = float(vals[close_idx])
    if invert_if_fraction and 0 < value < 1:
        value = round(1 / value, 2)
        logger.info(f"{label} stooq 역단위 감지 → 역수 보정: {value}")

    stooq_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
    today = today or datetime.now(KST).date()
    days_old = (today - stooq_date).days
    if days_old > max_days_old:
        logger.warning(f"{label} stooq 데이터 오래됨 ({days_old}일, {raw_date}) — 건너뜀")
        return None

    if min_value <= value <= max_value:
        logger.info(f"{label} stooq fallback 성공: {value} ({raw_date})")
        return value

    logger.warning(f"{label} stooq 범위 밖 수신: {value} (예상 {min_value:g}~{max_value:g}) — 건너뜀")
    return None


# 시장 데이터 수집 실패 시 사용하는 fallback 기본값 (conftest.py 등 테스트에서도 사용)
MARKET_DEFAULTS: dict[str, float] = {
    "sp500": 5000.0,
    "kospi": 2500.0,
    "us_10y_yield": 4.3,
    "kr_base_rate": 3.5,
    "usd_krw": 1350.0,
    "gold_price": 2300.0,
    "cpi_us": 3.2,
}


def _fetch_yf_ticker(ticker: str) -> float | None:
    """Yahoo Finance 티커 최신 Close 가격 반환. 실패 시 None. (ThreadPoolExecutor에서 실행)"""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1mo")
        if hist.empty:
            logger.warning(f"시장 데이터 빈 응답 ({ticker}) — 건너뜀")
            return None
        close_data = hist["Close"].dropna()
        if close_data.empty:
            logger.warning(f"시장 데이터 Close 컬럼 비어있음 ({ticker}) — 건너뜀")
            return None
        return float(close_data.iloc[-1])
    except Exception as e:
        logger.warning(f"시장 데이터 수집 실패 ({ticker}): {e}")
        return None


def fetch_market_snapshot(fred_api_key: str = "") -> MarketSnapshot:
    """현재 시장 데이터 스냅샷 수집"""
    data = dict(MARKET_DEFAULTS)

    # Yahoo Finance에서 시장 지수 병렬 수집 (4개 티커 동시 요청 — 순차 대비 최악 지연 ~120s → ~30s)
    with ThreadPoolExecutor(max_workers=len(MARKET_TICKERS)) as executor:
        yf_futures = {key: executor.submit(_fetch_yf_ticker, ticker) for key, ticker in MARKET_TICKERS.items()}
        for key, fut in yf_futures.items():
            price = fut.result()
            if price is None:
                continue
            if key == "sp500":
                # S&P 500: 합리적 범위 체크 (1000~10000)
                if 1000 <= price <= 10000:
                    data["sp500"] = price
            elif key == "kospi":
                # KOSPI: 합리적 범위 체크 (1000~5000)
                if 1000 <= price <= 5000:
                    data["kospi"] = price
                else:
                    # 범위 밖: fast_info fallback (추가 KOSPI fallback 체인은 하단에서 처리)
                    try:
                        fp = float(yf.Ticker("^KS11").fast_info.last_price or 0)
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
                fp = _parse_stooq_close(
                    resp.text,
                    label="KOSPI",
                    min_value=1000,
                    max_value=5000,
                )
                if fp is not None:
                    data["kospi"] = fp
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
                fp = _parse_stooq_close(
                    resp.text,
                    label="SP500",
                    min_value=1000,
                    max_value=10000,
                )
                if fp is not None:
                    data["sp500"] = fp
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
                krw = _parse_stooq_close(
                    resp.text,
                    label="USD/KRW",
                    min_value=800,
                    max_value=2000,
                    invert_if_fraction=True,
                )
                if krw is not None:
                    data["usd_krw"] = krw
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
                fp = _parse_stooq_close(
                    resp.text,
                    label="금",
                    min_value=500,
                    max_value=5000,
                )
                if fp is not None:
                    data["gold_price"] = fp
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

    # 핵심 지표 기본값 사용 집계 — 2개 이상 기본값이면 시뮬레이션 결과 신뢰도가 크게 낮아짐
    _fallback_used = [
        name for name, val, default in [
            ("KOSPI", data["kospi"], 2500.0),
            ("S&P500", data["sp500"], 5000.0),
            ("USD/KRW", data["usd_krw"], 1350.0),
            ("금", data["gold_price"], 2300.0),
        ] if val == default
    ]
    if len(_fallback_used) >= 2:
        logger.error(
            f"시장 데이터 다수 기본값 사용 중 ({', '.join(_fallback_used)}) — "
            f"시뮬레이션·리밸런싱 결과가 실제와 크게 다를 수 있습니다. "
            f"네트워크 상태 및 외부 API(Yahoo Finance, stooq) 접근 가능 여부를 확인하세요."
        )
    elif _fallback_used:
        logger.warning(
            f"시장 데이터 기본값 사용 중 ({_fallback_used[0]}) — "
            f"해당 지표 관련 시뮬레이션 결과에 영향이 있을 수 있습니다."
        )

    # FRED API에서 금리/CPI 병렬 수집 (2개 시리즈 동시 요청 — 순차 대비 최악 지연 ~20s → ~10s)
    if fred_api_key:
        def _fetch_fred_series(key: str, series_id: str) -> tuple[str, float | None]:
            try:
                resp = requests.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={
                        "series_id": series_id,
                        "api_key": fred_api_key,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": 1,
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    obs = resp.json().get("observations", [])
                    if obs and obs[0]["value"] != ".":
                        return key, float(obs[0]["value"])
            except Exception as e:
                logger.warning(f"FRED 데이터 수집 실패 ({series_id}): {e}")
            return key, None

        with ThreadPoolExecutor(max_workers=len(FRED_SERIES)) as executor:
            fred_futures = {key: executor.submit(_fetch_fred_series, key, sid) for key, sid in FRED_SERIES.items()}
            for key, fut in fred_futures.items():
                _, value = fut.result()
                if value is not None:
                    data[key] = value

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
    base_return = BASE_RETURNS.get(allocation.asset_type, _DEFAULT_RETURN)
    base_vol = BASE_VOLATILITY.get(allocation.asset_type, _DEFAULT_VOLATILITY)

    # 현재 시장 상황 반영 조정
    adjusted_return = _adjust_return_for_market(base_return, allocation.asset_type, market_snapshot)

    # ticker가 있으면 과거 5년 실제 수익률 참고
    if allocation.ticker:
        try:
            hist_return, hist_vol = _fetch_historical_stats(allocation.ticker)
            # 역사적 수익률과 기본값 블렌딩 (_HIST_BLEND_RATIO)
            adjusted_return = adjusted_return * (1 - _HIST_BLEND_RATIO) + hist_return * _HIST_BLEND_RATIO
            base_vol = base_vol * (1 - _HIST_BLEND_RATIO) + hist_vol * _HIST_BLEND_RATIO
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

    # 고금리 환경 (US 10Y > _HIGH_RATE_THRESHOLD): 채권/단기채권 상향, 주식 소폭 하향
    # CASH는 아래 블록에서 kr_base_rate로 직접 설정하므로 여기서 boost를 적용하지 않음
    if market.us_10y_yield > _HIGH_RATE_THRESHOLD:
        if asset_type in (AssetType.BOND, AssetType.SHORT_BOND):
            adjusted += _HIGH_RATE_BOND_BOOST
        elif asset_type in (AssetType.FOREIGN_STOCK, AssetType.DOMESTIC_STOCK):
            adjusted -= _HIGH_RATE_STOCK_DRAG

    # 현금 수익률 = 한국 기준금리 연동
    if asset_type == AssetType.CASH:
        adjusted = market.kr_base_rate / 100

    # 인플레이션 조정 (실질 수익률) — 채권·단기채권·현금 모두 적용
    inflation_rate = market.cpi_us / 100
    if asset_type in (AssetType.BOND, AssetType.SHORT_BOND, AssetType.CASH):
        adjusted = max(adjusted - inflation_rate * _INFLATION_IMPACT_FACTOR, _MIN_REAL_RETURN)

    return adjusted


def _fetch_historical_stats(ticker: str) -> tuple[float, float]:
    """티커의 과거 5년 연평균 수익률과 변동성 계산"""
    t = yf.Ticker(ticker)
    end = datetime.now(timezone.utc)   # timezone-aware: yfinance 내부 비교 시 TypeError 방지
    start = end - timedelta(days=365 * 5)
    hist = t.history(start=start, end=end, interval="1mo")

    if hist.empty or len(hist) < 12:
        raise ValueError(f"데이터 부족: {ticker}")

    monthly_returns = hist["Close"].pct_change().dropna()
    annual_return = float((1 + monthly_returns.mean()) ** 12 - 1)
    annual_vol = float(monthly_returns.std() * (12 ** 0.5))

    return annual_return, annual_vol


_MARKET_CACHE_KEY = "market:snapshot"
_MARKET_CACHE_TTL = 300  # 5분 — 시장 데이터는 분 단위로 변하므로 5분 캐싱으로 충분


def fetch_market_snapshot_cached(fred_api_key: str = "") -> MarketSnapshot:
    """시장 데이터 스냅샷 수집 (5분 캐시 적용).

    캐시 히트 시 storage에서 즉시 반환, 미스 시 fetch_market_snapshot 호출 후 캐시 저장.
    /analyze 와 PDF 생성 백그라운드 태스크가 같은 캐시를 공유하므로 중복 네트워크 요청 방지.
    """
    from services.storage import storage_get, storage_set

    cached = storage_get(_MARKET_CACHE_KEY)
    if cached is not None:
        try:
            snapshot = MarketSnapshot.model_validate(cached)
            logger.debug(f"시장 데이터 캐시 히트 (fetched_at={cached.get('fetched_at')})")
            return snapshot
        except Exception as e:
            logger.warning(f"시장 데이터 캐시 역직렬화 실패 — 재수집: {e}")

    snapshot = fetch_market_snapshot(fred_api_key)
    try:
        storage_set(_MARKET_CACHE_KEY, snapshot.model_dump(mode="json"), ttl=_MARKET_CACHE_TTL)
        logger.debug("시장 데이터 캐시 저장 완료")
    except Exception as e:
        logger.warning(f"시장 데이터 캐시 저장 실패 (무시): {e}")

    return snapshot


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
