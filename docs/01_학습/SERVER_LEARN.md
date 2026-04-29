# VoiceGuide 서버 이해 가이드

> 팀원 공부용 — 서버를 처음 보는 사람 기준으로 작성

---

## 서버가 뭐야?

```
서버 = 24시간 켜있는 프로그램
       누군가 요청하면 처리해서 응답해주는 것
```

카카오톡으로 메시지 보내면 카카오 서버가 받아서 상대방한테 전달하듯이,
VoiceGuide 앱이 사진을 보내면 우리 서버가 받아서 분석하고 결과를 돌려줌.

```
[Android 앱]  →  사진 전송  →  [서버]  →  "왼쪽에 의자가 있어요" 반환  →  [Android 앱]
```

---

## 서버를 구성하는 파일 4개

```
src/api/
├── main.py      ← 서버 시작/종료 담당
├── routes.py    ← 요청 처리 담당 (가장 중요)
├── db.py        ← 데이터 저장/조회 담당
└── tracker.py   ← 사물 추적 담당
```

---

## main.py — 서버 켜고 끌 때 하는 일

### 서버가 켜질 때 (딱 한 번 실행)

```python
db.init_db()          # DB 테이블 준비
model(더미 이미지)     # YOLO 미리 로드
warmup_ocr()          # EasyOCR 미리 로드  (백그라운드)
warmup_tts()          # TTS 캐시 미리 준비 (백그라운드)
```

**왜 워밍업이 필요하냐면:**
YOLO 같은 AI 모델은 처음 실행할 때 느림 (5~10초).
서버 켤 때 미리 한 번 돌려놓으면 실제 첫 요청이 빠르게 처리됨.

### /health — 서버 상태 확인

```
GET http://서버주소/health

응답: {
  "status": "ok",
  "depth_v2": "loaded",   ← Depth 모델 로드됐는지
  "device": "cuda",       ← GPU 쓰는지 CPU 쓰는지
  "db_mode": "sqlite"     ← 어떤 DB 쓰는지
}
```

서버 켠 후 제일 먼저 이걸 확인하면 됨.

### 오류가 나도 앱이 안 죽는 이유

```python
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return {"sentence": "분석 중 오류가 발생했어요. 주의해서 이동하세요."}
```

서버 어디서든 오류가 나면 앱한테 이 문장을 돌려줌.
앱은 오류인지 모르고 그냥 TTS로 읽어줌 → 사용자 입장에서 서버가 죽은 티가 안 남.

---

## routes.py — 요청 처리 (핵심)

### 앱이 보내는 것들

```
POST /detect
  - image:              카메라 사진
  - wifi_ssid:          연결된 WiFi 이름 (공간 구분용)
  - camera_orientation: 카메라 방향 (front/back/left/right)
  - mode:               어떤 기능인지 (장애물/찾기/질문/저장/위치목록)
  - lat, lng:           GPS 좌표
```

### mode에 따라 처리가 완전히 달라짐

```
"저장"     → 이미지 분석 안 함. WiFi이름 + 장소명 DB에 저장하고 끝
"위치목록" → 이미지 분석 안 함. DB에서 목록 꺼내서 끝
나머지     → 이미지 분석 시작 ↓
```

### 이미지 분석 흐름 (장애물/찾기/질문/확인 모드)

```
1. GPS 좌표 저장
   lat, lng 있으면 DB에 기록 → 대시보드 지도에 표시됨

2. AI 분석
   detect_and_depth(image_bytes)
   → objects: 탐지된 사물 목록
     [{"class_ko":"의자", "direction":"9시", "distance_m":1.5}, ...]
   → hazards: 계단·낙차 감지 결과
   → scene:   군중/위험물체/신호등/안전경로

3. 추적기 업데이트 (tracker.py)
   거리 흔들림 제거 + 접근/소멸 감지

4. 공간기억 비교
   이전 방문 때랑 달라진 것 찾기
   → "의자가 생겼어요", "사람이 없어졌어요"

5. 모드별 문장 생성
   질문모드 → tracker 누적 상태까지 합산해서 포괄 응답
   찾기모드 → 특정 물체 위치만
   장애물   → 위험도 높은 것부터

6. TTS 중복 방지
   같은 문장이 5초 이내 반복이면 "silent"로 낮춤
   차량·계단은 항상 통과

7. 응답 반환
   {
     "sentence":   "왼쪽 바로 앞에 의자가 있어요. 오른쪽으로 비켜보세요.",
     "alert_mode": "critical" / "beep" / "silent",
     "objects":    [...],
     "hazards":    [...],
     "process_ms": 243
   }
```

### alert_mode가 뭐야?

| 값 | 의미 | Android 동작 |
|----|------|------------|
| `critical` | 즉시 안내 필요 | TTS 바로 재생, 속도 1.25배 |
| `beep` | 멀리 있는 물체 | 비프음만 (말 안 함) |
| `silent` | 같은 말 반복 방지 | TTS 안 함, 화면만 업데이트 |

### TTS 중복 방지 로직

```python
_DEDUP_SECS = 5.0  # 5초

# 같은 문장이 5초 이내에 이미 나왔으면 → "silent"로 낮춤
# critical(차량·계단)은 무조건 통과
```

의자가 계속 카메라에 잡히면 1초마다 "의자가 있어요"가 나와서 피로해짐.
이걸 막는 것.

### 공간기억 (_space_changes)

```python
새로 생긴 것 = 이번에 있고 이전엔 없던 것 → "의자가 생겼어요"
사라진 것   = 이전엔 있고 이번엔 없는 것 → "사람이 없어졌어요"
```

WiFi SSID = 공간 ID. 같은 WiFi에 다시 오면 이전 방문과 비교함.
매번 똑같은 설명 반복 안 하는 이유.

---

## db.py — 데이터 저장

### SQLite vs Supabase 자동 전환

```
.env에 DATABASE_URL 없음 → SQLite (파일, 로컬만 접속 가능)
.env에 DATABASE_URL 있음 → Supabase PostgreSQL (외부 어디서든 접속 가능)
```

```python
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    PostgreSQL 사용   # LTE 환경, 배포 서버
else:
    SQLite 사용       # 로컬 테스트
```

### 저장하는 데이터 3가지

```
snapshots 테이블
  → 공간별 사물 현황 저장 (공간기억 기능)
  → WiFi이름 + 시간 + 사물목록(JSON)

saved_locations 테이블
  → 사용자가 저장한 장소
  → 장소이름 + WiFi이름 + 시간

gps_history 테이블
  → GPS 이동 경로 (대시보드 지도용)
  → 세션당 최근 200개만 유지 (오래된 건 자동 삭제)
```

---

## tracker.py — 사물 추적

### 왜 필요하냐?

YOLO는 프레임마다 조금씩 다른 결과를 냄:
```
1초: 의자 1.0m
2초: 의자 1.3m   ← 의자가 움직인 게 아님. 측정 오차
3초: 의자 0.9m
```
그러면 TTS가 매번 다른 말을 함 → 혼란스러움.
tracker가 이걸 부드럽게 만들어줌.

### EMA (지수이동평균) — 거리 안정화

```
새 거리 = 현재 측정값 × 0.55 + 이전 평균 × 0.45

예시:
  1초: 1.0m → 1.0m
  2초: 1.3m → 1.3×0.55 + 1.0×0.45 = 1.165m
  3초: 0.9m → 0.9×0.55 + 1.165×0.45 = 1.019m
  → 흔들리지 않고 ~1.0m로 안정
```

### VotingBuffer — 오탐 방지

```
최근 10프레임 중 6번 이상 탐지된 것만 진짜로 인정

고양이: 10프레임 중 2번 탐지 → 오탐 → 경고 안 냄
의자:   10프레임 중 8번 탐지 → 진짜 → 경고 냄
차량:   무조건 즉시 통과 (안전 우선)
```

### 접근/소멸 감지

```
한 프레임에 0.4m 이상 가까워지면 → "가방이 가까워지고 있어요"
한 프레임에 0.8m 이상 급격히 가까워지면 → "조심! 빠르게 다가오고 있어요!"
4초 이상 안 보이면 → "의자가 사라졌어요"
```

---

## 팀원별 연결 포인트

내 서버가 각 팀원 코드를 어떻게 호출하는지:

### 김재현 (YOLO 탐지)

```python
# routes.py 에서 호출
from src.vision.detect import model
objects, hazards, scene = detect_and_depth(image_bytes)
```

`src/vision/detect.py`의 결과가 `objects` 리스트로 옴.
각 항목: `{"class_ko":"의자", "direction":"9시", "distance_m":1.5, "risk_score":1.0}`

### 문수찬 (Depth + STT)

```python
# routes.py 에서 호출
from src.depth.depth import detect_and_depth
```

YOLO + Depth를 합쳐서 `detect_and_depth()` 하나로 호출.
Depth 모델이 없으면 bbox 면적 기반 fallback으로 자동 처리.

### 임명광 (문장 생성)

```python
# routes.py 에서 호출
from src.nlg.sentence import build_sentence, build_find_sentence, build_question_sentence

sentence = build_sentence(objects, all_changes, camera_orientation)
```

objects 리스트 넣으면 완성된 한국어 문장이 나옴.

---

## 실제로 서버 켜는 법

```bash
# 프로젝트 루트에서
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 확인
http://localhost:8000/health     ← 상태 확인
http://localhost:8000/dashboard  ← 실시간 지도 대시보드
http://localhost:8000/docs       ← 전체 API 문서 (브라우저에서 직접 테스트 가능)
```

---

## 자주 묻는 것

**Q. WiFi이름(wifi_ssid)을 왜 이렇게 많이 쓰나?**
공간 ID 역할. 같은 WiFi = 같은 공간으로 판단.
장소 저장, 공간기억 비교, 추적기 분리가 모두 이 기준으로 동작.

**Q. 서버가 죽으면 앱은?**
Android 앱이 3번 연속 실패하면 온디바이스 ONNX 모드로 자동 전환.
서버 없이도 폰 혼자 동작 가능.

**Q. process_ms가 뭐야?**
서버가 이미지 받아서 처리 완료까지 걸린 시간(밀리초).
Android 앱 화면 상단에 FPS로 표시됨.

**Q. /docs 주소가 뭔가?**
FastAPI가 자동으로 만들어주는 API 테스트 페이지.
브라우저에서 열면 모든 API를 직접 눌러서 테스트해볼 수 있음.

---

## 로그 분석 가이드 (2026-04-29 추가)

강사님 피드백: **"로그가 중요, 안 되는 부분 원인을 로그로 파악해야 함"**

### Android Logcat 필터

Android Studio 하단 Logcat 탭에서:

| 필터 | 내용 |
|------|------|
| `tag:VG_PERF` | 단계별 처리 시간 (ms) |
| `tag:VG_DETECT` | 탐지 결과, 생성 문장 |

### 성능 로그 형식 (tag:VG_PERF)

```
# 온디바이스 추론
VG_PERF: decode|12|infer|180|dedup|3|total|195|objs|2
                 ↑YOLO 추론 (핵심 병목)

# 서버 응답
VG_PERF: mode|server|server_ms|243|net_ms|89|total|332
                             ↑서버 처리    ↑네트워크
```

### 병목 판단

| 값 | 원인 | 해결 |
|----|------|------|
| `infer` > 500ms | NNAPI 미지원 기기 | Logcat에서 "NNAPI 가속 활성화" 확인 |
| `server_ms` > 1000ms | Depth V2 부하 | 서버에서 Depth 비활성화 |
| `net_ms` > 500ms | 네트워크 불안정 | WiFi 상태 확인 |
| FPS < 5 | 전체 파이프라인 느림 | 각 단계 ms 값 비교 |

### 서버 로그 (uvicorn 터미널)

```bash
# 서버 실행 시 자동 출력
INFO:     127.0.0.1 - "POST /detect HTTP/1.1" 200 OK
# process_ms 값을 응답 JSON에서 확인
```
