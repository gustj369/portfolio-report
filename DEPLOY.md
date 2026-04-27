# 배포 가이드 — Vercel + Render + Cloudflare R2

무료로 다수 사용자에게 제공하기 위한 단계별 배포 방법입니다.

## 전체 구조

```
사용자 → Vercel (Next.js) → Render (FastAPI) → Cloudflare R2 (PDF)
                                     ↓
                              Upstash Redis (세션)
```

---

## 1단계: Upstash Redis 생성 (무료)

1. https://upstash.com 접속 → 회원가입
2. **Create Database** → 이름 입력 → 리전: `ap-northeast-1 (Tokyo)` 선택
3. 생성 후 **REST API** 탭 → `REDIS_URL` 복사
   - 형식: `rediss://default:PASSWORD@HOST:PORT`

---

## 2단계: Cloudflare R2 버킷 생성 (무료 10GB)

1. https://dash.cloudflare.com 접속 → **R2 Object Storage**
2. **Create bucket** → 이름: `portfolio-reports`
3. 좌측 **Manage R2 API Tokens** → **Create API Token**
   - 권한: `Object Read & Write`
   - 버킷: `portfolio-reports` 지정
4. 생성 후 다음 값 복사:
   - `Access Key ID` → R2_ACCESS_KEY
   - `Secret Access Key` → R2_SECRET_KEY
   - Account ID (대시보드 우측 상단) → R2_ACCOUNT_ID

---

## 3단계: Render 백엔드 배포

1. https://render.com 접속 → 회원가입
2. **New** → **Web Service** → GitHub 저장소 연결
3. 설정:
   - **Root Directory**: `backend`
   - **Runtime**: Python 3
   - **Build Command**: `apt-get update -y && apt-get install -y fonts-nanum || true && pip install --no-cache-dir -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: Free
4. **Environment Variables** 탭에서 다음 입력:

   | 키 | 값 |
   |---|---|
   | `GEMINI_API_KEY` | (선택) Gemini API 키 |
   | `FRED_API_KEY` | (선택) FRED API 키 |
   | `REDIS_URL` | Upstash에서 복사한 URL |
   | `R2_ACCOUNT_ID` | Cloudflare Account ID |
   | `R2_ACCESS_KEY` | R2 Access Key |
   | `R2_SECRET_KEY` | R2 Secret Key |
   | `R2_BUCKET` | `portfolio-reports` |
   | `USE_LOCAL_STORAGE` | `false` |
   | `FRONTEND_URL` | (일단 비워두고 Vercel 배포 후 채움) |
   | `REPORT_PRICE_KRW` | `0` |
   | `TOSS_CLIENT_KEY` | (선택) 토스페이먼츠 클라이언트 키 |
   | `TOSS_SECRET_KEY` | (선택) 토스페이먼츠 시크릿 키 |
   | `AWS_ACCESS_KEY_ID` | (선택) S3 사용 시 |
   | `AWS_SECRET_ACCESS_KEY` | (선택) S3 사용 시 |
   | `AWS_REGION` | (선택) 기본 `ap-northeast-2` |
   | `S3_BUCKET` | (선택) S3 버킷명 |
   | `SMTP_HOST` | `smtp.gmail.com` (이메일 사용 시) |
   | `SMTP_PORT` | `587` |
   | `SMTP_USER` | Gmail 주소 |
   | `SMTP_PASSWORD` | Gmail 앱 비밀번호 |
   | `SMTP_FROM` | (선택) 발신자 주소 |

5. **Create Web Service** → 배포 완료 후 URL 복사
   - 예: `https://portfolio-report-api.onrender.com`

> **주의**: Render 무료 플랜은 15분 비활성 후 슬립됩니다.
> 첫 요청 시 30~60초 지연이 발생합니다. (유료 플랜 $7/월 시 해결)

---

## 4단계: Vercel 프론트엔드 배포

1. https://vercel.com 접속 → 회원가입
2. **Add New Project** → GitHub 저장소 선택
3. 설정:
   - **Framework Preset**: Next.js (자동 감지)
   - **Root Directory**: `frontend`
4. **Environment Variables** 추가:

   | 키 | 값 |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | Render 백엔드 URL (예: `https://portfolio-report-api.onrender.com`) |
   | `NEXT_PUBLIC_TOSS_CLIENT_KEY` | (선택) 토스페이먼츠 클라이언트 키 |

5. **Deploy** → 완료 후 Vercel URL 복사
   - 예: `https://portfolio-report.vercel.app`

---

## 5단계: CORS 설정 완료

Render 대시보드로 돌아가서:
- `FRONTEND_URL` = `https://portfolio-report.vercel.app` 으로 업데이트

---

## 6단계: 동작 확인

1. Vercel URL 접속 → 포트폴리오 입력 → 리포트 생성
2. Render 로그에서 진행 상황 확인:
   - `Render 대시보드 → Web Service → Logs`

## 저장소와 다운로드 흐름

- 배포 환경은 `REDIS_URL`을 설정해 결제/리포트 상태를 Redis에 저장하는 구성을 권장합니다.
- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY`, `R2_SECRET_KEY`가 있으면 PDF는 Cloudflare R2에 저장되고, 다운로드는 백엔드의 `/report/download/{report_token}` 경로를 통해 스트리밍됩니다.
- R2가 없고 `USE_LOCAL_STORAGE=false`와 AWS S3 키가 있으면 S3에 저장하고 presigned URL을 반환합니다.
- R2/S3 설정이 없으면 로컬 파일시스템(`backend/generated_reports/`)에 저장합니다. 이 방식은 개발용이며, Render 인스턴스 재시작 시 파일 보존을 기대하면 안 됩니다.

---

## 비용 요약

| 서비스 | 무료 한도 | 초과 시 |
|--------|-----------|---------|
| Vercel | 무제한 요청, 100GB 대역폭/월 | $20/월~ |
| Render | 750시간/월 (웹서비스 1개 기준 무제한) | $7/월 (슬립 없음) |
| Upstash Redis | 10,000 req/일, 256MB | $0.2/10만 req |
| Cloudflare R2 | 10GB 저장, 100만 req/월 | $0.015/GB |

**월 1,000명 사용 시 예상 비용: 0원**
**월 5,000명 이상 시: Render 유료 전환 권장 ($7/월)**

---

## 로컬 개발 환경 실행 (변경 없음)

```bash
# 백엔드
cd backend
python -m uvicorn main:app --reload --port 8000

# 프론트엔드
cd frontend
npm run dev
```
