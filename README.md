# VoiceGuide

> 시각장애인을 위한 AI 음성 주변 인지 서비스  
> KDT AI Human 3팀 | 2026-04-26 ~ 2026-05-13

---

## AI 도구 사용 전 반드시 읽을 것

이 프로젝트는 팀원 각자가 AI 코딩 도구(Claude, Cursor, Copilot 등)를 사용해 개발합니다.  
AI 도구에 질문하기 전에 아래 컨텍스트를 프롬프트에 포함하세요.

```
나는 VoiceGuide 프로젝트의 [역할명]을 담당하고 있습니다.
이 프로젝트는 시각장애인을 위한 실내 장애물 음성 안내 서비스입니다.
기술 스택: Python, YOLO11m(파인튜닝), Depth Anything V2, FastAPI, gTTS, Android
내 담당 모듈: [모듈명]
내가 작성해야 할 함수/파일: [파일명 또는 함수명]
```

---

## 프로젝트 한 줄 요약

카메라로 주변을 찍으면 "왼쪽 바로 앞에 의자가 있어요. 오른쪽으로 비켜보세요." 처럼  
**방향과 행동**을 음성으로 안내하는 서비스입니다.

---

## 문제 정의

### 배경

시각장애인이 실내 이동 시 주변 환경을 실시간으로 파악하기 어렵습니다.  
기존 AI 서비스(Google Lookout, Seeing AI)는 물체를 **설명**하지만 **행동을 안내하지 않습니다.**

| 서비스 | 출력 예시 | 한계 |
|--------|---------|------|
| Google Lookout | "의자가 있습니다" | 방향·거리 없음 |
| Microsoft Seeing AI | "왼쪽에 의자가 있습니다" | 행동 안내 없음 |
| **VoiceGuide** | "왼쪽 바로 앞에 의자가 있어요. 오른쪽으로 비켜보세요." | ✓ |

### 최종 문제 정의

> **"시각장애인이 실내 이동 중 장애물의 위치와 회피 방향을 즉각적으로 안내받지 못하고 있으므로, 카메라와 음성 명령을 결합한 행동 중심 안내 서비스가 필요하다."**

---

## 핵심 기능 (구현 완료 — 2026-04-26 기준)

### 음성 명령 5가지 모드

| 모드 | 기능 | 트리거 키워드 예시 | 출력 예시 |
|------|------|----------------|---------|
| `장애물` | 실내외 장애물 안내 | "앞에 뭐 있어", "주변 알려줘", "분석해줘" | "오른쪽 앞에 의자가 있어요. 약 1.5m. 왼쪽으로 피해가세요." |
| `찾기` | 특정 물건 찾기 | "의자 찾아줘", "가방 어디있어", "휴대폰 어디야" | "의자는 왼쪽 앞에 있어요. 약 2m." |
| `확인` | 물건 확인 | "이거 뭐야", "이게 뭔지" | "오른쪽에 노트북도 있어요. 약 1m." |
| `저장` ⭐ | 현재 위치 저장 | "여기 저장해줘 편의점", "기억해줘 화장실" | "편의점을 저장했어요." |
| `위치목록` ⭐ | 저장 장소 확인 | "저장된 곳 알려줘", "내 장소 목록" | "저장된 장소는 편의점, 화장실이에요." |

### 자동 분석 기능 (음성 명령 없이 자동)

| 기능 | 동작 | 출력 예시 |
|------|------|---------|
| 안전 경로 제안 ⭐ | 정면 위험 감지 시 가장 안전한 방향 자동 안내 | "왼쪽 방향이 가장 안전해요." |
| 군중 경고 ⭐ | 3명 이상 감지 시 밀집 경고 | "사람이 많아요. 천천히 이동하세요." |
| 위험 물체 경고 ⭐ | 칼·가위 3m 이내 감지 시 즉시 경고 | "위험! 근처에 칼이 있어요! 조심하세요." |
| 차량 긴급 경고 | 차량 8m 이내 접근 시 강화 경고 | "위험! 오른쪽에 자동차가 있어요! 즉시 멈추세요!" |
| 계단·낙차 감지 | Depth 맵 12구역 분석으로 YOLO 사각지대 보완 | "조심! 0.7m 앞에 계단이나 낙차가 있어요." |
| 공간 기억 | 재방문 시 변화된 것만 안내 | "의자가 생겼어요." |
| 프레임 추적 | EMA 평활화로 같은 문장 반복 안내 방지 | — |

> ⭐ 경쟁 서비스(Google Lookout, Seeing AI)에 없는 차별 기능

### MVP 완성 기준

```
카메라로 의자 찍기 → YOLO 탐지 → "의자가 왼쪽에 있습니다" 음성 출력
이 흐름 하나가 작동하면 MVP 완성.
```

---

## 인식 대상 (COCO 80클래스 전체 + 계단 파인튜닝 = 81클래스)

COCO 80클래스를 전부 사용하고 계단을 직접 파인튜닝으로 추가했습니다.  
`YOLO_WORLD=1` 환경변수로 **전동킥보드·볼라드·맨홀** 등 한국 특화 클래스도 추가 탐지 가능합니다.

| 환경 | 카테고리 | 주요 클래스 | 위험도 배수 |
|------|---------|-----------|-----------|
| **야외** | 이동 차량 | 자동차·오토바이·버스·트럭·기차·비행기·보트 | **3.0~4.0×** |
| **야외** | 이동 수단 | 자전거·스케이트보드 | 2.0× |
| **야외** | 교통 시설 | 신호등·소화전·정지 표지판·주차 미터기 | 0.6~1.2× |
| **야외** | 동물 | 개·고양이·말·소·새·양·코끼리·곰·얼룩말·기린 | 1.2~4.0× |
| **실내외** | 날카로운 물체 | 칼·가위·유리잔·야구 방망이 | **1.5~2.5×** |
| **실내외** | 대형 가구·구조물 | 의자·소파·테이블·침대·냉장고·벤치·화분 | 1.0× |
| **실내외** | 바닥 장애물 | 배낭·핸드백·여행가방·우산·공·원반 | 1.0~1.4× |
| **실내외** | 미끄럼 위험 | 바나나·음식류 (바닥에 있으면 감지) | 1.0× |
| **실내외** | 사람 | 사람 | 1.0× |
| **실내외** | 확인용 | 휴대폰·노트북·병·컵·책·시계 | 0.5~1.0× |
| **파인튜닝** | **계단·낙차** | 계단 (mAP50=0.992) | **최우선** |
| **YOLO-World** ⭐ | 한국 특화 | 전동킥보드·볼라드·맨홀·에스컬레이터 | 활성화 시 |

---

## 팀 구성 및 역할

> **중요**: 각자 담당 모듈만 개발합니다.  
> 다른 모듈의 내부 구현은 알 필요 없습니다.  
> 신유득(서버)이 모든 모듈을 호출하는 허브입니다.

| 멤버 | 브랜치 | 담당 모듈 | 산출물 |
|------|--------|---------|-------|
| **정환주** | `feature/android` | Android 앱 | 카메라 캡처 → 서버 전송 → TTS 재생 앱 |
| **신유득** | `feature/api` | FastAPI 서버 | `/detect` API + DB + 모듈 통합 |
| **김재현** | `feature/vision` | YOLO + 방향/위험도 | `detect_and_depth()` 함수 |
| **문수찬** | `feature/voice` | Depth V2 + STT/TTS | `detect_and_depth()` 함수 (김재현과 협력) |
| **임명광** | `feature/nlg` | 문장 생성 + 발표 | `build_sentence()` 함수 + PPT |

---

## 팀 내 함수 인터페이스 약속

> 이 인터페이스는 변경 불가합니다.  
> 함수 시그니처(입력/출력 타입)를 바꾸려면 팀 전체 합의가 필요합니다.

```python
# 김재현 + 문수찬이 공동 작성 → 신유득이 호출
def detect_and_depth(image_bytes: bytes) -> list[dict]:
    """
    Returns:
        [
            {
                "class":      "chair",   # YOLO 클래스명 (영문)
                "class_ko":   "의자",    # 한국어 명칭
                "direction":  "12시",    # 8시~4시 (시계 방향 9구역)
                "distance":   "가까이",  # 가까이 / 보통 / 멀리
                "risk_score": 0.85       # 0.0 ~ 1.0, 높을수록 위험
            },
            ...
        ]
    """

# 임명광이 작성 → 신유득이 호출
def build_sentence(objects: list[dict], changes: list[str]) -> str:
    """
    Args:
        objects: detect_and_depth() 반환값
        changes: ["가방이 1개 더 있어요"] 형식의 변화 감지 결과
    Returns:
        "왼쪽 바로 앞에 의자가 있어요. 오른쪽으로 비켜보세요."
    """
```

---

## 전체 파이프라인

```
[사용자 음성 입력]
    ↓ STT (문수찬)
[텍스트 변환]
    ↓ 키워드 매칭 (문수찬)
[모드 선택: 장애물 / 찾기 / 확인]
    ↓ 카메라 이미지 캡처 (정환주: Android / 신유득: Gradio MVP)
[YOLO11m_indoor 탐지] ──────────────── (김재현) ← 계단 포함 파인튜닝 모델
    ↓ bbox + class + confidence
[Depth Anything V2] ───────────────── (문수찬) ← depth map → 거리(m)
    ↓
[계단/낙차/턱 감지] ─────────────────── (문수찬) ← depth 12구역 분석
    ↓
[방향 판단] bbox 중심 x → 8시~4시 ───── (김재현)
    ↓
[거리 판단] bbox 비율(MVP) → Depth V2(서버) ── (문수찬)
    ↓
[위험도 스코어] 방향 + 거리 → 상위 1~2개 ─── (김재현)
    ↓ detect_and_depth() 반환
[문장 생성] build_sentence() ─────────────── (임명광)
    ↓
[TTS 음성 출력] ──────────────────────────── (문수찬)
```

---

## 모듈별 기술 명세

### MODULE A: Android 앱
**담당**: 정환주 | **브랜치**: `feature/android`  
**파일**: `src/android/` (Android Studio 프로젝트)

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
  { "sentence": "왼쪽 바로 앞에 의자가 있어요.", "objects": [...], "changes": [...] }
```

사용 라이브러리: `OkHttp / Retrofit`, `WifiManager`, `Android TextToSpeech`  
MVP 비상 플랜: Android 연동이 막히면 → Gradio 데모로 대체, UI 와이어프레임 + 설계도 제출

---

### MODULE B: FastAPI 서버 (허브)
**담당**: 신유득 | **브랜치**: `feature/api`  
**파일**: `src/api/main.py`, `src/api/routes.py`, `src/api/db.py`

> 신유득은 팀의 허브입니다. 김재현, 문수찬, 임명광의 함수를 받아서 연결합니다.

```python
# 메인 탐지 API
POST /detect
  Params: image, wifi_ssid, camera_orientation, mode, query_text
  Modes:  장애물 / 찾기 / 확인 / 저장 / 위치목록
  Returns: { sentence, objects, hazards, changes, depth_source }

# 개인 네비게이팅 API ⭐
POST /locations/save          # 현재 WiFi에 장소 이름 저장
GET  /locations               # 저장된 장소 목록 조회
GET  /locations/find/{label}  # 특정 장소 검색 + 현재위치 일치 여부
DELETE /locations/{label}     # 장소 삭제

# 기타
POST /spaces/snapshot         # 공간 스냅샷 수동 저장
POST /stt                     # PC 마이크 음성인식 (Gradio 데모용)
```

SQLite DB 스키마:
```sql
CREATE TABLE snapshots (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    space_id  TEXT NOT NULL,   -- WiFi SSID
    timestamp TEXT NOT NULL,   -- ISO 8601
    objects   TEXT NOT NULL    -- JSON 직렬화
);

CREATE TABLE saved_locations (  -- 개인 네비게이팅 ⭐
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    label     TEXT NOT NULL,    -- "편의점", "화장실" 등
    wifi_ssid TEXT NOT NULL,    -- 저장 당시 WiFi SSID
    timestamp TEXT NOT NULL
);
```

공간 기억 데이터 흐름:
```
1회 방문:  YOLO 탐지 결과 + 공간 ID(WiFi SSID) → 서버 DB 저장
2회 이후:  이전 기록 vs 현재 탐지 비교 → 변화 감지 → "의자가 1개 더 있어요" 안내
```

변화 감지 로직:
```python
def detect_space_change(current_objects, previous_snapshot):
    changes = []
    for obj_class in current_objects:
        curr_count = current_objects[obj_class]["count"]
        prev_count = previous_snapshot.get(obj_class, {}).get("count", 0)
        if curr_count > prev_count:
            changes.append(f"{obj_class}이 {curr_count - prev_count}개 더 있어요")
        elif curr_count < prev_count:
            changes.append(f"{obj_class}이 {prev_count - curr_count}개 줄었어요")
    return changes
```

---

### MODULE C: YOLO 탐지 + 방향/위험도
**담당**: 김재현 | **브랜치**: `feature/vision`  
**파일**: `src/vision/detect.py`

```python
def detect_objects(image_bytes: bytes) -> list[dict]:
    """yolo11m_indoor.pt로 이미지에서 장애물+계단 탐지"""

# 방향 판단
# 8시~4시 시계 방향 9구역으로 판별
# cx_norm = bbox중심x / 이미지폭
# 0.00~0.11 → 8시(왼쪽), ..., 0.44~0.56 → 12시(바로앞), ..., 0.89~1.00 → 4시(오른쪽)

# 위험도 스코어
dir_score  = {"center": 1.0, "left": 0.7, "right": 0.7}[direction]
dist_score = {"가까이": 1.0, "보통": 0.6, "멀리": 0.3}[distance]
risk_score = round(dir_score * dist_score, 2)
# → 상위 2개만 반환 (위험도 내림차순)
```

---

### MODULE D: Depth 거리 추정 + STT/TTS
**담당**: 문수찬 | **브랜치**: `feature/voice`  
**파일**: `src/depth/depth.py`, `src/voice/stt.py`, `src/voice/tts.py`

**거리 측정 방식 비교 및 선택:**

| | 방법 A — bbox 비율 | 방법 B — Depth Anything V2 | 방법 C — Depth Pro |
|---|---|---|---|
| 난이도 | 낮음 | 중간 | 높음 |
| 정확도 | 낮음 | 중간~높음 | 높음 |
| 모바일 지원 | O | O (ONNX 변환) | X |
| 추가 비용 | 없음 | 없음 (오픈소스) | 없음 (오픈소스) |
| **적용 단계** | MVP 빠른 검증 | **본 구현 목표** | 고도화 단계 |

MVP 단계 (bbox 비율):
```python
bbox_area = (x2 - x1) * (y2 - y1)
frame_area = frame_w * frame_h
ratio = bbox_area / frame_area

if ratio > 0.15:   distance = "가까이"
elif ratio > 0.05: distance = "보통"
else:              distance = "멀리"
```

서버 연동 후 (Depth Anything V2):
```python
from depth_anything_v2.dpt import DepthAnythingV2

model = DepthAnythingV2(encoder='vits', features=64, out_channels=[48, 96, 192, 384])
model.load_state_dict(torch.load('depth_anything_v2_vits.pth'))
model.eval()

depth_map = model.infer_image(raw_img)  # HxW numpy array

# YOLO bbox 중심의 깊이값 추출
cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
depth_val = depth_map[cy][cx]

# 주의: 상대적(relative) depth → 임계값은 4/28 실내 실험으로 결정
if depth_val < 0.3:   distance_label = "가까이"
elif depth_val < 0.6: distance_label = "보통"
else:                 distance_label = "멀리"
```

```python
def estimate_distance(image_np, x1, y1, x2, y2) -> str:
    """bbox 중심점 depth 값으로 거리 분류 → "가까이" / "보통" / "멀리" """

def listen_and_classify() -> tuple[str, str]:
    """Returns: (원문 텍스트, 모드명)
    모드: "장애물" / "찾기" / "확인" / "저장" / "위치목록"
    키워드 미매칭 시 → "장애물" (기본값, unknown으로 버리지 않음)
    """

def speak(text: str):
    """한국어 텍스트 → 음성 재생 (gTTS 사용)"""
```

---

### MODULE E: 문장 생성 + 발표
**담당**: 임명광 | **브랜치**: `feature/nlg`  
**파일**: `src/nlg/sentence.py`, `src/nlg/templates.py`

```python
def build_sentence(objects: list[dict], changes: list[str]) -> str:
    """
    규칙:
    1. objects가 비어있으면 → "주변에 장애물이 없어요."
    2. risk_score 가장 높은 것을 먼저 안내
    3. changes가 있으면 마지막에 추가
    4. 문장은 최대 2문장
    """

TEMPLATES = {
    ("left",   "가까이"): "{obj}가 왼쪽 바로 앞에 있어요. 오른쪽으로 비켜보세요.",
    ("center", "가까이"): "{obj}가 정면 가까이에 있어요. 멈추세요.",
    ("right",  "가까이"): "{obj}가 오른쪽 바로 앞에 있어요. 왼쪽으로 비켜보세요.",
    ("left",   "보통"):   "{obj}가 왼쪽에 있어요.",
    ("center", "보통"):   "{obj}가 앞에 있어요. 조심하세요.",
    ("right",  "보통"):   "{obj}가 오른쪽에 있어요.",
    ("left",   "멀리"):   "{obj}가 왼쪽 멀리에 있어요.",
    ("center", "멀리"):   "{obj}가 멀리 앞에 있어요.",
    ("right",  "멀리"):   "{obj}가 오른쪽 멀리에 있어요.",
    # 30~50개로 확장 예정
}
```

---

## 폴더 구조

```
VoiceGuide/
├── README.md              프로젝트 개요 + 팀 컨텍스트 (이 파일)
├── SETUP.md               실기기 데모 실행 가이드
├── app.py                 Gradio 데모 (발표·시연용)
├── requirements.txt
├── .env.example
│
├── src/
│   ├── vision/            [feature/vision] 김재현 담당
│   │   └── detect.py      YOLO11m 탐지 + 방향/위험도
│   ├── depth/             [feature/voice] 문수찬 담당
│   │   ├── depth.py       Depth Anything V2 거리 추정
│   │   └── hazard.py      계단/낙차/턱 감지
│   ├── voice/             [feature/voice] 문수찬 담당
│   │   ├── stt.py         STT (Google Speech, 5모드 키워드)
│   │   └── tts.py         TTS (gTTS + pygame 캐시)
│   ├── nlg/               [feature/nlg] 임명광 담당
│   │   ├── sentence.py    build_sentence/find/navigation 함수
│   │   └── templates.py   시계방향·행동 템플릿
│   └── api/               [feature/api] 신유득 담당
│       ├── main.py        FastAPI 앱 + 워밍업
│       ├── routes.py      /detect /locations /stt API
│       ├── db.py          SQLite (snapshots + saved_locations)
│       └── tracker.py     프레임간 EMA 추적
│
├── android/               [feature/android] 정환주 담당
│   └── app/src/main/java/com/voiceguide/
│       ├── MainActivity.kt     카메라+STT+TTS+네트워크
│       ├── YoloDetector.kt     온디바이스 ONNX 추론
│       ├── SentenceBuilder.kt  온디바이스 문장 생성
│       └── VoiceGuideConstants.kt  클래스명·방향 상수
│
├── tools/                 개발 유틸리티 스크립트
│   ├── benchmark.py       성능 자동 실험 (python tools/benchmark.py)
│   ├── verify.py          라이브러리 설치 검증
│   ├── export_onnx.py     YOLO → ONNX 변환
│   └── patch_gradio_client.py  gradio_client 버그 패치 (1회)
│
├── tests/                 pytest 테스트
│   ├── test_detect.py
│   ├── test_sentence.py
│   ├── test_api.py
│   └── test_imports.py
│
├── train/                 파인튜닝 파이프라인
│   ├── finetune.py        YOLO 파인튜닝 (계단 특화)
│   └── prepare_dataset.py 데이터셋 수집/준비
│
├── docs/                  프로젝트 문서
│   ├── PRD.md / TECH.md / TEAM.md / RESEARCH.md
│   ├── PROJECT_GUIDE.md   강사님용 통합 가이드
│   └── troubleshooting.md 에러 해결법
│
├── data/test_images/      시나리오별 테스트 이미지
└── results/eval_log.md    자동 성능 실험 결과
```

---

## Git 브랜치 전략

```
main
  └── develop          → 통합 브랜치 (신유득 관리)
        ├── feature/android   (정환주)
        ├── feature/api       (신유득)
        ├── feature/vision    (김재현)
        ├── feature/voice     (문수찬)
        └── feature/nlg       (임명광)
```

| 규칙 | 내용 |
|------|------|
| `feature/*` → `develop` | PR 필수, 신유득이 review 후 merge |
| `develop` → `main` | 주 1회 (매주 월요일), 팀 전체 확인 후 |
| 직접 `main` push | **금지** |
| PR 단위 | 함수 하나 또는 기능 하나 완성 단위 |

**커밋 메시지 컨벤션**
```
feat(vision):    YOLO 방향 판단 로직 추가
fix(api):        /detect 핸들러의 오류 수정
docs(nlg):       문장 템플릿 30개 추가
test(vision):    YOLO 인식률 테스트 결과 추가
refactor(depth): depth 임계값 하드코딩 제거
```

**충돌 방지 규칙**
```
김재현과 문수찬은 detect_and_depth()를 공동 작성합니다.
→ 역할 분리: 김재현은 detect_objects() 작성, 문수찬은 estimate_distance() 작성
→ 통합: 문수찬이 detect_and_depth() 최종 함수를 합칩니다.
→ 충돌 시: 신유득에게 알리고 팀 전체 모여서 해결 (혼자 3시간 이상 붙잡지 말 것)
```

---

## 타임라인

| 날짜 | 정환주 (Android) | 신유득 (서버) | 김재현 (YOLO) | 문수찬 (Depth+음성) | 임명광 (문장+발표) |
|------|------|------|------|------|------|
| 4/24 ✅ | Android 환경 세팅 | FastAPI + Gradio MVP | YOLO11m + 방향 판단 | gTTS/pygame TTS | 문장 템플릿 시작 |
| 4/25 ✅ | CameraX + ONNX 온디바이스 + failsafe | Depth V2 통합 + EMA 추적 + 공간 DB | **파인튜닝 계단 mAP50=0.992** | STT + 계단·낙차 감지 | NLG 긴박도 4단계 |
| **4/26 ✅🔥** | **Android 독립 앱 완성** | **개인 네비게이팅 + COCO81 + 안전경로** | **41개 테스트 폴더 + YOLO-World** | **STT 5모드 + 키워드 확장** | **LEARN.md + 발표 자료** |
| 4/27 (월) | APK 실기기 배포 테스트 | 전체 통합 테스트 + 버그 수정 | 테스트 이미지 수집 시작 | STT 소음 환경 테스트 | PPT 초안 작성 |
| 4/28 | 실기기 QA | 서버 안정화 | 인식률 측정 | 임계값 튜닝 | 서비스 비교표 |
| 4/29 | 서버 통신 구현 | 공간 API 작성 | `detect()` 함수 작성 | 임계값 튜닝 | 기존 서비스 비교표 |
| 4/30 | 이미지 전송 | ngrok 설정 | 인식률 테스트 | STT 소음 환경 테스트 | 데모 스크립트 |
| 5/1  | 시나리오 1 완성 | 서버 안정화 | 테스트 이미지 수집 | `detect_and_depth()` 작성 | PPT 구조 확정 |
| 5/2  | 공간 기억 연동 | 공간 연동 테스트 | 오차 케이스 분석 | `build_sentence` 지원 | PPT 본문 작성 |
| 5/6  | 시나리오 2·3 완성 | 통합 테스트 | 최종 인식률 정리 | 전체 음성 흐름 점검 | PPT 완성 |
| 5/7  | UI 개선 | 서버 문서화 | 함수 최종 완성 | 함수 최종 완성 | 발표 대본 작성 |
| 5/8  | **전체 통합 테스트 + 오류 수정** ||||| 
| 5/9  | **데모 영상 1차 녹화** |||||
| 5/12 | **리허설 1~2회** |||||
| 5/13 | **최종 발표** |||||

---

## 플랫폼 전략

| 단계 | 플랫폼 | 목표 | 비고 |
|------|--------|------|------|
| MVP | Python + Gradio | ~4/30 | 로컬 실행, 데모 우선 |
| 2단계 | Android 앱 + FastAPI 서버 | ~5/7 | 실제 사용 환경 |
| 고도화 | iOS / 스마트 안경 | 5/13 이후 | 공모전 로드맵 |

---

## 성공 지표

| 지표 | 목표 | 측정 방법 |
|------|------|---------|
| 탐지 성공률 | 100% | 81클래스(COCO+계단) + Depth V2 실거리 / 미탐지 시 bbox fallback |
| 음성 응답 시간 | 3초 이내 | 이미지 입력 → 음성 출력 측정 |
| STT 인식률 | 100% | 5모드 × 키워드 15개 이상 / 미매칭 시 장애물 모드 fallback |
| 방향 판단 정확도 | 100% | 8시~4시 9구역 결정론적 분류 |
| 개인 네비게이팅 | 100% | WiFi SSID 기반 장소 저장·찾기·목록 |

---

## 차별점

```
기존 서비스 : 환경을 설명한다
VoiceGuide : 환경을 기억하고 행동을 안내한다
```

| 차별점 | 구현 방식 |
|--------|---------|
| 행동 중심 안내 | 방향 + 거리 + 회피 방향 동시 제공 |
| 공간 기억 | WiFi SSID 기반 공간 식별 → 재방문 시 변화만 안내 |
| 접근성 | 스마트폰 하나로 동작, 추가 비용 없음 |

---

## 공모전 연계

```
부트캠프 팀 데모 (5/13)
    → 결과물 재활용
2026 국민행복 서비스 발굴·창제 경진대회 (6/1 마감)
    - 주제: "사회보장 + AI 기술 융합 서비스"
    - 포스터 양식: "시각장애인용 지능형 웨어러블 가이드" 직접 언급
    - 추가 요소: 사업계획서 + Android 앱 계획
```

---

## 빠른 시작

```bash
# 1. 클론
git clone https://github.com/coding-jhj/VoiceGuide.git
cd VoiceGuide

# 2. conda 환경 활성화 (Python 3.10)
conda activate ai_env

# 3. 의존성 설치
pip install -r requirements.txt

# 4. gradio_client 버그 패치 (1회만)
python patch_gradio_client.py

# 5. Depth Anything V2 모델 가중치 다운로드 (1회만, 약 94MB)
python -c "
import urllib.request
urllib.request.urlretrieve(
    'https://huggingface.co/depth-anything/Depth-Anything-V2-Small/resolve/main/depth_anything_v2_vits.pth',
    'depth_anything_v2_vits.pth'
)
print('완료')
"

# 6. Gradio 데모 실행 (발표·데모용)
python app.py
# → http://localhost:7860 브라우저 자동 열림

# 폰으로 보여줄 때 (공개 URL 생성)
python app.py --share

# 7. FastAPI 서버 실행 (Android 앱 연동용)
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 로컬 IP 확인 (Android 앱에 입력할 주소)
ipconfig   # Windows
# → http://192.168.x.x:8000
```

> **참고**: `depth_anything_v2_vits.pth` 는 `.gitignore` 대상(용량 큼)이므로 팀원 각자 PC에서 5번을 실행해야 합니다.

---

## 현재 구현 완료 목록 (2026-04-26 기준)

### AI·비전

| 기능 | 상태 | 상세 |
|------|------|------|
| YOLO11m **COCO80 전체 + 계단** | ✅ | 81클래스, conf 클래스별 차등 적용 |
| **계단 파인튜닝** | ✅ | 404장 학습, mAP50=**0.992** (정밀도 91.7% / 재현율 100%) |
| 9방향 시계 방향 판단 | ✅ | 8시~4시, 위험도 가중치 (정면 1.0 → 양끝 0.3) |
| 차량 위험도 강화 | ✅ | 자동차·버스·트럭 3.5×, 기차 4.0× |
| 동물 위험도 | ✅ | 개 1.8×, 말 2.5×, 코끼리·곰 4.0× |
| 날카로운 물체 경고 | ✅ | 칼 2.5×, 가위 2.0×, 유리잔 1.5× |
| Depth Anything V2 거리 추정 | ✅ | GPU 자동 감지, bbox 면적 기반 fallback |
| 깊이 맵 계단·낙차·턱 감지 | ✅ | 바닥 12구역 분석, YOLO 사각지대 보완 |
| **안전 경로 제안** ⭐ | ✅ | 정면 위험 시 가장 안전한 방향 자동 안내 |
| **군중 밀집 경고** ⭐ | ✅ | 3명+ "사람 많아요", 5명+ "매우 혼잡" |
| **위험 물체 경고** ⭐ | ✅ | 칼·가위 3m 이내 시 즉시 경고 |
| **YOLO-World 확장** ⭐ | ✅ | `YOLO_WORLD=1`로 전동킥보드·볼라드 등 추가 |
| 위험도 스코어링 | ✅ | 방향 × 거리 × 바닥 여부 × 클래스 배수 |
| 객체 추적 (EMA) | ✅ | 프레임 간 jitter 제거, 접근·소멸 감지 |

### 서버·API

| 기능 | 상태 | 상세 |
|------|------|------|
| FastAPI `/detect` | ✅ | 5모드 처리 + scene_analysis 응답 |
| **개인 네비게이팅 API** ⭐ | ✅ | POST/GET/DELETE `/locations/*` |
| 공간 기억 DB | ✅ | SQLite, WiFi SSID 기반 재방문 변화 감지 |
| 서버 워밍업 | ✅ | 첫 요청 지연 없음 (lifespan 방식) |
| 전역 예외 핸들러 | ✅ | 오류 시에도 음성 안내 반환 |
| Gradio 데모 | ✅ | 바운딩 박스 시각화, 추론 시간 표시 |

### Android 앱

| 기능 | 상태 | 상세 |
|------|------|------|
| **완전 독립 동작** ⭐ | ✅ | 서버 URL 없이 즉시 실행 |
| **ONNX 온디바이스 추론** | ✅ | yolo11m.onnx, 서버 연결 실패 시 자동 전환 |
| CameraX 1초 자동 캡처 | ✅ | 즉시 첫 캡처, 같은 문장 반복 방지 |
| Android TTS | ✅ | 한국어, 속도 1.1배 |
| STT **5모드 음성 명령** | ✅ | 장애물/찾기/확인/저장/위치목록, 키워드 15개+ |
| STT 미인식 fallback | ✅ | 어떤 말을 해도 기본 장애물 모드로 동작 |
| **개인 네비게이팅** ⭐ | ✅ | SharedPreferences 장소 저장·찾기·목록 |
| 카메라 방향 자동 감지 | ✅ | 가속도 센서 → front/left/right/back |
| WiFi SSID 수집 | ✅ | 공간 기억 연동 |
| Failsafe + Watchdog | ✅ | 3회 실패 경고, 6초 무응답 경고 |

### 문서·도구

| 파일 | 내용 |
|------|------|
| `docs/LEARN.md` | 팀원 공부용 코드 주석 가이드 |
| `docs/TEAM_BRIEFING.md` | 발표 대본 + Q&A 대비 + 리스크 대응 |
| `docs/PRESENTATION.md` | 경쟁사 비교 + APK 설치 방법 |
| `tools/benchmark.py` | 자동 성능 측정 (방향·문장·응답시간) |
| `data/test_images/` | 41개 카테고리 폴더 (실내외 전체) |

---

## 비상 플랜

| 상황 | 대응 |
|------|------|
| Android 연동 실패 | Gradio 데모로 대체, Android 설계도 제출 |
| 서버 배포 실패 | ngrok 로컬 서버로 대체 |
| Depth V2 모델 파일 없을 경우 | bbox 면적 비율 자동 fallback (코드 수정 불필요) |
| STT 불안정 | 버튼 입력으로 대체 |
| 공간 기억 불안정 | 데모 제외, PPT 로드맵으로 대체 |

---

## 참고 자료

### AI 모델

| 자료 | 링크 |
|------|------|
| Depth Anything V2 (NeurIPS 2024) | [depth-anything-v2.github.io](https://depth-anything-v2.github.io) |
| Depth Anything V2 논문 | [arxiv.org/abs/2406.09414](https://arxiv.org/abs/2406.09414) |
| Depth Anything V2 모델 가중치 | [huggingface.co/depth-anything](https://huggingface.co/depth-anything/Depth-Anything-V2-Small) |
| YOLO11 공식 문서 | [docs.ultralytics.com/models/yolo11](https://docs.ultralytics.com/models/yolo11/) |
| YOLO11 GitHub | [github.com/ultralytics/ultralytics](https://github.com/ultralytics/ultralytics) |
| Apple Depth Pro (ICLR 2025) | [machinelearning.apple.com/research/depth-pro](https://machinelearning.apple.com/research/depth-pro) |

### Android 구현

| 자료 | 링크 |
|------|------|
| Depth Anything Android (ONNX) | [github.com/shubham0204/Depth-Anything-Android](https://github.com/shubham0204/Depth-Anything-Android) |
| ONNX Runtime Android 가이드 | [onnxruntime.ai/docs/tutorials/mobile](https://onnxruntime.ai/docs/tutorials/mobile/) |
| CameraX 공식 문서 | [developer.android.com/training/camerax](https://developer.android.com/training/camerax) |

### 사용자 조사 · 논문

| 자료 | 링크 |
|------|------|
| UC Davis 사용자 조사 (2024) — 행동 안내 부재가 핵심 불편 | [arxiv.org/abs/2504.06379](https://arxiv.org/abs/2504.06379) |
| Nature Scientific Reports (2025) — 보조기기 실사용 포기 원인 | [doi.org/10.1038/s41598-025-91755-w](https://doi.org/10.1038/s41598-025-91755-w) |
| VISA 시스템 논문 (J. Imaging 2025) — AR+YOLO+Depth 실내 내비 | [doi.org/10.3390/jimaging11010009](https://doi.org/10.3390/jimaging11010009) |
| WHO 시각장애 통계 — 전 세계 2억 8500만 명 | [who.int/news-room/fact-sheets/detail/blindness-and-visual-impairment](https://www.who.int/news-room/fact-sheets/detail/blindness-and-visual-impairment) |

### 경쟁 서비스

| 서비스 | 링크 |
|--------|------|
| Google Lookout | [lookout.app](https://lookout.app) |
| Microsoft Seeing AI | [microsoft.com/en-us/ai/seeing-ai](https://www.microsoft.com/en-us/ai/seeing-ai) |
| Be My Eyes | [bemyeyes.com](https://www.bemyeyes.com) |
