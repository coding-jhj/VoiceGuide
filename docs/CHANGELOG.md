# VoiceGuide 작업 내역 (2026-04-27 최신)

---

## 2026-04-27 후반 수정 (조장 정환주)

```bash
git pull origin main
pip install -r requirements.txt  # websockets 버전 업데이트 포함
```

### 버그 수정

| 파일 | 수정 내용 |
|------|---------|
| `src/vision/detect.py` | `stairs` 최소 신뢰도 0.50→0.72 (키보드 계단 오탐 방지) |
| `src/vision/detect.py` | `tie`·`umbrella`·`handbag`·`wine glass`·`cup`·`bowl` 신뢰도 상향 (실내 오탐) |
| `src/voice/tts.py` | ElevenLabs SDK 완전 제거 → gTTS 기본, Naver Clova 준비 |
| `src/api/routes.py` | `/tts` 엔드포인트 추가 (Android 앱 TTS용 mp3 반환) |
| `requirements.txt` | `websockets>=12.0,<13.0` (ElevenLabs SDK websockets 충돌 해결) |
| `android/.../MainActivity.kt` | `isListening` 플래그 — STT 중 TTS 차단, STT 시작 시 TTS 즉시 중단 |
| `android/.../MainActivity.kt` | `promptAutoStart` 폴링 방식 — TTS 끝난 후 STT 시작 ("네" 무반응 해결) |
| `android/.../MainActivity.kt` | `ttsRequestId` — stale 재생 방지 (겹침 완전 해결) |
| `android/.../MainActivity.kt` | `lastDetectionTime` — 탐지 텍스트 3초 유지 후 "장애물 없음" 전환 |
| `android/.../MainActivity.kt` | `speakElevenLabs` → `ttsExecutor` 직렬화 + MediaPlayer 단일 인스턴스 |

### TTS 구조 변경

- **서버**: gTTS(무료) 기본 → `.env`에 `NAVER_CLIENT_ID`/`NAVER_CLIENT_SECRET` 추가 시 Naver Clova 자동 전환
- **앱**: 서버 URL 있으면 서버 `/tts` mp3 스트리밍, 없으면 Android 내장 TTS

---

> 팀원 공유용 — 오늘 추가/수정된 내용 전체 정리

---

## 2026-04-27 변경 내역

**git pull 후 아래 명령어 실행해주세요.**

```bash
git pull origin main
pip install -r requirements.txt
```

### 팀원 브랜치 반영 (조장 정환주)

| 브랜치 | 팀원 | 반영 내용 |
|--------|------|---------|
| `feature/tts` | 문수찬 | gTTS → **ElevenLabs TTS** 교체 (Anna Kim 보이스, eleven_multilingual_v2 모델, 캐시 유지) |
| `feature/nlg` | 임명광 | `get_alert_mode()` 경고 피로 방지 / `피해가세요→피하세요` 문구 / 고양이 동물 목록 추가 / `_secondary()` 정보 과다 방지 / `build_find_sentence()` 문장 자연스럽게 / **바운딩박스 오버레이** (`BoundingBoxOverlay.kt`) / 차량 경고 문구 "즉시→잠깐" |
| `feature/api` | 신유득 | **Supabase/PostgreSQL FastAPI 서버** (`서버_DB/`) — items CRUD + DB 저장 엔드포인트 / `.env.example` DB 변수 추가 / `requirements.txt` psycopg 추가 |

### 보안

- **ElevenLabs API 키** 하드코딩 → `.env` 환경변수로 이동
- `git filter-repo`로 전체 히스토리에서 키 완전 제거 후 force push
- `.env.example`에 `ELEVENLABS_API_KEY`, `OPENAI_API_KEY` 항목 추가

### 버그 수정

| 파일 | 수정 내용 |
|------|---------|
| `src/voice/tts.py` | `client.generate()` → `client.text_to_speech.convert()` (ElevenLabs SDK v2 호환) |
| `src/api/routes.py` | `alert_level`/`beep` → `alert_mode` 통일 |
| `android/.../MainActivity.kt` | `beep` 필드 → `alert_mode` 읽도록 수정 (breaking bug 해결) |
| `requirements.txt` | `elevenlabs`, `easyocr`, `python-dotenv`, `websockets>=10.0,<13.0` 추가 |
| `src/api/main.py` | 서버 시작 시 `load_dotenv()` 호출 |

### 기능 강화

| 항목 | 내용 |
|------|------|
| **alert_mode 3단계** | `critical` — 말 중이어도 끊고 1.25× 빠르게 즉각 경고 |
| | `beep` — 비프음만 재생, TTS 없음 (경고 피로 방지) |
| | `silent` — 무음, UI만 업데이트 |
| **TTS 캐시 워밍업** | 서버 시작 시 자주 쓰는 문장 10개 미리 생성 (첫 요청 지연 방지) |

---

## 요약 (2026-04-26)

기존 MVP 위에 AI 성능 강화·Android 기능 완성·안전성 개선·문서 전면 업데이트를 진행했습니다.  
**git pull 후 아래 설치 명령어 실행해주세요.**

```bash
git pull origin main
pip install ddgs pygame onnx onnxscript
```

> **`depth_anything_v2_vits.pth`** (94MB) — 각자 받아야 합니다 → `SETUP.md` 3단계 참고
>
> **`yolo11m_indoor.pt`** (파인튜닝 모델, 39MB) — `.gitignore`로 git 미포함. 아래 둘 중 하나:
> - 방법 A (권장): 직접 학습 (~9분, GPU 필요)
>   ```bash
>   python train/prepare_dataset.py   # 데이터 다운로드
>   python train/finetune.py          # 학습 → yolo11m_indoor.pt 자동 생성
>   ```
> - 방법 B: 조장에게 구글드라이브로 파일 받기

---

## 1. AI 모델

### YOLO11m 파인튜닝 — 계단 클래스 추가

기존 YOLO11m에는 계단 클래스가 없었습니다.  
DuckDuckGo로 계단 이미지 404장을 수집하고 자동 라벨링 후 직접 학습했습니다.

| 항목 | 내용 |
|------|------|
| 학습 데이터 | 계단 이미지 404장 (자동 수집·라벨링) |
| 학습 시간 | RTX 5060 GPU, 약 9분 |
| 계단 mAP50 | **0.992** (정밀도 91.7%, 재현율 100%) |
| 결과 모델 | `yolo11m_indoor.pt` |

- `src/vision/detect.py` — `yolo11m_indoor.pt` 자동 로드, 없으면 `yolo11m.pt` fallback
- `TARGET_CLASSES`에 `stairs → 계단` 추가
- 계단은 항상 `is_ground_level=True` 처리 (위험도 상향)

---

### Depth Anything V2 — GPU 활성화

기존에 주석으로 비활성화되어 있던 Depth V2를 완전히 켰습니다.

- `depth_anything_v2_vits.pth` 파일 있으면 자동 로드, 없으면 bbox 기반 자동 fallback
- GPU(CUDA) 자동 감지, CPU도 지원
- 이미지당 depth map 1회 추론 (bbox별 반복 제거 → 속도 최적화)
- **안전 우선**: bbox 내 하위 30% 깊이값 사용 → 실제보다 약간 가깝게 추정 → 조기 경고

---

### 깊이 맵 기반 계단·낙차·턱 감지 — 신규 (`src/depth/hazard.py`)

YOLO가 잡지 못하는 계단을 Depth V2 출력만으로 감지합니다.

- 이미지 하단 60% 바닥 영역을 12구역으로 분석
- 깊이 급증(>1.2m) → 낙차/계단 하강 경고
- 깊이 급감(>1.0m) → 턱/계단 상승 경고
- 좌우가 중앙보다 가까우면 좁은 통로 경고

```
"조심! 0.7m 앞에 계단이나 낙차가 있어요. 멈추세요."
"발 앞에 턱이나 계단이 있어요. 약 0.8m."
```

---

### 객체 추적기 — 신규 (`src/api/tracker.py`)

프레임마다 튀는 거리값을 EMA(지수이동평균)로 안정화합니다.

- 거리 평활화 (α=0.55): 1.2m→1.8m→1.1m 튀는 것을 1.3m→1.4m→1.35m으로 안정화
- 접근 감지: 0.4m 이상 가까워지면 "사람이 가까워지고 있어요" 자동 생성
- 소멸 감지: 4초간 미탐지 + 3m 이내였던 물체 → "의자가 사라졌어요" 자동 생성

---

## 2. Android 앱

### 캡처 간격 단축

**2초 → 1초** (INTERVAL_MS = 1000L)

### STT 음성 명령 — 신규

| 명령어 | 전환 모드 |
|--------|---------|
| "주변 알려줘", "앞에 뭐 있어" | 장애물 모드 |
| "찾아줘", "어디 있어" | 찾기 모드 |
| "이거 뭐야", "뭐야" | 확인 모드 |

초록 "음성 명령" 버튼으로 실행합니다.

### 카메라 방향 자동 감지 — 신규

가속도 센서(TYPE_ACCELEROMETER)로 폰 기울기를 실시간 감지합니다.

| 기울기 | 감지 방향 |
|--------|---------|
| 세로 정상 | front |
| 세로 뒤집힘 | back |
| 가로 왼쪽 | left |
| 가로 오른쪽 | right |

기존 하드코딩 `"front"` 제거 — 이제 서버에 실제 방향 자동 전송합니다.

### ONNX 온디바이스 추론 — 신규

`android/app/src/main/assets/yolo11m.onnx` 파일이 있으면 서버 없이 폰 단독으로 탐지합니다.

- 서버 있을 때: 서버 추론 (Depth V2 포함, 더 정확)
- 서버 없을 때: 온디바이스 ONNX 추론 자동 전환
- 계단 탐지 시 "조심! 앞에 계단이 있어요." 최우선 출력

ONNX 파일 생성 방법:
```bash
python export_tflite.py
```

### Failsafe 안전 경고 — 신규

| 상황 | 동작 |
|------|------|
| 서버 3회 연속 실패 | "서버 연결이 끊겼어요. 주의해서 이동하세요." 음성 |
| 6초간 결과 없음 | "분석이 중단됐어요. 주의해서 이동하세요." 음성 |
| 카메라 오류 | "카메라를 사용할 수 없어요. 주의하세요." 음성 |

네트워크 타임아웃도 단축했습니다 (15초→5초, 30초→8초).

### UI 추가

- 초록 "음성 명령" 버튼
- 모드/방향 상태 표시 텍스트 (`모드: 장애물 | 방향: 정면`)

---

## 3. 서버

### NLG 문장 품질 개선 (`src/nlg/sentence.py`)

거리 기반 긴박도 4단계 — 기존의 텍스트 라벨(가까이/보통) 대신 실제 미터값으로 판단합니다.

| 거리 | 출력 예시 |
|------|---------|
| 0.5m 미만 | `"위험! 바로 앞 의자!"` |
| 0.5~1.0m | `"멈추세요! 바로 앞에 의자가 있어요. 약 70cm."` |
| 1.0~2.5m | `"바로 앞에 의자가 있어요. 약 1.2m. 멈추세요."` |
| 2.5m 이상 | `"바로 앞에 의자가 있어요. 약 3.0m."` |

바닥 장애물 전용 문장도 추가했습니다.
```
"조심! 발 아래 배낭. 오른쪽으로 피해가세요."
```

### 서버 안전성

- **전역 예외 핸들러** — 서버 오류 시에도 Android에 `"분석 중 오류가 발생했어요. 주의해서 이동하세요."` 반환
- **FastAPI lifespan** — 기존 deprecated `on_event` 방식 교체

### TTS 캐시 (`src/voice/tts.py`)

같은 문장은 `__tts_cache__/` 폴더에 MP3로 저장해 다음부터 네트워크 없이 즉시 재생합니다.

### Gradio 데모 개선 (`app.py`)

- 장애물/찾기/확인 모드 라디오 버튼 추가
- 탐지 결과 이미지에 바운딩 박스 시각화
- 추론 시간(ms), Depth V2 사용 여부 표시
- 계단/낙차 감지 시 화면 하단 빨간 배너 표시

---

## 4. 버그 수정

| 버그 | 수정 내용 |
|------|---------|
| Android 앱 크래시 | `yolo11n.onnx` → `yolo11m.onnx` 파일명 불일치 수정 |
| 거리 긴급도 오판 | area_ratio 라벨 대신 distance_m 직접 사용 |
| 거리 99.9m 표시 | area_ratio=0일 때 10.0m로 cap |
| Gradio 방향 오표시 | `"far_left"` 등 잘못된 키 → `CLOCK_TO_DIRECTION` 직접 사용 |
| 테스트 3개 실패 | fixture 누락(`conftest.py` 추가), direction 값 오류 수정 |
| "가방" 중복 | handbag→핸드백, backpack→배낭으로 구분 |
| FastAPI 경고 | deprecated `on_event` → `lifespan` 방식 교체 |

---

## 5. 테스트

**12/12 전부 통과** (`pytest tests/`)

새로 추가된 테스트:
- `stairs` 클래스 포함 확인
- `hazards` 응답 필드 확인
- `/stt` 엔드포인트 확인
- direction 값 `8시~4시` 기준으로 수정

---

## 6. 문서

| 파일 | 수정 내용 |
|------|---------|
| `docs/INSTRUCTOR.md` | 강사님 설명 스크립트 현재 구현 기준 전면 재작성 |
| `docs/PRESENTATION.md` | **신규** — 발표 스크립트, 경쟁사 비교, Q&A |
| `docs/CODE_FLOW.md` | **신규** — 코드 흐름 이해 가이드 |
| `docs/CALIBRATION_TEST.md` | **신규** — 거리 실측 보정 방법 |
| `docs/mvp_checklist.md` | 미완성 → 전부 완료, 파인튜닝·계단·Failsafe 추가 |
| `docs/PROJECT_GUIDE.md` | 미완성 섹션 제거, 현재 기능 목록으로 교체 |
| `docs/TECH.md` | 파이프라인 YOLO11n→11m, left/center/right→8시~4시 교체 |
| `docs/troubleshooting.md` | CONF 0.45→0.60, 계단 오류 항목 추가 |
| `SETUP.md` | 캡처 2초→1초, 모델 다운로드, APK 무선 설치 추가 |
| `README.md` | YOLO11n→11m, 파이프라인 최신화 |

---

## 7. 변경되지 않은 것

- 기존 Android 앱 핵심 구조 (CameraX, OkHttp, TTS)
- FastAPI 엔드포인트 `/detect`, `/spaces/snapshot` 인터페이스
- SQLite DB 스키마
- 한국어 조사 처리 로직 (이/가, 을/를)
- 기존 커밋 히스토리
- `RESEARCH.md`, `TEAM.md`, `PRD.md` (초기 기획 문서 — 역사 보존)
