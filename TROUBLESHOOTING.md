# Troubleshooting

로컬 개발 중 자주 만나는 환경 문제와 확인 방법입니다.

## 목차

- [문서 관리 기준](#문서-관리-기준)
- [Python 명령을 찾을 수 없는 경우](#python-명령을-찾을-수-없는-경우)
- [Git 전역 ignore 권한 경고가 보이는 경우](#git-전역-ignore-권한-경고가-보이는-경우)
- [Toss 결제 모듈을 불러오지 못하는 경우](#toss-결제-모듈을-불러오지-못하는-경우)
- [결제 승인 후 저장 실패가 발생한 경우](#결제-승인-후-저장-실패가-발생한-경우)
- [결제 재처리 관리자 스크립트 (별도 문서)](RECOVERY.md)
- [Sentry SDK 의존성 결정](#sentry-sdk-의존성-결정)
- [FastAPI TestClient 통합 테스트 실행](#fastapi-testclient-통합-테스트-실행)
- [가상환경 Python 실행 파일이 열리지 않는 경우](#가상환경-python-실행-파일이-열리지-않는-경우)

## 문서 관리 기준

문제 해결 섹션이 5개 이상으로 늘어나면 상단에 목차를 추가합니다.

## Python 명령을 찾을 수 없는 경우

`python` 명령이 PATH에 없으면 OS에 맞는 명령 또는 가상환경 Python을 직접 사용합니다.

| 환경 | 명령 예시 |
|------|----------|
| Windows | `python test_pipeline.py` 또는 `.\.venv\Scripts\python.exe test_pipeline.py` |
| macOS/Linux | `python3 test_pipeline.py` 또는 `.venv/bin/python test_pipeline.py` |

## Git 전역 ignore 권한 경고가 보이는 경우

`git status` 실행 중 `C:\Users\gustj/.config/git/ignore` 접근 권한 경고가 보이면 저장소 코드 문제가 아니라 사용자 홈의 Git 전역 설정 권한 문제입니다.

현재 확인된 증상:

- `C:\Users\gustj\.config\git\ignore` 접근이 거부됩니다.
- `.git/config`에 쓰기 또는 잠금 생성을 막을 수 있는 권한 제한이 있어 `git config --local ...` 명령도 실패할 수 있습니다.
- 이 문제는 저장소 코드 수정으로 해결하지 않고, 사용자 권한으로 홈 폴더 또는 저장소의 Git 설정 권한을 정리합니다.
- Codex 작업 중에는 권한 설정을 강제로 바꾸지 않고, 읽기 확인과 문서화까지만 진행합니다.

먼저 Git이 참조하는 전역 ignore 경로를 확인합니다.

```bash
git config --get core.excludesfile
```

Windows에서는 접근 가능한 전역 ignore 파일을 새로 만들고 다시 지정할 수 있습니다.

```powershell
New-Item -ItemType File -Force "$env:USERPROFILE\.gitignore_global"
git config --global core.excludesfile "$env:USERPROFILE\.gitignore_global"
```

저장소별로만 우회하려면 해당 저장소에서 로컬 설정을 지정할 수 있습니다.

```bash
git config --local core.excludesfile .git/info/exclude
```

단, `.git/config` 권한이 막혀 있으면 로컬 설정도 실패할 수 있으므로 터미널 권한이나 저장소 폴더 권한을 먼저 확인하세요.

권한 확인 예시:

```powershell
Get-Acl .git\config
Get-Acl "$env:USERPROFILE\.config\git\ignore"
```

저장소 폴더 권한 문제라면 관리자 권한 터미널 또는 파일 탐색기의 보안 탭에서 현재 사용자에게 쓰기 권한이 있는지 확인합니다.

권장 정리 순서:

1. `C:\Users\gustj\.config\git\ignore` 파일 또는 상위 폴더에 현재 사용자가 접근할 수 있는지 확인합니다.
2. 접근이 어렵다면 `core.excludesfile`을 접근 가능한 전역 ignore 파일로 다시 지정합니다.
3. 저장소별 설정이 필요하면 `.git/config`에 현재 사용자의 쓰기 권한이 있는지 먼저 확인합니다.
4. 권한 정리 후 `git status --short`를 다시 실행해 경고가 사라졌는지 확인합니다.

작업 트리에 이미 남아 있는 코드 변경은 권한 문제와 별개입니다. 권한을 정리할 때도 기존 수정 파일을 되돌리거나 삭제하지 말고, 필요한 경우 `git status --short`로 변경 목록만 확인합니다.

## Toss 결제 모듈을 불러오지 못하는 경우

실제 Toss 키 환경에서 결제 모듈 로드가 반복 실패하면 다음을 확인합니다.

- 인터넷 연결이 온라인 상태인지 확인합니다.
- 광고 차단 또는 보안 확장 프로그램을 잠시 끕니다.
- 회사/학교/공용 네트워크에서 CDN 접속이 차단되는지 확인합니다.
- 다른 브라우저나 다른 네트워크에서 다시 시도합니다.

## 결제 승인 후 저장 실패가 발생한 경우

서버 로그에 `결제 승인 후 저장 실패 — 수동 복구 필요`가 보이면 Toss 승인 이후 Redis/storage 저장이 실패한 상황입니다. 사용자는 결제를 완료했지만 리포트 토큰 발급이 실패했을 수 있으므로 운영자가 수동으로 확인합니다.

확인할 값:

- `order_id`
- 결제 금액 `amount`
- 로그에 남은 `payment_key_prefix`
- 같은 시간대의 `/payment/request`, `/payment/confirm`, report 생성 로그

대응 순서:

1. Toss 관리자 또는 결제 내역에서 `order_id` 기준으로 실제 승인 여부와 결제 금액을 확인합니다.
2. 승인 금액이 서버 로그의 `amount`와 일치하는지 확인합니다.
3. Redis/storage 장애가 복구되었는지 확인합니다.
4. pending 데이터가 남아 있으면 동일 주문을 재시도하거나, 운영자가 `analyze_request`를 기준으로 리포트를 재생성합니다.
5. pending 데이터가 없으면 요청 시점의 서버 로그 또는 고객 입력 정보로 `analyze_request`를 복원해 리포트를 생성하고 고객에게 전달합니다.
6. 중복 환불/중복 발급을 피하기 위해 처리 결과를 `order_id` 기준으로 운영 기록에 남깁니다.

운영 알림을 받으려면 배포 환경 변수에 웹훅 URL을 설정합니다.

```bash
ADMIN_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/...
```

이 값은 Slack Incoming Webhook처럼 JSON 요청을 받을 수 있는 URL을 기대합니다. 알림 payload는 `text` fallback과 Slack Block Kit `blocks`를 함께 전송합니다. 실제 URL은 비밀 값이므로 코드나 문서 예시에 커밋하지 않습니다.

## 결제 재처리 관리자 스크립트

결제 승인 후 저장 실패, 복구 명령, 리포트 생성 재요청, Redis 동시 실행 검증 절차는 [RECOVERY.md](RECOVERY.md)를 확인합니다.

이 troubleshooting 문서에는 증상별 빠른 확인만 남기고, 운영 복구 절차는 별도 문서에서 관리합니다.

복구 lock TTL은 코드 기준 `RECOVERY_LOCK_TTL_SECONDS = 300`으로 300초입니다. lock 획득 실패 시 최대 5분 기다린 뒤 dry-run으로 상태를 다시 확인하고 confirm을 재시도합니다.


## Sentry SDK 의존성 결정

현재 코드는 `SENTRY_DSN`이 있어도 `sentry-sdk`가 설치된 경우에만 오류 보고를 켭니다. 따라서 의존성을 추가하지 않은 환경에서도 서버 실행은 유지됩니다.

실제 운영에서 Sentry를 사용하기로 결정하면 다음을 함께 반영합니다.

- `backend/requirements.txt`에 `sentry-sdk[fastapi]` 또는 `sentry-sdk` 추가
- 배포 환경 변수 `SENTRY_DSN` 설정
- 개인정보가 포함될 수 있는 요청 본문/결제 키가 Sentry 이벤트에 들어가지 않는지 확인
- staging 환경에서 의도적인 예외로 이벤트 수집 여부 확인
- staging에서 결제 실패, Redis 장애, 리포트 생성 실패가 각각 민감정보 없이 수집되는지 확인
- Sentry release/environment 값을 배포 환경과 맞출지 결정
- staging에서 `SENTRY_DSN`만 설정하고 `sentry-sdk`가 빠진 경우 서버가 정상 기동하는지 확인
- `sentry-sdk` 추가 후 `/health`와 주요 결제 오류 흐름이 정상 응답하는지 확인
- 수집 이벤트에 `paymentKey`, `toss_secret_key`, 이메일, 고객 이름이 포함되지 않는지 확인

아직 운영 도입이 확정되지 않았다면 requirements에는 추가하지 않습니다. 현재 optional import 방식은 DSN 설정 실수나 SDK 미설치가 서비스 시작 실패로 이어지지 않게 하기 위한 임시 안전장치입니다.

운영 도입이 확정된 뒤 requirements를 바꾸는 순서:

1. 별도 브랜치에서 `sentry-sdk[fastapi]`를 추가합니다.
2. staging에만 `SENTRY_DSN`을 먼저 설정합니다.
3. `/health`, 결제 요청, 결제 실패, 리포트 생성 실패 흐름을 확인합니다.
4. Sentry 이벤트에서 민감정보가 없는지 확인한 뒤 production에 적용합니다.

## FastAPI TestClient 통합 테스트 실행

`test_payment_integration.py`는 FastAPI와 프로젝트 의존성이 설치된 정상 venv에서만 실행됩니다. 의존성이 없는 번들 Python 환경에서는 skip되는 것이 정상입니다.

Windows 예시:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest test_payment_integration.py
```

macOS/Linux 예시:

```bash
cd backend
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest test_payment_integration.py
```

전체 테스트를 같이 확인하려면 다음처럼 실행합니다.

```bash
python -m unittest test_payment.py test_payment_integration.py test_ai_engine.py test_market_data.py
```

## 가상환경 Python 실행 파일이 열리지 않는 경우

Windows에서 `backend\.venv\Scripts\python.exe` 파일은 있지만 실행 시 `Unable to create process`가 나오면 가상환경 내부의 Python 경로 연결이 깨졌거나 실행 파일 접근 권한이 꼬인 상태일 수 있습니다.

확인 명령:

```powershell
Test-Path backend\.venv\Scripts\python.exe
& backend\.venv\Scripts\python.exe --version
```

복구 방법:

1. 기존 `.venv`를 바로 삭제하기 전에 현재 작업 트리 변경 사항을 확인합니다.
2. 프로젝트 루트가 아닌 `backend` 폴더 기준으로 새 가상환경을 만듭니다.
3. 의존성을 다시 설치합니다.

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest test_payment_integration.py
```

권한 문제로 `.venv`를 덮어쓸 수 없으면 파일 탐색기 보안 탭 또는 관리자 권한 터미널에서 `backend\.venv` 폴더의 현재 사용자 쓰기/실행 권한을 확인합니다.
