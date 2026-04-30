# ngrok + FastAPI 서버 실행/외부접속 가이드 (CMD 기준)

이 문서는 `서버_DB_수정2/main.py` 서버를 로컬에서 실행하고, `ngrok`으로 외부 접근을 여는 방법을 정리한 안내서입니다.

## 1) 준비 사항

- Windows CMD 사용
- Python 및 의존성 설치 완료 (`requirements.txt`)
- ngrok 설치 및 로그인(authtoken 등록) 완료
- Supabase DB 접속 정보 보유

## 2) 서버 실행 (CMD)

아래 명령을 **한 CMD 창**에서 순서대로 실행합니다.

```bat
cd /d "C:\Users\User\OneDrive\Desktop\AI 휴먼 1차 프로젝트_서버_db\서버_DB_수정2"

set DATABASE_URL=
set "PGHOST=aws-1-ap-northeast-2.pooler.supabase.com"
set "PGPORT=5432"
set "PGDATABASE=postgres"
set "PGUSER=postgres.frelaihwuacofvvukphv"
set "PGPASSWORD=여기에_실제_DB_비밀번호"
set "PGSSLMODE=require"

python -m uvicorn main:app --host 0.0.0.0 --port 8002
```

정상 실행되면 서버가 기동된 상태로 CMD 창이 유지됩니다. 이 창은 닫지 마세요.

### 로컬 접속 확인

- `http://127.0.0.1:8002/`
- `http://127.0.0.1:8002/docs`
- `http://127.0.0.1:8002/health`

> 주의: `http://0.0.0.0:8002` 는 브라우저 접속 주소가 아닙니다.

## 3) ngrok 실행

서버를 켠 상태에서 **다른 CMD 창**을 열고 실행:

```bat
ngrok http 8002
```

실행 후 출력 예시:

```text
Forwarding  https://jubilant-trimmer-reggae.ngrok-free.dev -> http://localhost:8002
```

여기서 `https://...ngrok-free.dev` 가 외부 접속 주소입니다.

## 4) 외부에서 서버 접근 방법

외부 클라이언트(다른 PC, 모바일, 외부 네트워크)에서는 아래처럼 접속합니다.

- 루트: `https://<ngrok주소>/`
- Swagger 문서: `https://<ngrok주소>/docs`
- 상태 확인: `https://<ngrok주소>/health`

예시:

- `https://jubilant-trimmer-reggae.ngrok-free.dev/docs`

## 5) 자주 막히는 포인트

1. **주소 오류**
   - `0.0.0.0`로 접속하면 실패합니다.
   - 반드시 `127.0.0.1`(로컬) 또는 `https://<ngrok주소>`(외부) 사용

2. **DB 환경변수 누락**
   - `Missing required env var: PGHOST` 등의 에러가 나면 환경변수 다시 설정

3. **ngrok 주소 변경**
   - 무료 플랜에서는 ngrok 재실행 시 주소가 바뀔 수 있습니다.
   - 항상 ngrok 창의 최신 `Forwarding` 주소 사용

4. **서버/터널 프로세스 종료**
   - uvicorn CMD 창 또는 ngrok CMD 창이 닫히면 접속이 끊깁니다.

## 6) 빠른 점검 체크리스트

- [ ] 서버 CMD 창이 살아있다 (`uvicorn` 실행 중)
- [ ] ngrok CMD 창이 살아있다 (`Forwarding https://...` 표시)
- [ ] 로컬 `http://127.0.0.1:8002/health` 가 응답한다
- [ ] 외부 `https://<ngrok주소>/health` 가 응답한다

