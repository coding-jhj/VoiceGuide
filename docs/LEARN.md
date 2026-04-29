# VoiceGuide 코드 학습 가이드

> 팀원 공부용 — 코드를 처음 보는 사람도 이 파일 하나로 전체 흐름을 이해할 수 있게 작성했습니다.  
> "이게 왜 이렇게 돼있지?" 싶은 부분을 먼저 찾아보세요.

---

## 전체 흐름 (이것만 알아도 됨)

```
사용자가 말한다 → STT가 듣는다 → 모드를 결정한다
                                        ↓
                              카메라로 사진을 찍는다 (1초마다 자동)
                                        ↓
                              YOLO가 물체를 찾는다
                              Depth V2가 거리를 추정한다
                              신호등 색상 / 색상 / 점자블록 분석
                                        ↓
                              위험도 계산 → 문장 생성
                                        ↓
                              TTS로 말해준다
```

---

## 1. 물체 탐지 (`src/vision/detect.py`)

### 물체를 찾는 AI — YOLO11m

카메라 이미지를 받아서 "의자가 어디 있고, 자동차가 어디 있는지" 찾아줘요.
COCO 80가지 클래스. (계단은 YOLO 오탐률이 높아 제외 → Depth 맵 12구역 분석으로 대체)

```python
CONF_THRESHOLD = 0.50   # 확신도 50% 이상인 것만 탐지
CLASS_MIN_CONF = {
    "car": 0.38,        # 차량은 멀어도 일찍 잡아야 해서 낮게
    "cell phone": 0.65, # 소형 물체는 오탐 많아서 높게
}
```

### 방향 판단 — 이미지를 9구역으로 나눔

이미지를 가로로 9등분해서 왼쪽부터 "8시, 9시, 10시 ... 4시" 로 매핑해요.

```
이미지:  [왼쪽] ←————————————————→ [오른쪽]
방향:     8시    9시  10시  11시  12시  1시  2시  3시  4시
한국어:  왼쪽  왼쪽  왼앞  왼앞  바로앞  우앞  우앞  오른쪽  오른쪽
```

**방향 좌우 반전 버그 (2026-04-27 수정):**
카메라 이미지가 mirror 상태로 전달되는 문제가 있어서,
서버에서 이미지를 받자마자 좌우 flip을 해요.

```python
img = cv2.flip(img, 1)   # 이 한 줄이 방향 오류를 고쳐줌
```

### 위험도 계산

```python
risk = 방향가중치 × 거리가중치 × 바닥여부 × 클래스배수

# 예시: 바로 앞(12시) 가까이에 자동차
risk = 1.0 × 0.8 × 1.0 × 3.0 = 2.4 → min(2.4, 1.0) = 1.0  # 최고 위험
```

클래스별 위험도 배수:
- 자동차 3.0 / 버스·트럭 3.5 / 기차 4.0 (이동 차량)
- 개 1.8 / 말 2.5 (돌발 행동 동물)
- 칼 2.5 / 가위 2.0 (날카로운 물체)

### 경고 모드 분류 (alert_mode)

탐지된 물체를 2단계로 분류해서, Android에서 음성·무음으로 처리해요.
`get_alert_mode()` 함수 (`src/nlg/sentence.py`)가 담당.

```python
# critical — 계단/차량/2.5m 이내 장애물 → 말 중이어도 끊고 1.25× 빠르게
# silent   — 2.5m 이상 → 무음 (사용자가 물어볼 때만 안내)
# (beep 제거: 비프음 대신 음성으로 교체 — 인터뷰 피드백 반영)
if is_hazard or (is_vehicle and dist < 8.0): return "critical"
if dist < 2.5:  return "critical"
return "silent"
```

### 신호등 빨강/초록 감지 (신규)

YOLO가 신호등을 찾으면, 그 bbox 영역을 잘라서 색상을 분석해요.

```python
# 신호등은 세로로 긺: 위쪽 1/3 = 빨간불 위치, 아래쪽 1/3 = 초록불 위치
# HSV 색공간에서 초록 픽셀 비율이 5% 이상이면 "green"
if green_ratio > 0.05: return "green"   # "신호등이 초록불이에요. 건너도 돼요."
if red_ratio   > 0.05: return "red"     # "신호등이 빨간불이에요. 멈추세요."
```

### 색상 감지 (신규)

"색깔 알려줘" 명령 시 물체 중심부를 HSV로 분석해요.

```python
# HSV의 H값(색조)으로 색상 분류
if h < 15 or h >= 165: return "빨간색"
if h < 30:             return "주황색"
if h < 45:             return "노란색"
if h < 75:             return "초록색"
if h < 130:            return "파란색"
```

### 점자 블록 위 장애물 경고 (신규)

보행 경로(이미지 하단 중앙 40% 너비)에 자전거·킥보드 등이 있으면 경고해요.

```python
# 화면 하단 35%, 좌우 중앙 40%가 "보행 경로"
# 여기 바닥에 자전거 감지 → "보행 경로에 자전거가 있어요. 우회하세요."
```

---

## 2. 거리 추정 (`src/depth/depth.py`)

### Depth Anything V2

이미지 한 장으로 픽셀별 "얼마나 멀리 있는지" 를 추정해요.
딥러닝 모델이라 완벽하진 않고 오차가 있어요.

```python
# 안전 우선: bbox 안에서 가장 가까운 쪽(하위 30%) 값 사용
depth_val = np.percentile(region, 30)
# 왜 중앙값 아닌가? → 물체 뒤쪽(먼 부분)이 섞여서 실제보다 멀게 추정될 수 있음
```

모델 파일이 없으면 자동으로 bbox 면적 기반 fallback.

### 거리 표현 (2026-04-27 변경)

강사님 피드백 반영: 카메라로 정확한 수치 거리는 측정 불가.
"약 1.2미터" 대신 상대 표현 사용.

```python
def _format_dist(dist_m):
    if dist_m < 0.5:  return "바로 코앞"
    if dist_m < 1.0:  return "매우 가까이"
    if dist_m < 2.5:  return "가까이"
    if dist_m < 5.0:  return "조금 멀리"
    return "멀리"
```

### 계단·낙차 감지 (`src/depth/hazard.py`)

이미지 바닥 영역을 12구역으로 나눠서 깊이 변화를 봐요.

```
정상: 가까운 바닥 → 먼 바닥으로 갈수록 깊이가 점점 증가
낙차: 갑자기 1.2m 이상 깊어짐 → "앞에 계단이나 낙차가 있어요."
턱:   갑자기 1.0m 이상 얕아짐 → "발 앞에 턱이나 계단이 있어요."
```

---

## 3. 문장 생성 (`src/nlg/sentence.py`)

### 긴박도에 따른 문장 구조

```
0.5m 미만 (초긴급):  "위험! 바로 앞 의자!"
0.5~1.0m (긴급):    "바로 앞에 의자가 있어요. 매우 가까이. 기다리세요."
1.0~2.5m (경고):    "왼쪽 앞에 의자가 있어요. 가까이. 오른쪽으로 피하세요."
2.5m 이상 (정보):   "왼쪽에 의자가 있어요. 조금 멀리."
```

### 차량은 별도 처리

```python
if is_vehicle and dist < 3.0:
    return "위험! 오른쪽에 자동차가 있어요! 잠깐 왼쪽으로 피하세요!"
if is_vehicle and dist < 8.0:
    return "조심! 오른쪽에 자동차가 접근 중이에요. 조금 멀리. 왼쪽으로 피하세요."
# 차량은 이동 물체라서 2.5m 기준이 아니라 8m 이내부터 경고
```

### 한국어 조사 자동화

```python
def _i_ga(word):
    # "의자가" vs "책이" — 받침 유무로 자동 결정
    # (글자코드 - 0xAC00) % 28 == 0 이면 받침 없음
    # 의자: "가", 책: "이", 소파: "가", 냉장고: "가"
```

---

## 4. 객체 추적 (`src/api/tracker.py`)

### EMA(지수이동평균) — 흔들림 제거

YOLO 결과는 프레임마다 조금씩 달라져요 (jitter).
매 프레임 다른 거리를 TTS가 읽으면 혼란스럽기 때문에 평균을 내요.

```python
alpha = 0.55
# 새 거리 = 현재 55% + 이전 45%
smooth_d = alpha * new_d + (1 - alpha) * old_d
```

### 접근 경고

```python
# 이전보다 0.4m 이상 가까워지고 && 2.5m 이내
# → "가방이 가까워지고 있어요"
delta = old_d - smooth_d   # 양수 = 가까워지는 중
if delta >= 0.4 and smooth_d < 2.5:
    changes.append(f"{name}이 가까워지고 있어요")
```

### 빠른 접근 경고 (신규) — 낙하·날아오는 물체

```python
# 한 프레임에 0.8m 이상 급격히 가까워지면 → 날아오는 물체나 떨어지는 물체
if delta >= 0.8 and smooth_d < 3.0:
    changes.append(f"조심! {name}이 빠르게 다가오고 있어요!")
```

---

## 5. 서버 API (`src/api/routes.py`)

### /detect 엔드포인트 응답 구조

```json
{
  "sentence":    "왼쪽 앞에 의자가 있어요. 가까이. 오른쪽으로 피하세요.",
  "objects":     [...],
  "hazards":     [...],
  "scene":       { "safe_direction": "...", "traffic_light_msg": "..." },
  "alert_mode":  "critical",
  "changes":     ["의자가 생겼어요"]
}
```

`alert_mode: "critical"` 이면 말 중이어도 끊고 1.25× 속도로 즉각 음성 출력.
`alert_mode: "silent"` 이면 무음 (UI만 업데이트).
(beep 모드 제거 — 비프음 대신 일반 속도 음성 안내로 교체됨)

### 공간 기억 — 재방문 시 달라진 것만 안내

```python
# WiFi SSID를 공간 ID로 사용 (GPS 대신, 실내도 동작)
previous = db.get_snapshot(wifi_ssid)          # 이전 방문 기억
space_changes = _space_changes(objects, previous)  # 달라진 것만 추출
# 결과: ["의자가 생겼어요", "사람이 없어졌어요"]
```

---

## 6. Android 앱 (`android/.../MainActivity.kt`)

### 음성 자동 시작 (신규)

앱을 처음 켜면 버튼 없이 말로 시작할 수 있어요.

```kotlin
// TTS 초기화 완료 → 1초 후 자동으로 물어봄
speak("음성 안내를 시작할까요? 네 또는 아니오로 말씀해주세요.")
// "네" 라고 하면 → requestPermissions() → 카메라 시작
```

### 조도 센서 (신규)

빛 센서를 이용해서 주변이 어두우면 알려줘요.

```kotlin
// Sensor.TYPE_LIGHT로 조도 읽기
if (lastLux >= 10f && lux < 10f) {
    speak("주변이 많이 어두워요. 조심하세요.")
}
```

### 경고 계층 — alert_mode 3단계 (신규)

서버 응답의 `alert_mode` 값에 따라 Android가 음성·무음을 선택해요.

```kotlin
when (alertMode) {
    "critical" -> { tts.setSpeechRate(1.25f); speak(sentence) }  // 즉각 경고
    "beep"     -> { /* 비프음 제거 — 일반 속도 음성으로 대체 */ speak(sentence) }
    "silent"   -> { /* 무음 — UI만 업데이트 */ }
}
```

### OCR — 텍스트 읽기 (신규)

"글자 읽어줘" 라고 말하면 카메라로 찍어서 ML Kit이 텍스트를 읽어요.

```kotlin
// ML Kit TextRecognition (한국어 지원)
val recognizer = TextRecognition.getClient(KoreanTextRecognizerOptions)
recognizer.process(image).addOnSuccessListener { result ->
    speak(result.text)  // 읽은 텍스트를 TTS로 말해줌
}
```

### 바코드 스캔 (신규)

"바코드" 라고 말하면 상품 바코드를 읽어서 이름을 알려줘요.

```kotlin
val scanner = BarcodeScanning.getClient()
scanner.process(image).addOnSuccessListener { barcodes ->
    speak("${barcodes[0].displayValue}이에요.")
}
```

### STT 모드 분류

```kotlin
private fun classifyKeyword(text: String): String {
    for ((mode, keywords) in STT_KEYWORDS) {
        if (keywords.any { text.contains(it) }) return mode
    }
    return "장애물"  // 뭘 말해도 기본 장애물 모드 → 안내 누락 없음
}
```

현재 11가지 모드:
`장애물 / 찾기 / 확인 / 저장 / 위치목록 / 텍스트 / 바코드 / 색상 / 밝기 / 신호등 / 확인`

---

## 7. 자주 묻는 질문

**Q. 거리가 정확해요?**
카메라 하나로 정확한 거리 측정은 어려워요 (강사님도 지적).
Depth V2가 상대적 깊이를 추정하는 거라 오차가 있어요.
그래서 "약 1.2미터" 대신 "가까이", "조금 멀리" 같은 상대 표현으로 바꿨어요.

**Q. 왜 최대 2~3개 물체만 안내해요?**
"의자, 가방, 사람, 테이블이 있어요" 처럼 다 읽어주면 오히려 혼란스러워요.
가장 위험한 것 위주로 골라서 짧게 안내하는 게 더 안전해요.

**Q. 신호등 색깔 판별이 항상 맞아요?**
HSV 색상 분석 기반이라 조명 조건에 따라 오탐이 있을 수 있어요.
낮/밤, 역광 등에서 정확도 차이가 있을 수 있어요.

**Q. OCR이 한국어도 돼요?**
네, ML Kit의 `text-recognition-korean` 라이브러리 사용해서 한국어 지원해요.

**Q. 서버 없이도 OCR/바코드 돼요?**
네, ML Kit은 온디바이스(폰 단독)로 동작해요. 인터넷 불필요.

**Q. 점자 블록을 어떻게 찾아요?**
현재는 보행 경로 영역(이미지 하단 중앙)에 바닥 물체가 있으면 경고해요.
점자 블록 자체를 찾는 게 아니라 경로 위 장애물을 찾는 방식이에요.
정확한 점자 블록 감지는 별도 파인튜닝 필요.
