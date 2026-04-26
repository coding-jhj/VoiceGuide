# TECH: VoiceGuide 기술 명세

> **AI 도구 참고용**: 이 문서는 "어떻게 만드는가"를 설명합니다.
> 각 섹션 상단에 담당 멤버와 브랜치가 명시되어 있습니다.
> 자신의 담당 섹션만 구현하면 됩니다.
> 다른 모듈의 내부를 알 필요 없고, 함수 인터페이스만 지키면 됩니다.

---

## 전체 파이프라인 (최종 구현 기준 2026-04-26)

```
[Android 카메라] ─────────────────────────── (정환주)
    ↓ 1초마다 JPEG + WiFi SSID + 카메라방향(가속도센서 자동감지)
[STT 음성 명령] ──────────────────────────── (정환주)
    ↓ "주변 알려줘/찾아줘/이거 뭐야" → 장애물/찾기/확인 모드
[FastAPI /detect 서버]
    ↓
[yolo11m_indoor.pt 탐지] ─────────────────── (김재현)
    ↓ bbox + class (COCO 80 + 계단 = 81클래스, conf=0.60)
[방향 판단] bbox 중심 x → 8시~4시 9구역 ──── (김재현)
    ↓
[Depth Anything V2 GPU] ─────────────────── (문수찬)
    ↓ depth map(H×W) → bbox별 거리(m) 정제 (안전 우선 보수 추정)
[계단/낙차/턱 감지] ─────────────────────── (문수찬)
    ↓ 바닥 12구역 깊이 변화 분석 → hazards[]
[객체 추적기 EMA] ────────────────────────── (신유득)
    ↓ 거리 평활화(α=0.55) + 접근/소멸 감지
[공간 기억 DB] ───────────────────────────── (신유득)
    ↓ WiFi SSID → 이전 방문 비교 → 변화 감지
[위험도 스코어] 방향×거리×바닥여부 → 상위 3개 (김재현)
    ↓ (objects, hazards) 튜플 반환
[문장 생성] build_sentence() / build_hazard_sentence() ── (임명광)
    ↓ 긴박도 4단계, 계단 최우선 안내
[Android TTS + Failsafe] ─────────────────── (정환주)
    ↓ 음성 재생 / 3회 실패시 "연결 끊겼어요" / 6초 무응답시 경고
```

---

## 모듈별 기술 명세

---

### MODULE A: Android 앱
**담당**: 정환주 | **브랜치**: `feature/android`
**파일**: `src/android/` (Android Studio 프로젝트)

#### 역할
- 카메라 이미지 캡처
- 서버에 이미지 + WiFi SSID POST 전송
- 서버 JSON 응답 수신
- Android TTS로 음성 재생

#### 구현 사양

```
입력: 카메라 이미지 (JPEG, 최대 1MB)
출력: HTTP POST → FastAPI 서버

요청 형식:
  POST http://{서버주소}/detect
  Content-Type: multipart/form-data
  Body:
    - image: (JPEG 파일)
    - wifi_ssid: (문자열, WifiManager로 읽기)

응답 형식:
  {
    "sentence": "왼쪽 바로 앞에 의자가 있어요.",
    "objects": [...],
    "changes": [...]
  }
```

#### 사용 라이브러리

```
OkHttp 또는 Retrofit   // HTTP 통신
WifiManager            // WiFi SSID 읽기
Android TextToSpeech   // TTS 재생 (gTTS 대신 온디바이스)
```

#### AI 도구에 질문할 때 참고 컨텍스트

```
나는 Android 앱 개발을 담당합니다.
역할: 카메라 캡처 → HTTP POST(이미지 + wifi_ssid) → 응답 JSON 수신 → TTS 재생
서버 주소는 ngrok URL을 사용합니다 (예: https://xxxx.ngrok.io)
Android minSdk: 26 (Android 8.0)
언어: Kotlin 또는 Java (팀이 결정)
```

#### MVP 비상 플랜
Android 연동이 막히면 → Gradio 데모로 대체, Android는 UI 와이어프레임 + 설계도 제출

---

### MODULE B: FastAPI 서버 (허브)
**담당**: 신유득 | **브랜치**: `feature/api`
**파일**: `src/api/main.py`, `src/api/routes.py`, `src/api/db.py`

> B는 팀의 허브입니다. C, D, E의 함수를 받아서 연결합니다.
> 다른 모듈의 내부 구현을 몰라도 됩니다. 함수 인터페이스만 호출하면 됩니다.

#### 역할
- POST /detect API 구현
- 김재현+문수찬의 `detect_and_depth()` 호출
- E의 `build_sentence()` 호출
- SQLite DB로 공간 스냅샷 저장 + 변화 감지

#### API 명세

```python
# POST /detect
# 요청: multipart/form-data (image + wifi_ssid)
# 응답:
{
    "sentence": "왼쪽 바로 앞에 의자가 있어요.",   # build_sentence() 결과
    "objects": [                                  # detect_and_depth() 결과
        {
            "class": "chair",
            "class_ko": "의자",
            "direction": "12시",       # 8시~4시 시계 방향 9구역
            "distance": "가까이",
            "distance_m": 1.2,          # 실제 거리(m), Depth V2 기준
            "risk_score": 0.85,
            "is_ground_level": false,
            "depth_source": "v2"        # "v2" or "bbox"
        }
    ],
    "hazards": [{"type":"drop","distance_m":0.7,"message":"조심!...","risk":0.8}],
    "changes": ["의자가 생겼어요"]              # 재방문 시 변화, 없으면 []
}

# POST /spaces/snapshot
# 요청: { space_id, objects }
# 응답: { "saved": true }
```

#### 핵심 로직

```python
@app.post("/detect")
async def detect(image: UploadFile, wifi_ssid: str = Form("")):
    image_bytes = await image.read()

    # 1. 탐지 + 거리 (김재현+문수찬 함수 호출)
    objects = detect_and_depth(image_bytes)

    # 2. 공간 기억: 이전 기록 조회
    previous = db.get_snapshot(wifi_ssid)
    changes = detect_space_change(objects, previous) if previous else []

    # 3. 공간 기록 저장
    db.save_snapshot(wifi_ssid, objects)

    # 4. 문장 생성 (임명광 함수 호출)
    sentence = build_sentence(objects, changes)

    return {"sentence": sentence, "objects": objects, "changes": changes}
```

#### SQLite DB 스키마

```sql
CREATE TABLE snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    space_id    TEXT NOT NULL,          -- WiFi SSID
    timestamp   TEXT NOT NULL,          -- ISO 8601
    objects     TEXT NOT NULL           -- JSON 직렬화
);
```

#### AI 도구에 질문할 때 참고 컨텍스트

```
나는 FastAPI 서버를 담당합니다.
역할: 이미지 수신 → detect_and_depth() 호출 → build_sentence() 호출 → 응답 반환
detect_and_depth()와 build_sentence()는 팀원이 완성한 함수를 import해서 씁니다.
DB는 SQLite, 배포는 ngrok로 외부 접근합니다.
Python 3.10, FastAPI 0.104
```

---

### MODULE C: YOLO 탐지 + 방향/위험도
**담당**: 김재현 | **브랜치**: `feature/vision`
**파일**: `src/vision/detect.py`

#### 역할 (최종 구현)
- yolo11m_indoor.pt로 81클래스 탐지 (COCO 80 + 계단)
- 방향 판단: 8시~4시 9구역 시계 방향
- 위험도 스코어: 방향 × 거리 × 바닥여부(계단 포함)
- 상위 3개 반환, 거리는 Depth V2로 정제됨

#### 완성해야 할 함수

```python
# src/vision/detect.py

from ultralytics import YOLO

import os
_f = "yolo11m_indoor.pt" if os.path.exists("yolo11m_indoor.pt") else "yolo11m.pt"
model = YOLO(_f)   # 파인튜닝 모델 우선, 없으면 기본 모델 자동 fallback

TARGET_CLASSES = {
    "person": "사람", "chair": "의자", "dining table": "테이블",
    "backpack": "가방", "suitcase": "가방", "cell phone": "휴대폰",
}

def detect_objects(image_bytes: bytes) -> list[dict]:
    """
    yolo11m_indoor.pt로 81클래스(계단 포함) 탐지
    Returns: [{class, class_ko, bbox, direction, distance, distance_m,
               risk_score, is_ground_level, depth_source}, ...]
    """
    # 실제 구현은 src/vision/detect.py 참조
    # 방향: 8시~4시 9구역 시계 방향
    # 거리: Depth V2 기준 미터값 (fallback: bbox 면적 비율)
    # 위험도: RISK_DIR[direction] × RISK_DIST[distance] × ground_multiplier
    # 상위 3개 반환
    pass
```

#### 현재 구현 핵심 (실제 코드 기준)

```
방향 9구역:  cx_norm → 0.11/0.22/0.33/0.44/0.56/0.67/0.78/0.89
            → 8시/9시/10시/11시/12시/1시/2시/3시/4시

위험도 가중치:
  방향: 12시=1.0, 11시/1시=0.9, 10시/2시=0.7, 9시/3시=0.5, 8시/4시=0.3
  거리: 매우가까이=1.0, 가까이=0.8, 보통=0.5, 멀리=0.2, 매우멀리=0.1
  바닥장애물(계단 포함): × 1.4 보정
```

---

### MODULE D: Depth 거리 추정 + STT/TTS
**담당**: 문수찬 | **브랜치**: `feature/voice`
**파일**: `src/depth/depth.py`, `src/voice/stt.py`, `src/voice/tts.py`

#### 역할 1: Depth Anything V2로 거리 추정 (김재현과 협력)

```python
# src/depth/depth.py

# MVP: C의 bbox 면적 비율 사용 (아무것도 안 해도 됨)
# 서버 연동 후: 아래 함수로 C의 distance 값을 교체

import torch
from depth_anything_v2.dpt import DepthAnythingV2

# 서버 시작 시 1회만 로드
_depth_model = None

def get_depth_model():
    global _depth_model
    if _depth_model is None:
        _depth_model = DepthAnythingV2(
            encoder='vits', features=64,
            out_channels=[48, 96, 192, 384]
        )
        _depth_model.load_state_dict(
            torch.load('depth_anything_v2_vits.pth', map_location='cpu')
        )
        _depth_model.eval()
    return _depth_model

def estimate_distance(image_np, x1, y1, x2, y2) -> str:
    """
    bbox 중심점의 depth 값으로 거리 분류
    Returns: "가까이" / "보통" / "멀리"

    주의: Depth Anything V2는 상대적(relative) depth 출력
    → 임계값은 실내 환경 실험으로 결정 (4/28 튜닝 예정)
    → 실험: 의자를 0.5m / 1m / 2m 거리에 놓고 depth_val 측정
    """
    model = get_depth_model()
    depth_map = model.infer_image(image_np)
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    depth_val = float(depth_map[cy][cx])

    # 아래 임계값은 4/28 실험 후 업데이트
    NEAR_THRESHOLD = 0.3   # TODO: 실험으로 결정
    MID_THRESHOLD  = 0.6   # TODO: 실험으로 결정

    if depth_val < NEAR_THRESHOLD:   return "가까이"
    elif depth_val < MID_THRESHOLD:  return "보통"
    else:                            return "멀리"
```

#### 역할 2: C와 함께 완성할 통합 함수

```python
# detect_and_depth() — 신유득이 호출하는 최종 함수
# 김재현의 detect_objects() + 문수찬의 estimate_distance() 통합

def detect_and_depth(image_bytes: bytes) -> list[dict]:
    import numpy as np, cv2
    nparr = np.frombuffer(image_bytes, np.uint8)
    image_np = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    from src.vision.detect import detect_objects
    objects = detect_objects(image_bytes)

    # MVP: distance는 C가 계산한 bbox 비율 그대로 사용
    # 서버 연동 후: 아래 주석 해제
    # for obj in objects:
    #     x1,y1,x2,y2 = obj["bbox"]
    #     obj["distance"] = estimate_distance(image_np, x1, y1, x2, y2)

    return objects
```

#### 역할 3: STT

```python
# src/voice/stt.py

import speech_recognition as sr

KEYWORDS = {
    "장애물": ["앞에 뭐 있어", "주변 알려줘", "뭐 있어"],
    "찾기":   ["찾아줘", "어딨어", "어디 있어"],
    "확인":   ["이거 뭐야", "이게 뭐야", "뭐야"],
}

def listen_and_classify() -> tuple[str, str]:
    """
    Returns: (원문 텍스트, 모드명)
    모드: "장애물" / "찾기" / "확인" / "unknown"
    """
    r = sr.Recognizer()
    with sr.Microphone() as source:
        r.adjust_for_ambient_noise(source, duration=0.5)
        audio = r.listen(source, timeout=5)

    try:
        text = r.recognize_google(audio, language="ko-KR")
    except sr.UnknownValueError:
        return "", "unknown"

    for mode, keywords in KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return text, mode

    return text, "unknown"
```

#### 역할 4: TTS

```python
# src/voice/tts.py

from gtts import gTTS
import os, tempfile

def speak(text: str):
    """한국어 텍스트 → 음성 재생"""
    tts = gTTS(text, lang="ko")
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tts.save(f.name)
        os.system(f"afplay {f.name}")    # macOS
        # os.system(f"mpg321 {f.name}") # Linux
```

#### AI 도구에 질문할 때 참고 컨텍스트

```
나는 Depth 추정과 STT/TTS를 담당합니다.
Depth: estimate_distance(image_np, x1, y1, x2, y2) -> "가까이"/"보통"/"멀리"
STT: Google Speech API, 한국어, 키워드 매칭으로 모드 분류
TTS: gTTS 한국어
Depth Anything V2는 상대적 depth를 출력합니다. (절대 거리 아님)
임계값은 4/28 실내 실험으로 결정합니다.
```

---

### MODULE E: 문장 생성 + 발표
**담당**: 임명광 | **브랜치**: `feature/nlg`
**파일**: `src/nlg/sentence.py`, `src/nlg/templates.py`

#### 역할
- `build_sentence()` 함수 완성
- 방향 + 거리 조합 문장 템플릿 30~50개 작성
- 변화 감지 결과 자연어 변환
- 발표자료(PPT) + 데모 시나리오 대본

#### 완성해야 할 함수

```python
# src/nlg/sentence.py

from src.nlg.templates import TEMPLATES, CHANGE_TEMPLATES

def build_sentence(objects: list[dict], changes: list[str]) -> str:
    """
    Args:
        objects: detect_and_depth() 반환값 (위험도 높은 순 최대 2개)
        changes: ["가방이 1개 더 있어요"] 형식 (없으면 빈 리스트)
    Returns:
        "왼쪽 바로 앞에 의자가 있어요. 오른쪽으로 비켜보세요."

    규칙:
    1. objects가 비어있으면 → "주변에 장애물이 없어요."
    2. risk_score 가장 높은 것을 먼저 안내
    3. changes가 있으면 마지막에 추가
    4. 문장은 최대 2문장 (너무 길면 사용자가 따라가기 어려움)
    """
    if not objects:
        base = "주변에 장애물이 없어요."
    else:
        parts = []
        for obj in objects[:2]:
            key = (obj["direction"], obj["distance"])
            tmpl = TEMPLATES.get(key, "{obj}가 {direction}에 있어요.")
            parts.append(tmpl.format(obj=obj["class_ko"]))
        base = " ".join(parts)

    change_text = " ".join(changes[:1]) if changes else ""
    return f"{base} {change_text}".strip()
```

```python
# src/nlg/templates.py

# 실제 구현은 CLOCK_TO_DIRECTION, CLOCK_ACTION 사전 기반 (src/nlg/templates.py)
# direction: 8시~4시 시계방향 → "왼쪽", "왼쪽 앞", "바로 앞", "오른쪽 앞", "오른쪽"
# 긴박도 4단계:
#   dist_m < 0.5  → "위험! 바로 앞 의자!"
#   dist_m < 1.0  → "멈추세요! 바로 앞에 의자가 있어요. 약 70cm."
#   dist_m < 2.5  → "바로 앞에 의자가 있어요. 약 1.2m. 멈추세요."
#   dist_m >= 2.5 → "바로 앞에 의자가 있어요. 약 3.0m."
```

#### 현재 구현 핵심

```
build_sentence(objects, changes, camera_orientation="front") → str
build_hazard_sentence(hazard, objects, changes, camera_orientation) → str
  └─ 계단/낙차 위험 시 최우선 안내, risk >= 0.7이면 장애물 정보 생략
```

---

## Git 정책

### 브랜치 전략

```
main          ← 발표용 최종 코드 (직접 push 금지)
  └── develop ← 통합 브랜치 (신유득이 관리, 주 1회 main merge)
        ├── feature/android  (정환주)
        ├── feature/api      (신유득)
        ├── feature/vision   (김재현)
        ├── feature/voice    (문수찬)
        └── feature/nlg      (임명광)
```

### PR 규칙

| 규칙 | 내용 |
|------|------|
| `feature/*` → `develop` | PR 필수, 신유득이 review 후 merge |
| `develop` → `main` | 주 1회 (매주 수요일), 팀 전체 확인 후 |
| 직접 `main` push | **금지** |
| PR 단위 | 함수 하나 또는 기능 하나 완성 단위 |

### 커밋 메시지 컨벤션

```
feat(vision):   YOLO 방향 판단 로직 추가
fix(api):       /detect 타임아웃 오류 수정
docs(nlg):      문장 템플릿 30개 추가
test(vision):   YOLO 인식률 테스트 결과 추가
refactor(depth): depth 임계값 튜닝 반영
```

### 충돌 방지 규칙

```
김재현과 문수찬은 detect_and_depth() 를 공동 완성합니다.
→ 작업 분리: 김재현은 detect_objects() 완성, 문수찬은 estimate_distance() 완성
→ 통합: 문수찬이 detect_and_depth() 에 두 함수를 합칩니다.
→ 충돌 시: 신유득에게 알리고 팀 전체 모여서 해결 (혼자 3시간 이상 붙잡지 말 것)
```

### .gitignore 필수 항목

```
.env               # API 키
*.pth              # 모델 가중치 (용량 큼)
__pycache__/
*.pyc
.DS_Store
data/test_images/  # 테스트 이미지 (용량 큼, 별도 공유)
```

---

## 설치 및 실행

```bash
# 환경 세팅
conda create -n voiceguide python=3.10 -y
conda activate voiceguide
pip install -r requirements.txt
cp .env.example .env

# MVP 실행 (Gradio)
python app.py
# → http://localhost:7860

# 서버 실행 (2단계)
uvicorn src.api.main:app --reload --port 8000

# ngrok 외부 접근
ngrok http 8000
```

## requirements.txt

```
ultralytics          # YOLO11m (파인튜닝: yolo11m_indoor.pt)
SpeechRecognition    # STT
gtts                 # TTS
gradio               # MVP UI
fastapi              # 서버
uvicorn              # ASGI 서버
python-multipart     # 파일 업로드
torch                # Depth Anything V2
opencv-python        # 이미지 처리
numpy
```
