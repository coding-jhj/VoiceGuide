# VoiceGuide — 시각장애인 보행 보조 앱

> KDT AI Human 3팀 | 2026-04-24 ~ 2026-05-13

시각장애인이 혼자 이동할 때, 스마트폰 카메라로 앞의 장애물을 감지하고 **진동과 음성으로 즉시 안내**하는 Android 앱입니다.

---

## 작동 방식

YOLO 추론은 Android 기기에서 직접 실행됩니다. 서버는 이미지를 받거나 추론을 수행하지 않습니다.

```
[Android]
CameraX → TFLite YOLO → MvpPipeline → SentenceBuilder → TTS / 진동 출력
                                  ↓ (백그라운드)
                          POST /detect (JSON)
                                  ↓
[FastAPI 서버]
JSON 정규화 → SessionTracker (EMA) → DB 저장 → SSE
                                                ↓
                                     [대시보드] 실시간 현황 · 지도 · 이력
```

긴급 경고는 서버 응답을 기다리지 않고 Android에서 즉시 처리합니다.

---

## 기능

| 영역 | 기능 |
|---|---|
| 객체 탐지 | TFLite YOLO11n 온디바이스 추론 (서버 불필요) |
| 안정화 | Vote 필터(3프레임 중 2회), IoU Tracking, EMA 평활화 |
| 위험도 판단 | 거리 · 중심성 · 클래스 기반 risk score |
| 진동 안내 | NONE / SHORT / DOUBLE / URGENT 4단계 |
| 음성 안내 | Android 내장 TTS, 한국어 즉시 발화 |
| 오프라인 동작 | 서버 없이 TTS + 진동만으로 동작 |
| 서버 연동 | 탐지 결과 · GPS JSON 업로드 |
| 대시보드 | 현재 객체 · 이동 경로 · 24시간 이력 실시간 표시 |

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| Android | Kotlin, CameraX, TensorFlow Lite |
| 온디바이스 모델 | yolo11n_320.tflite (기본), yolo26n_float32.tflite (fallback) |
| TTS | Android 내장 |
| 백엔드 | Python 3.10+, FastAPI, uvicorn |
| DB | SQLite (기본) / PostgreSQL Supabase (운영) |
| 배포 | GCP Cloud Run |
| 대시보드 | Leaflet.js, SSE |

---

## 서버 실행

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

서버에 ML 모델이 필요하지 않습니다.

### 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DATABASE_URL` | (없음) | PostgreSQL URL. 없으면 `voiceguide.db` SQLite 사용 |
| `API_KEY` | (없음) | 설정 시 `Authorization: Bearer <key>` 또는 `X-API-Key: <key>` 필요 |
| `ALLOWED_ORIGINS` | localhost:8000 외 | CORS 허용 origin. `*` 로 전체 허용 |
| `DETECT_SAVE_EVERY_N_FRAMES` | 5 | DB 저장 간격 (N 프레임마다 1회) |
| `SNAPSHOT_MIN_INTERVAL_S` | 1.0 | 스냅샷 최소 저장 간격 (초) |
| `PORT` | 8000 | 서버 포트 |

### 배포된 서버

**대시보드:** https://voiceguide-1063164560758.asia-northeast3.run.app/dashboard

```
GET  /dashboard  →  실시간 대시보드
GET  /health     →  서버 + DB 상태 확인
GET  /           →  /dashboard 리다이렉트
```

세션 ID를 입력하면 해당 기기의 탐지 현황 · 이동 경로 · 24시간 이벤트 내역을 실시간으로 확인합니다.

---

## Android 앱 실행

1. Android Studio에서 `android/` 폴더 열기
2. Gradle Sync
3. USB로 기기 연결 (USB 디버깅 활성화)
4. Run (`Shift+F10`)
5. 앱 설정(⚙) → 서버 URL 입력

서버 URL 없이 실행하면 로컬 TTS + 진동만 동작합니다 (오프라인 모드).

```powershell
# APK 빌드만 할 경우
cd android
.\gradlew.bat assembleDebug
```

---

## API

`API_KEY` 환경변수가 설정된 경우 `Authorization: Bearer <key>` 또는 `X-API-Key: <key>` 헤더가 필요합니다.

| 메서드 | 경로 | 사용 주체 | 설명 |
|---|---|---|---|
| GET | `/health` | 운영 | 서버 · DB · writer 상태 확인 |
| GET | `/api/policy` | Android | 정책 JSON 동기화 (ETag 캐싱) |
| POST | `/detect` | Android | 온디바이스 탐지 JSON 수신 → DB 저장 + 대시보드 브로드캐스트 |
| POST | `/detect_json` | Android | 구형 포맷 호환용 탐지 수신 |
| POST | `/question` | Android | tracker 상태 기반 질문 응답 |
| POST | `/gps` | Android | 현재 위치 저장 및 SSE 발행 |
| POST | `/gps/route/save` | Android | 현재 GPS track을 저장 경로로 확정 |
| GET | `/status/{session_id}` | 대시보드 | 현재 객체 · GPS · track · 최근 이벤트 |
| GET | `/events/{session_id}` | 대시보드 | SSE 실시간 스트림 |
| GET | `/sessions` | 대시보드 | 최근 GPS 세션 목록 |
| GET | `/team-locations` | 대시보드 | 최근 위치가 있는 기기 목록 |
| GET | `/history/{session_id}` | 대시보드 | 최근 24시간 탐지 이력 |
| GET | `/heatmap/{session_id}` | 대시보드 | 위험 구간 히트맵 데이터 |
| GET | `/routes/{session_id}` | 대시보드 | 저장된 GPS 경로 목록 |
| GET | `/routes/{session_id}/{route_id}` | 대시보드 | 특정 GPS 경로 좌표 |
| GET | `/dashboard/summary` | 대시보드 | 전체 단말 24시간 탐지 통계 |
| POST | `/locations/save` | Android | 세션별 저장 장소 등록 |
| GET | `/locations` | Android | 저장 장소 목록 조회 |
| GET | `/locations/find/{label}` | Android | 저장 장소 검색 |
| DELETE | `/locations/{label}` | Android | 저장 장소 삭제 |
| GET | `/dashboard` | 브라우저 | 대시보드 HTML |

---

## 테스트

```bash
# 서버 단위 테스트
python -m pytest tests/ -v -m "not integration"

# 실제 서버 대상 integration 테스트 (서버 실행 후)
python -m pytest tests/test_server.py -v -m integration

# GPS 데모 시뮬레이터 (대시보드 세션 ID: demo-device-03)
python tools/simulator.py
```

---

## 프로젝트 구조

```
VoiceGuide/
├── android/app/src/main/
│   ├── assets/
│   │   ├── yolo11n_320.tflite        # 온디바이스 추론 모델 (기본)
│   │   ├── yolo26n_float32.tflite    # fallback 모델
│   │   └── policy_default.json       # 서버 정책 없을 때 fallback
│   └── java/com/voiceguide/
│       ├── MainActivity.kt           # 카메라 · TTS · 서버 연동 총괄
│       ├── TfliteYoloDetector.kt     # TFLite 추론 엔진
│       ├── MvpPipeline.kt            # IoU tracking · EMA · 위험도 · 진동
│       ├── SentenceBuilder.kt        # 온디바이스 한국어 TTS 문장 생성
│       ├── VoicePolicy.kt            # policy.json 파싱 및 캐시
│       ├── BoundingBoxOverlay.kt     # 화면 위 bbox 표시
│       └── Detection.kt              # 탐지 결과 데이터 클래스
│
├── src/
│   ├── api/
│   │   ├── main.py                   # FastAPI 진입점
│   │   ├── routes.py                 # API 엔드포인트
│   │   ├── db.py                     # SQLite / PostgreSQL 저장
│   │   ├── tracker.py                # 세션별 EMA 추적기
│   │   └── events.py                 # SSE 브로드캐스트
│   ├── nlg/
│   │   ├── sentence.py               # 한국어 안내 문장 생성 (서버 · 대시보드용)
│   │   └── templates.py              # 방향 · 행동 문구 상수
│   └── config/
│       ├── policy.json               # 탐지 분류 기준 SSOT
│       └── policy.py                 # policy.json 로더
│
├── templates/dashboard.html          # 실시간 대시보드
├── tests/                            # pytest 테스트
├── tools/simulator.py                # 데모용 GPS 동선 시뮬레이터
├── Dockerfile
└── requirements.txt
```

---

GitHub: https://github.com/coding-jhj/VoiceGuide
