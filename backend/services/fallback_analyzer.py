"""
Gemini API 없이 포트폴리오 데이터 기반으로 개인화된 분석 콘텐츠 생성
"""
from models.portfolio import Portfolio, UserProfile, AssetType
from models.report import AIContent, MarketSnapshot, SimulationResult
from services.simulator import calculate_risk_score


# 리스크 성향별 목표 자산 배분 (%)
_TARGET_ALLOC = {
    "안정형": {"equity": 35, "bond": 45, "cash": 20, "alt": 0},
    "중립형": {"equity": 60, "bond": 25, "cash": 15, "alt": 0},
    "공격형": {"equity": 70, "bond": 10, "cash": 10, "alt": 10},
}

_EQUITY_TYPES = {AssetType.FOREIGN_STOCK, AssetType.DOMESTIC_STOCK}
_BOND_TYPES = {AssetType.BOND, AssetType.SHORT_BOND}
_CASH_TYPES = {AssetType.CASH}
_ALT_TYPES = {AssetType.ALTERNATIVE, AssetType.BITCOIN, AssetType.CRYPTO, AssetType.GOLD}

# 자산 유형별 한국어 표시명
_ALT_NAMES = {
    AssetType.BITCOIN: "비트코인",
    AssetType.CRYPTO: "암호화폐",
    AssetType.GOLD: "금",
    AssetType.ALTERNATIVE: "대안자산",
}


def _group_weights(portfolio: Portfolio) -> dict:
    g = {"equity": 0.0, "bond": 0.0, "cash": 0.0, "alt": 0.0}
    for a in portfolio.allocations:
        if a.asset_type in _EQUITY_TYPES:
            g["equity"] += a.weight
        elif a.asset_type in _BOND_TYPES:
            g["bond"] += a.weight
        elif a.asset_type in _CASH_TYPES:
            g["cash"] += a.weight
        elif a.asset_type in _ALT_TYPES:
            g["alt"] += a.weight
    return g


def _risk_asset_weight(g: dict) -> float:
    """주식 + 대안자산(비트코인·금 등) 합산 위험자산 비중"""
    return g["equity"] + g["alt"]


def generate_personalized_content(
    user_profile: UserProfile,
    portfolio: Portfolio,
    simulation: SimulationResult,
    market_snapshot: MarketSnapshot,
    risk_score: int,
    risk_grade: str,
) -> AIContent:
    """포트폴리오 데이터 기반 개인화 분석 (API 키 불필요)"""

    g = _group_weights(portfolio)
    equity_w = g["equity"]
    bond_w = g["bond"]
    cash_w = g["cash"]
    alt_w = g["alt"]
    risky_w = _risk_asset_weight(g)  # 주식 + 대안자산

    age = user_profile.age
    goal = user_profile.investment_goal.value if hasattr(user_profile.investment_goal, "value") else str(user_profile.investment_goal)
    risk_tol = user_profile.risk_tolerance.value if hasattr(user_profile.risk_tolerance, "value") else str(user_profile.risk_tolerance)
    monthly = portfolio.monthly_saving
    total = portfolio.total_asset

    # 최대 비중 자산 파악
    max_alloc = max(portfolio.allocations, key=lambda a: a.weight)

    # ── 종합 진단 ─────────────────────────────────────────────────
    years_to_retire = max(60 - age, 10)

    # 위험자산(주식+대안) 기준으로 포트폴리오 성격 판단
    if risky_w >= 70:
        dominance = f"위험자산(주식·대안) {risky_w:.0f}%로 성장 중심"
        structure_comment = "장기 복리 수익을 극대화할 수 있는 공격적 구조입니다."
    elif risky_w >= 50:
        dominance = f"위험자산 {risky_w:.0f}%·안전자산 {100 - risky_w:.0f}%의 균형형"
        structure_comment = "성장과 안정의 균형을 추구하는 구조입니다."
    else:
        dominance = f"안전자산(채권·현금) {bond_w + cash_w:.0f}%로 보수적 구성"
        structure_comment = "안정적인 자산 보전에 유리한 구조입니다."

    # 자산군 구체 설명
    comp_parts = []
    if equity_w > 0:
        comp_parts.append(f"주식 {equity_w:.0f}%")
    if alt_w > 0:
        alt_names = {_ALT_NAMES.get(a.asset_type, "대안자산") for a in portfolio.allocations if a.asset_type in _ALT_TYPES}
        comp_parts.append(f"{'·'.join(alt_names)} {alt_w:.0f}%")
    if bond_w > 0:
        comp_parts.append(f"채권 {bond_w:.0f}%")
    if cash_w > 0:
        comp_parts.append(f"현금 {cash_w:.0f}%")
    comp_str = ", ".join(comp_parts)

    diagnosis = (
        f"{age}세 {risk_tol} 투자자의 포트폴리오는 {comp_str}으로 구성된 {dominance} 포트폴리오입니다. "
        f"투자 목표 '{goal}'에 맞춰 월 {monthly:,}만원씩 {total:,}만원 규모의 자산을 운용하고 있으며, "
        f"리스크 점수 {risk_score}/100({risk_grade})으로 평가됩니다. "
        f"은퇴까지 약 {years_to_retire}년의 투자 기간이 남아 있어 {structure_comment}"
    )

    # ── 강점 ─────────────────────────────────────────────────────
    strengths = []

    asset_count = len(portfolio.allocations)
    asset_types = set(a.asset_type for a in portfolio.allocations)

    if asset_count >= 4:
        strengths.append(f"{asset_count}개 자산에 분산 투자해 특정 종목 리스크를 분산")
    elif asset_count >= 2:
        strengths.append(f"{asset_count}개 자산 조합으로 기본적인 분산 효과 확보")

    if monthly >= 50:
        strengths.append(f"월 {monthly:,}만원 정기 적립으로 평균 매입 단가를 낮추는 코스트 에버리징 효과")
    elif monthly > 0:
        strengths.append(f"월 {monthly:,}만원 정기 적립으로 꾸준한 자산 축적 진행 중")

    # 실제 보유 자산군에 기반한 문구 생성
    held_types = []
    if equity_w > 0:
        held_types.append("주식")
    if alt_w > 0:
        # 비트코인, 금 등 구체적 명칭 사용
        for a in portfolio.allocations:
            if a.asset_type in _ALT_TYPES:
                held_types.append(_ALT_NAMES.get(a.asset_type, "대안자산"))
                break
    if bond_w > 0:
        held_types.append("채권")
    if cash_w > 0:
        held_types.append("현금")

    if len(held_types) >= 3:
        strengths.append(f"{'·'.join(held_types[:3])} 등 이종 자산군 보유로 시장 충격 분산 가능")
    elif len(held_types) == 2:
        strengths.append(f"{held_types[0]}·{held_types[1]} 결합으로 수익성·안정성 동시 추구")

    if risky_w >= 60 and age <= 40:
        strengths.append(f"{age}세 젊은 나이에 위험자산 {risky_w:.0f}% 보유로 장기 복리 성장 극대화 가능")

    if cash_w + bond_w >= 15:
        strengths.append(f"현금·채권 {cash_w + bond_w:.0f}% 확보로 급락 시 추가 매수 여력 및 유동성 대비")

    target = _TARGET_ALLOC.get(risk_grade, _TARGET_ALLOC["중립형"])
    if abs(risky_w - (target["equity"] + target["alt"])) <= 10:
        strengths.append(f"{risk_grade} 성향에 적합한 위험자산 비중({risky_w:.0f}%) 유지")

    strengths = strengths[:4] if strengths else ["분산 투자 기반의 포트폴리오 구조"]

    # ── 약점 ─────────────────────────────────────────────────────
    weaknesses = []

    # 단일 자산 집중 (비트코인 포함)
    max_w = max(a.weight for a in portfolio.allocations)
    max_name = next(a.asset_name for a in portfolio.allocations if a.weight == max_w)
    if max_w >= 40:
        weaknesses.append(f"'{max_name}' 단일 비중 {max_w:.0f}%로 집중 — 해당 자산 급락 시 전체 포트폴리오 영향 큼")

    # 암호화폐(비트코인/기타) 고변동성 경고
    crypto_allocs = [a for a in portfolio.allocations if a.asset_type in (AssetType.BITCOIN, AssetType.CRYPTO)]
    if crypto_allocs:
        crypto_w = sum(a.weight for a in crypto_allocs)
        if crypto_w >= 20:
            weaknesses.append(
                f"암호화폐 {crypto_w:.0f}% — 연 변동성 70~80%+ 자산으로 단기 50~70% 급락 가능성 존재, "
                f"손실 감내 능력 충분히 고려 필요"
            )

    # 채권 부족
    target_bond_w = target.get("bond", 0)
    if bond_w == 0:
        weaknesses.append("채권 0% — 금리 급등·경기침체 시 전체 포트폴리오 보호막 부재")
    elif bond_w < target_bond_w - 5:
        weaknesses.append(
            f"채권 비중 {bond_w:.0f}%로 {risk_grade} 목표({target_bond_w:.0f}%) 대비 미달 — "
            f"금리 급등·경기침체 시 방어력 부족"
        )

    # 해외자산 환노출
    foreign_allocs = [a for a in portfolio.allocations if a.asset_type == AssetType.FOREIGN_STOCK]
    if foreign_allocs:
        foreign_w = sum(a.weight for a in foreign_allocs)
        weaknesses.append(f"해외주식 {foreign_w:.0f}% 달러 노출 — 환율 변동에 따른 원화 수익률 변동 위험")

    # 위험자산 과잉 vs 성향 목표
    target_risky = target["equity"] + target.get("alt", 0)
    if risky_w > target_risky + 15:
        weaknesses.append(
            f"위험자산 {risky_w:.0f}%는 {risk_grade} 권장({target_risky}%) 대비 과도 — "
            f"시장 급락 시 심리적 패닉 매도 위험"
        )

    weaknesses = weaknesses[:4] if weaknesses else ["리밸런싱 주기 계획 수립 권장"]

    # ── 시나리오 코멘트 ────────────────────────────────────────────
    # 포트폴리오의 실제 주요 자산 표현
    top_assets = sorted(portfolio.allocations, key=lambda a: a.weight, reverse=True)[:2]
    portfolio_desc = "·".join(f"{a.asset_name}({a.weight:.0f}%)" for a in top_assets)

    scenario_commentary = {
        "bear": (
            f"글로벌 경기침체 또는 금리 급등 시나리오로, "
            f"{portfolio_desc} 포트폴리오는 "
            f"5년 후 {simulation.bear.final_value:,.0f}만원(연환산 {simulation.bear.cagr:.1f}%)으로 예상됩니다."
        ),
        "base": (
            f"현재 시장 상황이 지속되는 기본 시나리오로, "
            f"월 {monthly:,}만원 적립 지속 시 "
            f"5년 후 {simulation.base.final_value:,.0f}만원(연환산 {simulation.base.cagr:.1f}%)으로 예상됩니다."
        ),
        "bull": (
            f"경기 회복 및 위험자산 강세 시나리오로, "
            f"{portfolio_desc} 포트폴리오가 강세를 보여 "
            f"5년 후 {simulation.bull.final_value:,.0f}만원(연환산 {simulation.bull.cagr:.1f}%)으로 예상됩니다."
        ),
    }

    # ── 리밸런싱 추천 ──────────────────────────────────────────────
    recommendations = _generate_rebalancing(portfolio, g, target, risk_grade)

    # ── 시장 코멘트 ────────────────────────────────────────────────
    market_commentary = _generate_market_commentary(market_snapshot, portfolio, g)

    # ── 맞춤 주의사항 ──────────────────────────────────────────────
    cautions = _generate_cautions(portfolio, g, user_profile, market_snapshot)

    return AIContent(
        portfolio_diagnosis=diagnosis,
        strengths=strengths,
        weaknesses=weaknesses,
        risk_score=risk_score,
        risk_grade=risk_grade,
        scenario_commentary=scenario_commentary,
        rebalancing_recommendations=recommendations,
        market_commentary=market_commentary,
        cautions=cautions,
    )


def _generate_rebalancing(portfolio: Portfolio, g: dict, target: dict, risk_grade: str) -> list[dict]:
    """리스크 성향 기반 리밸런싱 추천 생성"""
    equity_w = g["equity"]
    alt_w = g["alt"]

    equity_allocs = [a for a in portfolio.allocations if a.asset_type in _EQUITY_TYPES]
    alt_allocs = [a for a in portfolio.allocations if a.asset_type in _ALT_TYPES]
    bond_allocs = [a for a in portfolio.allocations if a.asset_type in _BOND_TYPES]
    cash_allocs = [a for a in portfolio.allocations if a.asset_type in _CASH_TYPES]

    recs = []

    # ── 현금: 현 비중 유지 ────────────────────────────────────────
    cash_w = g["cash"]
    for a in cash_allocs:
        recs.append({"asset_name": a.asset_name, "current_weight": a.weight,
                      "recommended_weight": a.weight, "direction": "유지",
                      "reason": "유동성 확보 및 비상 자금 용도로 현 비중 유지"})

    # ── 채권: 목표 비중 적용 / 없으면 신규 편입 제안 ──────────────
    target_bond = float(target["bond"])
    bond_rec_total = 0.0

    if bond_allocs:
        bond_diff = target_bond - g["bond"]
        per_adj = bond_diff / len(bond_allocs)
        for a in bond_allocs:
            new_w = round(max(0.0, min(60.0, a.weight + per_adj)), 1)
            direction = "증가" if new_w > a.weight + 0.5 else ("감소" if new_w < a.weight - 0.5 else "유지")
            reason = (
                f"고금리 환경에서 채권 매력 상승 — {risk_grade} 목표({target_bond:.0f}%) 향해 점진적 확대"
                if direction == "증가" else
                (f"{risk_grade} 목표({target_bond:.0f}%) 수준으로 조정" if direction == "감소" else
                 f"{risk_grade} 목표({target_bond:.0f}%) 범위 내 적정")
            )
            recs.append({"asset_name": a.asset_name, "current_weight": a.weight,
                          "recommended_weight": new_w, "direction": direction, "reason": reason})
            bond_rec_total += new_w
    elif target_bond > 0:
        # 채권 없는 포트폴리오 → 신규 편입 제안
        bond_rec_total = target_bond
        recs.append({
            "asset_name": "채권 ETF (신규 편입 권장)",
            "current_weight": 0.0,
            "recommended_weight": target_bond,
            "direction": "추가",
            "reason": (
                f"{risk_grade} 권장 채권 비중 {target_bond:.0f}% — "
                "금리 급등·경기침체 시 포트폴리오 방어막 역할. "
                "국내채권 ETF(KOSEF국고채) 또는 미국채 ETF(IEF·TLT) 단계적 편입 고려"
            ),
        })

    # ── 위험자산 배분 가능 비중 산출 ─────────────────────────────
    # 현금·채권 배분 후 남은 비중을 주식·대안에 배분
    available_risky = 100.0 - cash_w - bond_rec_total
    target_alt = min(float(target.get("alt", 0)), available_risky)
    target_equity = available_risky - target_alt

    # ── 대안자산(비트코인·금 등) 조정 ─────────────────────────────
    if alt_allocs:
        alt_diff = target_alt - alt_w
        per_adj = alt_diff / len(alt_allocs)
        for a in alt_allocs:
            new_w = round(max(0.0, min(50.0, a.weight + per_adj)), 1)
            direction = "증가" if new_w > a.weight + 0.5 else ("감소" if new_w < a.weight - 0.5 else "유지")
            reason = _alt_reason(direction, a.asset_type, a.asset_name, target_alt, a.weight, new_w)
            recs.append({"asset_name": a.asset_name, "current_weight": a.weight,
                          "recommended_weight": new_w, "direction": direction, "reason": reason})

    # ── 주식 조정 ──────────────────────────────────────────────────
    if equity_allocs:
        equity_diff = target_equity - equity_w
        per_adj = equity_diff / len(equity_allocs)
        for a in equity_allocs:
            new_w = round(max(5.0, min(95.0, a.weight + per_adj)), 1)
            direction = "증가" if new_w > a.weight + 0.5 else ("감소" if new_w < a.weight - 0.5 else "유지")
            reason = _equity_reason(direction, risk_grade, target["equity"])
            recs.append({"asset_name": a.asset_name, "current_weight": a.weight,
                          "recommended_weight": new_w, "direction": direction, "reason": reason})

    # ── 비중 합 100% 미세 보정 ───────────────────────────────────
    total_rec = sum(r["recommended_weight"] for r in recs)
    diff = round(100.0 - total_rec, 1)
    if abs(diff) >= 0.1:
        # 조정 가능한 자산 중 비중이 가장 큰 자산에서 잔차 흡수
        adjustable = [r for r in recs if r["direction"] in ("증가", "감소", "유지")
                      and r.get("recommended_weight", 0) >= 5.0]
        if adjustable:
            largest = max(adjustable, key=lambda r: r["recommended_weight"])
            largest["recommended_weight"] = round(largest["recommended_weight"] + diff, 1)
            # 보정 후 방향 재계산
            gap = largest["recommended_weight"] - largest["current_weight"]
            if abs(gap) < 0.5:
                largest["direction"] = "유지"
            elif gap < 0:
                largest["direction"] = "감소"
            else:
                largest["direction"] = "증가"

    return recs


def _equity_reason(direction: str, risk_grade: str, target_equity: float) -> str:
    if direction == "증가":
        return f"{risk_grade} 성향 권장 주식비중({target_equity:.0f}%)에 미달 — 점진적 확대 고려"
    elif direction == "감소":
        return f"{risk_grade} 성향 권장 주식비중({target_equity:.0f}%) 대비 과도 — 단계적 축소 권장"
    return f"{risk_grade} 성향 목표 범위({target_equity:.0f}%±10%) 내 적정 수준"


def _alt_reason(direction: str, asset_type: AssetType, asset_name: str, target_alt: float, current_w: float, recommended_w: float) -> str:
    type_name = _ALT_NAMES.get(asset_type, "대안자산")
    display = asset_name if asset_name else type_name
    if direction == "감소":
        if asset_type in (AssetType.BITCOIN, AssetType.CRYPTO):
            return (
                f"{display}({current_w:.0f}%) 고변동성 암호화폐 — "
                f"리스크 관리 차원에서 {recommended_w:.1f}%로 단계적 축소 권장"
            )
        else:
            return (
                f"{display}({current_w:.0f}%) 비중 과다 — "
                f"전체 대안자산 목표({target_alt:.0f}%) 감안하여 {recommended_w:.1f}%로 조정 권장"
            )
    elif direction == "증가":
        return f"포트폴리오 다각화 목적으로 {display} {recommended_w:.1f}% 수준 보유 고려"
    return f"현재 {display} 비중 적정 수준 유지"


def _generate_market_commentary(
    market: MarketSnapshot, portfolio: Portfolio, g: dict
) -> str:
    """실제 시장 데이터 기반 코멘트 — 실제 보유 자산에 맞게 생성"""
    risky_w = _risk_asset_weight(g)
    parts = []

    # 금리 환경
    if market.us_10y_yield >= 4.5:
        parts.append(
            f"미국 10년 국채 금리 {market.us_10y_yield:.2f}%로 고금리 환경 지속 중으로, "
            f"채권·현금 비중 확대가 수익 방어에 유리합니다."
        )
    elif market.us_10y_yield >= 3.5:
        parts.append(
            f"미국 10년 국채 금리 {market.us_10y_yield:.2f}%는 중립적 수준으로, "
            f"주식·채권 균형 유지가 적절한 전략입니다."
        )
    else:
        parts.append(
            f"미국 10년 국채 금리 {market.us_10y_yield:.2f}%로 완화 국면에 진입하고 있어 "
            f"위험자산의 매력도가 높아지고 있습니다."
        )

    # 해외 주식 보유자만 환율 코멘트
    foreign_w = sum(a.weight for a in portfolio.allocations if a.asset_type == AssetType.FOREIGN_STOCK)
    if foreign_w >= 20:
        if market.usd_krw >= 1400:
            parts.append(
                f"달러/원 환율 {market.usd_krw:,.0f}원으로 원화 약세가 지속되어, "
                f"해외주식 {foreign_w:.0f}% 보유 포트폴리오는 환차익 효과가 기대됩니다. "
                f"다만 환율 반전 시 원화 수익률이 하락할 수 있어 분기별 모니터링이 필요합니다."
            )
        else:
            parts.append(
                f"달러/원 환율 {market.usd_krw:,.0f}원 수준에서 해외주식 {foreign_w:.0f}%의 "
                f"환율 리스크를 주기적으로 점검하세요."
            )

    # 암호화폐(비트코인/기타) 보유자 전용 코멘트
    crypto_allocs = [a for a in portfolio.allocations if a.asset_type in (AssetType.BITCOIN, AssetType.CRYPTO)]
    if crypto_allocs:
        crypto_w = sum(a.weight for a in crypto_allocs)
        parts.append(
            f"암호화폐 {crypto_w:.0f}% 보유 포트폴리오는 급등·급락 사이클에 민감합니다. "
            f"금 현물 가격 ${market.gold_price:,.0f} 수준도 참고하여 대안자산 비중을 점검하세요."
        )

    # 인플레이션
    if market.cpi_us >= 3.0:
        parts.append(
            f"미국 CPI {market.cpi_us:.1f}%로 인플레이션 압력이 지속되고 있어 "
            f"실질 수익률 보호를 위한 자산 다각화를 고려하시기 바랍니다."
        )

    return " ".join(parts) if parts else (
        f"현재 금리 {market.us_10y_yield:.2f}%, 환율 {market.usd_krw:,.0f}원 환경을 감안하여 "
        f"분기별 포트폴리오 점검을 권장합니다."
    )


def _generate_cautions(
    portfolio: Portfolio, g: dict, user_profile: UserProfile, market: MarketSnapshot
) -> list[str]:
    """포트폴리오 맞춤 주의사항"""
    cautions = []

    crypto_allocs = [a for a in portfolio.allocations if a.asset_type in (AssetType.BITCOIN, AssetType.CRYPTO)]
    if crypto_allocs:
        crypto_w = sum(a.weight for a in crypto_allocs)
        cautions.append(
            f"암호화폐({crypto_w:.0f}%)는 규제 변화, 거래소 리스크 등 일반 주식과 다른 고유 리스크가 있습니다. "
            f"전체 자산의 10~20% 이내 보유를 일반적으로 권장합니다."
        )

    foreign_allocs = [a for a in portfolio.allocations if a.asset_type == AssetType.FOREIGN_STOCK]
    if foreign_allocs:
        foreign_w = sum(a.weight for a in foreign_allocs)
        cautions.append(
            f"해외 ETF 투자 시 환율 변동(현재 {market.usd_krw:,.0f}원)이 원화 실질 수익률에 미치는 영향을 "
            f"정기적으로 확인하세요."
        )

    risky_w = _risk_asset_weight(g)
    if risky_w >= 60:
        cautions.append(
            f"위험자산 {risky_w:.0f}%로 시장 급락 시 단기 평가손실이 발생할 수 있습니다. "
            f"장기 관점을 유지하며 공황 매도를 피하는 것이 중요합니다."
        )

    cautions.append(
        "본 시뮬레이션은 과거 역사적 수익률 기반 추정치이며, "
        "실제 시장 상황에 따라 결과가 크게 달라질 수 있습니다."
    )

    cautions.append(
        "본 리포트는 투자 정보 제공 목적이며, 투자 권유 또는 자문이 아닙니다. "
        "중요한 투자 결정 전 공인 재무설계사와 상담하시기 바랍니다."
    )

    return cautions[:4]


def generate_personalized_preview_summary(
    user_profile: UserProfile,
    portfolio: Portfolio,
    market_snapshot: MarketSnapshot,
    risk_score: int,
    risk_grade: str,
) -> str:
    """미리보기용 개인화 요약 문장"""
    g = _group_weights(portfolio)
    risky_w = _risk_asset_weight(g)
    age = user_profile.age
    goal = user_profile.investment_goal.value if hasattr(user_profile.investment_goal, "value") else str(user_profile.investment_goal)

    comp_parts = []
    if g["equity"] > 0:
        comp_parts.append(f"주식 {g['equity']:.0f}%")
    if g["alt"] > 0:
        alt_names = {_ALT_NAMES.get(a.asset_type, "대안자산") for a in portfolio.allocations if a.asset_type in _ALT_TYPES}
        comp_parts.append(f"{'·'.join(alt_names)} {g['alt']:.0f}%")
    if g["bond"] > 0:
        comp_parts.append(f"채권 {g['bond']:.0f}%")
    if g["cash"] > 0:
        comp_parts.append(f"현금 {g['cash']:.0f}%")
    comp_str = "·".join(comp_parts) if comp_parts else "다양한 자산"

    return (
        f"{age}세 {goal} 목표의 {comp_str} 포트폴리오입니다. "
        f"리스크 점수 {risk_score}/100({risk_grade})으로 평가되며, "
        f"월 {portfolio.monthly_saving:,}만원 정기 적립 시 "
        f"5년 후 자산 성장이 기대됩니다. "
        f"포트폴리오 강점과 리밸런싱 전략을 전체 리포트에서 확인하세요."
    )
