# VoiceGuide 코드 학습 가이드

> 팀원 공부용 — 각 모듈이 왜 이렇게 만들어졌는지 한 줄씩 설명합니다.  
> 코드를 처음 보는 팀원도 이 파일 하나로 전체 흐름을 이해할 수 있게 작성했습니다.

---

## 1. 전체 파이프라인 한눈에

```
[사용자 음성] → STT → 모드 결정
[카메라 이미지] → YOLO 탐지 → 방향/위험도 계산
                → Depth V2 → 실제 거리(m) 추정
                → 계단/낙차 감지 (바닥 분석)
                → 객체 추적 (EMA 평활화)
                → 공간 기억 비교 (재방문 변화 감지)
[문장 생성] → TTS 음성 출력
```

---

## 2. YOLO 탐지 (`src/vision/detect.py`)

### 왜 confidence 0.55인가?
```python
CONF_THRESHOLD = 0.55
# 야외 차량은 거리가 멀면 작게 보여서 confidence가 낮게 나옴
# 0.60이면 멀리 있는 자동차를 못 잡음 → 안전 문제
# 차량은 CLASS_MIN_CONF에서 0.40으로 더 낮춤 (일찍 감지)
CLASS_MIN_CONF = {
    "car": 0.40,        # 야외: 멀리서 빨리 잡아야 함
    "motorcycle": 0.40, # 야외: 빠르게 접근하므로 일찍 감지
    "cell phone": 0.68, # 실내 소형: 오탐 많아서 높게 설정
}
```

### 왜 차량 위험도가 3배인가?
```python
CLASS_RISK_MULTIPLIER = {
    "car":    3.0,  # 정적 의자가 아니라 이동 물체 → 3배 위험
    "bus":    3.5,  # 크고 빠름 → 의자(1.0)보다 3.5배 위험
    "truck":  3.5,
    "train":  4.0,  # 피할 수 없음 → 최고 위험
    "dog":    1.8,  # 돌발 행동 위험
}
# 실제 계산: risk = dir_weight × dist_weight × ground_mult × class_mult
# 예) 12시 방향 가까이 자동차: 1.0 × 0.8 × 1.0 × 3.0 = 2.4 → min(2.4, 1.0) = 1.0 (최고 위험)
```

### 방향 9구역이 왜 시계 방향인가?
```python
ZONE_BOUNDARIES = [
    (0.11, "8시"),   # 이미지 왼쪽 끝 = 8시 방향
    (0.56, "12시"),  # 이미지 중앙 = 12시 = 바로 앞
    (1.01, "4시"),   # 이미지 오른쪽 끝 = 4시 방향
]
# 시계 방향 표현: 시각장애인이 이미 시계 방향 개념에 익숙하기 때문
# "왼쪽"보다 "10시 방향"이 더 정확한 위치 전달 가능
```

### 거리 보수 추정이란?
```python
# 안전 우선 → 실제보다 가깝게 추정 (보수적)
distance_m = round(math.sqrt(calib / area_ratio), 1)
# calib는 물체별 실제 크기 기반 값
# 예) 의자(0.06): 화면 6% 면적이면 약 1m 거리
# 이 공식은 깊이 센서 없이 카메라만으로 추정하는 근사값
```

---

## 3. Depth Anything V2 (`src/depth/depth.py`)

### 왜 하위 30% 깊이값을 쓰는가?
```python
# bbox 안에서 가장 가까운 부분(=가장 위험한 부분)을 대표값으로 사용
# 중앙값을 쓰면 물체 뒤쪽(먼 부분) 깊이가 섞여서 실제보다 멀리 추정됨
# 하위 30% = 물체에서 가장 가까운 쪽 → 안전 우선
depth_val = np.percentile(region, 30)
```

### Depth 모델이 없을 때?
```python
# depth_anything_v2_vits.pth 파일이 없으면 자동으로 bbox 방식으로 fallback
depth_source = "bbox"   # 면적 비율로 거리 추정 (덜 정확하지만 동작)
depth_source = "v2"     # Depth V2 모델 사용 (더 정확)
```

---

## 4. 계단/낙차 감지 (`src/depth/hazard.py`)

### 어떻게 계단을 감지하나?
```python
# 이미지 하단(사람 걸어가는 방향)을 12개 수평 밴드로 분할
# 각 밴드의 중앙 깊이값을 계산
# 가까운 밴드에서 먼 밴드로 갈수록 깊이가 점점 증가하는 게 정상
# 갑자기 1.2m 이상 깊어지면 → 낙차/계단 경고
# 갑자기 1.0m 이상 얕아지면 → 턱/계단 경고
_DROP_THRESH = 1.2  # 낙차 감지 임계값 (m)
_STEP_THRESH = 1.0  # 턱 감지 임계값 (m)
```

---

## 5. 문장 생성 (`src/nlg/sentence.py`)

### 거리별 긴박도 4단계
```python
# 0.5m 미만: 초긴급 — 짧게! TTS 재생시간 최소화
"위험! 바로 앞 의자!"

# 0.5~1.0m: 긴급 — 방향 + 거리 + 행동
"바로 앞에 의자가 있어요. 약 80cm. 멈추세요."

# 1.0~2.5m: 경고 — 방향 + 거리 + 행동
"왼쪽 앞에 의자가 있어요. 약 1.5m. 오른쪽으로 피해가세요."

# 2.5m 이상: 정보 — 방향 + 거리만
"왼쪽에 의자가 있어요. 약 3.0m."
```

### 왜 차량은 별도 처리?
```python
# 차량은 이동 물체 → 2.5m 기준이 아니라 8m 이내부터 긴급
if is_vehicle:
    if dist_m < 3.0:
        return f"위험! {direction}에 {name}이 있어요! {dist_str}. 즉시 {action}!"
    if dist_m < 8.0:
        return f"조심! {direction}에 {name}이 접근 중이에요. {dist_str}. {action}."
```

### 한국어 조사 자동화
```python
def _i_ga(word):
    # 받침 있음(책, 의자) → "이"  /  받침 없음(소파, 배낭) → "가"
    # (ord(마지막글자) - 0xAC00) % 28 == 0 이면 받침 없음
    # 예) 의자: 자(0xC790) → (51088-44032)%28 = 7056%28 = 0 → "가" → "의자가" ✓
    # 예) 책:   책(0xCC45) → (52293-44032)%28 = 8261%28 = 1 → "이" → "책이" ✓
```

---

## 6. 객체 추적 (`src/api/tracker.py`)

### EMA(지수이동평균)가 왜 필요한가?
```python
# 프레임마다 YOLO 결과가 조금씩 달라짐 (jitter)
# 예) 1m → 1.2m → 0.9m → 1.1m → TTS가 계속 다른 말을 함 → 혼란
# EMA로 평활화: new = alpha * current + (1-alpha) * previous
alpha = 0.55  # 현재 값 55% + 이전 값 45% → 안정적
```

### 접근 감지
```python
# 이전 프레임보다 0.4m 이상 가까워지고 && 2.5m 이내
# → "가방이 가까워지고 있어요" 알림
# 정지한 물체에는 발생하지 않음 → 실제로 움직이는 물체(사람, 차량)만 감지
```

---

## 7. 공간 기억 (`src/api/db.py`)

### WiFi SSID를 공간 ID로 쓰는 이유
```python
# GPS는 실내에서 작동 안 함
# WiFi SSID = 무선공유기 이름 = 같은 공간이면 항상 같은 값
# "MyHome_5G" = 집, "Starbucks_Guest" = 특정 카페
# 비용 0원, 추가 하드웨어 없음, 정확도 충분
```

### saved_locations 테이블 (개인 네비게이팅)
```sql
CREATE TABLE saved_locations (
    id        INTEGER PRIMARY KEY,
    label     TEXT,     -- 사용자가 지정한 이름 ("편의점", "화장실")
    wifi_ssid TEXT,     -- 저장 당시 WiFi SSID
    timestamp TEXT      -- 저장 시각
);
-- "여기 저장해줘 화장실" → label="화장실", wifi_ssid="현재SSID"
-- 다음에 같은 WiFi에 연결되면 → "화장실이 이 곳이에요!"
```

---

## 8. Android 앱 (`android/app/src/main/java/com/voiceguide/`)

### 왜 CameraX를 쓰나?
```kotlin
// CameraX = Google이 만든 카메라 API 추상화 레이어
// Camera2 API는 너무 복잡 (수백 줄)
// CameraX = 수십 줄로 같은 기능 구현, lifecycle 자동 관리
```

### 온디바이스 ONNX 추론
```kotlin
// ONNX = Open Neural Network Exchange = 모델 포맷
// PyTorch로 학습한 YOLO → ONNX로 변환 → Android에서 실행
// 서버 없이 폰 단독 동작 → 인터넷 없어도 OK
// 추론 속도: ~50ms (RTX GPU의 10배 느리지만 실사용 OK)

val input = FloatBuffer.allocate(1 * 3 * 640 * 640)  // batch × RGB × H × W
// NCHW 포맷: N=배치, C=채널(RGB=3), H=높이, W=너비
```

### STT 키워드 fallback 처리
```kotlin
// 키워드 미매칭 → 기본 장애물 모드 (버리지 않음)
// "배고파" 라고 말해도 장애물 모드로 동작 → 안내 누락 없음
private fun classifyKeyword(text: String): String {
    for ((mode, keywords) in STT_KEYWORDS) {
        if (keywords.any { text.contains(it) }) return mode
    }
    return "장애물"  // 미매칭 시 기본값
}
```

### SharedPreferences로 장소 저장
```kotlin
// Room DB는 SQLite 추상화 레이어 (복잡)
// SharedPreferences = 앱 설정 저장용 key-value 스토어
// 장소 목록은 JSON 배열로 저장 → 직렬화/역직렬화 간단
// 데이터 양이 적어서 (수십 개 장소) SharedPreferences로 충분
```

---

## 9. 실내외 위험 요소 분류

### 실내
| 위험 요소 | 탐지 방법 | 위험도 배수 |
|---------|---------|-----------|
| 의자·소파·테이블 | YOLO | 1.0 |
| 바닥 가방·여행가방 | YOLO + 바닥 판별 | 1.4 (바닥) |
| 계단·낙차 | YOLO + Depth 분석 | 최우선 |
| 화분·변기·세면대 | YOLO | 1.0 |
| 사람 | YOLO | 1.0 |

### 야외
| 위험 요소 | 탐지 방법 | 위험도 배수 |
|---------|---------|-----------|
| **자동차·오토바이·버스** | YOLO (conf 0.40) | **3.0~3.5** |
| **기차** | YOLO | **4.0** |
| 자전거 | YOLO | 2.0 |
| 개·말 (돌발 행동) | YOLO | 1.8~2.5 |
| 신호등 | YOLO | 0.8 (정보) |
| 소화전·벤치 (걸림) | YOLO | 1.0 |

> 야외 차량은 이동 물체이므로 위험도 배수를 3~4배로 설정.  
> 같은 "가까이" 거리여도 의자보다 자동차가 훨씬 위험하기 때문.

---

## 10. 자주 묻는 질문

**Q. Depth V2 없으면 거리가 얼마나 부정확한가?**  
A. bbox 면적 기반은 ±50% 오차가 있을 수 있음. Depth V2는 ±20~30%. 안전 우선으로 항상 더 가깝게 추정하도록 보수 계수 적용.

**Q. 왜 최대 3개 물체만 반환하나?**  
A. TTS가 동시에 너무 많은 정보를 읽으면 오히려 혼란. "의자, 가방, 사람, 테이블이 있어요" → 어디로 피해야 할지 모름. 가장 위험한 1~2개만 안내하는 것이 더 도움.

**Q. 야외에서 신호등 색깔도 감지하나?**  
A. 현재는 신호등의 존재만 감지(YOLO). 색깔(빨강/초록) 판별은 별도 분류 모델 필요 → 향후 개선 과제.

**Q. 소리(경적)는 감지 못하나?**  
A. 현재 카메라 기반이라 소리 감지 없음. 오디오 분류 모델 추가가 가능한 향후 개선 방향.
