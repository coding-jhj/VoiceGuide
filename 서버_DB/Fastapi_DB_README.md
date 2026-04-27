# Postgres FastAPI 서버

## 1) 설치

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## 2) 환경변수 설정

`.env.example`를 참고해서 아래 값을 설정하세요(파워쉘 기준):

```powershell
$env:DATABASE_URL="postgresql://USER:PASSWORD@HOST:5432/DBNAME"
```

## 3) 실행

```bash
uvicorn main:app --reload
```

## 4) 테이블 준비

기본 테이블은 `public.items` 입니다.

```sql
create table if not exists public.items (
  id bigserial primary key,
  name text not null,
  mode integer null,
  created_at timestamptz not null default now()
);
```

## 4) API

- `GET /health`
- `GET /items`
- `GET /items/{id}`
- `POST /items`
- `PATCH /items/{id}`
- `DELETE /items/{id}`
- `POST /detect` (예시: mode 값을 DB에 저장)

