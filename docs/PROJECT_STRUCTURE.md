# VoiceGuide 폴더 구조

> 기준: 발표/배포/Android 연동에서 실제로 사용하는 구조만 먼저 봅니다.
> 오래된 실험 서버와 참고 코드는 `legacy/` 아래에 보관되어 있으며, 현재 실행 진입점이 아닙니다.

## 실행 진입점

| 목적 | 진입점 | 상태 |
|---|---|---|
| Android 앱 | `android/` | 현재 앱 프로젝트 |
| 서버 API | `src.api.main:app` | 현재 GCP/로컬 서버 |
| 서버 라우트 | `src/api/routes.py` | `/detect`, `/status`, `/dashboard` 등 |
| DB/tracker | `src/api/db.py`, `src/api/tracker.py` | SQLite 또는 `DATABASE_URL` |
| 대시보드 | `templates/dashboard.html` | 서버 `/dashboard`에서 반환 |
| Gradio 데모 | `app.py` | 보조 데모, Android 본 흐름 아님 |

Android Studio에서 열 폴더:

```text
C:\VoiceGuide\VoiceGuide\android
```

서버 로컬 실행:

```bat
cd /d C:\VoiceGuide\VoiceGuide
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

GCP 배포:

```bat
cd /d C:\VoiceGuide\VoiceGuide
gcloud run deploy voiceguide --source . --region asia-northeast3 --memory 2Gi --cpu 2 --timeout 120 --allow-unauthenticated --port 8080
```

## 루트 폴더

| 경로 | 용도 | 비고 |
|---|---|---|
| `README.md` | 프로젝트 첫 진입 문서 | 과장 없이 현재 검증된 기능 중심 |
| `SETUP.md` | 로컬 실행 가이드 | CMD 기준은 `docs/00_실행/CMD_RUNBOOK.md` 우선 |
| `Dockerfile` | Cloud Run 컨테이너 빌드 | `src.api.main:app` 실행 |
| `requirements-server.txt` | 서버 배포 의존성 | Cloud Run 기준 |
| `requirements.txt` | 전체/개발 의존성 | 로컬 데모 포함 |
| `start.bat`, `stop.bat` | 로컬 서버/ngrok 편의 스크립트 | 선택 사용 |
| `app.py` | Gradio 데모 | 발표 보조용 |

루트에 두지 않는 것:

| 항목 | 정리 기준 |
|---|---|
| 개발 가이드/역할 문서 | `docs/04_팀/` |
| 실행/배포 절차 | `docs/00_실행/`, `docs/03_서버/` |
| 회의록 | `docs/02_미팅/` |
| 모델 가중치 | Git 제외, 필요 시 별도 공유 |
| DB 파일/캐시/실행 로그 | Git 제외 |

## 주요 코드 폴더

| 경로 | 역할 |
|---|---|
| `android/` | Android Studio 프로젝트 |
| `src/api/` | FastAPI 서버, DB, tracker |
| `src/vision/` | YOLO 탐지 |
| `src/depth/` | Depth Anything V2 및 hazard 보정 |
| `src/nlg/` | 한국어 안내 문장 생성 |
| `src/voice/` | STT/TTS |
| `src/ocr/` | 버스 번호 OCR fallback |
| `templates/` | HTML 대시보드 |
| `tools/` | 검증/배포 보조 스크립트 |
| `tests/` | pytest 테스트 |
| `train/` | 학습/데이터 준비 스크립트 |
| `depth_anything_v2/` | Depth 모델 코드 |

## 문서 폴더

| 경로 | 역할 |
|---|---|
| `docs/00_실행/` | CMD 실행 순서 |
| `docs/01_학습/` | 코드/기술 이해 문서 |
| `docs/02_미팅/` | 미팅/강사 피드백 |
| `docs/03_서버/` | GCP, ngrok, 서버 배포 |
| `docs/04_팀/` | 역할, 팀장/서버 담당 체크리스트 |
| `docs/05_기획/` | PRD, MVP, 기획 |
| `docs/06_발표/` | 발표 자료/스크립트 |
| `docs/07_디버그/` | 성능/장애물/문제 해결 |

핵심 문서:

| 문서 | 용도 |
|---|---|
| `docs/00_실행/CMD_RUNBOOK.md` | CMD 실행/배포/검증 순서 |
| `docs/04_팀/SERVER_AND_LEAD_ACTIONS.md` | 서버 담당 + 팀장 할 일 |
| `docs/04_팀/STUDENT_DEVELOPMENT_GUIDELINE.md` | 원본 개발 개선 가이드 |
| `docs/07_디버그/DETECTION_DEBUG.md` | 장애물 인식 디버그 |
| `docs/07_디버그/PERF_DEBUG.md` | FPS/추론속도 디버그 |

## Legacy와 실험 코드

| 경로 | 상태 |
|---|---|
| `legacy/서버_DB/` | Supabase 연결 테스트용 과거 서버 |
| `legacy/서버_DB_수정/` | 블러/도로 관련 실험 서버 |

이 폴더들은 참고용입니다. Android 앱과 GCP 배포는 여기의 `main.py`를 실행하지 않습니다.

## Git에 올리지 않는 것

`.gitignore` 기준:

| 항목 | 이유 |
|---|---|
| `.env`, `.env.*` | 키/DB URL 보호 |
| `*.pt`, `*.pth`, `*.onnx`, `*.onnx.data`, `*.tflite` | 대용량 모델 |
| `voiceguide.db` | 로컬 DB |
| `.gradle-*`, `android/app/build/` | Android 빌드 캐시 |
| `.pytest_cache/`, `.ultralytics/`, `__pycache__/` | 실행 캐시 |
| `runs/`, `datasets/`, `flagged/` | 실행/학습 산출물 |

## 정리 원칙

1. 새 팀원이 `README.md`와 `docs/00_실행/CMD_RUNBOOK.md`만 보고 실행할 수 있어야 합니다.
2. 서버 진입점은 `src.api.main:app` 하나로 말합니다.
3. 실험 기능은 문서에서 "동작 확인", "실험 기능", "예정 기능"으로 구분합니다.
4. 안전 관련 기능은 과장하지 않습니다. 거리 정보는 "대략적 추정"이라고 설명합니다.
5. 발표 D-2 이후에는 기능 추가보다 실행 재현과 로그 증명을 우선합니다.
