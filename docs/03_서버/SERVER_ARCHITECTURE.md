# 서버 연결 구조 — 정환주 서버 + 신유득 서버

> 두 서버를 어떻게 붙여서 쓸 수 있는지 설명

---

## 전체 구조

```
Android 앱
    │
    ▼ 모든 요청은 여기로
┌─────────────────────────────┐
│   메인 서버 (정환주, 8000)   │
│                             │
│  /detect 처리 중...         │
│  필요할 때만 내부 호출 ──────┼──→ ┌──────────────────────────┐
│                             │    │  신유득 서버 (8002)       │
│  결과 받아서 이어서 처리     │ ←──┼─ /blur  얼굴·번호판 블러  │
│                             │    │  /stats 탐지 통계         │
└─────────────────────────────┘    └──────────────────────────┘
                │                            │
                └──────────┬─────────────────┘
                           ▼
                    같은 Supabase DB
```

**핵심 원칙:**
- Android 앱은 메인 서버(8000)에만 연결
- 메인 서버가 필요할 때만 신유득 서버(8002)를 내부에서 호출
- 신유득 서버가 꺼져있어도 메인 서버는 정상 동작

---

## 연결 포인트 1 — /blur (얼굴·번호판 블러)

### 왜 필요한가?

지금 `/detect`는 이미지를 분석하고 바로 버림.
여기에 블러 처리 후 이미지를 저장하면:
- 공간기억에 실제 이미지 첨부 가능
- 대시보드에서 "이 공간이 지난번 방문 때 어떻게 생겼는지" 이미지로 확인
- 개인정보 보호 (얼굴·번호판 자동 블러)

### 흐름

```
이미지 도착 (/detect)
    ↓
메인 서버: YOLO + Depth 분석
    ↓
신유득 서버 /blur 호출
    ↓ 얼굴·번호판 블러된 이미지 반환
블러된 이미지를 공간기억 스냅샷으로 저장
    ↓
대시보드에서 이미지 확인 가능
```

### 메인 서버에 추가할 코드 (routes.py)

```python
import httpx
import os

BLUR_SERVER_URL = os.getenv("BLUR_SERVER_URL", "http://localhost:8002")

async def _blur_image(image_bytes: bytes) -> bytes:
    """신유득 서버에 블러 요청. 실패하면 원본 반환."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(
                f"{BLUR_SERVER_URL}/blur",
                files={"file": ("img.jpg", image_bytes, "image/jpeg")},
            )
            if resp.status_code == 200:
                return resp.content
    except Exception:
        pass  # 신유득 서버 꺼져도 메인 서버는 계속 동작
    return image_bytes  # 실패 시 원본 그대로
```

`/detect` 안에서 이미지 분석 후:

```python
# 기존 코드 (변경 없음)
objects, hazards, scene = detect_and_depth(image_bytes)

# 추가: 블러 처리 후 스냅샷 이미지 저장
if wifi_ssid and os.getenv("BLUR_SERVER_URL"):
    blurred = await _blur_image(image_bytes)
    # blurred 이미지를 파일로 저장
```

---

## 연결 포인트 2 — /stats (탐지 통계)

### 왜 필요한가?

발표 때 "얼마나 탐지했는지" 숫자로 보여줄 수 있음.
신유득 서버가 같은 Supabase DB를 읽어서 통계를 만들어 줌.

### 흐름

```
대시보드(브라우저)
    ↓ 폴링
메인 서버 /dashboard
    ↓ 내부 호출
신유득 서버 /stats
    ↓ 같은 Supabase DB 조회
{
  "total_detections": 1523,
  "most_common": ["의자", "사람", "가방"],
  "hazard_count": 47,
  "saved_locations": 12
}
    ↓
대시보드에 통계 카드로 표시
```

### 신유득 서버에 추가할 코드 (서버_DB_수정/main.py)

```python
@app.get("/stats")
def get_stats():
    with _pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # snapshots 테이블에서 총 탐지 횟수
            cur.execute("SELECT COUNT(*) AS total FROM snapshots")
            total = cur.fetchone()["total"]

            # saved_locations 테이블에서 저장된 장소 수
            cur.execute("SELECT COUNT(*) AS cnt FROM saved_locations")
            locations = cur.fetchone()["cnt"]

    return {
        "total_detections": total,
        "saved_locations": locations,
    }
```

---

## 공유 DB — 연결의 핵심

두 서버가 **같은 Supabase DB**를 바라보면 자연스럽게 연결됨.

```
.env (두 서버 모두 같은 값 사용)
DATABASE_URL=postgresql://postgres.xxx:비번@aws-xxx.supabase.com/postgres
```

| 테이블 | 누가 씀 |
|--------|--------|
| `snapshots` | 메인 서버 — 공간기억 저장 |
| `saved_locations` | 메인 서버 — 장소 저장 |
| `gps_history` | 메인 서버 — GPS 경로 |
| `items` | 신유득 서버 — 기본 CRUD |
| `lane_wear_results` | 신유득 서버 — 마모 분석 |

신유득 서버가 `snapshots` 테이블을 읽으면 탐지 통계를 낼 수 있음.

---

## 실행 방법

```bash
# 터미널 1 — 메인 서버 (정환주)
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 터미널 2 — 신유득 서버 (서브)
cd 서버_DB_수정
uvicorn main:app --host 0.0.0.0 --port 8002
```

`.env`에 추가:
```
BLUR_SERVER_URL=http://localhost:8002
DATABASE_URL=postgresql://...   ← 두 서버 모두 같은 값
```

---

## 지금 당장 연결하려면

1. 두 서버 모두 같은 `DATABASE_URL` 쓰기 → 공유 DB 연결
2. 메인 서버 `.env`에 `BLUR_SERVER_URL=http://localhost:8002` 추가
3. `routes.py`에 `_blur_image()` 함수 추가
4. 신유득 서버에 `/stats` 엔드포인트 추가

---

## GCP 배포할 때

```
메인 서버  → Cloud Run 서비스 A (voiceguide-main)
신유득 서버 → Cloud Run 서비스 B (voiceguide-blur)
```

`.env`에서:
```
BLUR_SERVER_URL=https://voiceguide-blur-xxx.run.app
```

두 서비스가 같은 Supabase DB를 바라보면 완성.

---

## 발표용 설명

```
"마이크로서비스 구조로 역할을 분리했습니다.

정환주 서버 (메인)     신유득 서버 (서브)
  YOLO + Depth    ←→   얼굴·번호판 블러
  장소저장/GPS         탐지 통계 집계
  공간기억

두 서버가 같은 Supabase DB를 공유하며,
메인 서버가 다운되어도 각 기능이 독립적으로 동작합니다."
```
