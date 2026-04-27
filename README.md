# 포트폴리오 AI 분석 리포트

> AI 기반 맞춤형 자산 배분 진단 + 5년 시뮬레이션 + PDF 리포트 생성 서비스

## 빠른 시작

### 1. 백엔드 설정

```bash
cd backend
pip install -r requirements.txt

# 환경 변수 설정
cp .env.example .env
# .env 파일에 API 키 입력

# 폰트 설치 (한글 PDF 렌더링용)
python download_fonts.py
# 안내에 따라 NotoSansKR 폰트를 assets/fonts/ 에 저장

# 서버 실행
uvicorn main:app --reload
```

백엔드: http://localhost:8000
API 문서: http://localhost:8000/docs

### 2. 프론트엔드 설정

```bash
cd frontend
npm install

# 환경 변수 설정
cp .env.local.example .env.local

# 개발 서버 실행
npm run dev
```

프론트엔드: http://localhost:3000

### 3. 파이프라인 테스트 (결제 없이 PDF 생성 확인)

```bash
cd backend
python test_pipeline.py
# test_report.pdf 파일이 생성됩니다
```

---

## 환경 변수

### 백엔드 (`backend/.env`)

| 변수 | 설명 | 필수 |
|------|------|------|
| `GEMINI_API_KEY` | Google Gemini API 키 ([무료 발급](https://aistudio.google.com/app/apikey)) | 권장 (없으면 fallback 분석기 사용) |
| `FRED_API_KEY` | FRED API 키 (금리/CPI 데이터) | 선택 |
| `TOSS_CLIENT_KEY` | 토스페이먼츠 클라이언트 키 | 결제 필요 시 |
| `TOSS_SECRET_KEY` | 토스페이먼츠 시크릿 키 | 결제 필요 시 |
| `REDIS_URL` | Redis URL (결제/리포트 상태 저장) | 배포 권장 |
| `R2_ACCOUNT_ID` | Cloudflare R2 Account ID | R2 사용 시 |
| `R2_ACCESS_KEY` | Cloudflare R2 Access Key | R2 사용 시 |
| `R2_SECRET_KEY` | Cloudflare R2 Secret Key | R2 사용 시 |
| `R2_BUCKET` | Cloudflare R2 버킷명 | 기본 `portfolio-reports` |
| `AWS_ACCESS_KEY_ID` | AWS 액세스 키 | S3 사용 시 |
| `AWS_SECRET_ACCESS_KEY` | AWS 시크릿 키 | S3 사용 시 |
| `AWS_REGION` | AWS 리전 | 기본 `ap-northeast-2` |
| `S3_BUCKET` | S3 버킷명 | S3 사용 시 |
| `USE_LOCAL_STORAGE` | `true` = 로컬 저장 (개발) | 기본 true |
| `FRONTEND_URL` | 프론트엔드 URL (CORS 허용) | 배포 시 필수 |
| `REPORT_PRICE_KRW` | 리포트 가격 (원) | 기본 4900 |
| `SMTP_HOST` | SMTP 서버 호스트 | 이메일 발송 시 |
| `SMTP_PORT` | SMTP 포트 | 기본 587 |
| `SMTP_USER` | SMTP 사용자 | 이메일 발송 시 |
| `SMTP_PASSWORD` | SMTP 비밀번호 | 이메일 발송 시 |
| `SMTP_FROM` | 발신자 주소 | 선택 |

### 프론트엔드 (`frontend/.env.local`)

| 변수 | 설명 |
|------|------|
| `NEXT_PUBLIC_API_URL` | 백엔드 API URL (기본: http://localhost:8000) |
| `NEXT_PUBLIC_TOSS_CLIENT_KEY` | 토스페이먼츠 클라이언트 키 |

---

## 개발 모드 특이사항

- **AI 키 없이도 동작**: Gemini API 키가 없으면 fallback 분석기를 사용합니다.
- **결제 없이 테스트**: 토스 시크릿 키가 없으면 개발 모드로 결제 승인 단계가 통과됩니다.
- **상태 저장 fallback**: `REDIS_URL`이 없으면 결제/리포트 상태를 인메모리에 저장하므로 서버 재시작 시 초기화됩니다.
- **로컬 파일 저장**: R2/S3 설정이 없거나 `USE_LOCAL_STORAGE=true`이면 `backend/generated_reports/`에 PDF를 저장합니다.
- **PDF 한글**: `backend/assets/fonts/`에 NotoSansKR 폰트가 없으면 영문 폰트로 대체될 수 있습니다.
- **다운로드 경로**: 리포트 상태 응답의 `download_url`은 저장 방식에 따라 `/report/download/{token}` 또는 `/report/file/{filename}` 형태가 될 수 있습니다.

---

## 기술 스택

| 항목 | 기술 |
|------|------|
| 프론트엔드 | Next.js 16, React 18, TypeScript, Tailwind CSS |
| 백엔드 | FastAPI, Python 3.11+ |
| AI | Google Gemini API (gemini-1.5-flash, 무료 티어) |
| 시장 데이터 | yfinance, FRED API |
| PDF 생성 | ReportLab |
| 차트 | matplotlib |
| 결제 | 토스페이먼츠 |
| 상태 저장 | Redis (미설정 시 인메모리 fallback) |
| 파일 저장 | Cloudflare R2 또는 AWS S3 (로컬 개발: 파일시스템) |

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
│   ├── requirements.txt
│   └── test_pipeline.py          # 파이프라인 테스트
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
