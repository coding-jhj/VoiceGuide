# VoiceGuide 코드 흐름 이해 가이드

## 전체 데이터 흐름 (한 번의 분석 사이클)

```
Android 카메라 (1초마다)
    │
    │  JPEG 이미지 바이트
    ▼
POST /detect  ← src/api/routes.py
    │
    ├─ 1. detect_and_depth(image_bytes)  ← src/depth/depth.py
    │       │
    │       ├─ detect_objects(image_bytes)  ← src/vision/detect.py
    │       │       └─ YOLO11m 추론 → bbox, 방향, 거리, 위험도
    │       │
    │       ├─ Depth Anything V2 추론 → depth_map (H×W)
    │       │       └─ bbox별 깊이값 → distance_m 갱신
    │       │
    │       └─ detect_floor_hazards(depth_map)  ← src/depth/hazard.py
    │               └─ 바닥 영역 12밴드 분석 → 계단/낙차/턱 감지
    │
    ├─ 2. tracker.update(objects)  ← src/api/tracker.py
    │       └─ EMA 거리 평균화 + 접근/소멸 감지
    │
    ├─ 3. db.get_snapshot() / save_snapshot()  ← src/api/db.py
    │       └─ WiFi SSID 기반 공간 이전 상태 비교
    │
    └─ 4. build_sentence() or build_hazard_sentence()  ← src/nlg/sentence.py
            └─ 한국어 안내 문장 생성

    ▼
JSON 응답: {sentence, objects, hazards, changes}
    │
    ▼
Android TTS → 음성 재생
```

---

## 파일별 역할 한 줄 설명

| 파일 | 역할 |
|------|------|
| `src/vision/detect.py` | YOLO 실행, 방향/거리/위험도 계산 |
| `src/depth/depth.py` | Depth V2 로드·추론, 거리 정제 |
| `src/depth/hazard.py` | 깊이 맵으로 계단·낙차·턱 감지 |
| `src/nlg/sentence.py` | 탐지 결과 → 한국어 문장 |
| `src/nlg/templates.py` | 방향·행동 표현 사전 |
| `src/api/routes.py` | HTTP 엔드포인트, 파이프라인 연결 |
| `src/api/tracker.py` | 프레임 간 객체 추적 (jitter 제거) |
| `src/api/db.py` | SQLite 공간 스냅샷 저장/조회 |
| `src/voice/tts.py` | gTTS + 파일 캐시 |
| `app.py` | Gradio 데모 UI |

---

## 핵심 함수 3개 상세 설명

### 1. `detect_objects()` — src/vision/detect.py

```python
# 입력: JPEG 이미지 바이트
# 출력: 탐지된 물체 리스트 (위험도 내림차순 상위 3개)

def detect_objects(image_bytes: bytes) -> list[dict]:
    img = cv2.imdecode(...)       # 바이트 → 이미지
    results = model(img, conf=0.60)  # YOLO 추론

    for box in results.boxes:
        # 1. 방향 계산 (bbox 중심 x좌표 → 8시~4시)
        cx_norm = bbox중심x / 이미지폭
        direction = "12시"  # if cx_norm 0.44~0.56

        # 2. 거리 계산 (bbox 면적 비율 → 미터)
        area_ratio = bbox면적 / 이미지면적
        distance_m = sqrt(calib_ratio / area_ratio)

        # 3. 위험도 (방향가중치 × 거리가중치 × 바닥여부)
        risk = RISK_DIR[direction] * RISK_DIST[distance]

    return sorted(by risk)[:3]
```

**방향 구역:**
```
[8시][9시][10시][11시][12시][1시][2시][3시][4시]
 0%  11%  22%  33%  44% 56%  67% 78%  89% 100%
```

---

### 2. `detect_floor_hazards()` — src/depth/hazard.py

```python
# 입력: depth_map (H×W, 값이 작을수록 가깝다)
# 출력: 위험 목록 [{type, distance_m, message, risk}]

def detect_floor_hazards(depth_map):
    # 이미지 하단 60% = 바닥 영역
    floor = depth_map[h*0.4:, :]

    # 12개 수평 구역으로 분할 (하단=가까운 쪽)
    for i in range(12):
        band_depths[i] = 해당구역_중앙값

    # 낙차 감지: 깊이가 갑자기 1.2m 이상 증가
    if band_depths[i+1] - band_depths[i] > 1.2:
        → "조심! {거리}m 앞에 계단이나 낙차가 있어요"

    # 턱 감지: 깊이가 갑자기 1.0m 이상 감소
    if band_depths[i+1] - band_depths[i] < -1.0:
        → "발 앞에 턱이나 계단이 있어요"
```

---

### 3. `build_sentence()` — src/nlg/sentence.py

```python
# 거리에 따른 긴급도 4단계
if dist_m < 0.5:   → "위험! 바로 앞 의자!"           (초근접, 짧게)
if dist_m < 1.0:   → "멈추세요! 바로 앞에 의자가 있어요."  (긴급)
if dist_m < 2.5:   → "바로 앞에 의자가 있어요. 멈추세요." (경고)
else:              → "바로 앞에 의자가 있어요. 약 3.0m."  (정보)

# 한국어 조사 자동 선택
"의자이 있어요" → "의자가 있어요"  (받침 없으면 '가')
"사람이 있어요" → "사람이 있어요"  (받침 있으면 '이')
```

---

## Android 앱 흐름

```
onCreate()
    ├─ TTS 초기화 (한국어)
    ├─ SpeechRecognizer 초기화 (STT)
    ├─ SensorManager 등록 (가속도 센서 → 카메라 방향)
    └─ YoloDetector 초기화 (yolo11m.onnx 로드, 백그라운드)

"분석 시작" 버튼 클릭
    └─ 1초마다 captureAndProcess() 반복

captureAndProcess()
    ├─ 온디바이스 모드: YoloDetector.detect() → SentenceBuilder.build() → speak()
    └─ 서버 모드: POST /detect → response.sentence → speak()

실패 시 (handleFail)
    ├─ 3회 연속 실패 → "서버 연결 끊겼어요. 주의해서 이동하세요."
    └─ 6초간 무응답 → "분석이 중단됐어요. 주의해서 이동하세요."
```

---

## 객체 추적기 (tracker.py) 작동 방식

**왜 필요한가?**  
같은 의자가 1프레임에 1.2m, 다음 프레임에 1.8m로 튀면 음성이 계속 달라짐.  
EMA(지수이동평균)로 평균을 내면 1.3m → 1.4m → 1.45m 처럼 안정적.

```python
# EMA: 새 값을 55%, 이전 값을 45% 반영
smooth_d = 0.55 * new_d + 0.45 * old_d

# 접근 감지: 이전보다 0.4m 이상 가까워지고 2.5m 이내
if (old_d - smooth_d) >= 0.4 and smooth_d < 2.5:
    → "사람이 가까워지고 있어요"
```
