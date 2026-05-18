# 포트폴리오 AI 분석 리포트

AI 기반 맞춤형 자산 배분 진단 + 5년 시뮬레이션 + PDF 리포트 생성 서비스<br>
투자 판단을 대신하기보다, 자산 비중과 흐름을 한눈에 파악하기 위해 만들었습니다.

# 만든 이유

자산이 여러 계좌와 투자 상품에 흩어져 있으면 전체 비중과 흐름을 한눈에 파악하기 어렵다고 느꼈습니다.<br>
이 프로젝트는 수익률을 예측하거나 투자 결정을 대신하기 위한 도구가 아니라,<br>
개인 자산 현황을 정리하고 AI를 활용해 점검 관점을 얻기 위해 만들었습니다. 

## 사용 목적

- 자산 구성 비중을 한눈에 확인하기
- 투자 상품별 분산 상태 점검하기
- 현금, 주식, ETF 등 자산 흐름 정리하기
- AI를 활용해 포트폴리오에 대한 참고 리포트 생성하기
- 장기 투자 관점에서 자산 상태를 기록하기

## 주요 기능

- 자산 항목 입력 및 관리
- 자산군별 비중 시각화
- 포트폴리오 구성 요약
- AI 기반 분석 리포트 생성
- 장기 투자 관점의 참고 코멘트 제공

## AI 분석 기준

AI 분석은 입력된 자산 정보를 바탕으로<br>
자산군 비중, 분산 상태, 리스크 노출, 장기 투자<br>
관점의 참고 의견을 정리하는 방식으로 구성했습니다.<br>

분석 결과는 투자 권유가 아니라<br>
개인 자산 점검을 돕기 위한 참고 정보로<br>
활용하는 것을 목표로 합니다.

## 환경 변수

### 백엔드 (`backend/.env`)

| 변수 | 설명 | 필수 |
|------|------|------|
| `GEMINI_API_KEY` | Google Gemini API 키 ([무료 발급](https://aistudio.google.com/app/apikey)) | 권장 (없으면 fallback 분석기 사용) |

### 프론트엔드 (`frontend/.env.local`)

| 변수 | 설명 |
|------|------|
| `NEXT_PUBLIC_API_URL` | 백엔드 API URL (기본: http://localhost:8000) |

---


## 기술 스택

| 항목 | 기술 |
|------|------|
| 프론트엔드 | Next.js 16, React 18, TypeScript, Tailwind CSS |
| 백엔드 | FastAPI, Python 3.11+ |
| AI | Google Gemini API (gemini-2.5-flash, 무료 티어) |
| 시장 데이터 | yfinance, FRED API |
| PDF 생성 | ReportLab |
| 차트 | matplotlib |
| 상태 저장 | Redis (미설정 시 인메모리 fallback) |
| 파일 저장 | Cloudflare R2 (로컬 개발: 파일시스템) |

---

## 배포

### Vercel (프론트엔드)

```bash
cd frontend
npx vercel --prod
```

환경 변수: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_TOSS_CLIENT_KEY`

### Render (백엔드)

```bash
# render.yaml 사용
# Render 대시보드에서 Web Service 생성 후 rootDir=backend로 배포
```

환경 변수: 위 표의 백엔드 변수 모두 설정

---

## 파일 구조

```
portfolio-report/
├── backend/
│   ├── main.py                   # FastAPI 앱 진입점
│   ├── config.py                 # 환경 변수 설정
│   ├── models/
│   │   ├── portfolio.py          # 포트폴리오 Pydantic 모델
│   │   └── report.py             # 리포트 데이터 모델
│   ├── routers/
│   │   ├── analyze.py            # 분석 API
│   │   ├── payment.py            # 결제 처리
│   │   └── report.py             # PDF 생성 + 다운로드
│   ├── services/
│   │   ├── market_data.py        # 시장 데이터 수집 (yfinance, FRED)
│   │   ├── simulator.py          # 5년 시뮬레이션
│   │   ├── ai_engine.py          # Gemini API 연동
│   │   ├── fallback_analyzer.py  # Gemini 없을 때 rule-based 분석 엔진
│   │   ├── chart_generator.py    # matplotlib 차트
│   │   ├── pdf_generator.py      # ReportLab PDF 생성
│   │   ├── storage.py            # Redis / 인메모리 상태 저장 (report_token)
│   │   └── email_service.py      # 이메일 발송 (SMTP)
│   ├── assets/fonts/             # NotoSansKR 폰트 파일
│   ├── generated_reports/        # 로컬 PDF 저장 (개발)
│   ├── requirements.txt          # 프로덕션 의존성
│   ├── requirements-dev.txt      # 개발·테스트 의존성 (pytest)
│   ├── pytest.ini                # pytest 설정
│   ├── conftest.py               # 공용 fixture
│   ├── test_pipeline.py          # 파이프라인 통합 테스트 (PDF 생성)
│   ├── test_ai_engine.py         # ai_engine 단위 테스트
│   ├── test_fallback_analyzer.py # fallback_analyzer 단위 테스트
│   ├── test_chart_generator.py   # chart_generator 스모크 테스트
│   ├── test_pdf_generator.py     # pdf_generator 스모크 테스트
│   └── test_market_data.py       # market_data 단위 테스트
│
└── frontend/
    ├── app/
    │   ├── page.tsx              # 랜딩 페이지
    │   ├── input/
    │   │   ├── step1/page.tsx    # 기본 정보
    │   │   ├── step2/page.tsx    # 포트폴리오 입력
    │   │   └── step3/page.tsx    # 확인 + 분석 시작
    │   ├── preview/page.tsx      # 무료 미리보기
    │   └── payment/
    │       ├── page.tsx          # 결제 화면
    │       ├── complete/page.tsx # 결제 완료 + 다운로드
    │       └── fail/page.tsx     # 결제 실패
    ├── components/
    │   ├── PortfolioChart.tsx    # 파이차트 컴포넌트
    │   ├── BlurSection.tsx       # 블러 처리 컴포넌트
    │   └── StepProgress.tsx      # 진행 바
    ├── context/InputContext.tsx  # 전역 상태 관리
    ├── lib/api.ts                # API 클라이언트
    └── types/portfolio.ts        # TypeScript 타입
```
