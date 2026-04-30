# Supabase(Postgres) DB 연결 가이드 (Windows + CMD)

이 문서는 `FastAPI + psycopg(커넥션풀)` 서버를 **Supabase Postgres**에 연결하고, API 동작까지 확인하는 과정을 정리한 공유용 가이드입니다.

## 준비물

- Windows (CMD 기준)
- Python 설치
- Supabase 프로젝트 (Database 활성화)

## 프로젝트 구조 요약

- 이 프로젝트는 **DB를 직접 실행하지 않습니다.**
- 이미 실행 중인 **Supabase Postgres(DB)** 에 접속해서 FastAPI 서버를 실행합니다.

## 1) 패키지 설치 (처음 1회)

프로젝트 폴더에서 실행:

```bat
cd /d "C:\Users\User\OneDrive\Desktop\AI 휴먼 1차 프로젝트_서버_db"
python -m pip install -r requirements.txt
```

## 2) Supabase “Direct connection”이 안 될 때 (중요)

일부 네트워크(학교/회사/특정 DNS)에서는 `db.<projectref>.supabase.co`가 **DNS/IPv4 경로 문제로 해석/접속이 실패**할 수 있습니다.

증상 예시:

- `getaddrinfo failed`
- `Ping 요청에서 ... 호스트를 찾을 수 없습니다`

이 경우 해결책은 **Supabase Pooler(연결풀링) 주소를 사용**하는 것입니다.

## 3) Supabase Pooler 주소 확인

Supabase 콘솔에서:

- **Project Settings → Database → Connection string**
- Connection Method에서 **Session pooler**(권장) 또는 **Transaction pooler** 선택

이때 화면에서 아래 값을 확인합니다:

- **Host**: 예) `aws-1-ap-northeast-2.pooler.supabase.com`
- **Port**: 예) `5432`
- **Database**: 예) `postgres`
- **User**: 예) `postgres.<projectref>`
- **Password**: 본인 비밀번호
- **SSL mode**: 보통 `require`

## 4) CMD에서 환경변수 설정 후 서버 실행 (같은 창에서 연속 실행)

아래는 예시입니다. **Host/Port/User/Password는 본인 값으로** 바꿔주세요.

```bat
cd /d "C:\Users\User\OneDrive\Desktop\AI 휴먼 1차 프로젝트_서버_db"

REM 혹시 남아있는 DATABASE_URL을 비웁니다(선택)
set DATABASE_URL=

set "PGHOST=aws-1-ap-northeast-2.pooler.supabase.com"
set "PGPORT=5432"
set "PGDATABASE=postgres"
set "PGUSER=postgres.frelaihwuacofvvukphv"
set "PGPASSWORD=YOUR_PASSWORD"
set "PGSSLMODE=require"

python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### 자주 나는 오류: `Missing required env var: PGHOST`

- **환경변수를 설정한 CMD 창과 서버를 실행한 CMD 창이 다르면** 발생합니다.
- 반드시 **한 CMD 창에서** `set ...` 다음에 바로 `uvicorn`을 실행하세요.

## 5) 서버 실행 확인

- 문서 페이지: `http://127.0.0.1:8000/docs`
- 헬스 체크: `http://127.0.0.1:8000/health`

## 6) DB 테이블 준비 (필수)

`/items`, `/detect`는 기본 테이블 `"items"`를 사용합니다.

Supabase 콘솔의 **SQL Editor**에서 아래 SQL을 실행해 테이블을 생성합니다.

```sql
create table if not exists public.items (
  id bigserial primary key,
  name text not null,
  mode int4 null,
  created_at timestamptz default now()
);
```

## 7) API 테스트

### 서버를 켜둔 상태에서 테스트하기

서버 실행용 CMD 창은 계속 켜두고, 테스트는 **새 CMD 창**에서 진행하는 것을 권장합니다.

헬스 체크:

```bat
curl http://127.0.0.1:8000/health
```

`/detect` 호출 (JSON body):

```bat
curl -X POST http://127.0.0.1:8000/detect -H "Content-Type: application/json" -d "{\"mode\": 1}"
```

성공하면 응답에 `saved` 데이터가 포함되고, Supabase DB에도 레코드가 저장됩니다.

## 결론 (연결 완료 기준)

- 서버가 `Application startup complete.`로 기동되고
- `/detect` 또는 `/items` 호출이 성공(INSERT/SELECT 성공)하면

**서버 ↔ Supabase DB 연결이 정상 완료**된 상태입니다.

