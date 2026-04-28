# 서버_DB — Supabase DB 연결 테스트 서버

> ⚠️ **이 서버는 Android 앱과 연결하는 서버가 아닙니다.**  
> Supabase PostgreSQL DB 연결이 잘 되는지 확인하는 **테스트용**입니다.

---

## 두 서버의 차이 (중요)

| | 이 서버 (`서버_DB/main.py`) | 메인 서버 (`src/api/main.py`) |
|--|---|---|
| **역할** | Supabase DB 연결 테스트 | YOLO + Depth V2 + 모든 VoiceGuide 기능 |
| **Android 앱 연결** | ❌ 안 함 | ✅ 여기에 연결 |
| **외부 배포(LTE)** | ❌ 배포 안 함 | ✅ Railway/GCP 등에 배포 |
| **포함 기능** | items CRUD + /detect DB저장 | /detect(YOLO), /dashboard, /health, /locations 등 |

---

## 언제 이 서버를 쓰나?

**Supabase DB 연결 자체가 되는지** 확인할 때만 사용합니다.  
연결 확인 후에는 `src/api/main.py` 서버의 `.env`에 `DATABASE_URL`을 설정하면 됩니다.  
메인 서버가 SQLite → Supabase PostgreSQL로 자동 전환됩니다.

---

## 실행 방법 (연결 테스트용)

```bash
cd 서버_DB

# 패키지 설치 (최초 1회)
pip install -r requirements.txt

# 환경변수 설정 (Supabase Session pooler 주소 사용)
# SUPABASE_DB_CONNECT_GUIDE.md 참고
set PGHOST=aws-xxx.pooler.supabase.com
set PGPORT=5432
set PGUSER=postgres.프로젝트ID
set PGPASSWORD=비밀번호
set PGDATABASE=postgres
set PGSSLMODE=require

# 서버 실행
uvicorn main:app --reload --port 8001
```

```bash
# 연결 확인
curl http://localhost:8001/health
# {"status": "ok"} 나오면 Supabase 연결 성공
```

---

## Supabase 연결 성공 후 해야 할 것

이 테스트 서버 말고, **메인 서버**에 Supabase를 연결해야 합니다.

```bash
# 프로젝트 루트의 .env 파일에 추가
DATABASE_URL=postgresql://postgres.xxx:비밀번호@aws-xxx.pooler.supabase.com:5432/postgres?sslmode=require

# 메인 서버 실행
cd ..
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 확인
curl http://localhost:8000/health
# {"db_mode": "postgresql"} ← Supabase 연결됨
```

자세한 내용: `docs/DEPLOY_GUIDE.md`

---

## 이 서버의 API (테스트용)

- `GET /health` — DB 상태 확인
- `GET /items` — 아이템 목록
- `POST /items` — 아이템 추가
- `POST /detect` — DB 저장 테스트 (`mode` 값만 저장, YOLO 없음)
