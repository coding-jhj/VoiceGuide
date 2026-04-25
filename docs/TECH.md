# TECH: VoiceGuide 기술 명세

> **AI 도구 참고용**: 이 문서는 "어떻게 만드는가"를 설명합니다.
> 각 섹션 상단에 담당 멤버와 브랜치가 명시되어 있습니다.
> 자신의 담당 섹션만 구현하면 됩니다.
> 다른 모듈의 내부를 알 필요 없고, 함수 인터페이스만 지키면 됩니다.

---

## 전체 파이프라인

```
[사용자 음성 입력]
    ↓ STT (문수찬)
[텍스트 변환]
    ↓ 키워드 매칭 (문수찬)
[모드 선택: 장애물 / 찾기 / 확인]
    ↓ 카메라 이미지 캡처 (정환주: Android / 신유득: Gradio MVP)
[YOLO11n 탐지] ──────────────────── (김재현)
    ↓ bbox + class
[방향 판단] bbox 중심 x → left/center/right ── (김재현)
    ↓
[거리 판단] bbox 비율(MVP) → Depth V2(서버) ── (문수찬)
    ↓
[위험도 스코어] 방향 + 거리 → 상위 1~2개 ─── (김재현)
    ↓ detect_and_depth() 반환
[문장 생성] build_sentence() ──────────────── (임명광)
    ↓
[TTS 음성 출력] ─────────────────────────── (문수찬)
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
            "direction": "left",
            "distance": "가까이",
            "risk_score": 0.85
        }
    ],
    "changes": ["가방이 1개 더 있어요"]             # 재방문 시에만, 없으면 []
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

#### 역할
- YOLO11n으로 5종 물체 탐지
- 방향 판단 (left / center / right)
- 위험도 스코어 계산
- 문수찬과 협력해서 `detect_and_depth()` 완성

#### 완성해야 할 함수

```python
# src/vision/detect.py

from ultralytics import YOLO

model = YOLO("yolo11n.pt")   # 최초 실행 시 자동 다운로드

TARGET_CLASSES = {
    "person": "사람", "chair": "의자", "dining table": "테이블",
    "backpack": "가방", "suitcase": "가방", "cell phone": "휴대폰",
}

def detect_objects(image_bytes: bytes) -> list[dict]:
    """
    YOLO11n으로 이미지에서 5종 물체 탐지
    Returns: [{class, class_ko, bbox, direction, risk_score}, ...]
    """
    import numpy as np, cv2
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    h, w = img.shape[:2]

    results = model(img)[0]
    detections = []

    for box in results.boxes:
        cls_name = model.names[int(box.cls)]
        if cls_name not in TARGET_CLASSES:
            continue                        # 5종 외 무시

        x1, y1, x2, y2 = map(int, box.xyxy[0])
        cx = (x1 + x2) / 2

        # 방향 판단
        if cx < w * 0.33:       direction = "left"
        elif cx < w * 0.66:     direction = "center"
        else:                   direction = "right"

        # bbox 면적 비율 (MVP 거리 추정 — D가 Depth V2로 교체)
        area_ratio = ((x2-x1) * (y2-y1)) / (w * h)
        if area_ratio > 0.15:   distance = "가까이"
        elif area_ratio > 0.05: distance = "보통"
        else:                   distance = "멀리"

        # 위험도 스코어 (방향=center + 거리=가까이 일수록 높음)
        dir_score  = {"center": 1.0, "left": 0.7, "right": 0.7}[direction]
        dist_score = {"가까이": 1.0, "보통": 0.6, "멀리": 0.3}[distance]
        risk_score = round(dir_score * dist_score, 2)

        detections.append({
            "class":     cls_name,
            "class_ko":  TARGET_CLASSES[cls_name],
            "bbox":      [x1, y1, x2, y2],
            "direction": direction,
            "distance":  distance,           # D가 Depth V2로 교체 예정
            "risk_score": risk_score,
        })

    # 위험도 내림차순 정렬, 상위 2개만 반환
    return sorted(detections, key=lambda x: x["risk_score"], reverse=True)[:2]
```

#### AI 도구에 질문할 때 참고 컨텍스트

```
나는 YOLO 탐지 모듈을 담당합니다.
detect_objects(image_bytes: bytes) -> list[dict] 함수를 완성해야 합니다.
인식 대상: person, chair, dining table, backpack, suitcase, cell phone (5종)
출력 필드: class, class_ko, bbox, direction, distance, risk_score
방향: bbox 중심 x좌표 기준 left/center/right
위험도: 방향과 거리 조합으로 0.0~1.0 스코어
상위 2개만 반환합니다.
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

TEMPLATES = {
    # (direction, distance) → 문장 템플릿
    # direction: left / center / right
    # distance: 가까이 / 보통 / 멀리

    ("left",   "가까이"): "{obj}가 왼쪽 바로 앞에 있어요. 오른쪽으로 비켜보세요.",
    ("center", "가까이"): "{obj}가 정면 가까이에 있어요. 멈추세요.",
    ("right",  "가까이"): "{obj}가 오른쪽 바로 앞에 있어요. 왼쪽으로 비켜보세요.",
    ("left",   "보통"):   "{obj}가 왼쪽에 있어요.",
    ("center", "보통"):   "{obj}가 앞에 있어요. 조심하세요.",
    ("right",  "보통"):   "{obj}가 오른쪽에 있어요.",
    ("left",   "멀리"):   "{obj}가 왼쪽 멀리에 있어요.",
    ("center", "멀리"):   "{obj}가 멀리 앞에 있어요.",
    ("right",  "멀리"):   "{obj}가 오른쪽 멀리에 있어요.",
    # ... 30~50개로 확장 예정
}
```

#### AI 도구에 질문할 때 참고 컨텍스트

```
나는 문장 생성 모듈을 담당합니다.
build_sentence(objects: list[dict], changes: list[str]) -> str 함수를 완성해야 합니다.
objects 입력 예시: [{"class_ko": "의자", "direction": "left", "distance": "가까이", "risk_score": 0.85}]
출력: "왼쪽 바로 앞에 의자가 있어요. 오른쪽으로 비켜보세요."
규칙: 최대 2문장, 위험도 높은 순서, 변화 감지 결과는 마지막에 추가
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
ultralytics          # YOLO11n
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
