# 보이스가이드 (VoiceGuide) 프로젝트 계획서

## 1. 프로젝트 개요

### 한 줄 설명
> 시각장애인 또는 저시력 사용자가 음성 명령과 스마트폰 카메라를 통해 주변 장애물, 찾는 물건, 손에 든 물건을 확인할 수 있도록 돕는 TTS-STT 기반 주변 인지 보조 서비스

### 목표 대회
- **부트캠프 프로젝트**: 10일 안에 작동하는 데모 완성 → 1등 목표
- **2026 국민행복 서비스 발굴·창업 경진대회**: 6월 1일까지 제출 (공모주제: 사회보장정보 + AI 기술 융합 서비스)
  - 포스터 예시에 "시각장애인용 지능형 웨어러블 가이드"가 직접 언급됨 → 보이스가이드와 완벽히 일치

---

## 2. 핵심 기능 (데모에서 보여줄 것)

딱 3개만 제대로 보여준다.

| 기능 | 사용자 입력 | 시스템 출력 |
|---|---|---|
| 장애물 안내 | "앞에 뭐 있어?" | "정면 가까이에 의자가 있습니다." |
| 물건 찾기 | "컵 찾아줘" | "컵은 왼쪽 앞에 있습니다." |
| 물건 확인 | "이거 뭐야?" | "카메라 중앙의 물건은 텀블러입니다." |

---

## 3. 전체 파이프라인

```
마이크 음성 입력
    ↓ STT (SpeechRecognition)
텍스트 명령 ("컵 찾아줘")
    ↓ 키워드 매칭 (if/elif)
모드 선택 (장애물 / 찾기 / 확인)
    ↓ 객체 탐지 (YOLO11n)
물체 이름 + bounding box 위치/크기
    ↓ 방향 판단 + 거리 판단
"왼쪽 / 정면 / 오른쪽" + "가까이 / 멀리"
    ↓ 안내 문장 생성
"컵은 왼쪽 가까이에 있습니다"
    ↓ TTS (gTTS)
음성 출력
```

---

## 4. 기술 스택 (10일 확정판)

### 사용할 기술

| 역할 | 기술 | 이유 |
|---|---|---|
| 객체 탐지 | YOLO11n (ultralytics) | 학습 불필요, 설치 한 줄, COCO 80종 인식 |
| 방향 판단 | bounding box x 중심값 계산 | 라이브러리 불필요, 코드 5줄 |
| 거리 판단 | bounding box 면적 비율 계산 | Depth 모델 없이 대체 가능 |
| 의도 파악 | 키워드 매칭 if/elif | NLP 모델 불필요 |
| TTS | gTTS + pygame | 한국어 발음 자연스러움 |
| STT | SpeechRecognition | 한국어 지원, 어려우면 버튼으로 대체 |
| UI | Gradio | 파이썬만으로 웹 화면 자동 생성, 발표에 적합 |

### 전체 설치 명령어

```bash
pip install ultralytics gTTS pygame SpeechRecognition gradio opencv-python
```

### 절대 건드리지 말 것 (시간 낭비)

| 욕심내고 싶은 것 | 대체 방법 |
|---|---|
| Depth Anything V2 | bounding box 크기로 대체 |
| Grounding DINO | 키워드 매칭 if/elif로 대체 |
| YOLO fine-tuning | pretrained COCO 모델 그대로 사용 |
| Flutter/Android 앱 | Python + Gradio 웹 데모로 대체 |
| 실사용자 데이터 수집 | 팀 내부 테스트로 대체 |

> 발표에서는 "현재 프로토타입은 Python 기반이며, 실제 서비스는 Android 앱으로 전환 예정입니다"라고 설명하면 충분하다.

---

## 5. 핵심 코드 구조

### 방향 판단

```python
def get_direction(center_x, frame_width):
    if center_x < frame_width / 3:
        return "왼쪽"
    elif center_x < frame_width * 2 / 3:
        return "정면"
    else:
        return "오른쪽"
```

### 거리 판단

```python
def get_distance(box_area, frame_area):
    ratio = box_area / frame_area
    if ratio > 0.3:
        return "가까이"
    else:
        return "멀리"
```

### 의도 파악

```python
def parse_intent(text):
    if "뭐 있어" in text or "장애물" in text:
        return "obstacle", None
    elif "찾아줘" in text:
        target = text.replace("찾아줘", "").strip()
        return "find", target
    elif "뭐야" in text or "이거" in text:
        return "identify", None
    elif "짧게" in text:
        return "short_mode", None
    elif "자세히" in text:
        return "detail_mode", None
```

### 한국어 → YOLO 클래스명 매핑 (필수!)

```python
target_map = {
    "컵": "cup",
    "의자": "chair",
    "사람": "person",
    "가방": "backpack",
    "병": "bottle",
    "핸드폰": "cell phone",
    "노트북": "laptop",
    "책": "book",
    # 필요한 물체 추가
}
```

---

## 6. 역할 분담 (6명 확정)

| 역할 | 인원 | 담당 업무 |
|---|---|---|
| **구현 A** | 1명 | YOLO11n 설치 + 객체 탐지 + 방향/거리 판단 |
| **구현 B** | 1명 | TTS + STT + 의도 파악 (키워드 매칭) |
| **구현 C** | 1명 | 시나리오 3개 통합 + Gradio UI |
| **기획/자료팀** | 2명 | 문제 정의, 자료조사, 비교표, PPT 제작, 발표 대본, 발표 |
| **테스트/데모팀** | 1명 | 테스트 시나리오 설계, 결과 기록, 데모 영상 촬영 |

### 역할별 상세 업무

**구현 A — YOLO11n + 방향/거리 판단**
- 1~2일차: YOLO11n 설치 및 웹캠 테스트
- 3일차: 방향 판단 + 거리 판단 로직 완성
- 4일차~: 구현 B/C와 통합 작업 지원

**구현 B — TTS + STT + 의도 파악**
- 1~2일차: gTTS + pygame 연결, 음성 출력 확인
- 3일차: 키워드 매칭 의도 파악 함수 완성
- 4~5일차: STT 연결 or 버튼 대체 결정
- 6일차~: 구현 C와 통합 작업 지원

**구현 C — 시나리오 통합 + Gradio UI**
- 1~4일차: 구현 A/B 진행 상황 파악 + Gradio 기초 학습
- 5~6일차: 시나리오 3개 통합
- 7일차: Gradio UI 연결, 통합 데모 완성
- 8일차~: 오류 수정, 잘 되는 물체만 데모에 사용

**기획/자료팀 2명**
- 1~2일차: 문제 정의 문장 확정, 자료조사 시작
- 3~4일차: 기존 서비스 비교표 완성, 근거 자료 5개 정리
- 5~6일차: PPT 본문 작성
- 7~8일차: PPT 완성, 발표 대본 작성
- 9~10일차: 리허설, 최종 수정
- **발표자: 기획/자료팀 2명 중 1명**

**테스트/데모팀 1명**
- 1~4일차: 테스트 시나리오 설계, 테스트 물체 선정
- 5~6일차: 구현팀 보조
- 7~8일차: 테스트 진행 + 결과 기록표 작성
- 9일차: 데모 영상 촬영 (실시간 데모 실패 대비)

---

## 7. 온라인 팀플 대응 전략

> 온라인 팀플 특성상 실시간 웹캠 통합 테스트가 어렵다. VS Code + Git 브랜치 전략으로 환경을 통일하고 리스크를 최소화한다.

### 온라인 팀플 핵심 문제

| 문제 | 구체적 상황 |
|---|---|
| 웹캠 공유 불가 | 각자 환경이 달라 실시간 카메라 통합 테스트 어려움 |
| 환경 차이 | Python 버전, 패키지 버전 등 제각각이면 통합 시 오류 폭발 |
| 통합 타이밍 | 구현 A/B/C가 따로 짜다가 합치는 순간 충돌 가능 |
| 데모 리스크 | 발표 당일 실시간 데모 실패 가능성 |

---

### 대안 1 — 환경 통일: Python 버전 + requirements.txt 고정

팀원 전체가 동일한 Python 버전과 패키지를 사용하도록 맞춘다.

**Python 버전 고정 (권장: 3.10)**
```bash
# 버전 확인
python --version

# 팀 전체 통일할 버전 예시
Python 3.10.x
```

**requirements.txt로 패키지 버전 고정**
```txt
ultralytics==8.3.0
gtts==2.5.1
pygame==2.6.1
SpeechRecognition==3.10.4
gradio==4.44.0
opencv-python==4.10.0.84
```

```bash
# 팀원 전원 아래 명령어 한 줄로 동일 환경 세팅
pip install -r requirements.txt
```

> `requirements.txt`는 GitHub 루트에 올려두고, 팀원 전원이 clone 후 첫 번째로 실행한다.

---

### 대안 2 — Git 브랜치 전략 (VS Code 기준)

각자 자기 브랜치에서 작업 후 main에 병합하는 구조로 충돌을 최소화한다.

**브랜치 구조**
```
main                  ← 항상 돌아가는 통합 버전 (건드리지 않음)
├── feature/detect    ← 구현 A 전용 (YOLO + 방향/거리)
├── feature/voice     ← 구현 B 전용 (TTS + STT + 의도파악)
└── feature/app       ← 구현 C 전용 (통합 + Gradio UI)
```

**팀원별 브랜치 작업 흐름**
```bash
# 1. 레포 clone (최초 1회)
git clone https://github.com/[팀레포].git
cd voiceguide

# 2. 자기 브랜치로 이동
git checkout feature/detect   # 구현 A
git checkout feature/voice    # 구현 B
git checkout feature/app      # 구현 C

# 3. 작업 후 push
git add .
git commit -m "방향 판단 로직 완성"
git push origin feature/detect
```

**병합은 구현 C가 담당**
```bash
# feature/detect, feature/voice 완성되면 구현 C가 app 브랜치에 병합
git checkout feature/app
git merge feature/detect
git merge feature/voice
# → 통합 테스트 후 main에 최종 병합
```

**VS Code에서 브랜치 확인하는 법**
- 좌측 하단 브랜치 이름 클릭 → 브랜치 전환 가능
- Source Control 탭(Ctrl+Shift+G)에서 commit, push 가능
- 충돌 발생 시 VS Code가 시각적으로 표시해줌

---

**프로젝트 폴더 구조**
```
voiceguide/
├── detect.py        # 구현 A 담당 (YOLO + 방향/거리)
├── voice.py         # 구현 B 담당 (TTS + STT + 의도파악)
├── app.py           # 구현 C 담당 (통합 + Gradio UI)
├── test_images/     # 공용 테스트 이미지 (전원 동일 사용)
│   ├── cup.jpg
│   ├── chair.jpg
│   └── bottle.jpg
└── requirements.txt
```

---

### 대안 3 — 웹캠 대신 이미지 파일로 테스트

실시간 카메라 없이도 개발·테스트 100% 가능하다.

```python
# 웹캠 대신 이미지 파일로 YOLO 테스트
from ultralytics import YOLO

model = YOLO("yolo11n.pt")
results = model("test_images/cup.jpg")  # GitHub에 올린 공용 이미지
```

- 구글에서 "cup on table", "chair indoor" 등 검색해 테스트 이미지 5~10장 저장
- `test_images/` 폴더에 넣고 GitHub에 올리면 팀원 전체가 동일한 이미지로 테스트 가능
- 웹캠 없이도 YOLO 탐지 → 방향/거리 판단 → TTS 출력 전체 흐름 테스트 가능

**테스트 이미지 추천 검색어:**
```
"cup on desk photo"
"chair indoor photo"
"water bottle on table"
"person standing indoor"
```

---

### 대안 4 — 실시간 데모 대신 데모 영상으로 발표 (권장)

```
시나리오 1: "앞에 뭐 있어?" → 탐지 결과 + TTS 출력 화면 녹화
시나리오 2: "컵 찾아줘"    → 탐지 결과 + TTS 출력 화면 녹화
시나리오 3: "이거 뭐야?"   → 탐지 결과 + TTS 출력 화면 녹화
```

- 구현이 가장 잘 되는 순간을 골라 미리 녹화
- 발표 당일 실패 리스크 = 0
- 실제 기업 IR, 해커톤에서도 영상 데모가 표준

**발표에서 이렇게 말하면 된다:**
> "네트워크 환경에 따른 실시간 데모 불안정성을 방지하기 위해 사전 녹화 영상으로 시연합니다."

---

## 8. 10일 상세 일정 (온라인 팀플 버전)

| 일차 | 구현팀 | 기획/자료팀 | 테스트/데모팀 |
|---|---|---|---|
| 1일 | Colab에서 YOLO11n 설치 + 이미지 파일로 테스트 | 문제 정의 확정, 자료조사 시작 | 테스트 시나리오 설계, 공용 이미지 수집 |
| 2일 | 물체 인식 확인, test_images GitHub 업로드 | WHO/보건복지부 자료 정리 | 테스트 물체 선정, 성공 기준 작성 |
| 3일 | 방향 판단 + 거리 판단 로직 완성 (detect.py) | 기존 서비스 비교표 작성 | 테스트 결과 기록표 초안 |
| 4일 | gTTS 연결, 음성 출력 확인 (voice.py) | 차별점 3개 정리, PPT 구조 확정 | 구현팀 보조 |
| 5일 | STT 연결 or 버튼 대체 결정 | PPT 본문 작성 시작 | 구현팀 보조 |
| 6일 | 구현 C: app.py에서 시나리오 3개 통합 시작 | PPT 본문 작성 | Colab 링크로 1차 테스트 + 결과 기록 |
| 7일 | Gradio UI 완성, Colab share=True로 팀 전체 테스트 | PPT 완성 | 2차 테스트, 실패 사례 정리 |
| 8일 | 오류 수정, 잘 되는 물체만 데모에 사용 | 발표 대본 작성 | 테스트 결과표 최종 완성 |
| 9일 | 최종 오류 수정 | 리허설 준비 | **데모 영상 녹화** (구현 C 로컬 or Colab 화면) |
| 10일 | 리허설 참여 | 발표 리허설 2회 이상 | 영상 확인 + 제출 파일 정리 |

### 7일차 중요 체크포인트
> 7일차까지 시나리오 3개가 작동하지 않으면 범위를 줄인다.
> - STT 제거 → Radio 버튼 입력으로 대체
> - 인식 물체 종류 줄이기 (컵, 의자, 사람 3종만)
> - 거리 안내 제거 → 방향만 안내

---

## 8. 매일 15분 회의 방식

회의는 길게 하지 않는다. 매일 15분만, 각자 3가지만 말한다.

1. 어제 한 일
2. 오늘 할 일
3. 막힌 점

회의 후 바로 작업한다.

---

## 9. 자료조사 핵심 근거 5개

PPT에는 5개 근거만 넣는다.

1. **WHO**: 시력 손상이 이동, 삶의 질, 사회 참여에 영향을 줄 수 있다.
2. **보건복지부**: 국내 등록장애인 263만 명 이상, 시각장애 포함.
3. **국내 실내보행 연구**: 시각장애인은 복잡한 실내 공간에서 독립 이동에 어려움을 겪는다.
4. **Google Lookout / Microsoft Seeing AI**: 카메라 기반 접근성 서비스가 실제로 존재하고 사용된다.
5. **Be My Eyes / TapTapSee**: 시각 정보 설명과 물건 확인 서비스 수요가 있다.

---

## 10. 기존 서비스 비교표

| 서비스 | 주요 기능 | 보이스가이드 차별점 |
|---|---|---|
| Google Lookout | 주변 객체/텍스트 인식 | 음성 명령에 따라 장애물/물건/확인 모드 전환 |
| Microsoft Seeing AI | 텍스트, 사람, 객체 설명 | 실내 이동 중 방향 안내 강조 |
| Be My Eyes | 사람/AI 기반 시각 도움 | 사람 연결 없이 즉시 주변 상황 안내 |
| TapTapSee | 촬영한 물체 식별 | 물체 확인뿐 아니라 찾기 + 방향 안내까지 연결 |
| Envision AI | OCR, 주변 설명 | 핵심 시나리오 3개에 집중한 MVP |

### 보이스가이드 차별점 3가지
1. **음성 명령 기반**: "컵 찾아줘", "이거 뭐야?"처럼 말하면 모드가 바뀐다.
2. **방향 중심 안내**: "컵"이 아니라 "컵은 왼쪽 앞에 있습니다"처럼 행동 가능한 정보를 제공한다.
3. **상황별 안내 문장**: 짧게/자세히 안내 모드 전환이 가능하다.

---

## 11. 검증 전략

설문조사를 하지 않아도 된다. 발표에서 이렇게 말한다.

> "시간 제약상 실제 사용자 모집 대신, 문헌 조사와 기존 서비스 비교를 통해 문제의 필요성을 확인하고, 팀 내부 시야 제한 테스트로 프로토타입의 기능 흐름을 검증했습니다."

### 테스트 결과표 (8일차에 완성)

| 테스트 | 입력 | 기대 결과 | 실제 결과 | 성공 여부 |
|---|---|---|---|---|
| 장애물 안내 | 앞에 뭐 있어? | 장애물 방향 안내 | 작성 | 작성 |
| 물건 찾기 | 컵 찾아줘 | 컵 방향 안내 | 작성 | 작성 |
| 물건 확인 | 이거 뭐야? | 중앙 물체 설명 | 작성 | 작성 |
| 안내 방식 | 짧게 말해줘 | 짧은 안내 출력 | 작성 | 작성 |

---

## 12. PPT 구성 (12슬라이드)

1. 표지
2. 문제 배경 (WHO, 보건복지부 통계)
3. 사용자 분석
4. 문제 정의
5. 고객 여정 지도
6. 서비스 소개
7. 핵심 기능 3개
8. 파이프라인
9. 기존 서비스 비교
10. 구현 결과 + 테스트 결과표
11. 실패 사례 + 개선 방향
12. 기대 효과 + 공모전 연계 방향

---

## 13. 성공 기준

### 기능 성공 기준
- 장애물 안내 시나리오가 작동한다.
- 물건 찾기 시나리오가 작동한다.
- 물건 확인 시나리오가 작동한다.
- TTS 음성 안내가 나온다.
- 테스트 결과표가 있다.

### 발표 성공 기준
- 사용자가 누구인지 명확하다.
- 문제가 무엇인지 명확하다.
- 왜 TTS/STT가 필요한지 설명한다.
- 기존 서비스와 차별점이 있다.
- 파이프라인이 논리적이다.
- 데모 영상이 있다.

---

## 14. 최종 체크리스트

- [ ] PPT 완성
- [ ] 데모 영상 완성 (실시간 데모 실패 대비)
- [ ] 테스트 결과표 포함
- [ ] 파이프라인 구조도 포함
- [ ] 기존 서비스 비교표 포함
- [ ] 발표 대본 준비
- [ ] WHO 자료 포함
- [ ] 보건복지부 통계 포함
- [ ] 차별점 3개 명확히 설명
- [ ] 실패 사례 + 개선 방향 포함
- [ ] 발표 리허설 2회 이상

---

## 15. 공모전 연계 전략 (6월 1일까지)

부트캠프 10일 데모 완성 후 공모전용으로 고도화한다.

**부트캠프 결과물 → 공모전 재활용**
- Python 데모 → 데모 영상으로 제출
- 테스트 결과표 → 사업계획서 검증 파트에 활용
- 기존 서비스 비교표 → 그대로 사용

**공모전에서 추가할 것**
- 사업계획서 작성 (문제 정의 → 솔루션 → 시장 규모 → 수익 모델)
- Android 앱 전환 계획 (설계도 수준으로 작성)
- 실사용자 인터뷰 계획 추가

> 공모전은 앱 완성도보다 아이디어와 사업성을 본다. 데모가 Python이어도 충분히 제출 가능하다.

---

## 16. 기술 상세 설명 (팀원 공유용)

> 이 섹션은 구현팀이 각 기술을 처음 접하는 경우를 위한 설명입니다.

### 모델 학습/LLM/데이터에 대한 흔한 걱정 — 정리

| 걱정 | 결론 | 이유 |
|---|---|---|
| 모델 학습이 필요한가? | ❌ 필요 없음 | YOLO11n은 COCO 80종 사전학습 완료 |
| LLM을 써야 하나? | ❌ 쓰지 않음 | 키워드 매칭이 더 빠르고 오프라인 작동 |
| 데이터 수집이 필요한가? | ❌ 필요 없음 | 테스트 물체 몇 개면 충분 |
| 가장 어려운 부분은? | 한국어↔YOLO 클래스명 매핑 | 딕셔너리 직접 작성 필요 |

**LLM을 쓰지 않는 이유:**
- API 비용 발생
- 인터넷 연결 필수 → 발표장에서 끊기면 전체 망함
- 응답 속도 느림 → 실시간 보조 도구로 부적합
- 키워드 매칭이 더 빠르고 안정적

---

### 🟡 YOLO11n — 객체 탐지

**YOLO**는 "You Only Look Once"의 약자로, 카메라 이미지를 **한 번만 훑어서** 물체의 위치와 종류를 동시에 찾아주는 딥러닝 모델이다.

- **11n의 n** = nano 버전. 가장 작고 빠름. 실시간 웹캠 처리 가능
- **bounding box**: 탐지된 물체 주위에 그려지는 직사각형. x, y, width, height 좌표를 제공
- **COCO 80종**: 컵, 의자, 사람, 가방, 병, 핸드폰, 노트북 등 일상 물건 포함
- 추가 학습 없이 `YOLO("yolo11n.pt")` 한 줄로 바로 사용 가능

```python
from ultralytics import YOLO
import cv2

model = YOLO("yolo11n.pt")  # 첫 실행 시 자동 다운로드

cap = cv2.VideoCapture(0)   # 웹캠 연결
ret, frame = cap.read()

results = model(frame)
for box in results[0].boxes:
    cls_id = int(box.cls)
    label = model.names[cls_id]   # 예: "cup"
    x1, y1, x2, y2 = box.xyxy[0] # bounding box 좌표
    center_x = (x1 + x2) / 2
```

---

### 🔵 SpeechRecognition — STT (음성 → 텍스트)

마이크 음성을 텍스트로 변환하는 라이브러리. 내부적으로 Google Speech API를 호출한다.

- **인터넷 연결 필수** (Google 서버로 음성 전송)
- 불안정하면 Gradio Radio 버튼 3개로 모드 선택 대체 가능

```python
import speech_recognition as sr

r = sr.Recognizer()
with sr.Microphone() as source:
    print("말하세요...")
    audio = r.listen(source)

text = r.recognize_google(audio, language="ko-KR")
# text = "컵 찾아줘"
```

**STT가 실패할 경우 Gradio 버튼 대체 방안:**
```python
import gradio as gr

def process(image, mode):
    # mode = "장애물 안내" / "물건 찾기" / "물건 확인"
    ...

gr.Interface(
    fn=process,
    inputs=[
        gr.Image(sources="webcam"),
        gr.Radio(["장애물 안내", "물건 찾기", "물건 확인"])
    ],
    outputs=gr.Textbox()
).launch()
```

---

### 🟢 gTTS + pygame — TTS (텍스트 → 음성)

**gTTS**는 텍스트를 한국어 음성 mp3로 변환한다. **pygame**은 그 mp3를 실제로 재생한다.

- **인터넷 연결 필수** (Google TTS 서버 사용)
- 오프라인 대안: `pyttsx3` (품질 약간 낮음)

```python
from gtts import gTTS
import pygame
import io

def speak(text):
    tts = gTTS(text, lang="ko")
    mp3 = io.BytesIO()
    tts.write_to_fp(mp3)
    mp3.seek(0)

    pygame.mixer.init()
    pygame.mixer.music.load(mp3)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pass  # 음성 재생 완료까지 대기

speak("컵은 왼쪽 가까이에 있습니다")
```

---

### 🟠 키워드 매칭 if/elif — 의도 파악

NLP 모델 없이 **문자열 포함 여부**만으로 사용자 의도를 파악한다. 빠르고 오프라인에서도 작동한다.

```python
def parse_intent(text):
    if "뭐 있어" in text or "장애물" in text:
        return "obstacle", None        # 장애물 안내 모드
    elif "찾아줘" in text:
        target = text.replace("찾아줘", "").strip()
        return "find", target          # 찾기 모드 + 대상 물체명
    elif "뭐야" in text or "이거" in text:
        return "identify", None        # 확인 모드
    elif "짧게" in text:
        return "short_mode", None
    elif "자세히" in text:
        return "detail_mode", None
    else:
        return None, None
```

**한국어 → YOLO 클래스명 매핑 딕셔너리 (필수):**
```python
target_map = {
    "컵": "cup", "의자": "chair", "사람": "person",
    "가방": "backpack", "병": "bottle",
    "핸드폰": "cell phone", "노트북": "laptop", "책": "book",
}
# 사용 예: target_map.get("컵") → "cup"
```

---

### 🟣 Gradio — UI

파이썬만으로 웹 인터페이스를 자동 생성한다. HTML/CSS 없이 발표용 데모 화면을 만들 수 있다.

```python
import gradio as gr

def voiceguide(image, mode):
    # 1. YOLO 탐지
    # 2. 방향/거리 판단
    # 3. 문장 생성
    # 4. TTS 출력
    return "컵은 왼쪽 가까이에 있습니다"

demo = gr.Interface(
    fn=voiceguide,
    inputs=[
        gr.Image(sources="webcam", label="카메라"),
        gr.Radio(["장애물 안내", "물건 찾기", "물건 확인"], label="모드 선택")
    ],
    outputs=gr.Textbox(label="안내 문장")
)
demo.launch()
# → 브라우저에서 localhost:7860 접속
```

---

## 17. 통합 코드 흐름 (구현 C 참고용)

```python
# 전체 흐름 예시 (pseudocode)

def run_voiceguide(frame, mode_text):
    # 1. 의도 파악
    intent, target = parse_intent(mode_text)

    # 2. YOLO 탐지
    results = model(frame)
    detections = parse_detections(results)  # [{label, center_x, area}, ...]

    # 3. 모드별 처리
    if intent == "obstacle":
        closest = get_closest(detections)
        direction = get_direction(closest["center_x"], frame_width)
        distance = get_distance(closest["area"], frame_area)
        message = f"정면 {direction}에 {closest['label_ko']}이 있습니다."

    elif intent == "find":
        yolo_label = target_map.get(target)
        found = [d for d in detections if d["label"] == yolo_label]
        if found:
            direction = get_direction(found[0]["center_x"], frame_width)
            message = f"{target}은 {direction}에 있습니다."
        else:
            message = f"{target}을 찾지 못했습니다."

    elif intent == "identify":
        center_obj = get_center_object(detections, frame_width)
        message = f"카메라 중앙의 물건은 {center_obj['label_ko']}입니다."

    # 4. TTS 출력
    speak(message)
    return message
```

---

*작성일: 2026년 4월*
*대상: 이스트캠프 AI Human Camp 4기 보이스가이드 팀*
*버전: v4 (온라인 팀플 대응 → VS Code + Git 브랜치 전략 + requirements.txt 환경 고정으로 전면 수정)*
