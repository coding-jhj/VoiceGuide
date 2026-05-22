# VoiceGuide

> 시각장애인을 위한 온디바이스 AI 보행 보조 앱

스마트폰 카메라로 전방 장애물을 실시간 탐지하고, **진동 + 한국어 음성**으로 즉시 안내합니다.  
모든 AI 추론은 기기 안에서 처리됩니다. 서버 없이도 동작합니다.

---

## 어떻게 작동하나요

```
카메라 프레임
    └─▶ TFLite YOLO (온디바이스)
            └─▶ 투표 필터 · IoU 추적 · EMA 평활화
                    └─▶ 위험도 계산
                            ├─▶ 진동 (URGENT / DOUBLE / SHORT)
                            └─▶ 한국어 TTS ("정면 1.2m 앞 계단")
                                    │
                                    └─▶ POST /detect (JSON + GPS)
                                                └─▶ 실시간 대시보드
```

---

## 핵심 기능

| 기능 | 설명 |
|------|------|
| 온디바이스 추론 | `yolo11n_320.tflite` — 서버 전송 없음, 개인정보 보호 |
| 안정화 파이프라인 | 3프레임 투표, IoU 추적, EMA 평활화 |
| 위험도 4단계 | NONE → SHORT → DOUBLE → URGENT 진동 |
| 한국어 TTS | Android 내장 TTS, 화면 없이 즉시 발화 |
| 오프라인 동작 | 서버 없이 TTS + 진동만으로 완전 동작 |
| 공공데이터 연동 | GPS 기반 보행자 사고다발구역 · 장애인 인구 통계 실시간 조회 |
| 실시간 대시보드 | 탐지 이력 · GPS 경로 · 위험 히트맵 |

---

## 빠른 시작

### 서버

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

### Android 앱

1. Android Studio에서 `android/` 폴더 열기
2. Gradle Sync → USB 연결 → `Shift+F10`
3. 앱 설정(⚙) → 서버 URL 입력 *(없으면 오프라인 모드)*

```powershell
# APK만 빌드할 경우
cd android && .\gradlew.bat assembleDebug
```

---

## 배포된 서버

**대시보드** → https://voiceguide-1063164560758.asia-northeast3.run.app/dashboard

| 엔드포인트 | 설명 |
|-----------|------|
| `POST /detect` | 탐지 JSON 수신 → DB + 대시보드 |
| `GET /api/policy` | Android 정책 동기화 (ETag 캐싱) |
| `GET /pedestrian-hotspots/nearby` | GPS 기반 사고다발구역 조회 |
| `GET /disabled-population/nearby` | GPS 기반 시각장애 인구 컨텍스트 |
| `GET /dashboard` | 실시간 대시보드 |

---

## 프로젝트 구조

```
VoiceGuide/
├── android/app/src/main/
│   ├── assets/
│   │   ├── yolo11n_320.tflite      # 온디바이스 모델
│   │   └── policy_default.json     # 오프라인 fallback 정책
│   └── java/com/voiceguide/
│       ├── TfliteYoloDetector.kt   # TFLite 추론
│       ├── MvpPipeline.kt          # 추적 · 위험도 · 진동
│       ├── SentenceBuilder.kt      # 한국어 TTS 문장
│       └── VoicePolicy.kt          # 서버 정책 파싱
│
├── src/api/                        # FastAPI 서버
│   ├── main.py
│   ├── routes.py                   # API 엔드포인트
│   ├── db.py                       # SQLite / PostgreSQL
│   └── tracker.py                  # 세션 EMA 추적
│
├── datasets/                       # 공공데이터
│   ├── pedestrian_hotspots/        # 보행자 사고다발구역
│   ├── disabled_population/        # 시각장애인 등록 현황
│   └── disabled_gender_degree/     # 성별 · 장애등급 통계
│
├── models/                         # 학습된 모델
├── train/                          # 파인튜닝 스크립트
├── tools/                          # 평가 · 데이터 도구
└── templates/dashboard.html        # 실시간 대시보드
```

---

## 테스트

```bash
python -m pytest tests/ -v -m "not integration"
```

---

## 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DATABASE_URL` | SQLite | PostgreSQL URL |
| `API_KEY` | 없음 | Bearer / X-API-Key 인증 |
| `PORT` | 8000 | 서버 포트 |
