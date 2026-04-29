# VoiceGuide 버그 수정으로 배우는 코드 구조

> 2026-04-29 디버깅 세션에서 실제로 겪은 버그들을 통해  
> Android + FastAPI 전체 구조를 이해하는 학습 가이드입니다.  
> "왜 이 버그가 생겼는가" → "어디를 어떻게 고쳤는가" → "이 코드가 실제로 어떻게 동작하는가" 순서로 읽으세요.

---

## 목차

1. [TTS(음성)가 전혀 안 나오는 버그](#1-tts음성가-전혀-안-나오는-버그)
2. [분析 중지 버튼이 작동 안 하는 버그](#2-분석-중지-버튼이-작동-안-하는-버그)
3. [첫 감지가 느리고 바운딩박스가 늦게 바뀌는 버그](#3-첫-감지가-느리고-바운딩박스가-늦게-바뀌는-버그)
4. [바운딩박스가 물체 사라져도 유지되는 버그](#4-바운딩박스가-물체-사라져도-유지되는-버그)
5. [서버 첫 요청이 느리고 "분석 실패" 뜨는 버그](#5-서버-첫-요청이-느리고-분석-실패-뜨는-버그)
6. [핵심 개념 정리](#6-핵심-개념-정리)

---

## 1. TTS(음성)가 전혀 안 나오는 버그

### 증상
텍스트는 화면에 나오는데 소리가 안 남.

### 버그 A — speak() 라우팅 누락

**어디서 생겼나: `MainActivity.kt` `speak()` 함수**

```kotlin
// 버그 있는 코드
private fun speak(text: String) {
    if (isListening) { ... }
    speakBuiltIn(text)  // ← 항상 내장 TTS만 호출
}
```

`speakElevenLabs()`라는 함수가 구현되어 있었지만, `speak()`에서 호출하는 경로가 없었음.

**왜 문제가 됐나:**

`isSpeaking()` 함수를 보면:
```kotlin
private fun isSpeaking(): Boolean =
    if (etServerUrl.text.toString().trim().isNotEmpty()) isElevenLabsSpeaking
    else ttsBusy.get()
```

서버 URL이 입력되어 있으면 `isElevenLabsSpeaking`을 체크. 그런데 `speakElevenLabs()`가 호출되지 않으니 `isElevenLabsSpeaking`은 항상 `false`.

`handleSuccess()`에서:
```kotlin
else -> {
    if (sentence != lastSentence && !isSpeaking()) {  // isSpeaking()=false → 통과
        lastSentence  = sentence   // ← lastSentence 업데이트
        speak(sentence)            // ← speakBuiltIn() 호출
        // speakBuiltIn() 내부: ttsBusy.compareAndSet(false, true)
        // TTS 재생 중이면 → false → 말 버려짐
        // lastSentence는 이미 업데이트됐으니 다음 프레임에 같은 문장이 와도 재시도 안 함
    }
}
```

결과: TTS가 재생 중일 때 새 문장이 오면 `isSpeaking()`은 false인데 `speakBuiltIn()`의 `ttsBusy` 잠금은 true → 말이 조용히 버려짐. 그리고 `lastSentence`가 이미 업데이트됐으므로 같은 문장은 다시 시도 안 함.

**수정:**
```kotlin
private fun isSpeaking(): Boolean = ttsBusy.get() || isElevenLabsSpeaking
```
→ 어떤 경로로 TTS를 쓰든 항상 정확하게 "지금 말 중"인지 반영.

---

**버그 B — /tts 엔드포인트 HTTP 200 에러**

**어디서 생겼나: `src/api/routes.py` `/tts` 엔드포인트**

```python
# 버그 있는 코드
@router.post("/tts")
async def tts_endpoint(text: str = Form("")):
    from src.voice.tts import _api_key
    if not _api_key:
        return {"error": "ELEVENLABS_API_KEY not set"}  # ← HTTP 200으로 JSON 반환!
```

**왜 문제가 됐나:**

FastAPI에서 `return {"error": "..."}` 하면 HTTP 200 + JSON body로 나감.

Android에서:
```kotlin
if (!resp.isSuccessful) {  // HTTP 200이므로 이 조건 통과 못 함!
    speakBuiltIn(text)     // ← 폴백 실행 안 됨
    return@execute
}
val tmpFile = File(cacheDir, "tts_$myId.mp3")
tmpFile.writeBytes(resp.body!!.bytes())  // JSON을 .mp3로 저장
// MediaPlayer가 JSON 파일을 MP3로 재생 시도 → 실패 → Exception
```

**수정:**
```python
from fastapi.responses import JSONResponse
if not text:
    return JSONResponse({"error": "text is empty"}, status_code=400)  # 400 반환
```
→ 에러 시 4xx/5xx HTTP 코드 반환. Android의 `!resp.isSuccessful` 체크가 제대로 작동.

---

**버그 C — Gradio 데모 브라우저 무음**

**어디서 생겼나: `app.py`의 `speak()` 호출**

```python
speak(sentence)  # pygame으로 서버 머신 스피커에서 재생
```

Gradio를 브라우저로 접속하면 `speak()`는 서버가 있는 PC 스피커로 재생. 브라우저에는 소리 안 감.

**수정:**
```python
# 브라우저 재생용 MP3 생성해서 반환
audio_path = _cache_path(sentence)
if not os.path.exists(audio_path):
    _generate(sentence, audio_path)
return annotated, "\n".join(lines), audio_path  # gr.Audio로 출력

# Gradio outputs에 추가:
gr.Audio(label="음성 안내 듣기", autoplay=True)
```

---

### 배운 것: Android TTS 흐름

```
speak(text)
    │
    └─ speakBuiltIn(text)
            │
            ├─ ttsBusy.compareAndSet(false, true)
            │     false면: 이미 재생 중 → 버림
            │     true면: TTS 시작
            │
            └─ tts.speak(text, QUEUE_FLUSH, ...)
                    │
                    └─ onDone() 콜백 (재생 완료 시)
                            │
                            └─ 700ms 후 ttsBusy.set(false)  ← 잠금 해제
```

**핵심**: `ttsBusy`는 한 번에 하나의 TTS만 재생되도록 보장하는 잠금(mutex). 재생 완료 후 700ms를 더 기다리는 이유는 말이 끊겼다는 느낌 없이 자연스럽게 다음 말을 시작하기 위함.

---

## 2. 분析 중지 버튼이 작동 안 하는 버그

### 증상
"분석 중지" 버튼을 눌러도 계속 음성 안내가 나옴.

### 어디서 생겼나

**`stopAnalysis()` 함수:**
```kotlin
private fun stopAnalysis() {
    isAnalyzing.set(false)
    handler.removeCallbacksAndMessages(null)  // Handler 작업만 취소
    ...
}
```

`handler.removeCallbacksAndMessages(null)`: `Handler`에 예약된 작업들은 취소됨. 하지만 백그라운드 `Thread`는 취소되지 않음.

**문제의 흐름:**
```
captureAndProcess()
    │
    └─ Thread { sendToServer(imageFile) }.start()
           │
           │  ← 이 Thread는 중지 버튼 눌러도 계속 실행됨
           │
           ▼
      handleSuccess(sentence, alertMode)
           │
           └─ runOnUiThread { speak(sentence) }  ← 중지 후에도 음성 나옴!
```

**왜 `handler.removeCallbacksAndMessages`로 Thread를 못 막나:**

Handler와 Thread는 다른 개념.
- `Handler`: 메인 스레드의 메시지 큐. `postDelayed`, `post`로 예약한 작업들.
- `Thread`: 독립 실행 중인 스레드. 한번 시작하면 `interrupt()` 또는 종료 조건으로만 멈춤.

`sendToServer()`는 `Thread { ... }.start()`로 실행 → Handler로 취소 불가.

**수정:**
```kotlin
private fun handleSuccess(sentence: String, alertMode: String = "critical") {
    ...
    isSending.set(false)
    if (!isAnalyzing.get()) return  // ← 이 한 줄이 핵심
    ...
}
```

Thread가 완료됐을 때 `isAnalyzing`이 false이면 아무것도 하지 않고 종료.

---

### 배운 것: Android의 Handler vs Thread

| | Handler | Thread |
|--|---------|--------|
| 실행 방식 | 메인 스레드 메시지 큐 | 독립 스레드 |
| 예약 | `postDelayed(runnable, ms)` | `Thread { ... }.start()` |
| 취소 | `removeCallbacksAndMessages(null)` | `interrupt()` 또는 플래그 |
| 용도 | UI 업데이트, 타이머 | 네트워크, 파일 I/O |

VoiceGuide에서:
- `scheduleNext()`, `scheduleWatchdog()` → Handler (취소 가능)
- `sendToServer()`, `processOnDevice()` → Thread (플래그로 제어)

---

## 3. 첫 감지가 느리고 바운딩박스가 늦게 바뀌는 버그

### 증상
- 앱 시작 후 첫 장애물 안내까지 1~2초 걸림
- 다른 물체로 카메라를 옮겨도 반응이 늦음

### 원인 1: detectionHistory 미초기화

**`startAnalysis()` 함수:**
```kotlin
private fun startAnalysis() {
    isAnalyzing.set(true)
    SentenceBuilder.clearStableClocks()
    lastSentence = ""
    // detectionHistory.clear() ← 이게 없었음!
    ...
}
```

`detectionHistory`는 최근 3프레임의 탐지 결과를 기억하는 버퍼. 앱을 껐다 켜거나 중지 후 재시작해도 이전 데이터가 남아있음 → 투표 결과가 이상하게 나옴.

### 원인 2: VOTE_MIN_COUNT = 2

**투표(Voting) 버퍼가 어떻게 동작하는지:**

```kotlin
private val VOTE_WINDOW    = 3   // 최근 3프레임 기억
private val VOTE_MIN_COUNT = 2   // 2프레임 이상 감지돼야 통과

private fun voteOnly(detections: List<Detection>): List<Detection> {
    detectionHistory.addLast(currentClasses)
    if (detectionHistory.size > VOTE_WINDOW) detectionHistory.removeFirst()
    
    val counts = mutableMapOf<String, Int>()
    for (frame in detectionHistory) frame.forEach { counts[it] = (counts[it] ?: 0) + 1 }
    
    return detections.filter { d ->
        d.classKo in ALWAYS_PASS || (counts[d.classKo] ?: 0) >= VOTE_MIN_COUNT
    }
}
```

`VOTE_MIN_COUNT = 2`이면:
- 프레임 1: history=[{의자}], count={의자:1}, 1 < 2 → 탈락
- 프레임 2: history=[{의자},{의자}], count={의자:2}, 2 >= 2 → **통과**

ONNX 추론 한 프레임에 ~200ms라면, 첫 안내까지 최소 400ms 대기.

**왜 투표 버퍼가 필요한가:**
YOLO는 매 프레임마다 약간씩 다른 결과를 냄. 잠깐 손이 카메라에 걸렸을 때 "핸드백이 있어요"처럼 오탐이 한 번 발생할 수 있음. 투표 버퍼는 이런 일시적 오탐을 걸러냄.

**수정:**
```kotlin
private val VOTE_MIN_COUNT = 1  // 1프레임만 감지돼도 즉시 통과

private fun startAnalysis() {
    ...
    detectionHistory.clear()  // 재시작 시 이전 데이터 초기화
    ...
}
```

트레이드오프: 오탐이 약간 늘 수 있지만, 시각장애인 보조 앱에서 빠른 반응이 더 중요.

---

### 배운 것: 투표 버퍼 설계 철학

```
정밀도 중시    ←————————→    속도 중시
VOTE_MIN_COUNT=3         VOTE_MIN_COUNT=1
(3프레임 모두 감지)       (1프레임만 감지)
오탐 거의 없음            오탐 가끔 있음
첫 감지 느림(600ms)      첫 감지 빠름(200ms)
```

위험한 물체(차량, 칼 등)는 `ALWAYS_PASS`에 등록해서 투표 없이 즉시 통과.

---

## 4. 바운딩박스가 물체 사라져도 유지되는 버그

### 증상
카메라를 다른 곳으로 돌려도 이전에 있던 물체의 바운딩박스가 화면에 남아있음.

### 어디서 생겼나

**`processOnDevice()` (온디바이스 모드):**
```kotlin
runOnUiThread {
    if (voted.isEmpty()) {
        boundingBoxOverlay.clearDetections()  // ← 있음
    } else {
        boundingBoxOverlay.setDetections(voted, imgW, imgH)  // ← 있음
    }
}
```

온디바이스 모드는 탐지 결과가 나올 때마다 박스 업데이트.

**`sendToServer()` (서버 모드):**
```kotlin
val json = JSONObject(response.body?.string() ?: "{}")
val sentence = json.optString("sentence", "주변에 장애물이 없어요.")
val alertMode = json.optString("alert_mode", "critical")
// ← boundingBoxOverlay 업데이트 코드가 완전히 없었음!
handleSuccess(sentence, alertMode)
```

서버 응답에는 `objects` 배열이 포함되어 있는데, Android 코드에서 이를 무시하고 있었음.

### 왜 놓쳤나

온디바이스 모드(`processOnDevice`)와 서버 모드(`sendToServer`)가 별도 함수로 구현되어 있어서, 온디바이스에 추가한 코드가 서버 모드에는 자동으로 적용되지 않았음.

### 수정

서버 응답의 `objects` 배열을 파싱해서 `Detection` 객체로 변환 후 박스 업데이트:

```kotlin
val serverObjs = json.optJSONArray("objects")
val detections = mutableListOf<Detection>()
if (serverObjs != null && sentImgW > 0 && sentImgH > 0) {
    for (i in 0 until serverObjs.length()) {
        val obj  = serverObjs.getJSONObject(i)
        val bbox = obj.optJSONArray("bbox") ?: continue  // [x1, y1, x2, y2] 픽셀 좌표
        val x1 = bbox.optDouble(0).toFloat()
        val y1 = bbox.optDouble(1).toFloat()
        val x2 = bbox.optDouble(2).toFloat()
        val y2 = bbox.optDouble(3).toFloat()
        detections.add(Detection(
            classKo    = obj.optString("class_ko", "물체"),
            confidence = obj.optDouble("conf", 0.5).toFloat(),
            cx = ((x1 + x2) / 2f) / sentImgW,  // 픽셀 → 정규화 좌표(0~1)
            cy = ((y1 + y2) / 2f) / sentImgH,
            w  = (x2 - x1) / sentImgW,
            h  = (y2 - y1) / sentImgH
        ))
    }
}
runOnUiThread {
    if (detections.isEmpty()) boundingBoxOverlay.clearDetections()
    else boundingBoxOverlay.setDetections(detections, sentImgW, sentImgH)
}
```

### 좌표 변환이 왜 필요한가

서버는 픽셀 좌표로 반환 (`bbox: [120, 80, 400, 350]` — 이미지 640×480 기준).  
`BoundingBoxOverlay`는 정규화 좌표 (0.0~1.0) 사용.

```
픽셀 좌표 → 정규화 좌표
cx = (x1 + x2) / 2 / imgWidth     중심 x ÷ 이미지 너비
cy = (y1 + y2) / 2 / imgHeight    중심 y ÷ 이미지 높이
w  = (x2 - x1) / imgWidth         박스 너비 ÷ 이미지 너비
h  = (y2 - y1) / imgHeight        박스 높이 ÷ 이미지 높이
```

정규화 좌표를 쓰는 이유: 화면 크기가 달라도 같은 좌표 체계로 박스를 그릴 수 있음.

---

## 5. 서버 첫 요청이 느리고 "분析 실패" 뜨는 버그

### 증상
서버 시작 직후 첫 요청이 10~30초 걸리고 Android에서 "분析 실패 — 주의하세요"가 나옴.

### 왜 생겼나

**`src/api/main.py` lifespan:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    # YOLO 워밍업
    from src.vision.detect import model, CONF_THRESHOLD
    model(np.zeros((640, 640, 3)), conf=CONF_THRESHOLD, verbose=False)
    # ← Depth V2 워밍업 없었음!
    yield
```

서버 시작 시 YOLO는 워밍업하지만 Depth V2는 첫 요청이 올 때 비로소 로드.

**`src/depth/depth.py`의 싱글톤 패턴:**
```python
_depth_model = None  # 전역 변수

def _load_model():
    global _depth_model
    if _depth_model is not None:
        return _depth_model  # 이미 로드됨 → 즉시 반환
    
    # 처음 호출 시 모델 파일 로드 (100MB+, 10~30초 소요)
    m = DepthAnythingV2(encoder="vits", ...)
    state = torch.load(_MODEL_PATH, map_location=_DEVICE)
    m.load_state_dict(state)
    m.to(_DEVICE).eval()
    _depth_model = m
    return _depth_model
```

Depth V2 모델은 100MB+ 파일. 처음 로드할 때 10~30초. Android의 `readTimeout=8s`보다 훨씬 김 → timeout 발생.

**수정:**
```python
# lifespan에 추가
from src.depth.depth import _load_model
_load_model()  # 서버 시작 시 미리 로드 (요청 받기 전에 완료)
```

Android timeout도 증가:
```kotlin
private val httpClient = OkHttpClient.Builder()
    .connectTimeout(10, TimeUnit.SECONDS)  // 5 → 10
    .readTimeout(20, TimeUnit.SECONDS)     // 8 → 20
    .build()
```

### 배운 것: 싱글톤 + 지연 로딩(Lazy Loading) 패턴

```python
_model = None  # 처음엔 없음

def get_model():
    global _model
    if _model is None:        # 처음 호출 시만
        _model = load_big_model()  # 무거운 작업
    return _model             # 이후엔 즉시 반환
```

장점: 사용 안 하면 메모리 낭비 없음.  
단점: 첫 호출이 느림.  
해결: 서버 시작 시 미리 호출해서 "첫 호출 느림"을 제거.

---

## 6. 핵심 개념 정리

### isSending 플래그 — 프레임 중복 방지

```
captureAndProcess()
    │
    │ isSending=false일 때만 진행
    │
    ├─ isSending.set(true)   ← 프레임 처리 시작
    │
    ├─ processOnDevice() 또는 sendToServer()
    │
    └─ handleSuccess() 또는 handleFail()
            │
            └─ isSending.set(false)  ← 다음 프레임 허용
```

`isSending`이 `true`인 동안 `scheduleNext()`의 100ms 타이머는 계속 불리지만 `captureAndProcess()`가 즉시 return. 이전 프레임이 끝나야 다음 프레임 시작.

### 서버 응답 구조

```json
{
  "sentence": "왼쪽 앞에 의자가 있어요. 오른쪽으로 피하세요.",
  "alert_mode": "critical",
  "objects": [
    {
      "class_ko": "의자",
      "conf": 0.87,
      "bbox": [120, 80, 400, 350],
      "distance_m": 1.5,
      "risk_score": 0.72
    }
  ],
  "hazards": [],
  "process_ms": 243
}
```

- `sentence`: Android TTS로 읽을 문장
- `alert_mode`: `critical`(즉시 안내) / `silent`(UI만 업데이트) / `beep`(비프음)
- `objects`: 탐지된 물체 목록. bbox는 전송한 이미지 기준 픽셀 좌표
- `process_ms`: 서버 내부 처리 시간 (네트워크 시간 제외)

### FPS와 성능의 관계

```
실제 FPS = 1000ms ÷ 프레임 완료 시간

온디바이스 (YOLO11n + NNAPI):
  추론 ~100ms → FPS ≈ 1000/100 = 10fps

서버 모드 (로컬 WiFi):
  서버 처리 200ms + 네트워크 100ms = 300ms → FPS ≈ 3fps

서버 모드 (클라우드):
  서버 처리 500ms + 네트워크 500ms = 1000ms → FPS ≈ 1fps
```

시각장애인 보행 보조에는 최소 5fps 필요. 클라우드 서버 단독 사용은 부적합.

### 디버깅할 때 이 순서로

1. **Logcat 태그 필터**: `VG_DETECT`로 필터 → 프레임마다 탐지 결과 확인
2. **FPS 확인**: tvMode에 표시되는 `Xfps` 값 → 5 미만이면 느린 것
3. **서버 로그 확인**: Depth V2 로드 메시지, YOLO 초기화 메시지
4. **`/health` 엔드포인트**: `curl http://서버IP:8000/health` → `depth_v2: loaded` 확인
5. **소리 문제**: Android 설정 → 텍스트 음성 변환 → 한국어 설치 확인

---

## 오늘 수정한 파일 목록

| 파일 | 수정 내용 |
|------|---------|
| `MainActivity.kt` | `isSpeaking()` 수정, `handleSuccess()` isAnalyzing 체크, `detectionHistory.clear()`, `VOTE_MIN_COUNT` 2→1, `sendToServer()` 바운딩박스 갱신, `isSending` 안전망 |
| `src/api/routes.py` | `/tts` 엔드포인트 API 키 체크 제거, HTTP 400/500 반환 |
| `src/api/main.py` | Depth V2 `_load_model()` 워밍업 추가 |
| `app.py` | `gr.Audio(autoplay=True)` 출력 추가 |
