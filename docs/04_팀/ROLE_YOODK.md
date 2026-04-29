# 신유득 역할 가이드

> 지금 뭘 해야 하는지 + 서버 업그레이드 아이디어 정리

---

## 지금 당장 해야 할 것 (필수 — 5/8 통합 전까지)

### 1단계: Supabase 연결 셋업

LTE 환경에서 장소 저장·GPS 기록이 유지되려면 외부 DB 연결이 필요함.

```bash
# 서버_DB/ 폴더에서 연결 확인 먼저
cd 서버_DB

set "PGHOST=aws-xxx.pooler.supabase.com"
set "PGPORT=5432"
set "PGDATABASE=postgres"
set "PGUSER=postgres.프로젝트ID"
set "PGPASSWORD=비밀번호"
set "PGSSLMODE=require"

uvicorn main:app --reload --port 8001

# 확인
curl http://localhost:8001/health
# → {"status":"ok"} 나오면 성공
```

연결 성공하면 **프로젝트 루트 `.env`에 추가:**

```
DATABASE_URL=postgresql://postgres.프로젝트ID:비밀번호@aws-xxx.pooler.supabase.com:5432/postgres?sslmode=require
```

메인 서버 재시작 후 확인:
```bash
curl http://localhost:8000/health
# → {"db_mode":"postgresql"} ← 완료
```

---

### 2단계: 서버 테스트 실행

```bash
# 프로젝트 루트에서
python tests/test_server.py
```

9개 엔드포인트 자동 테스트. 실패하는 항목 찾아서 정환주한테 알려주기.

---

### 3단계: 외부 배포

Railway 기준 (제일 쉬움):

```bash
# GitHub에 push된 상태에서 Railway 사이트에서 클릭 한 번으로 배포
# 배포 후 나오는 URL을 Android 앱 서버 입력창에 입력
# LTE 환경에서 /health 응답 확인
```

자세한 방법: `docs/DEPLOY_GUIDE.md` 또는 `docs/GCP_GUIDE.md`

---

## 서버 업그레이드 — 할 수 있는 것들

### A. 탐지 통계 API 추가 ⭐ (추천)

서버_DB_수정의 `/stats/summary`를 참고해서 VoiceGuide용 통계 API 만들기.

**추가할 엔드포인트:** `GET /stats`

```python
# 이런 응답 만들기
{
  "total_detections": 1523,       # 총 탐지 횟수
  "most_common": ["의자", "사람", "가방"],  # 가장 많이 탐지된 사물
  "hazard_count": 47,             # 계단/낙차 감지 횟수
  "active_sessions": 2,           # 현재 활성 세션 수
  "saved_locations": 12           # 저장된 장소 수
}
```

**어디에 코드 추가하면 되냐:**
`src/api/routes.py` 맨 아래에 아래 추가:

```python
@router.get("/stats")
async def get_stats():
    with db._conn() as conn:
        # snapshots 테이블에서 통계 계산
        # saved_locations 개수
        # gps_history 개수
        pass
    return { ... }
```

발표 때 "몇 건 탐지했어요" 보여줄 수 있음 → 시각적 임팩트 있음.

---

### B. 공간기억 스냅샷에 이미지 저장 (중간 난이도)

지금 공간기억은 탐지된 사물 목록만 저장함.
여기에 실제 이미지도 함께 저장하면 대시보드에서 "이 공간이 어떻게 생겼는지" 볼 수 있음.

**구현 방법:**

`src/api/db.py`의 `snapshots` 테이블에 `image_path` 컬럼 추가:
```sql
ALTER TABLE snapshots ADD COLUMN image_path TEXT;
```

`src/api/routes.py`의 `/detect`에서 이미지 파일 저장 코드 추가:
```python
import pathlib, uuid

# 이미지 저장 (공간기억 연동)
if wifi_ssid:
    img_dir = pathlib.Path("snapshots_img")
    img_dir.mkdir(exist_ok=True)
    img_path = img_dir / f"{uuid.uuid4().hex}.jpg"
    img_path.write_bytes(image_bytes)
    db.save_snapshot(wifi_ssid, objects, image_path=str(img_path))
```

---

### C. 서버 요청 로그 기록 (쉬움)

지금은 서버 응답 시간(`process_ms`)을 반환만 하고 기록은 안 함.
이걸 파일이나 DB에 남기면 "서버가 얼마나 빠른지" 측정 가능.

`src/api/main.py`에 미들웨어 추가:

```python
import time
from fastapi import Request

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    elapsed = round((time.monotonic() - start) * 1000)
    print(f"[{request.method}] {request.url.path} → {response.status_code} ({elapsed}ms)")
    return response
```

발표 때 "평균 응답시간 OOOms" 데이터로 쓸 수 있음.

---

### D. /blur 통합 (어려움 — 시간 있을 때)

서버_DB_수정에 만들어둔 얼굴·번호판 블러 기능을 메인 서버에 붙이기.

VoiceGuide가 이미지를 저장하는 기능을 추가할 때 개인정보 보호용으로 쓸 수 있음.

`서버_DB_수정/main.py`에서 아래 함수들 복사해서 `src/api/routes.py`에 추가:
- `apply_blur()` — 박스 영역에 블러 적용
- `_detect_boxes()` — YOLO로 얼굴/번호판 좌표 추출

---

## 우선순위 정리

| 순서 | 할 일 | 난이도 | 마감 |
|------|------|--------|------|
| ✅ 1 | Supabase .env 셋업 | 쉬움 | 4/30 |
| ✅ 2 | test_server.py 실행 | 쉬움 | 4/30 |
| ✅ 3 | Railway/GCP 배포 | 보통 | 5/1 |
| ⭐ 4 | /stats API 추가 | 보통 | 5/6 |
| 5 | 요청 로그 추가 | 쉬움 | 5/6 |
| 6 | 스냅샷 이미지 저장 | 어려움 | 여유 있으면 |
| 7 | /blur 통합 | 어려움 | 여유 있으면 |

---

## 발표 때 신유득 담당 설명 (예시)

```
신유득: 외부 DB 연동 및 서버 배포 담당

- Supabase PostgreSQL 연결 구현
  → LTE 환경에서도 장소 저장·GPS 기록 유지

- Railway/GCP 외부 배포
  → WiFi 없이 어디서든 앱이 서버에 접속 가능한 URL 생성

- 서버 탐지 통계 API 구현 (/stats)
  → 총 탐지 횟수, 가장 많이 탐지된 사물, 위험 감지 횟수

- 9개 엔드포인트 통합 테스트
```
