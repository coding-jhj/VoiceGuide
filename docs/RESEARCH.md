# VoiceGuide — 자료조사 및 아이디어 정리

> 2026년 4월 24일 | 3팀 (정환주)  
> 프로젝트: (가제) 시각장애인을 위한 AI 음성 주변 인지 서비스

---

## 1. 시각장애인 실제 니즈 — 연구 기반

### 가장 큰 불편 (실사용자 조사 기반)

- **실내 장애물 회피**: 의자·테이블·바닥에 놓인 가방 등 충돌 위험이 가장 높음
- **물건 찾기**: 일상에서 가장 자주 필요로 하는 기능
- **낯선 건물 탐색**: 편의시설 위치, 출입구 등 구조 파악

### 기존 서비스(Google Lookout, Seeing AI 등)의 한계

- 앱 업데이트마다 UI가 바뀌어 매번 다시 배워야 하는 부담 → 큰 좌절 요인
- 정보량이 많고 응답이 느림 → 즉각적인 장애물 회피에 부적합
- 물체 설명은 해주지만 **행동 가능한 방향 안내가 없음**

### 핵심 인사이트

> 연구에 따르면 많은 기술이 시각장애인 당사자와의 협의 없이 개발되어 실사용성이 낮고 학습 곡선이 높다는 점이 반복적으로 지적됨.  
> → 보이스가이드의 차별점: **단순하고 일관된 UX** + **행동 유도 안내문**

사용자가 원하는 것:
- "빠르고 간결한" 안내 (긴 설명 X)
- "행동을 알려주는" 안내 ("왼쪽에 의자가 있습니다" → "왼쪽 비켜보세요")
- 소음 환경에서도 작동하는 fallback (버튼 입력)
- 업데이트해도 달라지지 않는 일관된 UX

**출처**: Nature Scientific Reports 2025, UC Davis 사용자 조사 2024 (arxiv:2504.06379), PMC VISA 시스템 논문 2025 (J. Imaging 11(1):9)

---

## 2. 거리 측정 기술

### 온디바이스 vs 서버 처리 결정

| 기능 | 처리 위치 | 이유 |
|------|---------|------|
| YOLO 객체 탐지 | **폰 온디바이스** ✅ | ONNX Runtime Android, ~50ms, 완전 오프라인 |
| 계단·낙차 감지 | **폰 온디바이스** ✅ | bbox 기반 경고, 서버 불필요 |
| Depth Anything V2 거리 | 서버 (선택) | 모바일 CPU 1~2초 → 안전에 치명적 딜레이 |
| STT | Android SpeechRecognizer | 오프라인 언어팩 지원 |
| TTS | Android TextToSpeech | 완전 오프라인 |

**결론: Android 앱은 서버 없이 완전히 동작합니다.**  
서버가 있으면 Depth Anything V2로 거리 정확도가 향상되지만, 없어도 bbox 기반 거리 추정으로 대체됩니다.

---

### 서버 파이프라인 구조

```
Android 카메라 → 이미지 캡처
    ↓ HTTP POST (이미지 전송)
FastAPI 서버
    ├── YOLO11n        → bbox + 방향 탐지
    └── Depth Anything V2 → depth map 생성
              ↓ bbox 중심 픽셀 깊이값 추출
    → 위험도 스코어 계산 (방향 + 거리 조합)
    → 상위 1~2개 선택
    ↓ JSON 응답
Android → gTTS 음성 출력
```

---

### MVP 단계 — bbox 크기 비율 (빠른 검증용)

서버 연동 전 Python MVP 단계에서는 bbox 면적 비율로 먼저 돌려봄.  
사용자 입장에서 "가까이/멀리" 구분은 두 방법 모두 동일하게 느껴짐.

```python
# bbox 면적 비율로 가까움/멀리 판단
bbox_area = (x2 - x1) * (y2 - y1)
frame_area = frame_w * frame_h
ratio = bbox_area / frame_area

if ratio > 0.15:
    distance = "가까이"
elif ratio > 0.05:
    distance = "보통"
else:
    distance = "멀리"
```

---

### 본 구현 — Depth Anything V2 (서버에서 실행) ★

| 항목 | 내용 |
|---|---|
| 발표 | NeurIPS 2024 |
| 모델 크기 | Small 25M params (서버 경량 운용) |
| 추론 속도 | ~0.3초/장 (GPU 서버 기준) |
| 실행 위치 | **FastAPI 서버** (Android 아님) |
| 라이선스 | Small: Apache-2.0 (공모전·상업 이용 가능) |
| 출력 | 상대적 depth map → "가까이/보통/멀리" 3단계 분류 |

```python
from depth_anything_v2.dpt import DepthAnythingV2

# 서버 시작 시 1회 로드
depth_model = DepthAnythingV2(encoder='vits', features=64, out_channels=[48, 96, 192, 384])
depth_model.load_state_dict(torch.load('depth_anything_v2_vits.pth'))
depth_model.eval()

def get_distance(raw_img, x1, y1, x2, y2):
    depth_map = depth_model.infer_image(raw_img)  # HxW numpy array
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    depth_val = depth_map[cy][cx]

    # 임계값은 실내 환경 실험으로 튜닝 필요
    if depth_val < 0.3:
        return "가까이"
    elif depth_val < 0.6:
        return "보통"
    else:
        return "멀리"
```

---

### 고도화 단계 — Apple Depth Pro

| 항목 | 내용 |
|---|---|
| 발표 | ICLR 2025 |
| 특징 | 절대 미터 단위 출력, 카메라 intrinsics 불필요 |
| 추론 속도 | 0.3초/장 (GPU 서버) |
| 적합 상황 | "1.2미터 앞에 의자가 있어요" 같은 실제 거리 안내가 필요할 때 |

> 프로젝트 기간 내에는 Depth Anything V2로 충분.  
> 공모전 고도화 단계에서 Depth Pro로 전환하면 안내 문장 품질이 올라감.

---

### 단계별 거리 측정 전략 요약

| 단계 | 방법 | 실행 위치 | 시점 |
|---|---|---|---|
| Python MVP | bbox 크기 비율 | 로컬 | 오늘~4/25 |
| 서버 연동 후 | Depth Anything V2 | FastAPI 서버 | 4/28~ |
| 공모전 고도화 | Apple Depth Pro | FastAPI 서버 | 5/13 이후 |

---

## 3. 개인 맞춤형 — 데이터 수집 방법

### 핵심 아이디어: 공간 스냅샷 누적

사용자가 특정 공간을 반복 방문할 때 탐지 결과를 자동으로 쌓아서 **변화를 감지**하는 방식.  
별도 인프라 없이 **WiFi SSID를 공간 ID**로 사용 → 집/학교/카페 자동 구분 가능.

### 데이터 흐름

```
1회 방문
  → YOLO 탐지 결과 + 공간 ID(WiFi SSID) → 서버 DB 저장

2회 이상 방문
  → 이전 기록과 현재 탐지 결과 비교
  → 물체 증감 감지
  → "평소보다 의자 하나 더 있어요" 안내
```

### 저장 데이터 구조

```json
{
  "space_id": "집_거실",
  "wifi_ssid": "MyHome_5G",
  "timestamp": "2026-04-24T09:00:00",
  "objects": [
    {"class": "chair", "direction": "left", "depth_ratio": 0.28, "count": 2},
    {"class": "dining table", "direction": "center", "depth_ratio": 0.55, "count": 1}
  ]
}
```

### 수집 방식 비교

| | 자동 수집 (MVP용) | 수동 등록 (고도화) |
|---|---|---|
| 방법 | 앱 사용할 때마다 자동 저장 | "여기 저장해줘" 음성 명령 |
| 공간 ID | WiFi SSID 자동 감지 | 사용자가 공간 이름 직접 지정 |
| 사용자 부담 | 없음 | 낮음 |
| 정확도 | 중간 | 높음 |
| 적합 단계 | MVP | 공모전 고도화 |

### 변화 감지 로직 (예시)

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

## 4. 팀별 방향 — 자료조사 반영

### 비전 모델팀

- YOLO11n 5종 탐지 (기존 계획 유지)
- **추가**: Depth Anything V2 Small 서버 탑재 → bbox 중심 픽셀 깊이값 추출
- 방향(left/center/right) + 거리(가까이/보통/멀리) 조합으로 위험도 스코어 계산
- 위험도 높은 상위 1~2개만 음성 출력 대상으로 전달

### 백엔드/서버팀

- FastAPI 기본 구조 + YOLO 추론 서버 (기존 계획 유지)
- **추가 1**: Depth Anything V2 서버 탑재 → YOLO와 동일 이미지에서 동시 실행
- **추가 2**: 공간 스냅샷 저장 API
- 이전/현재 탐지 결과 비교 로직
- WiFi SSID 기반 공간 ID 수신 + 매핑

```
# 핵심 추론 API
POST /detect
  body: { image, wifi_ssid }
  response: {
    objects: [{class, direction, distance, risk_score}],
    changes: ["의자가 1개 더 있어요"]   # 재방문 시에만
  }

# 공간 기록 API
POST /spaces/snapshot
  body: { space_id, objects: [{class, direction, depth, count}] }

GET /spaces/{space_id}/changes
  response: { changes: ["의자가 1개 더 있어요"] }
```

### 음성 모델팀

- gTTS 기본 출력 (기존 계획 유지)
- **추가**: 방향 + 거리 조합 문장 템플릿화 (30~50개)
- 변화 감지 결과를 자연어 안내문으로 변환
- 소음 환경 fallback (버튼) 유지

```python
# 문장 템플릿 예시
templates = {
    ("left",   "가까이"): "왼쪽 바로 앞에 {obj}가 있어요, 오른쪽으로 비켜보세요",
    ("center", "가까이"): "정면 가까이에 {obj}가 있어요, 멈추세요",
    ("right",  "보통"):   "오른쪽에 {obj}가 있어요",
    ("left",   "멀리"):   "왼쪽 멀리에 {obj}가 있어요",
}

# 변화 감지 결과 안내문
def change_to_speech(change):
    # "chair이 1개 더 있어요" → "의자가 하나 더 있어요"
    ...
```

### 디바이스팀 (Android)

- 카메라 이미지 캡처 + 서버 HTTP 전송 (기존 계획 유지)
- **추가**: WiFi SSID 읽기 → 요청 body에 포함해서 서버로 전송
- 거리 측정은 서버에서 처리하므로 Android 추가 부담 없음
- 서버 응답 JSON 파싱 → gTTS 음성 출력 연결

---

## 5. MVP → 공모전 포지셔닝

### 지금 MVP

```
카메라로 의자 찍기 → YOLO 탐지 → "의자가 왼쪽에 있습니다" 음성 출력
```

### 자료조사 반영 후 MVP (오늘~4/25)

```
카메라 → 로컬 YOLO 탐지 + bbox 비율 거리 추정
→ 위험도 높은 물체 1~2개 선택
→ "왼쪽 바로 앞에 의자가 있어요, 오른쪽으로 비켜보세요"
```

### 서버 연동 후 (4/28~)

```
Android 카메라
    ↓ HTTP POST (이미지 + WiFi SSID)
FastAPI 서버: YOLO + Depth Anything V2 동시 실행
    ↓ JSON 응답 (방향 + 거리 + 변화 감지 결과)
Android: gTTS 음성 출력
→ "왼쪽 바로 앞에 의자가 있어요" + "오늘은 가방이 하나 더 있어요"
```

### 공모전 포지셔닝 (고도화)

```
단순 YOLO 래퍼
  ↓
지능형 공간 인지 + 개인 맞춤형 안내 시스템
  → 처음 방문: 전체 안내
  → 재방문:    변화된 부분만 알려줌 ("평소랑 달리 가방이 하나 더 있어요")
  → 거리 안내: "1.2미터 앞에 의자가 있어요" (Depth Pro 고도화 시)
```

> 기존 서비스(Google Lookout 등)는 방문할 때마다 동일한 설명을 반복함.  
> 보이스가이드는 **공간을 기억하고 변화를 감지**한다는 점이 핵심 차별점.

---

## 6. 13일 개발 플랜 (주말 제외)

> 4/24(목) ~ 5/13(화), 실제 개발 가능일 13일 기준

### 전체 3단계

```
1단계 (4/24~4/25) — Python MVP 완성        [2일]
2단계 (4/28~5/9)  — 서버 구축 + Android 연동 [8일]
3단계 (5/12~5/13) — 통합 테스트 + 발표       [2일]
```

---

### 1단계: Python MVP (4/24~4/25)

| 날짜 | 비전 | 백엔드 | 음성 | 디바이스 |
|---|---|---|---|---|
| 4/24 (목) | YOLO11n 설치 + 5종 탐지 + 방향 판단 | FastAPI 기본 세팅 + 서버 구조 설계 | gTTS + 문장 템플릿 작성 | Android 개발환경 세팅 |
| 4/25 (금) | bbox 비율 거리 추정 + 위험도 스코어 | YOLO 서버 연결 + DB 스키마 설계 | STT 연결 + 키워드 매칭 | Android 카메라 캡처 구현 |

**✅ 완료 기준**: Python에서 "왼쪽 바로 앞에 의자가 있어요" 음성 출력 작동

---

### 2단계: 서버 구축 + Android 연동 (4/28~5/9)

| 날짜 | 주요 목표 |
|---|---|
| 4/28 (월) | Depth Anything V2 서버 탑재 + YOLO와 동시 실행 테스트 |
| 4/29 (화) | 공간 스냅샷 API 완성 + 변화 감지 로직 구현 |
| 4/30 (수) | ngrok 외부 접근 + Android → 서버 이미지 전송 구현 |
| 5/1 (목) | Android 시나리오 1 (장애물 안내) end-to-end 작동 |
| 5/2 (금) | WiFi SSID 전송 + 공간 기억 Android 연동 |
| 5/6 (화) | Android 시나리오 2·3 (물건 찾기·확인) 작동 |
| 5/7 (수) | 전체 흐름 통합 테스트 + 오류 수정 |
| 5/8 (목) | 인식률 데이터 정리 + 서버 안정화 |
| 5/9 (금) | 데모 시나리오 확정 + 데모 영상 1차 녹화 |

**⚠️ 리스크 포인트**
- 4/30: Android ↔ 서버 HTTP 통신 — 여기서 막히면 팀 전체 모여서 해결 (혼자 붙잡지 말 것)
- 5/2: WiFi SSID Android 권한 이슈 — 안 풀리면 사용자 직접 입력 fallback으로 대체

**✅ 완료 기준**: Android에서 시나리오 3개 end-to-end + 공간 기억 기능 작동

---

### 3단계: 통합 + 발표 (5/12~5/13)

| 날짜 | 주요 목표 |
|---|---|
| 5/12 (월) | 데모 영상 최종 녹화 + 발표 리허설 1~2회 |
| 5/13 (화) | **최종 발표** 🎯 |

---

### 비상 플랜

| 상황 | 대응 |
|---|---|
| Android 연동 안 될 경우 | Python + Gradio 데모로 대체, Android는 설계도만 제출 |
| 서버 배포 안 될 경우 | 로컬 서버(ngrok)로 대체 |
| WiFi SSID 권한 이슈 | 사용자 직접 공간명 입력 fallback |
| 공간 기억 기능 불안정 | 데모에서 제외, PPT 로드맵 슬라이드로 대체 |
| STT 불안정 | 버튼 입력으로 즉시 대체 |

---

## 7. 임팩트 및 차별성

### 핵심 한 문장

> **"기존 서비스는 환경을 설명하지만, 보이스가이드는 환경을 기억하고 행동을 안내한다."**

---

### 임팩트 — 왜 이 문제가 중요한가

- WHO 기준 전 세계 시각장애인 약 **2억 8500만 명**
- 실내 이동 보조 기술의 실질적 보급률은 매우 낮음
  - 기존 기기: 고가 하드웨어 필요, 학습 난이도 높음 → 실사용으로 이어지지 않음
  - 연구 결과 75% 이상이 "비용 문제"를 가장 큰 장벽으로 꼽음 (Zagreb 대학, 2024)
- 보이스가이드는 **스마트폰 하나**로 해결 → 추가 비용 없음, 별도 하드웨어 없음

---

### 차별성 1 — 방향 + 거리 + 행동 안내 동시 제공

| 서비스 | 출력 예시 | 한계 |
|---|---|---|
| Google Lookout | "의자가 있습니다" | 방향·거리 없음 |
| Microsoft Seeing AI | "왼쪽에 의자가 있습니다" | 행동 안내 없음 |
| **보이스가이드** | **"왼쪽 바로 앞에 의자가 있어요, 오른쪽으로 비켜보세요"** | — |

사용자가 실제로 원하는 것은 물체 설명이 아니라 **무엇을 해야 하는지**다.  
UC Davis 연구(2024)에서 시각장애인들이 공통적으로 요구한 것이 바로 이 "행동 유도 안내"였음.

---

### 차별성 2 — 공간을 기억하는 시스템

기존 서비스는 매번 방문해도 **처음 온 것처럼 동일한 설명을 반복**함.

보이스가이드는 다름:

| 상황 | 기존 서비스 | 보이스가이드 |
|---|---|---|
| 집 거실 매일 방문 | "소파, 테이블, 의자 있습니다" (매번) | "오늘은 가방이 하나 더 있어요" (변화만) |
| 자주 가는 카페 | 전체 물체 나열 | "평소보다 사람이 많아요" |
| 처음 가는 장소 | 전체 물체 나열 | 전체 안내 (동일하게 작동) |

반복 방문 공간에서 **변화된 것만 알려주는 것** 자체가 핵심 임팩트.  
집에서 매일 같은 안내를 듣는 건 오히려 인지 부하를 높이는 방해 요인임.

---

### 차별성 3 — 타이밍 (2024~2025년에야 가능한 조합)

| 기술 | 공개 시점 | 의미 |
|---|---|---|
| YOLO11n | 2024년 하반기 | 경량 고성능 객체 탐지 |
| Depth Anything V2 (NeurIPS 2024) | 2024년 6월 | 오픈소스 깊이 추정 SOTA, 서버 경량 운용 가능 |
| Apple Depth Pro (ICLR 2025) | 2024년 10월 | 절대 미터 단위 depth, 서버 고도화 옵션 |

**1~2년 전이었으면 이 스펙을 서버에서 실시간으로 돌리는 것 자체가 비용 문제로 어려웠음.**  
최신 오픈소스 모델들이 경량화되면서 지금 이 시점에 처음으로 현실적인 선택지가 된 것.

---

### 차별성 4 — 공모전 주제 적합성

2026 국민행복 서비스 발굴·창업 경진대회 (마감: 6월 1일)

- 공모 주제: "사회보장정보 + AI 기술 융합 서비스"
- 포스터 예시에 **"시각장애인용 지능형 웨어러블 가이드"** 직접 언급
- 스마트폰 기반 → 접근성·확장성 측면 설득력 높음
- 부트캠프 결과물 그대로 재활용 + 사업계획서·Android 전환 계획 추가로 제출 가능

---

## 8. 참고 자료

### AI 모델

| 자료 | 내용 | 링크 |
|---|---|---|
| Depth Anything V2 | NeurIPS 2024, 모노큘러 depth estimation SOTA | [depth-anything-v2.github.io](https://depth-anything-v2.github.io) |
| Depth Anything V2 논문 | arXiv:2406.09414 | [arxiv.org/abs/2406.09414](https://arxiv.org/abs/2406.09414) |
| Depth Anything V2 모델 | HuggingFace 공식 가중치 | [huggingface.co/depth-anything](https://huggingface.co/depth-anything/Depth-Anything-V2-Small) |
| Apple Depth Pro | ICLR 2025, 절대 미터 단위 depth | [machinelearning.apple.com](https://machinelearning.apple.com/research/depth-pro) |
| YOLO11 공식 문서 | Ultralytics YOLO11 모델 명세 | [docs.ultralytics.com/models/yolo11](https://docs.ultralytics.com/models/yolo11/) |
| YOLO11 GitHub | 소스코드 및 학습 가이드 | [github.com/ultralytics/ultralytics](https://github.com/ultralytics/ultralytics) |

### Android 구현 참고

| 자료 | 내용 | 링크 |
|---|---|---|
| Depth Anything Android | ONNX 기반 Android 구현 오픈소스 | [github.com/shubham0204/Depth-Anything-Android](https://github.com/shubham0204/Depth-Anything-Android) |
| ONNX Runtime Android | Microsoft 공식 Android 가이드 | [onnxruntime.ai/docs/tutorials/mobile](https://onnxruntime.ai/docs/tutorials/mobile/) |
| CameraX 공식 문서 | Android 카메라 API | [developer.android.com/training/camerax](https://developer.android.com/training/camerax) |

### 사용자 조사 및 논문

| 자료 | 내용 | 링크 |
|---|---|---|
| UC Davis 사용자 조사 (2024) | 시각장애인 네비게이션 니즈 정성 조사 | [arxiv.org/abs/2504.06379](https://arxiv.org/abs/2504.06379) |
| Nature Scientific Reports (2025) | 시각장애인 가정 내 보조기기 사용 행태 | [doi.org/10.1038/s41598-025-91755-w](https://doi.org/10.1038/s41598-025-91755-w) |
| VISA 시스템 논문 (2025) | 시각장애인 실내 내비게이션, AR+YOLO+depth 결합 | [doi.org/10.3390/jimaging11010009](https://doi.org/10.3390/jimaging11010009) |
| WHO 시각장애 통계 | 전 세계 시각장애인 현황 | [who.int/news-room/fact-sheets/detail/blindness-and-visual-impairment](https://www.who.int/news-room/fact-sheets/detail/blindness-and-visual-impairment) |

### 경쟁 서비스 분석

| 서비스 | 링크 |
|--------|------|
| Google Lookout | [lookout.app](https://lookout.app) |
| Microsoft Seeing AI | [microsoft.com/en-us/ai/seeing-ai](https://www.microsoft.com/en-us/ai/seeing-ai) |
| Be My Eyes | [bemyeyes.com](https://www.bemyeyes.com) |

---

*작성일: 2026-04-24 | 보이스가이드 3팀*
