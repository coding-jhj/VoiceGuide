# 바운딩박스 불일치 원인 및 해결 기록

> 언제: 2026-04-28 세션  
> 증상: 바운딩박스가 실제 물체 위치와 어긋나게 표시됨

---

## 문제 상황

카메라 화면에 바운딩박스가 표시되는데, 실제 물체 위치보다 **위쪽 또는 왼쪽으로 치우쳐** 그려짐.
예) 의자가 오른쪽 아래에 있는데 박스는 화면 중앙에 그려짐.

---

## 원인 — 좌표 공간이 두 번 어긋남

바운딩박스를 화면에 그리려면 **세 가지 좌표 공간**을 거쳐야 하는데,
이 중 두 군데서 변환 오류가 있었음.

```
[1단계] 원본 카메라 이미지  (예: 1280×960)
        ↓  letterbox 변환 (YOLO 입력용)
[2단계] 640×640 letterbox 이미지  ← YOLO가 여기서 추론
        ↓  좌표 역변환 필요 ← ❌ 버그1: 패딩 미처리
[3단계] 원본 이미지 기준 정규화 좌표 (0.0~1.0)
        ↓  FILL_CENTER 디스플레이 변환 필요 ← ❌ 버그2: 잘림 미처리
[4단계] PreviewView 화면 픽셀  ← 여기다 박스를 그려야 함
```

---

## 버그 1: Letterbox 패딩 미처리

### 원인

YOLO는 입력 이미지를 항상 **640×640** 정사각형으로 받음.
원본 이미지(예: 1280×960)는 비율을 유지하면서 640에 맞추면 640×480이 됨.
나머지 위아래 80픽셀은 검정 패딩(letterbox)으로 채움.

```
┌─────────────────────┐ ← 640px
│  검정 패딩 (40px)    │
├─────────────────────┤
│                     │
│   실제 이미지 480px  │
│                     │
├─────────────────────┤
│  검정 패딩 (40px)    │
└─────────────────────┘ ← 640px
```

YOLO가 반환하는 좌표는 이 **640×640 letterbox 공간** 기준.
패딩 40px를 빼지 않으면 좌표가 위로 40px 어긋남.

### 수정 코드 (`YoloDetector.kt`)

```kotlin
// 1. 패딩 크기 계산
val scale  = minOf(640f / origW, 640f / origH)
val scaledW = (origW * scale).toInt()   // 640
val scaledH = (origH * scale).toInt()   // 480
val padX   = (640 - scaledW) / 2        // 0
val padY   = (640 - scaledH) / 2        // 40 ← 이걸 빼야 함

// 2. YOLO 출력 좌표 → 원본 이미지 좌표로 역변환
val cxPx = buf.get(0 * numDet + i)  // letterbox 640px 단위
val cyPx = buf.get(1 * numDet + i)

// 패딩 제거 후 0~1 정규화
val cx = (cxPx - padX) / scaledW   // ← padX 빼고 실제 이미지 폭으로 나눔
val cy = (cyPx - padY) / scaledH   // ← padY 빼고 실제 이미지 높이로 나눔
val w  = wPx / scaledW
val h  = hPx / scaledH

// 3. 패딩 영역(검정 바깥)에 중심이 있으면 무시
if (cx < 0f || cx > 1f || cy < 0f || cy > 1f) continue
```

---

## 버그 2: PreviewView FILL_CENTER 잘림 미처리

### 원인

Android `PreviewView`의 기본 ScaleType은 **FILL_CENTER**.
이미지를 뷰에 꽉 채우되 비율을 유지 → 이미지의 좌우 또는 상하가 잘림.

```
원본 이미지 (세로가 더 길면):
┌───────────┐
│  잘림 영역 │ ← 화면 밖으로 나감
├───────────┤  ← 뷰 상단
│           │
│  보이는    │
│  영역     │
│           │
├───────────┤  ← 뷰 하단
│  잘림 영역 │ ← 화면 밖으로 나감
└───────────┘
```

박스 좌표가 이미지 기준 (0,0)~(1,1)인데,
뷰는 이미지를 중앙 정렬 후 잘라서 보여줌 → **오프셋이 생김**.
이 오프셋을 반영하지 않으면 박스가 어긋남.

### 수정 코드 (`BoundingBoxOverlay.kt`)

```kotlin
override fun onDraw(canvas: Canvas) {
    val vw = width.toFloat()   // 뷰 너비
    val vh = height.toFloat()  // 뷰 높이

    // FILL_CENTER 변환 직접 계산
    val scaleX    = vw / imageWidth
    val scaleY    = vh / imageHeight
    val fillScale = maxOf(scaleX, scaleY)      // 더 큰 쪽으로 채움
    val displayW  = imageWidth  * fillScale    // 화면에 표시되는 이미지 너비
    val displayH  = imageHeight * fillScale    // 화면에 표시되는 이미지 높이
    val offsetX   = (vw - displayW) / 2f       // 음수 = 좌우 잘림
    val offsetY   = (vh - displayH) / 2f       // 음수 = 상하 잘림

    // [0,1] 정규화 좌표 → 뷰 픽셀 (FILL_CENTER 오프셋 포함)
    val left   = offsetX + (det.cx - det.w / 2f) * displayW
    val top    = offsetY + (det.cy - det.h / 2f) * displayH
    val right  = offsetX + (det.cx + det.w / 2f) * displayW
    val bottom = offsetY + (det.cy + det.h / 2f) * displayH

    canvas.drawRect(RectF(left, top, right, bottom), boxPaint)
}
```

---

## 보너스: 방향 흔들림으로 인한 TTS 무한반복 (같은 날 발견)

### 증상

```
21:19:53  "마우스는 오른쪽에 있어요."      cx=0.90
21:19:57  "마우스는 오른쪽 앞에 있어요."   cx=0.78  ← 방향 변경 → 재발화
21:20:00  "마우스는 바로 앞에 있어요."     cx=0.55  ← 또 변경 → 또 발화
          ... 23초간 반복 ...
```

cx 값이 프레임마다 조금씩 달라져 방향이 경계 근처에서 왔다 갔다 함.
`critical` 모드는 문장이 달라질 때마다 TTS 발화 → 무한 반복.

### 해결: 방향 Hysteresis (`SentenceBuilder.kt`)

```kotlin
// 방향 캐시 — 클래스별 마지막 안정 방향 저장
private val stableClock = mutableMapOf<String, String>()

// 이전 방향에서 2존(~22% 화면 폭) 이상 벗어나야 방향 갱신
private fun getStableClock(classKo: String, cx: Float): String {
    val newClock = getClock(cx)
    val prev = stableClock[classKo]
    if (prev == null || clockDistance(prev, newClock) >= 2) {
        stableClock[classKo] = newClock  // 충분히 이동했을 때만 갱신
    }
    return stableClock[classKo]!!
}
```

결과: cx가 조금 흔들려도 방향이 바뀌지 않아 TTS 무한반복 해결.

---

## 수정 결과 요약

| 버그 | 원인 | 파일 | 핵심 수정 |
|------|------|------|---------|
| 박스 위치 어긋남 (letterbox) | YOLO 640×640 패딩 미처리 | `YoloDetector.kt` | `(cxPx - padX) / scaledW` |
| 박스 위치 어긋남 (화면 잘림) | FILL_CENTER 오프셋 미처리 | `BoundingBoxOverlay.kt` | `offsetX = (vw - displayW) / 2f` |
| TTS 방향 무한반복 | cx 흔들림으로 방향 경계 진동 | `SentenceBuilder.kt` | 2존 이상 이동해야 방향 갱신 |

---

## 수정 전/후 비교

```
수정 전:
  [YOLO] 의자 cx=0.7, cy=0.8 (letterbox 640px 기준)
  [BoundingBox] → 그냥 0.7×뷰너비, 0.8×뷰높이 위치에 박스 → 어긋남

수정 후:
  [YOLO] 의자 cx=0.7, cy=0.8 (letterbox)
  → padY 제거: cy = (0.8×640 - 40) / 480 = 0.97 (원본 이미지 기준)
  [BoundingBox] → FILL_CENTER 오프셋 계산 → 실제 화면 픽셀 정확히 계산
  → 의자 위에 정확하게 박스 표시
```
