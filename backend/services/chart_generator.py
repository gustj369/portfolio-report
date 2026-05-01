"""
matplotlib 기반 차트 생성
PDF 임베드용 PNG 이미지 (BytesIO)
"""
import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import font_manager
import numpy as np
import os
import logging

from models.portfolio import Portfolio
from models.report import SimulationResult, AIContent

logger = logging.getLogger(__name__)

# 컬러 팔레트
NAVY = "#1a2e5a"
GOLD = "#d4af37"
WHITE = "#ffffff"
LIGHT_GRAY = "#f5f5f5"
RED = "#e74c3c"
GREEN = "#27ae60"
BLUE = "#3498db"
COLORS_PIE = ["#d4af37", "#1a2e5a", "#3498db", "#27ae60", "#e74c3c",
              "#9b59b6", "#e67e22", "#1abc9c", "#95a5a6", "#2c3e50"]

# 한글 폰트 후보 (우선순위 순)
_FONT_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts", "NotoSansKR-Regular.ttf"),
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",      # Linux: fonts-nanum (Render)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux: fonts-noto-cjk
    r"C:\Windows\Fonts\malgun.ttf",    # 맑은 고딕 (Windows)
    r"C:\Windows\Fonts\gulim.ttc",     # 굴림
]


def _setup_font():
    """한글 폰트 설정 — 사용 가능한 첫 번째 폰트 사용"""
    for font_path in _FONT_CANDIDATES:
        if os.path.exists(font_path):
            try:
                font_manager.fontManager.addfont(font_path)
                prop = font_manager.FontProperties(fname=font_path)
                plt.rcParams["font.family"] = prop.get_name()
                logger.info(f"차트 폰트 설정: {font_path}")
                break
            except Exception as e:
                logger.warning(f"폰트 로드 실패 ({font_path}): {e}")
    else:
        # Windows 시스템 폰트명으로 직접 지정 시도
        plt.rcParams["font.family"] = ["Malgun Gothic", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


_setup_font()


def generate_portfolio_pie_chart(portfolio: Portfolio) -> bytes:
    """포트폴리오 자산 배분 파이차트 생성"""
    labels = [a.asset_name for a in portfolio.allocations]
    sizes = [a.weight for a in portfolio.allocations]
    colors = COLORS_PIE[:len(labels)]

    fig, ax = plt.subplots(figsize=(8, 6), facecolor=WHITE)
    ax.set_facecolor(WHITE)

    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=None,
        colors=colors,
        autopct="%1.1f%%",
        startangle=90,
        pctdistance=0.8,
        wedgeprops={"edgecolor": WHITE, "linewidth": 2},
    )

    for autotext in autotexts:
        autotext.set_color(WHITE)
        autotext.set_fontsize(10)
        autotext.set_fontweight("bold")

    # 범례
    legend_patches = [
        mpatches.Patch(color=colors[i], label=f"{labels[i]} ({sizes[i]:.1f}%)")
        for i in range(len(labels))
    ]
    ax.legend(
        handles=legend_patches,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.15),
        ncol=min(3, len(labels)),
        fontsize=9,
        frameon=False,
    )

    ax.set_title("현재 자산 배분", fontsize=14, fontweight="bold", color=NAVY, pad=15)

    return _fig_to_bytes(fig)


def generate_projection_line_chart(simulation: SimulationResult) -> bytes:
    """5년 시뮬레이션 꺾은선 그래프 생성"""
    months = list(range(0, len(simulation.base.monthly_values) + 1))
    initial = simulation.initial_value

    bear_values = [initial] + simulation.bear.monthly_values
    base_values = [initial] + simulation.base.monthly_values
    bull_values = [initial] + simulation.bull.monthly_values

    fig, ax = plt.subplots(figsize=(10, 5), facecolor=WHITE)
    ax.set_facecolor(WHITE)

    # 신뢰구간 음영
    ax.fill_between(months, bear_values, bull_values,
                    alpha=0.15, color=GOLD, label="_nolegend_")

    # 시나리오별 선
    ax.plot(months, bull_values, color=GREEN, linewidth=2.5, linestyle="--",
            label=f"낙관 ({simulation.bull.final_value:,.0f}만원)")
    ax.plot(months, base_values, color=GOLD, linewidth=3,
            label=f"기본 ({simulation.base.final_value:,.0f}만원)")
    ax.plot(months, bear_values, color=RED, linewidth=2.5, linestyle=":",
            label=f"비관 ({simulation.bear.final_value:,.0f}만원)")

    # 초기값 표시
    ax.axhline(y=initial, color=NAVY, linewidth=1, linestyle="-.", alpha=0.5,
               label=f"현재 ({initial:,.0f}만원)")

    # 축 설정
    ax.set_xlabel("기간 (개월)", fontsize=11, color=NAVY)
    ax.set_ylabel("자산 규모 (만원)", fontsize=11, color=NAVY)
    ax.set_title("5년 자산 성장 시뮬레이션", fontsize=14, fontweight="bold", color=NAVY, pad=15)

    # x축 레이블을 연도로 변환
    ax.set_xticks([0, 12, 24, 36, 48, 60])
    ax.set_xticklabels(["현재", "1년", "2년", "3년", "4년", "5년"])

    # 값 포매팅
    ax.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda x, _: f"{x:,.0f}")
    )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#e0e0e0")
    ax.spines["bottom"].set_color("#e0e0e0")
    ax.tick_params(colors=NAVY)
    ax.grid(axis="y", linestyle="--", alpha=0.4, color="#e0e0e0")

    ax.legend(
        loc="upper left",
        fontsize=9,
        frameon=True,
        framealpha=0.9,
        edgecolor="#e0e0e0",
    )

    fig.tight_layout()
    return _fig_to_bytes(fig)


def generate_stacked_bar_chart(
    portfolio: Portfolio,
    simulation: SimulationResult,
) -> bytes:
    """연도별 자산 구성 스택 바 차트 생성 (적립금 vs 수익)"""
    years = [1, 2, 3, 4, 5]
    month_indices = [11, 23, 35, 47, 59]

    base_values_at_years = [simulation.base.monthly_values[i] for i in month_indices]
    total_invested_at_years = [
        portfolio.total_asset + portfolio.monthly_saving * (12 * y)
        for y in years
    ]
    returns_at_years = [
        max(0, base_values_at_years[i] - total_invested_at_years[i])
        for i in range(5)
    ]
    # 손실 구간: 투자원금 > 기본 시나리오 실제값인 경우
    loss_at_years = [
        max(0, total_invested_at_years[i] - base_values_at_years[i])
        for i in range(5)
    ]
    has_loss = any(l > 0 for l in loss_at_years)

    fig, ax = plt.subplots(figsize=(8, 5), facecolor=WHITE)
    ax.set_facecolor(WHITE)

    x = np.arange(len(years))
    width = 0.5

    bars1 = ax.bar(x, total_invested_at_years, width, label="투자 원금", color=NAVY, alpha=0.85)
    bars2 = ax.bar(x, returns_at_years, width, bottom=total_invested_at_years,
                   label="기대 수익", color=GOLD, alpha=0.85)

    # 손실 구간 overlay: 원금 상단에서 아래로 loss만큼 RED hatch로 강조
    if has_loss:
        loss_bottoms = [base_values_at_years[i] if loss_at_years[i] > 0 else total_invested_at_years[i]
                        for i in range(5)]
        ax.bar(x, loss_at_years, width, bottom=loss_bottoms,
               color=RED, alpha=0.25, hatch="///", label="손실 구간", edgecolor=RED, linewidth=0.5)

    ax.set_xlabel("투자 기간", fontsize=11, color=NAVY)
    ax.set_ylabel("자산 규모 (만원)", fontsize=11, color=NAVY)
    ax.set_title("원금 vs 기대 수익 (기본 시나리오)", fontsize=14, fontweight="bold", color=NAVY, pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{y}년차" for y in years])
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda val, _: f"{val:,.0f}"))

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(colors=NAVY)
    ax.grid(axis="y", linestyle="--", alpha=0.4, color="#e0e0e0")

    ax.legend(fontsize=10, frameon=False)

    # 최종 금액 레이블 — 기본 시나리오 실제 포트폴리오 예상값 표시
    # (손익분기점 미달 시 스택 바 높이와 레이블 값이 다를 수 있으므로 실제값 사용)
    for i, actual in enumerate(base_values_at_years):
        bar_top = total_invested_at_years[i] + returns_at_years[i]
        ax.text(i, bar_top + bar_top * 0.02, f"{actual:,.0f}", ha="center",
                va="bottom", fontsize=8, color=NAVY, fontweight="bold")

    # y축 상한 여유 — 레이블이 figure 상단에 잘리지 않도록 15% 여백 확보
    all_tops = [total_invested_at_years[i] + returns_at_years[i] for i in range(5)]
    ax.set_ylim(0, max(all_tops) * 1.15)

    fig.tight_layout()
    return _fig_to_bytes(fig)


def generate_rebalancing_comparison_chart(
    portfolio: Portfolio,
    recommendations: list[dict],
) -> bytes:
    """현재 비중 vs 추천 비중 비교 파이차트 (나란히)"""
    current_labels = [a.asset_name for a in portfolio.allocations]
    current_sizes = [a.weight for a in portfolio.allocations]

    # 추천 비중 데이터 정리 (기존 자산)
    rec_map = {r["asset_name"]: r["recommended_weight"] for r in recommendations}
    rec_sizes = [rec_map.get(name, weight) for name, weight in zip(current_labels, current_sizes)]

    # 신규 편입 항목 추가 (추천 비중 차트에만 표시)
    new_rec_labels = list(current_labels)
    new_rec_sizes = list(rec_sizes)
    for r in recommendations:
        if r["asset_name"] not in current_labels and r.get("recommended_weight", 0) > 0:
            new_rec_labels.append(r["asset_name"])
            new_rec_sizes.append(r["recommended_weight"])

    # 합계를 100으로 정규화
    rec_total = sum(new_rec_sizes)
    if rec_total > 0:
        new_rec_sizes = [s / rec_total * 100 for s in new_rec_sizes]

    # 추천 파이차트에서 0% 자산 제거 (라벨 겹침 방지)
    filtered_rec = [(l, s) for l, s in zip(new_rec_labels, new_rec_sizes) if s > 0.05]
    new_rec_labels = [x[0] for x in filtered_rec]
    new_rec_sizes  = [x[1] for x in filtered_rec]

    max_labels = max(len(current_labels), len(new_rec_labels))
    colors = COLORS_PIE[:max_labels]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5), facecolor=WHITE)

    for ax, sizes, labels, title in [
        (ax1, current_sizes, current_labels, "현재 비중"),
        (ax2, new_rec_sizes, new_rec_labels, "추천 비중"),
    ]:
        ax.set_facecolor(WHITE)
        ax.pie(
            sizes,
            colors=colors[:len(sizes)],
            autopct="%1.1f%%",
            startangle=90,
            pctdistance=0.8,
            wedgeprops={"edgecolor": WHITE, "linewidth": 2},
        )
        ax.set_title(title, fontsize=13, fontweight="bold", color=NAVY, pad=10)

    # 공통 범례 (추천 비중 기준 — 신규 편입 항목 포함)
    legend_patches = [
        mpatches.Patch(color=colors[i], label=new_rec_labels[i])
        for i in range(len(new_rec_labels))
    ]
    fig.legend(
        handles=legend_patches,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.05),
        ncol=min(4, len(current_labels)),
        fontsize=9,
        frameon=False,
    )

    fig.suptitle("포트폴리오 리밸런싱 비교", fontsize=15, fontweight="bold", color=NAVY, y=1.02)
    fig.tight_layout()
    return _fig_to_bytes(fig)


def _fig_to_bytes(fig: plt.Figure) -> bytes:
    """matplotlib Figure → PNG bytes"""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()
