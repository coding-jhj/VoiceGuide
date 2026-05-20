# VoiceGuide — 시각장애인 보행 보조 앱

> KDT AI Human 3팀 | 2026-04-24 ~ 2026-05-13

시각장애인이 혼자 이동할 때, 카메라로 앞의 장애물을 감지하고 **진동과 음성으로 즉시 안내**하는 Android 앱입니다.

---

## 지금 동작하는 것 (MVP)

| 기능 | 상태 |
|---|---|
| 장애물 탐지 (장애물 모드) | ✅ 동작 |
| 위험도 기반 진동 패턴 (NONE/SHORT/DOUBLE/URGENT) | ✅ 동작 |
| 음성 안내 문장 TTS | ✅ 동작 |
| 물건 찾기 모드 ("의자 찾아줘") | ✅ 동작 |
| 질문 응답 모드 ("지금 뭐 있어?") | ✅ 동작 |
| 들고있는것 모드 | ✅ 동작 |
| 서버 전송 + DB 저장 | ✅ 동작 |
| 대시보드 실시간 현황 | ✅ 동작 |
| 대시보드 24시간 탐지 내역 | ✅ 동작 |
| 이동 경로 지도 시각화 | ✅ 동작 |
| 오프라인 동작 (서버 없이 진동 + 로컬 TTS) | ✅ 동작 |

---

## 아키텍처

```
Android (Kotlin)
 └─ CameraX
     └─ TfliteYoloDetector.kt
         └─ yolo11n_320.tflite (TFLite GPU / XNNPACK)
             └─ removeDuplicates() → voteOnly() (3프레임 중 2회 이상 확정)
                 └─ MvpPipeline.kt (IoU 트래킹 · EMA · riskScore · 진동 패턴)
                     ├─ 진동 즉시 출력
                     ├─ SentenceBuilder.kt → 로컬 TTS 즉시 발화
                     │
                     ├─ (백그라운드) POST /detect → DB 저장 + tracker 업데이트
                     └─ (fire-and-forget) POST /detect_json → tracker/recent_detections

FastAPI 서버 (GCP Cloud Run)
 ├─ SessionTracker: EMA 평활화, 접근 감지
 ├─ sentence.py: NLG 문장 생성 (대시보드 표시용)
 ├─ db.py: detection_events · GPS · recent_detections 저장
 └─ events.py: SSE → 대시보드 실시간 브로드캐스트
```

**TTS 음성은 로컬 SentenceBuilder가 생성합니다. 서버 응답을 기다리지 않습니다.**  
서버는 이미지를 받거나 YOLO 추론을 수행하지 않습니다.

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| Android | Kotlin, CameraX, TensorFlow Lite |
| 온디바이스 모델 | yolo11n_320.tflite (기본), yolo26n_float32.tflite (fallback) |
| TTS / STT | Android 내장 |
| 백엔드 | Python 3.10+, FastAPI |
| DB | SQLite (로컬) / PostgreSQL Supabase (운영) |
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

### 배포된 서버

```
https://voiceguide-1063164560758.asia-northeast3.run.app
GET /health      →  서버 + DB 상태 확인
GET /dashboard   →  실시간 대시보드
```

---

## Android 앱 실행

1. Android Studio에서 `android/` 폴더 열기
2. Gradle Sync
3. USB로 기기 연결 (USB 디버깅 활성화)
4. Run (`Shift+F10`)
5. 앱 설정(⚙) → 서버 URL 입력

서버 URL 없이 실행하면 로컬 TTS + 진동만 동작합니다 (오프라인 모드).

---

## 대시보드

```
GET /dashboard
```

세션 ID를 입력하면 해당 기기의 탐지 현황·이동 경로·24시간 이벤트 내역을 실시간으로 확인할 수 있습니다.

---

## 주요 API

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/detect` | 탐지 결과 JSON 수신 → DB 저장 + tracker 업데이트 |
| POST | `/detect_json` | 탐지 결과 fire-and-forget 저장 (응답 미사용) |
| POST | `/question` | 질문 응답 (tracker 누적 상태 조회) |
| GET | `/api/policy` | policy.json 동기화 (ETag 캐싱) |
| GET | `/status/{session_id}` | 세션 현재 상태 조회 |
| GET | `/events/{session_id}` | SSE 실시간 스트림 |
| POST | `/locations/save` | 세션별 저장 장소 등록 |
| GET | `/locations` | 저장 장소 목록 조회 |
| GET | `/locations/find/{label}` | 저장 장소 검색 |
| DELETE | `/locations/{label}` | 저장 장소 삭제 |
| GET | `/history/{session_id}` | 24시간 탐지 이벤트 내역 |
| GET | `/routes/{session_id}` | 저장된 GPS 경로 목록 |
| GET | `/dashboard` | 대시보드 HTML |

---

## 프로젝트 구조

```
VoiceGuide/
├── android/app/src/main/
│   ├── assets/
│   │   ├── yolo11n_320.tflite       # 온디바이스 추론 모델 (기본)
│   │   ├── yolo26n_float32.tflite   # fallback 모델
│   │   └── policy_default.json      # 기본 정책 (서버 policy 없을 때 사용)
│   └── java/com/voiceguide/
│       ├── MainActivity.kt          # 카메라·TTS·STT·서버 연동 총괄
│       ├── TfliteYoloDetector.kt    # TFLite 추론 엔진
│       ├── MvpPipeline.kt           # IoU 트래킹·EMA·위험도·진동 패턴
│       ├── SentenceBuilder.kt       # 온디바이스 한국어 TTS 문장 생성
│       ├── VoicePolicy.kt           # policy.json 파싱 및 캐시
│       ├── VoiceGuideConstants.kt   # 방향·클래스 상수
│       └── Detection.kt             # 탐지 결과 데이터 클래스
│
├── src/
│   ├── api/
│   │   ├── main.py                  # FastAPI 진입점
│   │   ├── routes.py                # 라우터
│   │   ├── db.py                    # SQLite/PostgreSQL 저장
│   │   ├── tracker.py               # 서버측 EMA 추적기
│   │   └── events.py                # SSE 브로드캐스트
│   ├── nlg/
│   │   ├── sentence.py              # 한국어 안내 문장 생성 (대시보드용)
│   │   └── templates.py             # 방향·행동 문구 상수
│   └── config/
│       ├── policy.json              # 탐지 분류 기준 SSOT
│       └── policy.py                # policy.json 로더
│
├── templates/dashboard.html         # 실시간 대시보드
├── tests/                           # pytest 테스트
├── tools/simulator.py               # 데모용 GPS 동선 시뮬레이터
├── Dockerfile
└── requirements.txt
```

---

GitHub: https://github.com/coding-jhj/VoiceGuide
