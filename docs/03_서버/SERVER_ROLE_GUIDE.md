# 서버 역할 정리 — 지금 뭘 해야 하는가

---

## 결론부터: 코드 다시 짤 필요 없어요

정환주 코드(`src/api/`)가 **진짜 서버**예요. 이미 완성됐어요.
신유득 코드를 참고해서 다시 짤 이유가 전혀 없어요.

---

## 지금 상황

```
정환주가 만든 것 (완성)
┌─────────────────────────────────┐
│  src/api/main.py                │  ← 서버 시작
│  src/api/routes.py              │  ← 모든 API (/detect 등)
│  src/api/db.py                  │  ← SQLite + Supabase 연결 이미 구현됨
│  src/api/tracker.py             │  ← 물체 추적
└─────────────────────────────────┘
            ↑
     Android 앱이 여기에 연결

신유득이 만든 것 (보조 도구)
┌─────────────────────────────────┐
│  서버_DB/                       │  ← Supabase 연결되는지 테스트용
│  서버_DB_수정/                   │  ← 블러 기능 실험용
└─────────────────────────────────┘
     메인 서버와 직접 연결 X
     신유득이 DB 공부하면서 만든 것
```

---

## 역할 분담이 왜 이렇게 됐나

| 멤버 | 원래 역할 | 실제로는 |
|------|---------|--------|
| 정환주 | Android + 전체 통합 | Android + **서버까지 전부** 만들어버림 |
| 신유득 | 서버 검증·테스트 | 별도 서버 만들다가 방향이 달라짐 |

정환주가 너무 빨리 다 만들어서 신유득이 붙을 곳이 없어진 상황.

---

## 신유득한테 지금 시킬 수 있는 일

### 1단계: Supabase 연결 (서버_DB/ 활용)

```bash
cd 서버_DB

set "PGHOST=aws-xxx.pooler.supabase.com"
set "PGPORT=5432"
set "PGDATABASE=postgres"
set "PGUSER=postgres.프로젝트ID"
set "PGPASSWORD=비밀번호"
set "PGSSLMODE=require"

uvicorn main:app --reload --port 8001
```

연결 확인:
```bash
curl http://localhost:8001/health
# → {"status":"ok"} 나오면 성공
```

### 2단계: 메인 서버에 Supabase 적용

프로젝트 루트 `.env` 파일에 추가:
```
DATABASE_URL=postgresql://postgres.프로젝트ID:비밀번호@aws-xxx.pooler.supabase.com:5432/postgres?sslmode=require
```

메인 서버 재시작 후 확인:
```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/health
# → {"db_mode":"postgresql"} ← Supabase 연결 완료
```

### 3단계: 서버 테스트

```bash
python tests/test_server.py
# 9개 엔드포인트 자동 테스트 — 실패 항목 확인 후 수정
```

### 4단계: 외부 배포 (Railway 또는 GCP)

배포 후 LTE 환경에서 Android 앱 연결 확인.
배포 방법은 `docs/DEPLOY_GUIDE.md` 참고.

---

## 정환주가 지금 해야 할 건

**서버 코드는 건드리지 않아도 됨.**

남은 것:
1. 신유득한테 Supabase `.env` 셋업 맡기기
2. 외부 배포 후 LTE 테스트
3. Android 앱에 배포된 URL 연결 확인

---

## 서버가 뭔지 아직 감이 안 온다면

```
서버 = 24시간 켜있는 프로그램
       "요청 오면 처리해서 응답"

앱이 사진 보냄
  → 서버가 YOLO 돌림
  → "왼쪽에 의자가 있어요" 반환
  → 앱이 TTS로 읽어줌

FastAPI = 서버 만드는 파이썬 도구

@app.post("/detect")     ← 이 주소로 POST 요청 오면
def detect(image):       ← 이 함수 실행
    return {"sentence"} ← 이걸 앱에 돌려줌
```

신유득의 `서버_DB/main.py`는 이 구조를 Supabase DB 연결에 맞게 만든 연습/테스트 서버.
메인 서버(`src/api/`)가 실제로 Android 앱과 통신하는 서버.
