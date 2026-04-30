"""
ReportLab 기반 5페이지 PDF 리포트 생성
"""
import io
import os
from datetime import datetime, timezone, timedelta

# Render 서버는 UTC 기준 — PDF에 표시되는 날짜/시간은 KST(UTC+9)로 고정
KST = timezone(timedelta(hours=9))
from xml.sax.saxutils import escape as _xe  # XML 특수문자 이스케이프 (&→&amp; 등)
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable, KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics.charts.piecharts import Pie
import logging

from models.portfolio import Portfolio, UserProfile
from models.report import SimulationResult, AIContent, MarketSnapshot

logger = logging.getLogger(__name__)

# 색상 정의
COLOR_NAVY = colors.HexColor("#1a2e5a")
COLOR_GOLD = colors.HexColor("#d4af37")
COLOR_WHITE = colors.white
COLOR_LIGHT_GRAY = colors.HexColor("#f7f7f7")
COLOR_DARK_GRAY = colors.HexColor("#555555")
COLOR_RED = colors.HexColor("#e74c3c")
COLOR_GREEN = colors.HexColor("#27ae60")

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 20 * mm

# 폰트 등록
FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")
FONT_REGULAR = "KoreanFont"
FONT_BOLD = "KoreanFont-Bold"

# Linux 시스템 한글 폰트 후보 경로 (Render apt fonts-nanum 우선)
_LINUX_FONT_CANDIDATES = [
    (
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    ),  # fonts-nanum (Render buildCommand에서 설치)
    (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ),  # fonts-noto-cjk
]

# Windows 시스템 한글 폰트 후보 경로 (맑은 고딕 우선)
_WINDOWS_FONT_CANDIDATES = [
    (r"C:\Windows\Fonts\malgun.ttf",    r"C:\Windows\Fonts\malgunbd.ttf"),   # 맑은 고딕
    (r"C:\Windows\Fonts\gulim.ttc",     r"C:\Windows\Fonts\gulim.ttc"),      # 굴림
    (r"C:\Windows\Fonts\batang.ttc",    r"C:\Windows\Fonts\batang.ttc"),     # 바탕
]

_fonts_registered = False


def _find_korean_font() -> tuple[str | None, str | None]:
    """사용 가능한 한글 폰트 경로 반환 (regular, bold)"""
    # 1순위: 프로젝트 내 NotoSansKR
    noto_regular = os.path.join(FONT_DIR, "NotoSansKR-Regular.ttf")
    noto_bold = os.path.join(FONT_DIR, "NotoSansKR-Bold.ttf")
    if os.path.exists(noto_regular):
        return noto_regular, noto_bold if os.path.exists(noto_bold) else noto_regular

    # 2순위: Linux 시스템 한글 폰트 (Render 환경 — fonts-nanum / fonts-noto-cjk)
    for reg_path, bold_path in _LINUX_FONT_CANDIDATES:
        if os.path.exists(reg_path):
            return reg_path, bold_path if os.path.exists(bold_path) else reg_path

    # 3순위: Windows 시스템 한글 폰트
    for reg_path, bold_path in _WINDOWS_FONT_CANDIDATES:
        if os.path.exists(reg_path):
            return reg_path, bold_path if os.path.exists(bold_path) else reg_path

    return None, None


def _register_fonts():
    global _fonts_registered, FONT_REGULAR, FONT_BOLD
    if _fonts_registered:
        return

    regular_path, bold_path = _find_korean_font()

    if regular_path:
        try:
            pdfmetrics.registerFont(TTFont(FONT_REGULAR, regular_path))
            logger.info(f"한글 폰트 등록: {regular_path}")
            if bold_path and bold_path != regular_path:
                pdfmetrics.registerFont(TTFont(FONT_BOLD, bold_path))
            else:
                FONT_BOLD = FONT_REGULAR
        except Exception as e:
            logger.warning(f"폰트 등록 실패: {e}. 기본 폰트 사용.")
            FONT_REGULAR = "Helvetica"
            FONT_BOLD = "Helvetica-Bold"
    else:
        logger.warning("한글 폰트를 찾을 수 없습니다. 영문 기본 폰트 사용.")
        FONT_REGULAR = "Helvetica"
        FONT_BOLD = "Helvetica-Bold"

    _fonts_registered = True


def build_report(
    user_profile: UserProfile,
    portfolio: Portfolio,
    simulation: SimulationResult,
    ai_content: AIContent,
    market_snapshot: MarketSnapshot,
    charts: dict[str, bytes],
) -> bytes:
    """
    5페이지 PDF 리포트 생성
    charts: {"pie": bytes, "line": bytes, "stacked_bar": bytes, "rebalancing": bytes}
    Returns: PDF bytes
    """
    _register_fonts()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title="포트폴리오 AI 분석 리포트",
        author="자산배분 AI",
    )

    styles = _build_styles()
    story = []

    # Page 1: 표지
    story.extend(_build_cover_page(user_profile, portfolio, ai_content, styles))
    story.append(PageBreak())

    # Page 2: 현재 포트폴리오 진단
    story.extend(_build_portfolio_page(portfolio, ai_content, charts.get("pie"), styles))
    story.append(PageBreak())

    # Page 3: 5년 시뮬레이션
    story.extend(_build_simulation_page(simulation, ai_content, charts.get("line"), charts.get("stacked_bar"), styles))
    story.append(PageBreak())

    # Page 4: 리밸런싱 추천
    story.extend(_build_rebalancing_page(ai_content, charts.get("rebalancing"), styles))
    story.append(PageBreak())

    # Page 5: 시장 환경 & 주의사항
    story.extend(_build_market_page(market_snapshot, ai_content, styles))

    doc.build(story, onFirstPage=_add_header_footer, onLaterPages=_add_header_footer)

    buf.seek(0)
    return buf.getvalue()


def _build_styles() -> dict:
    """커스텀 스타일 정의"""
    return {
        "cover_title": ParagraphStyle(
            "CoverTitle",
            fontName=FONT_BOLD,
            fontSize=26,
            textColor=COLOR_WHITE,
            alignment=1,  # center
            spaceAfter=10,
        ),
        "cover_subtitle": ParagraphStyle(
            "CoverSubtitle",
            fontName=FONT_REGULAR,
            fontSize=14,
            textColor=COLOR_GOLD,
            alignment=1,
            spaceAfter=6,
        ),
        "cover_body": ParagraphStyle(
            "CoverBody",
            fontName=FONT_REGULAR,
            fontSize=11,
            textColor=COLOR_WHITE,
            alignment=1,
            spaceAfter=4,
        ),
        "section_title": ParagraphStyle(
            "SectionTitle",
            fontName=FONT_BOLD,
            fontSize=16,
            textColor=COLOR_NAVY,
            spaceBefore=12,
            spaceAfter=8,
            borderPad=4,
        ),
        "subsection_title": ParagraphStyle(
            "SubsectionTitle",
            fontName=FONT_BOLD,
            fontSize=12,
            textColor=COLOR_NAVY,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "Body",
            fontName=FONT_REGULAR,
            fontSize=10,
            textColor=COLOR_DARK_GRAY,
            spaceAfter=4,
            leading=16,
        ),
        "caption": ParagraphStyle(
            "Caption",
            fontName=FONT_REGULAR,
            fontSize=8,
            textColor=COLOR_DARK_GRAY,
            alignment=1,
            spaceAfter=4,
        ),
        "disclaimer": ParagraphStyle(
            "Disclaimer",
            fontName=FONT_REGULAR,
            fontSize=7,
            textColor=colors.gray,
            spaceAfter=2,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            fontName=FONT_REGULAR,
            fontSize=10,
            textColor=COLOR_DARK_GRAY,
            leftIndent=15,
            spaceAfter=3,
            leading=15,
        ),
        "metric_label": ParagraphStyle(
            "MetricLabel",
            fontName=FONT_REGULAR,
            fontSize=9,
            textColor=COLOR_WHITE,
            alignment=1,
        ),
        "metric_value": ParagraphStyle(
            "MetricValue",
            fontName=FONT_BOLD,
            fontSize=16,
            textColor=COLOR_GOLD,
            alignment=1,
        ),
    }


def _build_cover_page(
    user_profile: UserProfile,
    portfolio: Portfolio,
    ai_content: AIContent,
    styles: dict,
) -> list:
    """Page 1: 표지"""
    story = []

    # 상단 네이비 배너 영역 (배경을 Table로 표현)
    banner_data = [
        [Paragraph("포트폴리오 AI 분석 리포트", styles["cover_title"])],
        [Paragraph("AI 기반 맞춤형 자산 배분 진단", styles["cover_subtitle"])],
        [Spacer(1, 8)],
        [Paragraph(f"생성일: {datetime.now(KST).strftime('%Y년 %m월 %d일')}", styles["cover_body"])],
    ]
    banner_table = Table(banner_data, colWidths=[PAGE_WIDTH - 2 * MARGIN])
    banner_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_NAVY),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 20),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 20),
        ("LEFTPADDING", (0, 0), (-1, -1), 20),
        ("RIGHTPADDING", (0, 0), (-1, -1), 20),
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 15))

    # 리스크 등급 배지
    grade_color = {
        "안정형": COLOR_GREEN,
        "중립형": COLOR_GOLD,
        "공격형": COLOR_RED,
    }.get(ai_content.risk_grade, COLOR_GOLD)

    grade_data = [[
        Paragraph(f"리스크 등급", ParagraphStyle(
            "GradeLabel", fontName=FONT_REGULAR, fontSize=10,
            textColor=COLOR_WHITE, alignment=1,
        )),
        Paragraph(f"{ai_content.risk_grade}", ParagraphStyle(
            "GradeValue", fontName=FONT_BOLD, fontSize=20,
            textColor=COLOR_WHITE, alignment=1,
        )),
        Paragraph(f"리스크 점수", ParagraphStyle(
            "ScoreLabel", fontName=FONT_REGULAR, fontSize=10,
            textColor=COLOR_WHITE, alignment=1,
        )),
        Paragraph(f"{ai_content.risk_score} / 100", ParagraphStyle(
            "ScoreValue", fontName=FONT_BOLD, fontSize=20,
            textColor=COLOR_GOLD, alignment=1,
        )),
    ]]
    grade_table = Table(grade_data, colWidths=[(PAGE_WIDTH - 2 * MARGIN) / 4] * 4)
    grade_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (1, -1), grade_color),
        ("BACKGROUND", (2, 0), (3, -1), COLOR_NAVY),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 15),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 15),
    ]))
    story.append(grade_table)
    story.append(Spacer(1, 15))

    # 기본 정보 테이블
    info_data = [
        ["항목", "내용"],
        ["투자자 나이", f"{user_profile.age}세"],
        ["투자 목표", user_profile.investment_goal.value],
        ["리스크 성향", user_profile.risk_tolerance.value],
        ["총 투자 자산", f"{portfolio.total_asset:,}만원"],
        ["월 적립액", f"{portfolio.monthly_saving:,}만원"],
        ["분석 기준일", datetime.now(KST).strftime("%Y년 %m월 %d일")],
    ]
    info_table = Table(info_data, colWidths=[80 * mm, PAGE_WIDTH - 2 * MARGIN - 80 * mm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 11),
        ("BACKGROUND", (0, 1), (-1, -1), COLOR_LIGHT_GRAY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLOR_WHITE, COLOR_LIGHT_GRAY]),
        ("FONTNAME", (0, 1), (-1, -1), FONT_REGULAR),
        ("FONTSIZE", (0, 1), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 15))

    # 면책 고지
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_GOLD))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        "※ 본 리포트는 정보 제공 목적으로만 작성되었으며, 투자 권유 또는 투자 자문이 아닙니다. "
        "모든 투자는 원금 손실 위험이 있으며, 과거 수익률이 미래 수익을 보장하지 않습니다.",
        styles["disclaimer"],
    ))

    return story


def _build_portfolio_page(
    portfolio: Portfolio,
    ai_content: AIContent,
    pie_chart_bytes: bytes | None,
    styles: dict,
) -> list:
    """Page 2: 현재 포트폴리오 진단"""
    story = []

    story.append(Paragraph("현재 포트폴리오 진단", styles["section_title"]))
    story.append(HRFlowable(width="100%", thickness=2, color=COLOR_GOLD))
    story.append(Spacer(1, 4))

    # 파이차트
    if pie_chart_bytes:
        chart_img = Image(io.BytesIO(pie_chart_bytes), width=120 * mm, height=58 * mm)
        story.append(chart_img)
        story.append(Spacer(1, 2))
    else:
        story.append(Paragraph("(차트 생성 실패 — 아래 자산 구성 표를 참고하세요)", styles["caption"]))

    # 자산 배분 테이블 (compact 패딩)
    story.append(Paragraph("자산 구성", styles["subsection_title"]))
    table_data = [["자산명", "유형", "비중", "투자금액 (추정)"]]
    total_asset = portfolio.total_asset
    for alloc in portfolio.allocations:
        amount = total_asset * alloc.weight / 100
        table_data.append([
            alloc.asset_name,
            alloc.asset_type.value,
            f"{alloc.weight:.1f}%",
            f"{amount:,.0f}만원",
        ])

    # 유효 너비 170mm (A4 210mm - 좌우 마진 20mm×2)
    asset_table = Table(table_data, colWidths=[58 * mm, 40 * mm, 22 * mm, 50 * mm])
    asset_table.setStyle(_compact_table_style())
    story.append(asset_table)
    story.append(Spacer(1, 4))

    # AI 진단
    story.append(Paragraph("AI 종합 진단", styles["subsection_title"]))
    story.append(Paragraph(ai_content.portfolio_diagnosis, ParagraphStyle(
        "DiagBody", fontName=FONT_REGULAR, fontSize=9,
        textColor=COLOR_DARK_GRAY, spaceAfter=3, leading=14,
    )))
    story.append(Spacer(1, 4))

    # 강점 / 약점 (KeepTogether로 헤더+내용 같은 페이지 유지)
    _sw_body = lambda items, prefix: [
        Paragraph(f"{prefix} {_xe(item)}", ParagraphStyle(
            f"sw_{prefix}", fontName=FONT_REGULAR, fontSize=8.5,
            textColor=COLOR_DARK_GRAY, leading=12, spaceAfter=2,
        ))
        for item in items
    ]
    sw_data = [
        [
            Paragraph("강점", ParagraphStyle("SwTitle", fontName=FONT_BOLD, fontSize=11,
                                             textColor=COLOR_WHITE, alignment=1)),
            Paragraph("약점", ParagraphStyle("SwTitle", fontName=FONT_BOLD, fontSize=11,
                                             textColor=COLOR_WHITE, alignment=1)),
        ],
        [
            _sw_body(ai_content.strengths, "✓"),
            _sw_body(ai_content.weaknesses, "△"),
        ],
    ]
    sw_table = Table(sw_data, colWidths=[(PAGE_WIDTH - 2 * MARGIN) / 2] * 2)
    sw_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), COLOR_GREEN),
        ("BACKGROUND", (1, 0), (1, 0), COLOR_RED),
        ("BACKGROUND", (0, 1), (0, 1), colors.HexColor("#f0fff0")),
        ("BACKGROUND", (1, 1), (1, 1), colors.HexColor("#fff0f0")),
        ("FONTNAME", (0, 1), (-1, -1), FONT_REGULAR),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("TEXTCOLOR", (0, 1), (-1, -1), COLOR_DARK_GRAY),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
    ]))
    story.append(KeepTogether(sw_table))

    return story


def _build_simulation_page(
    simulation: SimulationResult,
    ai_content: AIContent,
    line_chart_bytes: bytes | None,
    stacked_bar_bytes: bytes | None,
    styles: dict,
) -> list:
    """Page 3: 5년 시뮬레이션"""
    story = []

    story.append(Paragraph("5년 자산 성장 시뮬레이션", styles["section_title"]))
    story.append(HRFlowable(width="100%", thickness=2, color=COLOR_GOLD))
    story.append(Spacer(1, 6))

    # 총 투자 원금 요약
    total_invested = simulation.initial_value + simulation.monthly_contribution * 60
    story.append(Paragraph(
        f"초기 자산 {simulation.initial_value:,.0f}만원 + 월 {simulation.monthly_contribution:,.0f}만원 × 60개월 "
        f"= 5년간 총 투자 원금 {total_invested:,.0f}만원",
        ParagraphStyle("InvSummary", fontName=FONT_REGULAR, fontSize=9,
                       textColor=COLOR_NAVY, spaceAfter=6, leading=13,
                       backColor=colors.HexColor("#f0f4ff"), leftIndent=6, rightIndent=6),
    ))
    story.append(Spacer(1, 4))

    # 시나리오 요약 카드 — 셀 내용을 Paragraph로 감싸 줄바꿈 허용
    _cell = lambda text, bold=False, align=1, color=COLOR_DARK_GRAY: Paragraph(
        _xe(str(text)),
        ParagraphStyle(
            f"sc_{text[:4]}",
            fontName=FONT_BOLD if bold else FONT_REGULAR,
            fontSize=8,
            textColor=color,
            alignment=align,
            leading=12,
        ),
    )
    _head = lambda text: Paragraph(
        text,
        ParagraphStyle(
            f"sh_{text[:4]}",
            fontName=FONT_BOLD,
            fontSize=9,
            textColor=COLOR_WHITE,
            alignment=1,
            leading=12,
        ),
    )

    # 컬럼: 시나리오 | 5년 후 예상 자산 | 연수익률* | 코멘트
    W = PAGE_WIDTH - 2 * MARGIN
    col_widths = [20 * mm, 36 * mm, 22 * mm, W - 78 * mm]

    scenario_data = [
        [_head("시나리오"), _head("5년 후 예상 자산"), _head("연수익률*"), _head("코멘트")],
        [
            _cell("비관", bold=True, color=COLOR_RED),
            _cell(f"{simulation.bear.final_value:,.0f}만원"),
            _cell(f"{simulation.bear.cagr:.1f}%"),
            _cell(ai_content.scenario_commentary.get("bear", "-"), align=0),
        ],
        [
            _cell("기본", bold=True, color=colors.HexColor("#b8860b")),
            _cell(f"{simulation.base.final_value:,.0f}만원"),
            _cell(f"{simulation.base.cagr:.1f}%"),
            _cell(ai_content.scenario_commentary.get("base", "-"), align=0),
        ],
        [
            _cell("낙관", bold=True, color=COLOR_GREEN),
            _cell(f"{simulation.bull.final_value:,.0f}만원"),
            _cell(f"{simulation.bull.cagr:.1f}%"),
            _cell(ai_content.scenario_commentary.get("bull", "-"), align=0),
        ],
    ]
    scenario_table = Table(scenario_data, colWidths=col_widths, repeatRows=1)
    scenario_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_NAVY),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#fff3f3")),
        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#fffef0")),
        ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#f0fff4")),
        ("ALIGN", (0, 0), (2, -1), "CENTER"),
        ("ALIGN", (3, 0), (3, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
    ]))
    story.append(scenario_table)
    story.append(Paragraph(
        "* 연수익률 = (5년 후 예상 자산 ÷ 총 투자 원금)^(1/5) − 1 로 계산한 연환산 수익률 (총 투자 원금 = 초기 자산 + 월 적립 합계)",
        ParagraphStyle("SimNote", fontName=FONT_REGULAR, fontSize=7, textColor=colors.gray, spaceAfter=6, leading=10),
    ))
    story.append(Spacer(1, 4))

    # 꺾은선 그래프
    if line_chart_bytes:
        chart_img = Image(io.BytesIO(line_chart_bytes), width=155 * mm, height=78 * mm)
        story.append(chart_img)
        story.append(Spacer(1, 8))
    else:
        story.append(Paragraph("(시뮬레이션 차트 생성 실패 — 위 시나리오 표를 참고하세요)", styles["caption"]))

    # 스택 바 차트
    if stacked_bar_bytes:
        bar_img = Image(io.BytesIO(stacked_bar_bytes), width=130 * mm, height=78 * mm)
        story.append(bar_img)
    else:
        story.append(Paragraph("(연도별 자산 구성 차트 생성 실패)", styles["caption"]))

    return story


def _build_rebalancing_page(
    ai_content: AIContent,
    rebalancing_chart_bytes: bytes | None,
    styles: dict,
) -> list:
    """Page 4: 리밸런싱 추천"""
    story = []

    story.append(Paragraph("리밸런싱 추천", styles["section_title"]))
    story.append(HRFlowable(width="100%", thickness=2, color=COLOR_GOLD))
    story.append(Spacer(1, 8))

    # 비교 파이차트 — 실제 변경이 있는 경우에만 표시
    all_same = all(
        abs(rec.get("recommended_weight", 0) - rec.get("current_weight", 0)) < 0.5
        for rec in ai_content.rebalancing_recommendations
    )
    if rebalancing_chart_bytes and not all_same:
        chart_img = Image(io.BytesIO(rebalancing_chart_bytes), width=155 * mm, height=68 * mm)
        story.append(chart_img)
        story.append(Spacer(1, 8))
    elif not rebalancing_chart_bytes and not all_same:
        story.append(Paragraph("(리밸런싱 비교 차트 생성 실패 — 아래 조정 표를 참고하세요)", styles["caption"]))
    elif all_same:
        story.append(Paragraph(
            "현재 포트폴리오 비중이 리스크 성향 및 시장 상황에 적합하여 별도 리밸런싱이 필요하지 않습니다.",
            ParagraphStyle("RebNote", fontName=FONT_REGULAR, fontSize=10, textColor=COLOR_NAVY,
                           backColor=colors.HexColor("#f0f4ff"), spaceAfter=8, leading=15,
                           leftIndent=10, rightIndent=10, spaceBefore=8),
        ))
        story.append(Spacer(1, 4))

    # 리밸런싱 테이블
    story.append(Paragraph("자산별 조정 방향", styles["subsection_title"]))

    # 리밸런싱 테이블 — Paragraph로 줄바꿈 허용
    _rh = lambda t: Paragraph(_xe(t), ParagraphStyle(
        f"rh{t[:3]}", fontName=FONT_BOLD, fontSize=9,
        textColor=COLOR_WHITE, alignment=1, leading=12,
    ))
    _rc = lambda t, align=1: Paragraph(_xe(str(t)), ParagraphStyle(
        f"rc{t[:3]}", fontName=FONT_REGULAR, fontSize=9,
        textColor=COLOR_DARK_GRAY, alignment=align, leading=13,
    ))

    DIRECTION_COLOR = {"증가": COLOR_GREEN, "감소": COLOR_RED, "유지": COLOR_DARK_GRAY, "추가": COLOR_NAVY}
    _rd = lambda direction: Paragraph(
        {"증가": "▲ 증가", "감소": "▼ 감소", "유지": "─ 유지", "추가": "+ 추가"}.get(direction, "─ 유지"),
        ParagraphStyle(
            f"rd{direction}", fontName=FONT_BOLD, fontSize=9,
            textColor=DIRECTION_COLOR.get(direction, COLOR_DARK_GRAY),
            alignment=1, leading=12,
        ),
    )

    W = PAGE_WIDTH - 2 * MARGIN
    # 자산명(44) + 현재(22) + 추천(22) + 방향(22) + 조정이유(나머지)
    col_widths_rec = [44 * mm, 22 * mm, 22 * mm, 22 * mm, W - 110 * mm]

    rec_data = [[_rh("자산명"), _rh("현재 비중"), _rh("추천 비중"), _rh("방향"), _rh("조정 이유")]]
    for rec in ai_content.rebalancing_recommendations:
        direction = rec.get("direction", "유지")
        rec_data.append([
            _rc(rec.get("asset_name", "-"), align=0),
            _rc(f"{rec.get('current_weight', 0):.1f}%"),
            _rc(f"{rec.get('recommended_weight', 0):.1f}%"),
            _rd(direction),
            _rc(rec.get("reason", "-"), align=0),
        ])

    rec_table = Table(rec_data, colWidths=col_widths_rec, repeatRows=1)
    rec_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLOR_WHITE, COLOR_LIGHT_GRAY]),
        ("ALIGN", (1, 0), (3, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (4, 0), (4, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
    ]))
    story.append(rec_table)

    return story


def _build_market_page(
    market_snapshot: MarketSnapshot,
    ai_content: AIContent,
    styles: dict,
) -> list:
    """Page 5: 시장 환경 & 주의사항"""
    story = []

    story.append(Paragraph("시장 환경 & 주의사항", styles["section_title"]))
    story.append(HRFlowable(width="100%", thickness=2, color=COLOR_GOLD))
    story.append(Spacer(1, 8))

    # 시장 지표 스냅샷
    story.append(Paragraph("분석 시점 시장 스냅샷", styles["subsection_title"]))
    # 실시간 수집 실패 시 기본값이 그대로 출력되는 것을 방지 — 기본값이면 "(참고값)" 표기
    _ref = lambda v, d: " (참고값)" if v == d else ""
    market_data = [
        ["지표", "현재 값"],
        ["S&P 500",             f"{market_snapshot.sp500:,.0f}{_ref(market_snapshot.sp500, 5000.0)}"],
        ["코스피",               f"{market_snapshot.kospi:,.0f}{_ref(market_snapshot.kospi, 2500.0)}"],
        ["미국 10년 국채 금리",   f"{market_snapshot.us_10y_yield:.2f}%{_ref(market_snapshot.us_10y_yield, 4.3)}"],
        ["한국 기준금리",         f"{market_snapshot.kr_base_rate:.2f}%{_ref(market_snapshot.kr_base_rate, 3.5)}"],
        ["달러/원 환율",          f"{market_snapshot.usd_krw:,.0f}원{_ref(market_snapshot.usd_krw, 1350.0)}"],
        ["금 현물 가격",          f"${market_snapshot.gold_price:,.0f}{_ref(market_snapshot.gold_price, 2300.0)}"],
        ["미국 CPI (인플레이션)", f"{market_snapshot.cpi_us:.1f}%{_ref(market_snapshot.cpi_us, 3.2)}"],
        ["데이터 기준일",         market_snapshot.fetched_at.strftime("%Y-%m-%d %H:%M")],
    ]
    market_table = Table(market_data, colWidths=[90 * mm, 80 * mm])
    market_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 1), (-1, -1), FONT_REGULAR),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLOR_WHITE, COLOR_LIGHT_GRAY]),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
    ]))
    story.append(market_table)
    story.append(Spacer(1, 12))

    # AI 시장 코멘트
    story.append(Paragraph("현재 시장이 내 포트폴리오에 미치는 영향", styles["subsection_title"]))
    story.append(Paragraph(ai_content.market_commentary, styles["body"]))
    story.append(Spacer(1, 10))

    # 맞춤 주의사항
    story.append(Paragraph("맞춤 주의사항", styles["subsection_title"]))
    for i, caution in enumerate(ai_content.cautions, 1):
        story.append(Paragraph(f"{i}. {caution}", styles["bullet"]))
    story.append(Spacer(1, 15))

    # 면책 고지
    story.append(HRFlowable(width="100%", thickness=1, color=colors.gray))
    story.append(Spacer(1, 5))
    disclaimer_texts = [
        "【면책 고지】",
        "본 리포트는 인공지능(AI)이 생성한 정보 제공 목적의 자료로서, 투자 권유 또는 투자 자문에 해당하지 않습니다.",
        "모든 투자에는 원금 손실의 위험이 있으며, 과거의 수익률이 미래의 수익을 보장하지 않습니다.",
        "본 리포트에 포함된 시뮬레이션 결과는 예상치이며 실제 결과와 다를 수 있습니다.",
        "투자 결정은 본인의 판단과 책임 하에 이루어져야 하며, 필요 시 공인 재무설계사 또는 투자 전문가의 상담을 받으시기 바랍니다.",
        f"리포트 생성일: {datetime.now(KST).strftime('%Y년 %m월 %d일')} | 자산배분 AI (정보 제공 서비스)",
    ]
    for text in disclaimer_texts:
        story.append(Paragraph(text, styles["disclaimer"]))

    return story


def _compact_table_style() -> TableStyle:
    """자산구성 테이블용 compact 스타일 (행 높이 최소화)"""
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTNAME", (0, 1), (-1, -1), FONT_REGULAR),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLOR_WHITE, COLOR_LIGHT_GRAY]),
        ("ALIGN", (2, 1), (3, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
    ])


def _table_style() -> TableStyle:
    """기본 테이블 스타일"""
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTNAME", (0, 1), (-1, -1), FONT_REGULAR),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [COLOR_WHITE, COLOR_LIGHT_GRAY]),
        ("ALIGN", (2, 1), (3, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
    ])


def _add_header_footer(canvas_obj: canvas.Canvas, doc: SimpleDocTemplate):
    """모든 페이지에 헤더/푸터 추가"""
    canvas_obj.saveState()

    # 헤더
    canvas_obj.setFillColor(COLOR_NAVY)
    canvas_obj.rect(0, PAGE_HEIGHT - 12 * mm, PAGE_WIDTH, 12 * mm, fill=1, stroke=0)
    canvas_obj.setFillColor(COLOR_GOLD)
    canvas_obj.setFont(FONT_BOLD if FONT_BOLD != "Helvetica-Bold" else "Helvetica-Bold", 10)
    canvas_obj.drawString(MARGIN, PAGE_HEIGHT - 8 * mm, "포트폴리오 AI 분석 리포트")
    canvas_obj.setFont(FONT_REGULAR if FONT_REGULAR != "Helvetica" else "Helvetica", 8)
    canvas_obj.setFillColor(COLOR_WHITE)
    canvas_obj.drawRightString(
        PAGE_WIDTH - MARGIN,
        PAGE_HEIGHT - 8 * mm,
        datetime.now(KST).strftime("%Y.%m.%d"),
    )

    # 푸터
    canvas_obj.setFillColor(COLOR_LIGHT_GRAY)
    canvas_obj.rect(0, 0, PAGE_WIDTH, 8 * mm, fill=1, stroke=0)
    canvas_obj.setFillColor(COLOR_DARK_GRAY)
    canvas_obj.setFont(FONT_REGULAR if FONT_REGULAR != "Helvetica" else "Helvetica", 7)
    canvas_obj.drawString(MARGIN, 3 * mm, "※ 본 리포트는 정보 제공 목적으로만 작성되었으며, 투자 권유가 아닙니다.")
    canvas_obj.drawRightString(
        PAGE_WIDTH - MARGIN,
        3 * mm,
        f"Page {doc.page}",
    )

    canvas_obj.restoreState()
