# VoiceGuide

> 시각장애인을 위한 AI 음성 주변 인지 서비스  
> KDT AI Human 3팀 | 2026-04-24 ~ 2026-05-13

---

## AI 도구 사용 전 반드시 읽을 것

이 프로젝트는 팀원 각자가 AI 코딩 도구(Claude, Cursor, Copilot 등)를 사용해 개발합니다.  
AI 도구에 질문하기 전에 아래 컨텍스트를 프롬프트에 포함하세요.

```
나는 VoiceGuide 프로젝트의 [역할명]을 담당하고 있습니다.
이 프로젝트는 시각장애인을 위한 실내 장애물 음성 안내 서비스입니다.
기술 스택: Python, YOLO11n, Depth Anything V2, FastAPI, gTTS, Android
내 담당 모듈: [모듈명]
내가 작성해야 할 함수/파일: [파일명 또는 함수명]
```

---

## 프로젝트 한 줄 요약

카메라로 주변을 찍으면 "왼쪽 바로 앞에 의자가 있어요. 오른쪽으로 비켜보세요." 처럼  
**방향과 행동**을 음성으로 안내하는 서비스입니다.

---

## 팀 구성 및 역할

> **중요**: 각자 담당 모듈만 개발합니다.  
> 다른 모듈의 내부 구현은 알 필요 없습니다.  
> B(서버)가 모든 모듈을 호출하는 허브입니다.

| 멤버 | 브랜치 | 담당 모듈 | 산출물 |
|------|--------|---------|-------|
| **A** | `feature/android` | Android 앱 | 카메라 캡처 → 서버 전송 → TTS 재생 앱 |
| **B** | `feature/api` | FastAPI 서버 | `/detect` API + DB + 모듈 통합 |
| **C** | `feature/vision` | YOLO + 방향/위험도 | `detect_and_depth()` 함수 |
| **D** | `feature/voice` | Depth V2 + STT/TTS | `detect_and_depth()` 함수 (C와 협력) |
| **E** | `feature/nlg` | 문장 생성 + 발표 | `build_sentence()` 함수 + PPT |

---

## 팀 내 함수 인터페이스 약속

> 이 인터페이스는 변경 불가합니다.  
> 함수 시그니처(입력/출력 타입)를 바꾸려면 팀 전체 합의가 필요합니다.

```python
# C + D가 공동 작성 → B가 호출
def detect_and_depth(image_bytes: bytes) -> list[dict]:
    """
    Returns:
        [
            {
                "class":      "chair",   # YOLO 클래스명 (영문)
                "class_ko":   "의자",    # 한국어 명칭
                "direction":  "left",    # left / center / right
                "distance":   "가까이",  # 가까이 / 보통 / 멀리
                "risk_score": 0.85       # 0.0 ~ 1.0, 높을수록 위험
            },
            ...
        ]
    """

# E가 작성 → B가 호출
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

## 폴더 구조

```
voiceguide/
├── README.md
├── PRD.md
├── TECH.md
│
├── src/
│   ├── vision/            [feature/vision] 멤버 C 담당
│   │   ├── detect.py      YOLO11n 탐지 + 방향/위험도
│   │   └── __init__.py
│   │
│   ├── depth/             [feature/voice] 멤버 D 담당
│   │   ├── depth.py       Depth Anything V2 거리 추정
│   │   └── __init__.py
│   │
│   ├── voice/             [feature/voice] 멤버 D 담당
│   │   ├── stt.py         STT (SpeechRecognition)
│   │   ├── tts.py         TTS (gTTS)
│   │   └── __init__.py
│   │
│   ├── nlg/               [feature/nlg] 멤버 E 담당
│   │   ├── sentence.py    build_sentence() 함수
│   │   ├── templates.py   문장 템플릿 30~50개
│   │   └── __init__.py
│   │
│   ├── api/               [feature/api] 멤버 B 담당
│   │   ├── main.py        FastAPI 앱
│   │   ├── routes.py      /detect, /spaces API
│   │   ├── db.py          SQLite 공간 스냅샷 DB
│   │   └── __init__.py
│   │
│   └── android/           [feature/android] 멤버 A 담당
│       └── (Android Studio 프로젝트)
│
├── tests/
│   ├── test_detect.py
│   ├── test_sentence.py
│   └── test_api.py
│
├── data/
│   └── test_images/       시나리오별 테스트 이미지
│
├── results/
│   └── eval_log.md        인식률 실험 결과
│
├── app.py                 MVP Gradio 데모
├── requirements.txt
└── .env.example
```

---

## Git 브랜치 전략

```
main
  └── develop          → 통합 브랜치 (B가 관리)
        ├── feature/android   (A)
        ├── feature/api       (B)
        ├── feature/vision    (C)
        ├── feature/voice     (D)
        └── feature/nlg       (E)
```

**규칙**
- `feature/*` → `develop` : PR 필수, B가 review 후 merge
- `develop` → `main` : 주 1회 (매주 월요일), 팀 전체 확인 후
- 직접 `main` push 금지
- 커밋 메시지: `feat(vision): YOLO 방향 판단 로직 추가`

---

## 타임라인

| 날짜 | 마일스톤 |
|------|---------|
| 4/25 | Python MVP: 이미지 탐지 → 음성 출력 완성 |
| 4/30 | 시나리오 3개 Python에서 완성 |
| 5/7  | Android + 서버 end-to-end 완성 |
| 5/9  | 데모 영상 1차 녹화 |
| 5/13 | 최종 발표 |

---

## 빠른 시작

```bash
git clone https://github.com/[팀 리포]/voiceguide.git
cd voiceguide
conda create -n voiceguide python=3.10 -y
conda activate voiceguide
pip install -r requirements.txt
cp .env.example .env

# MVP 실행
python app.py
# → http://localhost:7860
```

---

## 비상 플랜

| 상황 | 대응 |
|------|------|
| Android 연동 실패 | Gradio 데모로 대체, Android 설계도 제출 |
| 서버 배포 실패 | ngrok 로컬 서버로 대체 |
| Depth V2 느릴 경우 | bbox 면적 비율 fallback |
| STT 불안정 | 버튼 입력으로 대체 |
| 공간 기억 불안정 | 데모 제외, PPT 로드맵으로 대체 |
