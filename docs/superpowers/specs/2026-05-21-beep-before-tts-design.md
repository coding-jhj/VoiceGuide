# 설계: 위험물 탐지 시 비프+진동 선행 후 TTS 알림

**날짜:** 2026-05-21  
**상태:** 승인됨  
**범위:** Android 앱 (`MainActivity.kt`)

---

## 목적

경고 피로(alert fatigue)를 줄이기 위해, `critical` 위험 탐지 시 즉각적인 음성(TTS) 대신
비프음+진동으로 먼저 주의를 환기한 뒤 500ms 후 TTS 안내를 재생한다.

---

## 현재 동작

```
performVibrationFeedback()  ──►  handleSuccess()  ──►  speak()   [사실상 동시]
```

- `critical` alert_mode → 진동 + TTS 거의 동시 발생
- 사용자가 경고를 들을 준비 없이 TTS가 시작되어 내용 파악이 어려움

---

## 변경 후 동작

```
performVibrationFeedback()          (즉시)
ToneGenerator.startTone(150ms)      (즉시)
      ↓  500ms postDelayed
speak(sentence)                     (500ms 후)
```

- `critical` 모드만 적용 (beep·normal·silent 모드는 기존 유지)
- 비프음: Android `ToneGenerator(STREAM_NOTIFICATION, 80)` + `TONE_PROP_BEEP` 150ms
- 딜레이: 500ms (`Handler(Looper.getMainLooper()).postDelayed`)

---

## 변경 파일

`android/app/src/main/java/com/voiceguide/MainActivity.kt` 단일 파일

---

## 구체 변경 내용

### 1. ToneGenerator 멤버 변수

```kotlin
private var toneGen: ToneGenerator? = null
```

### 2. onCreate — 초기화

```kotlin
toneGen = ToneGenerator(AudioManager.STREAM_NOTIFICATION, 80)
```

### 3. onDestroy — 해제

```kotlin
toneGen?.release()
toneGen = null
```

### 4. handleSuccess — critical 블록 수정

**변경 전:**
```kotlin
"critical" -> {
    val now = System.currentTimeMillis()
    if (forceSpeak || sentence != lastSentence || now - lastCriticalTime > 8000L) {
        val isVehicleDanger = VoicePolicy.voteBypassKo().any { sentence.contains(it) }
        if (!forceSpeak && !isVehicleDanger && isSpeaking()) return@runOnUiThread
        lastSentence     = sentence
        lastCriticalTime = now
        pendingStatusText = sentence
        tts.setSpeechRate(1.0f)
        if (forceSpeak || isVehicleDanger) speakBuiltIn(sentence, immediate = true)
        else speak(sentence)
    }
}
```

**변경 후:**
```kotlin
"critical" -> {
    val now = System.currentTimeMillis()
    if (forceSpeak || sentence != lastSentence || now - lastCriticalTime > 8000L) {
        val isVehicleDanger = VoicePolicy.voteBypassKo().any { sentence.contains(it) }
        if (!forceSpeak && !isVehicleDanger && isSpeaking()) return@runOnUiThread
        lastSentence     = sentence
        lastCriticalTime = now
        pendingStatusText = sentence
        tts.setSpeechRate(1.0f)
        // 1) 비프음 + 진동 즉시
        toneGen?.startTone(ToneGenerator.TONE_PROP_BEEP, 150)
        // 2) 500ms 후 TTS
        Handler(Looper.getMainLooper()).postDelayed({
            if (!isAnalyzing.get() && !forceSpeak) return@postDelayed
            if (forceSpeak || isVehicleDanger) speakBuiltIn(sentence, immediate = true)
            else speak(sentence)
        }, 500L)
    }
}
```

---

## 엣지 케이스

| 상황 | 처리 방식 |
|------|-----------|
| 500ms 내 새 critical 탐지 | `lastSentence` 비교로 중복 차단 (기존 쿨다운 로직 유지) |
| 500ms 내 분석 중지 | postDelayed 콜백에서 `isAnalyzing` + `forceSpeak` 체크 |
| `forceSpeak=true` (들고있는것 모드) | 동일하게 500ms 딜레이 적용, `isAnalyzing` 체크 건너뜀 |
| ToneGenerator 초기화 실패 / null | null-safe `?.`로 비프 건너뜀, TTS는 정상 실행 |
| STT 활성 중 (`isListening`) | 기존 `speak()` 내부 STT 체크 로직이 그대로 동작 |

---

## 미변경 사항

- `beep` / `normal` / `silent` alert 모드 동작 그대로
- `performVibrationFeedback()` 호출 시점 그대로 (sendDetectionJsonToServer 전)
- 서버 프로토콜 (`alert_mode` 필드) 변경 없음
- 쿨다운 (`lastCriticalTime` 8초, `speakCooldownUntil` 700ms) 변경 없음

---

## 테스트 기준

- [ ] critical 탐지 시 비프음이 TTS보다 먼저 들림
- [ ] 비프음과 TTS 사이 체감 딜레이 약 0.5초
- [ ] 500ms 내 분석 중지 시 TTS 재생되지 않음
- [ ] beep/normal/silent 모드는 기존과 동일하게 동작
- [ ] ToneGenerator null 상태에서도 TTS 정상 재생
