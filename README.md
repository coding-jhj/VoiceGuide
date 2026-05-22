<div align="center">

# 🦯 VoiceGuide

**시각장애인을 위한 온디바이스 AI 보행 보조 앱**

스마트폰 카메라로 전방 장애물을 실시간 탐지하고  
**진동 + 한국어 음성**으로 즉시 안내합니다

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Android](https://img.shields.io/badge/Android-Kotlin-3DDC84?style=flat-square&logo=android&logoColor=white)](https://developer.android.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![GCP](https://img.shields.io/badge/GCP-Cloud_Run-4285F4?style=flat-square&logo=googlecloud&logoColor=white)](https://cloud.google.com/run)

[**🌐 라이브 대시보드 →**](https://voiceguide-1063164560758.asia-northeast3.run.app/dashboard)

</div>

---

## 🔍 어떻게 작동하나요

```
📱 카메라 프레임
      │
      ▼
🤖 TFLite YOLO  ←── 온디바이스 추론 (서버 불필요)
      │
      ▼
⚙️  투표 필터 → IoU 추적 → EMA 평활화 → 위험도 계산
      │
      ├──🔴 URGENT 진동   "위험! 정면에 계단!"
      ├──🟠 DOUBLE 진동   "1.2m 앞 킥보드, 왼쪽으로"
      └──🟡 SHORT  진동   "오른쪽에 사람 있어요"
                │
                ▼ (백그라운드)
         POST /detect (JSON + GPS)
                │
                ▼
         📊 실시간 대시보드
```

---

## ✨ 핵심 기능

| | 기능 | 설명 |
|--|------|------|
| 🤖 | **온디바이스 AI** | `yolo11n_320.tflite` — 영상이 기기 밖으로 나가지 않음 |
| 🎯 | **82클래스 커스텀 모델** | COCO 80 + 계단 + 문 파인튜닝, hard negative mining |
| 📳 | **4단계 진동 안내** | NONE → SHORT → DOUBLE → URGENT |
| 🔊 | **한국어 TTS** | Android 내장, 화면 없이 즉시 발화 |
| 📡 | **오프라인 완전 동작** | 서버 없이도 TTS + 진동 100% 작동 |
| 🗺️ | **공공데이터 연동** | GPS 기반 보행자 사고다발구역 · 시각장애 인구 통계 |
| 📊 | **실시간 대시보드** | 탐지 이력 · GPS 경로 · 위험 히트맵 |

---

## 🚀 빠른 시작

### 서버 실행

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

### Android 앱

```
1. Android Studio → android/ 폴더 열기
2. Gradle Sync
3. USB 연결 (디버깅 활성화) → Shift+F10
4. 앱 설정 ⚙ → 서버 URL 입력  (없으면 오프라인 모드)
```

```powershell
# APK 빌드만
cd android && .\gradlew.bat assembleDebug
```

### 테스트

```bash
python -m pytest tests/ -v -m "not integration"
```

---

## 📁 프로젝트 구조

```
VoiceGuide/
│
├── 📱 android/app/src/main/
│   ├── assets/
│   │   ├── yolo11n_320.tflite       ← 온디바이스 모델
│   │   └── policy_default.json      ← 오프라인 fallback 정책
│   └── java/com/voiceguide/
│       ├── TfliteYoloDetector.kt    ← TFLite 추론 엔진
│       ├── MvpPipeline.kt           ← 추적 · 위험도 · 진동
│       ├── SentenceBuilder.kt       ← 한국어 TTS 문장 생성
│       └── VoicePolicy.kt           ← 서버 정책 파싱 · 캐시
│
├── ⚡ src/api/                       ← FastAPI 서버
│   ├── routes.py                    ← 모든 엔드포인트
│   ├── db.py                        ← SQLite / PostgreSQL
│   ├── tracker.py                   ← 세션 EMA 추적
│   └── events.py                    ← SSE 브로드캐스트
│
├── 🗂️  datasets/                     ← 공공데이터
│   ├── pedestrian_hotspots/         ← 보행자 사고다발구역 (GeoJSON)
│   ├── disabled_population/         ← 시각장애인 등록 현황
│   └── disabled_gender_degree/      ← 성별 · 장애등급 통계
│
├── 🧠 models/                        ← 학습된 YOLO 모델
├── 🏋️  train/                         ← 파인튜닝 스크립트
├── 🔧 tools/                         ← 평가 · 데이터 도구
└── 🖥️  templates/dashboard.html      ← 실시간 대시보드
```

---

## 🌐 배포된 서버 API

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| `POST` | `/detect` | 탐지 JSON 수신 → DB + 대시보드 |
| `GET`  | `/api/policy` | Android 정책 동기화 (ETag 캐싱) |
| `GET`  | `/pedestrian-hotspots/nearby` | GPS 기반 사고다발구역 |
| `GET`  | `/disabled-population/nearby` | GPS 기반 시각장애 인구 |
| `GET`  | `/dashboard` | 실시간 대시보드 |

---

## ⚙️ 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DATABASE_URL` | SQLite | PostgreSQL URL |
| `API_KEY` | 없음 | Bearer / X-API-Key 인증 |
| `PORT` | `8000` | 서버 포트 |

---

<div align="center">

**AI HUMAN 4기 3팀** · 2026

</div>
