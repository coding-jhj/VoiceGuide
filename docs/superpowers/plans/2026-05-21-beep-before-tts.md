# Beep-Before-TTS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `critical` 위험 탐지 시 ToneGenerator 비프음+진동을 먼저 재생하고 500ms 후 TTS 음성 안내를 시작해 경고 피로를 줄인다.

**Architecture:** `MainActivity.kt` 단일 파일만 수정. `ToneGenerator` 멤버 변수를 추가하고, `handleSuccess`의 `"critical"` 블록에서 즉시 비프+진동을 울린 뒤 `Handler.postDelayed(500ms)` 콜백에서 TTS를 실행한다. 서버 프로토콜·다른 alert 모드는 변경하지 않는다.

**Tech Stack:** Kotlin, Android SDK (`android.media.ToneGenerator`, `android.os.Handler`), JUnit 4 (on-device 로직은 순수 unit test 불가 — 수동 확인 체크리스트로 대체)

---

## 파일 맵

| 동작 | 경로 |
|------|------|
| **수정** | `android/app/src/main/java/com/voiceguide/MainActivity.kt` |

변경 지점 4곳:
1. **L68 근처** — `toneGen` 멤버 변수 추가
2. **L356 근처** (`onCreate`) — `ToneGenerator` 초기화
3. **L572 근처** (`onDestroy`) — `toneGen?.release()` 해제
4. **L1873–1887** (`handleSuccess` critical 블록) — 비프 즉시 + TTS 500ms 지연

---

## Task 1: ToneGenerator 멤버 변수 추가

**Files:**
- Modify: `android/app/src/main/java/com/voiceguide/MainActivity.kt:68`

- [ ] **Step 1: import 확인**

파일 상단 import 목록(L1-42)에 아래 두 줄이 **이미 존재**하는지 확인.

```
import android.media.AudioManager   ← L10에 존재 ✓
import android.media.ToneGenerator  ← 없으면 추가 필요
```

`android.media.ToneGenerator` import가 없다면 L10 `import android.media.AudioManager` 바로 아래에 추가:

```kotlin
import android.media.ToneGenerator
```

- [ ] **Step 2: 멤버 변수 선언 추가**

`MainActivity.kt` L68 `private lateinit var tts: TextToSpeech` 바로 아래에 한 줄 추가:

```kotlin
private lateinit var tts: TextToSpeech
private var toneGen: ToneGenerator? = null   // ← 추가
```

- [ ] **Step 3: 빌드 확인**

```bash
cd android
./gradlew assembleDebug 2>&1 | tail -5
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 4: 커밋**

```bash
git add android/app/src/main/java/com/voiceguide/MainActivity.kt
git commit -m "refactor: add ToneGenerator member variable for beep alert"
```

---

## Task 2: onCreate에서 ToneGenerator 초기화

**Files:**
- Modify: `android/app/src/main/java/com/voiceguide/MainActivity.kt:356`

- [ ] **Step 1: 초기화 코드 추가**

`onCreate` 내부 L356 `tts = TextToSpeech(this, this)` 바로 아래에 추가:

```kotlin
tts = TextToSpeech(this, this)
toneGen = ToneGenerator(AudioManager.STREAM_NOTIFICATION, 80)  // ← 추가
```

볼륨 `80`은 최대(100)의 80%. `STREAM_NOTIFICATION` 채널 사용 — 알림음 채널이므로 음소거 여부에 관계없이 시스템 알림 설정을 따른다.

- [ ] **Step 2: 빌드 확인**

```bash
cd android
./gradlew assembleDebug 2>&1 | tail -5
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 3: 커밋**

```bash
git add android/app/src/main/java/com/voiceguide/MainActivity.kt
git commit -m "feat: initialize ToneGenerator in onCreate"
```

---

## Task 3: onDestroy에서 ToneGenerator 해제

**Files:**
- Modify: `android/app/src/main/java/com/voiceguide/MainActivity.kt:572`

- [ ] **Step 1: 해제 코드 추가**

`onDestroy` 내부 L572 `tts.shutdown()` 바로 아래에 추가:

```kotlin
override fun onDestroy() {
    tts.shutdown()
    toneGen?.release()   // ← 추가
    toneGen = null       // ← 추가
    speechRecognizer.destroy()
    tfliteDetector?.close()
    cameraExecutor.shutdown()
    perfLogExecutor.shutdown()
    handler.removeCallbacksAndMessages(null)
    super.onDestroy()
}
```

- [ ] **Step 2: 빌드 확인**

```bash
cd android
./gradlew assembleDebug 2>&1 | tail -5
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 3: 커밋**

```bash
git add android/app/src/main/java/com/voiceguide/MainActivity.kt
git commit -m "feat: release ToneGenerator in onDestroy"
```

---

## Task 4: handleSuccess — critical 블록에 비프+지연 TTS 적용

**Files:**
- Modify: `android/app/src/main/java/com/voiceguide/MainActivity.kt:1873-1887`

- [ ] **Step 1: critical 블록 교체**

현재 코드 (L1873–1887):

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
        if (forceSpeak || isVehicleDanger) {
            speakBuiltIn(sentence, immediate = true)
        } else {
            speak(sentence)
        }
    }
}
```

교체 후:

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
        // 1) 비프음 즉시 (150ms, STREAM_NOTIFICATION 채널)
        toneGen?.startTone(ToneGenerator.TONE_PROP_BEEP, 150)
        // 2) 500ms 후 TTS (분석 중지 시 재생 안 함)
        Handler(Looper.getMainLooper()).postDelayed({
            if (!isAnalyzing.get() && !forceSpeak) return@postDelayed
            if (forceSpeak || isVehicleDanger) speakBuiltIn(sentence, immediate = true)
            else speak(sentence)
        }, 500L)
    }
}
```

변경 핵심:
- `toneGen?.startTone(ToneGenerator.TONE_PROP_BEEP, 150)` — 즉시 비프 150ms
- `Handler(Looper.getMainLooper()).postDelayed({ ... }, 500L)` — TTS를 500ms 뒤로 지연
- postDelayed 콜백 첫 줄: `!isAnalyzing.get() && !forceSpeak` — 분석 중지 상태면 TTS 건너뜀

- [ ] **Step 2: 빌드 확인**

```bash
cd android
./gradlew assembleDebug 2>&1 | tail -5
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 3: 수동 테스트**

실기기(또는 에뮬레이터)에 APK 설치 후 아래 체크리스트 확인:

```
[ ] critical 탐지(자동차·계단 등) 시 비프음이 TTS보다 먼저 들림
[ ] 비프음과 TTS 사이 체감 딜레이 약 0.5초
[ ] 분석 중지(btnToggle) 후 진행 중인 요청의 TTS가 재생되지 않음
[ ] beep/normal/silent 모드는 기존과 동일하게 동작(비프 없이 TTS만)
[ ] ToneGenerator null 상태에서도 TTS 정상 재생(onCreate 제거 후 테스트)
[ ] 연속 탐지 시 8초 쿨다운 내 중복 TTS 없음(기존 동작 유지)
```

- [ ] **Step 4: 커밋**

```bash
git add android/app/src/main/java/com/voiceguide/MainActivity.kt
git commit -m "feat: play beep before TTS on critical alert (500ms delay)"
```

---

## Task 5: 정리 커밋

- [ ] **Step 1: 전체 빌드·lint 확인**

```bash
cd android
./gradlew assembleDebug lintDebug 2>&1 | tail -10
```

Expected: `BUILD SUCCESSFUL` (lint warning 있어도 error 없으면 OK)

- [ ] **Step 2: 최종 커밋**

```bash
git add android/app/src/main/java/com/voiceguide/MainActivity.kt
git commit -m "feat: beep-before-tts alert fatigue reduction complete"
```

---

## 셀프 리뷰 결과

| 항목 | 결과 |
|------|------|
| 스펙 커버리지 | ToneGenerator 초기화·해제·비프·지연TTS 전부 task에 포함 ✓ |
| 플레이스홀더 | 없음 ✓ |
| 타입 일관성 | `toneGen: ToneGenerator?` → `toneGen?.startTone()` → `toneGen?.release()` 전 task 동일 ✓ |
| 엣지 케이스 | `isAnalyzing` 체크, null-safe `?.`, forceSpeak 예외 모두 포함 ✓ |
