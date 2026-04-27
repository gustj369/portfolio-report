# Project Agent Guide

## 1. Role

You are a careful coding agent working on this repository.

## 2. Core Principles

- Do not make broad changes without explaining the reason.
- Prefer small, reviewable diffs.
- Preserve existing architecture unless there is a clear reason.
- Before editing, summarize the intended change.
- After editing, explain what changed and how to verify it.

## 3. Project Context

- 이 프로젝트의 목적: 사용자의 포트폴리오 정보를 받아 AI 기반 자산 분석, 5년 시뮬레이션, 맞춤 리밸런싱 제안, PDF 리포트 생성을 제공한다.
- 주요 기술 스택:
  - Frontend: Next.js, React, TypeScript, Tailwind CSS
  - Backend: FastAPI, Python, Pydantic
  - Analysis/PDF: Gemini API, yfinance, FRED API, ReportLab, matplotlib
  - Storage/Deploy: Redis, Cloudflare R2 or S3, Vercel, Render
- 핵심 폴더:
  - `frontend/app`: Next.js 페이지와 사용자 플로우
  - `frontend/components`: 재사용 UI 컴포넌트
  - `frontend/context`: 입력 상태 공유
  - `frontend/lib`: 백엔드 API 호출
  - `frontend/types`: 프론트엔드 도메인 타입
  - `backend/routers`: 분석, 결제, 리포트 API 라우터
  - `backend/services`: 시장 데이터, 시뮬레이션, AI 분석, 차트, PDF, 저장소, 이메일 처리
  - `backend/models`: Pydantic 요청/응답/도메인 모델
  - `backend/assets/fonts`: PDF 한글 폰트
  - `backend/generated_reports`: 로컬 개발용 생성 PDF 저장소
- 실행 방법:
  - Backend: `cd backend`, `pip install -r requirements.txt`, `.env.example`을 `.env`로 복사 후 설정, `uvicorn main:app --reload`
  - Frontend: `cd frontend`, `npm install`, `.env.local.example`을 `.env.local`로 복사 후 설정, `npm run dev`
  - 기본 URL: Backend `http://localhost:8000`, Frontend `http://localhost:3000`
- 테스트 방법:
  - Backend health check: `http://localhost:8000/health`
  - Backend API docs: `http://localhost:8000/docs`
  - PDF pipeline smoke test: `cd backend`, `python test_pipeline.py`
  - Frontend build/lint: `cd frontend`, `npm run build`, `npm run lint`

## 4. Coding Style

- 네이밍 규칙:
  - Python은 기존 snake_case 함수/변수와 Pydantic 모델명을 따른다.
  - TypeScript는 기존 camelCase 함수/변수와 PascalCase 컴포넌트를 따른다.
  - API JSON 필드는 현재 백엔드 모델의 snake_case 계약을 유지한다.
- 파일 구조 규칙:
  - API 엔드포인트는 `backend/routers`에 둔다.
  - 비즈니스 로직과 외부 연동은 `backend/services`에 둔다.
  - 공유 도메인 모델은 `backend/models`와 `frontend/types`의 계약을 함께 확인한다.
  - 프론트 화면은 Next.js App Router 구조를 따른다.
- 에러 처리 방식:
  - 백엔드는 사용자 입력 오류에 `422`, 권한/토큰 오류에 `403`, 누락 리소스에 `404`, 처리 실패에 `500` 계열을 사용한다.
  - 외부 API 실패는 가능한 fallback이 있는지 확인하고, 로그를 남긴다.
  - 프론트엔드는 `lib/api.ts`의 API 오류 처리 흐름을 우선 재사용한다.
- 주석 기준:
  - 복잡한 분기, 외부 서비스 fallback, 저장소 선택처럼 맥락이 필요한 곳에만 짧게 남긴다.
  - 코드가 그대로 설명하는 내용을 반복하는 주석은 추가하지 않는다.
- 커밋/PR 기준:
  - 사용자가 요청하지 않으면 커밋, 푸시, PR 생성은 하지 않는다.
  - 변경은 작게 묶고, 변경 파일과 검증 방법을 명확히 보고한다.

## 5. High-Risk Contracts

- API 계약:
  - `backend/models/portfolio.py`와 `frontend/types/portfolio.ts`는 같은 요청/응답 구조를 공유한다.
  - 필드명은 현재 snake_case JSON 계약을 유지한다.
  - 자산군, 투자 목적, 위험 성향 enum을 바꿀 때는 프론트 선택지와 백엔드 검증을 함께 확인한다.
  - 포트폴리오 비중 합계는 백엔드에서 100% 기준으로 검증한다.
- 리포트 생성과 다운로드:
  - 결제 승인 후 발급된 `report_token`으로 `/report/generate`를 호출한다.
  - 생성 상태는 `/report/status/{report_token}`에서 확인한다.
  - R2 사용 시 다운로드는 `/report/download/{report_token}` 백엔드 스트리밍 경로를 사용한다.
  - S3 사용 시 presigned URL이 반환될 수 있다.
  - 로컬 저장 시 PDF는 `backend/generated_reports`에 저장되고 `/report/file/{filename}`로 접근할 수 있다.
- 상태 저장:
  - `REDIS_URL`이 없으면 결제/리포트 상태는 인메모리 fallback에 저장된다.
  - 서버 재시작 후에도 상태가 유지되어야 하는 흐름은 Redis 설정을 전제로 검증한다.
- PDF와 폰트:
  - PDF 관련 변경은 한글 폰트, 줄바꿈, 표/차트 렌더링을 확인한다.
  - 배포 환경은 `render.yaml`의 폰트 설치 명령과 `backend/assets/fonts` fallback을 함께 고려한다.

## 6. Workflow

1. Read related files first.
2. Summarize understanding.
3. Propose a minimal plan.
4. Make small changes.
5. Run or suggest verification.
6. Report changed files and risks.

## 7. Do Not

- 추측으로 대규모 리팩토링하지 않기
- 기존 API 계약을 임의로 바꾸지 않기
- 테스트 없이 핵심 로직 변경하지 않기
- 불필요한 의존성 추가하지 않기
- 비밀 키, 결제 키, API 키를 코드에 직접 넣지 않기
- 사용자가 만든 것으로 보이는 unrelated 변경을 되돌리지 않기
- 프론트엔드 타입만 또는 백엔드 모델만 단독으로 바꿔 계약을 깨뜨리지 않기
