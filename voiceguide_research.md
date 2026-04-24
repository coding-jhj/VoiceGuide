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

## 2. 거리 측정 기술 비교

### 방법 A — bbox 크기 비율 (휴리스틱)

| 항목 | 내용 |
|---|---|
| 원리 | 화면 면적 대비 bounding box 크기로 거리 추정 |
| 난이도 | 낮음 |
| 정확도 | 낮음 (물체 실제 크기 가정 필요) |
| 추가 모델 | 불필요 |
| 적합 상황 | 빠른 MVP 프로토타입 |

```python
# 예시: bbox 면적 비율로 가까움/멀리 판단
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

### 방법 B — Depth Anything V2 ★ 추천

| 항목 | 내용 |
|---|---|
| 발표 | NeurIPS 2024 |
| 모델 크기 | Small 25M params / Base 97M / Large / Giant |
| 추론 속도 | ~0.3초/장 (GPU 기준) |
| Android 지원 | ONNX 변환 후 온디바이스 실행 가능 (GitHub 오픈소스 앱 존재) |
| 라이선스 | Small: Apache-2.0 (상업 이용 가능) |
| 출력 | 상대적 depth map (절대 미터 X, 상대적 가까움/멀리 O) |

**구현 방식**:
1. YOLO11n이 bbox 탐지 → 중심 좌표 (cx, cy) 추출
2. Depth Anything V2가 동일 이미지에서 depth map 생성
3. depth_map[cy][cx] 값으로 거리 분류

```python
from depth_anything_v2.dpt import DepthAnythingV2

model = DepthAnythingV2(encoder='vits', features=64, out_channels=[48, 96, 192, 384])
model.load_state_dict(torch.load('depth_anything_v2_vits.pth'))
model.eval()

depth_map = model.infer_image(raw_img)  # HxW numpy array

# YOLO bbox 중심점에서 깊이값 추출
cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
depth_val = depth_map[cy][cx]

# 임계값으로 분류 (상대값이므로 실험으로 튜닝 필요)
if depth_val < 0.3:
    distance_label = "가까이"
elif depth_val < 0.6:
    distance_label = "보통 거리"
else:
    distance_label = "멀리"
```

> **참고**: Depth Anything V2 Small은 `Apache-2.0` 라이선스라 공모전·상업 이용 모두 가능.  
> Android ONNX 앱 레퍼런스: https://github.com/shubham0204/Depth-Anything-Android

---

### 방법 C — Apple Depth Pro

| 항목 | 내용 |
|---|---|
| 발표 | ICLR 2025 |
| 특징 | 절대 미터 단위 출력, 카메라 intrinsics 불필요 |
| 추론 속도 | 0.3초/장 (GPU) |
| 한계 | 라이선스 제한, 모바일 온디바이스 X (서버 전용) |
| 적합 상황 | 서버에서 절대 거리(미터) 필요할 때 |

> 공모전·프로토타입 단계에서는 Depth Anything V2로 충분.  
> 실제 서비스 고도화 시 Depth Pro로 전환 검토 가능.

---

### 거리 측정 방법 결론

| | 방법 A (bbox 비율) | 방법 B (Depth Anything V2) | 방법 C (Depth Pro) |
|---|---|---|---|
| 난이도 | 낮음 | 중간 | 높음 |
| 정확도 | 낮음 | 중간~높음 | 높음 |
| 모바일 | O | O (ONNX) | X |
| 추가 비용 | 없음 | 없음 (오픈소스) | 없음 (오픈소스) |
| **추천** | MVP 빠른 검증 | **본 구현 목표** | 고도화 단계 |

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
- **추가**: Depth Anything V2 Small 연결 → bbox 중심 픽셀 깊이값 추출
- 방향(left/center/right) + 거리(가까이/보통/멀리) 조합으로 위험도 스코어 계산
- 위험도 높은 상위 1~2개만 음성 출력 대상으로 전달

### 백엔드/서버팀

- FastAPI 기본 구조 + YOLO 추론 서버 (기존 계획 유지)
- **추가**: 공간 스냅샷 저장 API (`POST /spaces/snapshot`)
- 이전/현재 탐지 결과 비교 로직
- WiFi SSID 기반 공간 ID 자동 부여

```
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
    ("left", "가까이"): "왼쪽 바로 앞에 {obj}가 있어요, 오른쪽으로 비켜보세요",
    ("center", "가까이"): "정면 가까이에 {obj}가 있어요, 멈추세요",
    ("right", "보통"): "오른쪽에 {obj}가 있어요",
}
```

### 디바이스팀 (Android)

- 카메라 입력 + 서버 전송 (기존 계획 유지)
- **추가**: WiFi SSID 읽기 → 공간 ID로 서버에 전송
- Depth Anything V2 ONNX 온디바이스 실행 검토 (서버 부하 줄이기)

---

## 5. MVP → 공모전 포지셔닝

### 지금 MVP

```
카메라로 의자 찍기 → YOLO 탐지 → "의자가 왼쪽에 있습니다" 음성 출력
```

### 자료조사 반영 후 MVP (오늘~이번 주)

```
카메라 → YOLO 탐지 + Depth Anything V2 거리 추정
→ 위험도 높은 물체 1~2개 선택
→ "왼쪽 바로 앞에 의자가 있어요, 오른쪽으로 비켜보세요"
```

### 공모전 포지셔닝 (고도화)

```
단순 YOLO 래퍼
  ↓
지능형 공간 인지 + 개인 맞춤형 안내 시스템
  → "이 공간 처음 방문 시": 전체 안내
  → "재방문 시": 변화된 부분만 알려줌 ("평소랑 달리 가방이 하나 더 있어요")
```

> 기존 서비스(Google Lookout 등)는 방문할 때마다 동일한 설명을 반복함.  
> 보이스가이드는 **공간을 기억하고 변화를 감지**한다는 점이 핵심 차별점.

---

## 6. 임팩트 및 차별성

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
| Depth Anything V2 (NeurIPS 2024) | 2024년 6월 | 오픈소스 깊이 추정 SOTA |
| Depth Anything Android ONNX | 2024년 6월 | 모바일 온디바이스 실행 검증 |

**1~2년 전이었으면 이 스펙을 스마트폰에서 돌리는 게 불가능했음.**  
최신 오픈소스 기술의 조합이 지금 이 시점에 처음으로 현실적인 선택지가 된 것.

---

### 차별성 4 — 공모전 주제 적합성

2026 국민행복 서비스 발굴·창업 경진대회 (마감: 6월 1일)

- 공모 주제: "사회보장정보 + AI 기술 융합 서비스"
- 포스터 예시에 **"시각장애인용 지능형 웨어러블 가이드"** 직접 언급
- 스마트폰 기반 → 접근성·확장성 측면 설득력 높음
- 부트캠프 결과물 그대로 재활용 + 사업계획서·Android 전환 계획 추가로 제출 가능

---

## 7. 참고 자료

| 자료 | 내용 | 링크 |
|---|---|---|
| Depth Anything V2 | NeurIPS 2024, 모노큘러 depth estimation SOTA | https://depth-anything-v2.github.io |
| Depth Anything Android | ONNX 기반 Android 구현 오픈소스 | https://github.com/shubham0204/Depth-Anything-Android |
| Apple Depth Pro | ICLR 2025, 절대 미터 단위 depth | https://machinelearning.apple.com/research/depth-pro |
| VISA 시스템 논문 | 시각장애인 실내 내비게이션, AR+YOLO+depth 결합 | J. Imaging 2025, 11(1):9 |
| UC Davis 사용자 조사 | 시각장애인 네비게이션 니즈 정성 조사 | arxiv:2504.06379 |
| Nature Scientific Reports | 시각장애인 가정 내 보조기기 사용 행태 | DOI:10.1038/s41598-025-91755-w |
| YOLO11 + Depth Pro 결합 | bbox 중심점에서 depth 추출 구현 예시 | Medium: ghaith.khlifi |

---

*작성일: 2026-04-24 | 보이스가이드 3팀*
