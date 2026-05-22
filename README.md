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
| 🤖 | **온디바이스 AI** | `yolo11n_320.tflite` — 카메라 프레임은 기기 내부에서만 추론하며 서버로 전송하지 않음 |
| 🎯 | **82클래스 커스텀 모델** | COCO 80 + 계단 + 문 파인튜닝, hard negative mining |
| 📳 | **4단계 진동 안내** | NONE → SHORT → DOUBLE → URGENT |
| 🚨 | **위험 선행 알림** | 긴급 위험(critical) 감지 시 비프음과 진동으로 먼저 알리고 500ms 후 음성 안내 |
| 🎙️ | **음성 명령 모드** | 장애물 · 찾기 · 주변 확인 · 물건 확인 모드를 STT로 전환 |
| 🔊 | **한국어 TTS** | Android 내장, 화면 없이 상황별 안내 문장 발화 |
| 📡 | **오프라인 보조 안내** | 서버 연결 없이도 Android 내장 TTS와 진동 피드백 동작 |
| 🗺️ | **공공데이터 연동** | GPS 기반 보행자 사고다발구역 · 시각장애 인구 통계 |
| 📊 | **실시간 대시보드** | 탐지 이력 · GPS 경로 · 위험 히트맵 |

---

## 🗣️ 앱 모드

| 모드 | 음성 예시 | 동작 |
|------|-----------|------|
| **장애물** | “앞에 뭐 있어”, “주변 알려줘”, “길 어때” | 즉시 프레임을 분석해 위험도 상위 장애물을 안내 |
| **찾기** | “의자 찾아줘”, “가방 어디 있어” | 찾는 물체의 방향과 거리를 안내하고, 더 가까운 위험물이 있으면 함께 경고 |
| **주변 확인** | “지금 뭐가 있어”, “현재 상황 알려줘” | 현재 프레임과 최근 tracker 상태를 함께 요약 |
| **물건 확인** | “손에 든 게 뭐야”, “바로 앞 뭐야” | 손에 들었거나 바로 가까운 물체를 우선 답변 |

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
4. 앱 설정 ⚙ → 디버깅 모드 활성화
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
│       ├── MainActivity.kt          ← CameraX · STT/TTS · 모드 분기 · 서버 업로드
│       ├── TfliteYoloDetector.kt    ← TFLite 추론 엔진
│       ├── MvpPipeline.kt           ← 추적 · 위험도 · 진동
│       ├── SentenceBuilder.kt       ← 한국어 TTS 문장 생성
│       ├── VoiceGuideConstants.kt   ← COCO 한글 매핑 · 방향 · STT 키워드
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
| `POST` | `/detect` | 온디바이스 탐지 JSON 수신 → 문장 생성 · DB · 대시보드 |
| `POST` | `/detect_json` | 구형 호환 탐지 JSON 수신, 물건 확인/찾기 문장 생성 |
| `POST` | `/question` | 최근 tracker/DB 상태 기반 주변 확인 응답 |
| `POST` | `/gps` | Android 위치 업데이트 |
| `GET`  | `/api/policy` | Android 정책 동기화 (ETag 캐싱) |
| `GET`  | `/events/{session_id}` | 대시보드 SSE 이벤트 스트림 |
| `GET`  | `/history/{session_id}` | 세션별 탐지 이력 |
| `GET`  | `/heatmap/{session_id}` | 세션별 위험 히트맵 |
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
