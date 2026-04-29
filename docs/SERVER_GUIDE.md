# VoiceGuide 서버 완전 이해 가이드

> 팀원 공부용 — 코드를 처음 보는 사람도 이해할 수 있게 작성

---

## 먼저: 서버 폴더가 3개인데 어떤 게 진짜야?

```
VoiceGuide/
├── src/api/          ← ✅ 이게 진짜 서버. Android 앱이 여기에 연결함
├── 서버_DB/          ← 🔧 신유득이 Supabase DB 연결 테스트용으로 만든 것. 앱이랑 무관
└── 서버_DB_수정/     ← 🔧 RoadGlass(도로 마모 분석) 다른 프로젝트용. VoiceGuide와 무관
```

**헷갈리면 그냥 `src/api/` 폴더만 보면 됨.**

---

## 전체 그림 — Android 앱이 서버를 어떻게 쓰는가

```
[사용자 말함]
    ↓
[Android 앱]
    ↓ 이미지 + WiFi이름 + GPS + 모드 전송
    ↓ (HTTP 요청)
[서버 src/api/]
    ├─ YOLO로 사물 감지
    ├─ Depth V2로 거리 측정
    ├─ DB에 기록 저장
    └─ "왼쪽에 의자가 있어요" 문장 반환
    ↓
[Android 앱]
    ↓
[TTS로 음성 출력]
```

---

## 서버를 구성하는 4개 파일

| 파일 | 역할 | 비유 |
|------|------|------|
| `main.py` | 서버 켜고 끌 때 준비 작업 | 가게 오픈 전 준비 |
| `routes.py` | 실제 API 처리 (앱 요청 받기) | 가게 직원 |
| `db.py` | 데이터 저장/조회 | 창고 관리 |
| `tracker.py` | 사물 추적 및 안정화 | CCTV 분석관 |

---

## 1. main.py — 서버 시작 준비

### 하는 일

```
서버 켜질 때 (한 번만):
  1. DB 초기화 (테이블 없으면 만들기)
  2. YOLO 모델 워밍업 (첫 요청 느린 것 방지)
  3. EasyOCR 워밍업 (백그라운드에서 조용히)
  4. TTS 캐시 워밍업 (백그라운드에서 조용히)

서버 돌아가는 동안:
  - /health 엔드포인트 (서버 상태 확인)
  - 오류 나도 앱에 음성 안내 반환 (전역 예외 처리)
```

### 핵심 코드 이해

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()          # DB 테이블 준비
    model(더미이미지...)   # YOLO 미리 로드 (첫 요청 빠르게)
    yield                  # ← 이 줄이 "서버 운영 중" 을 의미
```

`yield` 위 = 서버 켜질 때 실행, `yield` 아래 = 서버 꺼질 때 실행

### /health 엔드포인트

```
GET http://서버주소/health
→ {"status":"ok", "depth_v2":"loaded", "device":"cuda", "db_mode":"sqlite"}
```

이걸로 서버가 살아있는지, GPU 쓰는지, DB 뭔지 한번에 확인 가능.

---

## 2. routes.py — API 처리 (가장 중요)

### 전체 엔드포인트 목록

| 주소 | 방식 | 역할 |
|------|------|------|
| `POST /detect` | 이미지 분석 | 핵심. 앱이 1초마다 여기에 이미지 보냄 |
| `GET /health` | 서버 상태 | 살아있는지 확인 |
| `GET /dashboard` | 대시보드 HTML | 브라우저로 지도 보기 |
| `GET /status/{session_id}` | 추적 상태 | 대시보드 폴링용 |
| `POST /locations/save` | 장소 저장 | "편의점 저장해줘" |
| `GET /locations` | 저장 장소 목록 | "저장된 곳 알려줘" |
| `GET /locations/find/{label}` | 장소 검색 | "편의점 어디야" |
| `DELETE /locations/{label}` | 장소 삭제 | |
| `POST /tts` | TTS 음성 파일 | ElevenLabs 사용 시 |
| `POST /vision/clothing` | 옷 분석 | GPT Vision 활용 |
| `POST /ocr/bus` | 버스 번호 읽기 | ML Kit 실패 시 대체 |
| `POST /stt` | PC 마이크 | Gradio 데모 전용 |

---

### POST /detect — 핵심 흐름

앱이 1초마다 호출하는 가장 중요한 API.

```
앱이 보내는 것:
  - image: 카메라 사진
  - wifi_ssid: 연결된 WiFi 이름 (공간 구분용)
  - camera_orientation: 카메라 방향 (front/back/left/right)
  - mode: 어떤 모드인지 (장애물/찾기/질문/저장/위치목록)
  - lat, lng: GPS 좌표
```

**mode에 따라 처리가 완전히 다름:**

```
"저장" 모드  → 이미지 안 봄! WiFi 이름 + 장소명 DB에 저장하고 바로 반환
"위치목록"   → 이미지 안 봄! DB에서 장소 목록 꺼내서 반환
나머지 모드  → 이미지 분석 시작
```

**이미지 분석 공통 흐름:**

```
1. GPS 좌표 DB 저장 (대시보드 지도 표시용)

2. YOLO + Depth 분석
   → objects: [{"class_ko":"의자", "direction":"9시", "distance_m":1.5, ...}, ...]
   → hazards: 계단/낙차 감지 결과
   → scene:   군중/위험물체/신호등/안전경로 분석

3. 추적기(tracker) 업데이트
   → 거리 흔들림 제거 (EMA)
   → 접근/소멸 감지

4. 공간 기억 비교
   → 이전 방문 때와 비교해서 달라진 것 탐지
   → "의자가 생겼어요", "사람이 없어졌어요"

5. 모드별 문장 생성
   "질문" → tracker 누적 상태 + 현재 프레임 합산
   "찾기" → 특정 물체 위치만
   나머지 → 위험도 높은 것부터

6. TTS 중복 방지
   → 같은 문장이 5초 이내 반복이면 "silent"로 낮춤
   → critical(차량/계단)은 항상 통과

7. 반환
   → sentence: TTS로 읽을 문장
   → alert_mode: "critical" / "beep" / "silent"
   → objects, hazards, scene, changes
   → process_ms: 처리 시간
```

**alert_mode가 뭔지:**

| 값 | 뜻 | Android 동작 |
|----|-----|------------|
| `critical` | 위험! 즉시 안내 | TTS 최우선 재생, 속도 1.25× |
| `beep` | 멀리 있는 물체 | 비프음만 (TTS 피로 방지) |
| `silent` | 같은 말 반복 | TTS 안 함, UI만 업데이트 |

---

### TTS 중복 억제 로직

```python
_DEDUP_SECS = 5.0  # 5초 이내 같은 문장이면 억제

def _should_suppress(session_id, sentence, alert_mode):
    if alert_mode == "critical":
        return False  # 위험 경고는 항상 발화
    # 같은 문장이 5초 이내에 전달됐으면 억제
    if sentence == 이전문장 and 경과시간 < 5초:
        return True
```

왜 이게 필요하냐면: 의자가 계속 카메라에 잡히면 1초마다 "의자가 있어요"가 나와서 피로해짐.

---

### 공간 기억 (_space_changes)

```python
def _space_changes(current, previous):
    # 이번 방문에 새로 생긴 것
    새로생긴것 = current에 있고 previous에 없는 것 → "의자가 생겼어요"
    # 사라진 것
    사라진것 = previous에 있고 current에 없는 것 → "사람이 없어졌어요"
```

WiFi SSID가 공간 ID 역할을 함 → 같은 WiFi에 다시 오면 이전 방문과 비교.

---

## 3. db.py — 데이터베이스

### SQLite vs PostgreSQL 자동 전환

```python
DATABASE_URL = os.getenv("DATABASE_URL")  # 환경변수에 있으면 PostgreSQL

if DATABASE_URL:
    PostgreSQL 사용 (Supabase — 외부에서 접속 가능, LTE 지원)
else:
    SQLite 사용 (로컬 파일 voiceguide.db — 간단, 외부 접속 불가)
```

**언제 뭘 쓰냐:**

| 상황 | DB | 설정 |
|------|-----|------|
| 로컬 테스트 (같은 WiFi) | SQLite | .env에 아무것도 안 써도 됨 |
| 외부 배포 (LTE) | PostgreSQL (Supabase) | .env에 DATABASE_URL 설정 |

### 저장하는 데이터 3종류

```
1. snapshots 테이블
   → 각 공간의 물체 현황 (공간 기억용)
   → space_id(WiFi SSID), timestamp, objects(JSON)

2. saved_locations 테이블
   → 사용자가 저장한 장소
   → label(장소명), wifi_ssid, timestamp

3. gps_history 테이블
   → GPS 이동 경로 (대시보드 지도용)
   → session_id, lat, lng, timestamp
   → 세션당 최근 200개만 유지 (오래된 건 자동 삭제)
```

### _conn() — SQLite/PostgreSQL 구분 없이 쓰는 방법

```python
with _conn() as conn:
    conn.execute("SELECT * FROM snapshots")
```

`_conn()`이 내부에서 SQLite인지 PostgreSQL인지 판단해서 알아서 처리.
코드 나머지 부분은 DB 종류 신경 안 써도 됨.

---

## 4. tracker.py — 사물 추적기

### 왜 필요한가?

YOLO가 매 프레임마다 약간씩 다른 결과를 냄:
```
1초: 의자 거리 1.0m
2초: 의자 거리 1.3m   ← 의자가 움직인 게 아니라 측정 오차
3초: 의자 거리 0.9m
```

이러면 TTS가 매번 다른 말을 해서 혼란스러움.
추적기가 이걸 안정화시켜 줌.

### EMA (지수이동평균) — 거리 안정화

```
EMA 공식: 새 거리 = 현재 측정값 × 0.55 + 이전 평균값 × 0.45

예시:
  1초 측정: 1.0m → 트랙 생성, 거리 = 1.0m
  2초 측정: 1.3m → 1.3×0.55 + 1.0×0.45 = 1.165m
  3초 측정: 0.9m → 0.9×0.55 + 1.165×0.45 = 1.019m
  → 흔들리지 않고 안정적으로 ~1.0m 유지
```

**alpha = 0.55 의미:**
- 현재 측정값 55% + 이전 평균 45%
- 클수록 반응이 빠르지만 흔들림
- 작을수록 안정적이지만 반응 느림
- 0.55이 적당한 균형점

### VotingBuffer — 오탐 방지

```
최근 10프레임 중 6번(60%) 이상 탐지된 물체만 확정

예시:
  고양이: 10프레임 중 2번 탐지 → 20% → 오탐 가능성 → 경고 안 냄
  의자:   10프레임 중 8번 탐지 → 80% → 확정 → 경고 냄
  차량:   무조건 즉시 통과 (안전 우선)
```

왜 필요하냐면: YOLO가 1~2프레임 동안 엉뚱한 걸 탐지하는 경우가 있음.
그걸 TTS로 바로 읽어주면 사용자가 혼란스러움.

### 접근 감지

```python
delta = 이전_거리 - 현재_거리  # 양수 = 가까워지는 중

# 일반 접근: 한 프레임에 0.4m 이상 가까워지면
if delta >= 0.4 and 거리 < 2.5m:
    → "가방이 가까워지고 있어요"

# 빠른 접근: 한 프레임에 0.8m 이상 (날아오거나 떨어지는 물체)
if delta >= 0.8 and 거리 < 3.0m:
    → "조심! 공이 빠르게 다가오고 있어요!"
```

### 소멸 감지

```python
# 마지막으로 본 이후 4초 이상 지나면
if age > 4.0 and 거리 < 3.0m:
    → "의자가 사라졌어요"

# 멀리 있던 건 굳이 안 알려줌 (3m 이상)
```

### 세션별 추적기

```python
_trackers = {
    "KT_WiFi_12345": SessionTracker(),  # 이 장소에서의 추적기
    "SKBB_Office":   SessionTracker(),  # 저 장소에서의 추적기
}
```

WiFi가 바뀌면 새 추적기 생성 → 장소별 물체 기억이 분리됨.

---

## 서버_DB 폴더 — 신유득이 만든 DB 테스트 서버

> ⚠️ Android 앱이 연결하는 서버가 **아님**. Supabase DB 연결 확인용 테스트 도구.

### 언제 쓰나?

Supabase(외부 PostgreSQL DB)를 처음 연결할 때 "연결이 제대로 되나?" 확인용.
연결 확인 후에는 `.env`에 `DATABASE_URL`만 추가하면 메인 서버(`src/api/`)가 자동으로 Supabase를 씀.

### 이 서버에 있는 API들

- `GET /items` — items 테이블 조회
- `POST /items` — items 테이블에 추가
- `POST /detect` — DB에 저장 테스트 (YOLO 없음, 그냥 저장만)
- `GET /health` — DB 연결 상태 확인

메인 서버의 `/detect`와 이름은 같지만 완전히 다른 것임.
이건 YOLO도 없고 이미지도 안 받음. 그냥 DB 저장 테스트.

---

## 서버_DB_수정 폴더 — RoadGlass 프로젝트 서버

> ⚠️ VoiceGuide와 무관. 도로 차선 마모 분석 프로젝트용.

이 서버가 하는 일:
- `/blur`: 사진에서 얼굴/번호판 자동 블러 처리
- `/lane_wear_infer`: 도로 차선 마모도 분석 (YOLO 세그멘테이션)
- `/stats/summary`: 마모 통계 집계

VoiceGuide 개발할 때는 신경 안 써도 됨.

---

## 실제로 서버 어떻게 실행해?

### 1. 로컬 실행 (같은 WiFi 테스트)

```bash
# 프로젝트 루트에서
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 확인
http://localhost:8000/health
http://localhost:8000/dashboard
```

### 2. LTE 외부 접속 (GCP Cloud Run 배포)

```bash
gcloud run deploy voiceguide \
  --source . \
  --region asia-southeast1 \
  --memory 4Gi \
  --allow-unauthenticated

# 나온 URL을 Android 앱 서버 입력창에 붙여넣기
```

### 3. Supabase DB 연결 (LTE에서 장소 저장 유지)

```bash
# .env 파일에 추가
DATABASE_URL=postgresql://postgres.xxx:비밀번호@aws-xxx.pooler.supabase.com:5432/postgres?sslmode=require

# 서버 재시작 → /health에서 "db_mode":"postgresql" 확인
```

---

## API 테스트 (직접 해보기)

서버 켜놓고 브라우저 또는 터미널에서:

```bash
# 서버 살아있나?
curl http://localhost:8000/health

# 장소 저장
curl -X POST http://localhost:8000/locations/save \
  -F "wifi_ssid=MyWifi" \
  -F "label=편의점"

# 저장된 장소 목록
curl "http://localhost:8000/locations?wifi_ssid=MyWifi"

# 대시보드 (브라우저에서)
http://localhost:8000/dashboard

# Swagger (API 자동 문서 — 브라우저에서)
http://localhost:8000/docs
```

`/docs`에 들어가면 모든 API를 브라우저에서 직접 테스트해볼 수 있는 화면이 나옴.

---

## 자주 묻는 것

**Q. WiFi SSID가 왜 그렇게 중요해?**
공간 ID 역할을 함. 같은 WiFi = 같은 장소로 판단.
장소 저장, 공간 기억, 추적기 분리가 모두 WiFi 기준으로 작동.

**Q. SQLite랑 PostgreSQL 차이가 뭐야?**
SQLite = 파일 하나. 설정 필요 없음. 같은 PC에서만 접속 가능.
PostgreSQL = 외부 서버 DB. 설정 필요. 어디서든 접속 가능.
LTE로 앱에서 서버에 접속하면 서버가 저장한 장소 정보가 날아가지 않으려면 PostgreSQL 필요.

**Q. 서버가 죽으면 앱은 어떻게 돼?**
Android 앱은 서버 없이도 ONNX 온디바이스 추론으로 혼자 동작함.
서버 연결 3번 실패하면 "서버 연결 끊겼어요" 안내 후 온디바이스 모드 전환.

**Q. process_ms가 뭐야?**
서버가 이미지 받아서 처리하는 데 걸린 시간(밀리초). Android 앱 화면에 FPS로 표시됨.
