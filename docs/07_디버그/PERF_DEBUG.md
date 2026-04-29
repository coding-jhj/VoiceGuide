# VoiceGuide 추론속도 / FPS 디버깅 가이드

> 실제 보행 테스트에서 2346ms / 2.2fps가 관측됐을 때  
> 원인을 찾고 개선하는 방법을 단계별로 정리합니다.

---

## 1. 왜 300ms / 10fps가 목표인가 — 보행 물리학 근거

"빠를수록 좋다"가 아닌, **보행 안전에 필요한 최소 기준**을 역산한 수치입니다.

| 항목 | 수치 |
|------|------|
| 일반 보행 속도 | 1.2~1.5 m/s |
| 위험 감지 후 정지까지 | ~0.5~1초 (반응 + 감속) |
| 1초 동안 이동 거리 | ~1.5m |
| TTS 음성 출력까지 | ~100~200ms |

시스템 지연이 1초이면, 경고가 나올 때 이미 0.5~1m 더 전진한 상태입니다.

### FPS별 실용 등급 (투표 버퍼 VOTE_WINDOW=3 기준)

| FPS | 추론 시간 | 투표 3프레임 대기 | TTS 포함 총 지연 | 평가 |
|-----|---------|----------------|----------------|------|
| <3fps | >400ms | >1200ms | ~2초 | **위험 — 보행 불적합** |
| 3~5fps | 200~400ms | 600~1200ms | ~1.2초 | 경계선 |
| 5fps | ~200ms | ~600ms | ~0.9초 | **실용 최소선** (실내 천천히) |
| 10fps | ~100ms | ~300ms | ~0.5초 | 쾌적 (실외 보행) |
| 15fps | ~67ms | ~200ms | ~0.4초 | 이상적 |

**목표: 추론 300ms 이내, FPS 10+**

### 환경별 예상 성능

| 환경 | 예상 FPS | 평가 |
|------|---------|------|
| YOLO11n + NNAPI | 8~15fps | 쾌적 |
| YOLO11n + CPU만 | 3~6fps | 실용권 |
| YOLO11m + NNAPI | 4~8fps | 실용권 |
| YOLO11m + CPU만 | 1~3fps | 위험 영역 |
| 서버 모드 (로컬 WiFi, GPU) | 5~10fps | 실용권 |
| 서버 모드 (로컬 WiFi, CPU) | 1~3fps | 보행 불적합 |
| 서버 모드 (클라우드) | 1~3fps | 보행 불적합 |

---

## 2. 디버그 오버레이 읽는 법 (앱 화면)

앱 상단 `tvMode`에 표시되는 값:

```
[장애물] 2.2fps ▄▃▅▄▃▅ | 서버:243ms
```

**서버 모드:**
```
FPS      : 2.2          ← ① 5 이상인지 확인
서버처리  : 243ms        ← ② 서버가 YOLO+Depth 처리한 시간
네트워크 : (왕복-서버)ms ← ③ 이미지 업로드+응답 수신 시간
총왕복   : 2346ms       ← ④ 가장 중요 — 300ms 이하 목표
```

**온디바이스 모드:**
```
FPS    : X            ← ① 5 이상인지
YOLO   : XXms         ← ② 200ms 이하인지 (온디바이스)
전체   : XXXms        ← ③ 300ms 이하인지 — 가장 중요
탐지수 : raw=N → M   ← ④ 필터 후 줄어드는 게 정상
```

`서버처리`와 `네트워크`를 비교하면 **병목이 서버인지 WiFi인지** 즉시 알 수 있습니다.

---

## 3. 디버깅 방법 3가지

### 방법 A — 앱 화면 오버레이 (즉시, 케이블 불필요)

앱 하단 tvMode 텍스트를 **길게 누르면** 디버그 수치 표시 전환.  
서버처리 ms와 네트워크 ms를 비교해 병목 식별.

---

### 방법 B — WiFi ADB Logcat (USB 없이 실시간 로그)

USB 한 번만 연결해 WiFi 모드를 활성화하면, 이후 USB 없이 Logcat을 사용할 수 있습니다.

```bash
# 1. USB 연결 상태에서 1회 실행
adb tcpip 5555

# 2. USB 분리 후, 폰의 WiFi IP로 연결 (설정 → WiFi → 상세)
adb connect 192.168.0.XX:5555

# 3. 연결 확인
adb devices

# 4. 성능 로그만 필터
adb logcat -s VG_PERF,VG_DETECT
```

**조건:** 폰과 PC가 같은 WiFi에 연결돼 있어야 합니다.

#### VG_PERF 로그 형식

```
# 온디바이스 모드
VG_PERF: decode|35|infer|280|dedup|12|total|327|objs|2

# 서버 모드
VG_PERF: mode|server|server_ms|243|net_ms|89|total|332
```

| 필드 | 의미 |
|------|------|
| `decode` | 이미지 디코딩 시간 (ms) |
| `infer` | YOLO 추론 시간 (ms) — **주요 지표** |
| `dedup` | NMS+필터 처리 시간 (ms) |
| `total` | 전체 처리 시간 (ms) |
| `server_ms` | 서버 내부 처리 시간 |
| `net_ms` | 네트워크 전송 시간 |

`infer`가 높으면 → NNAPI 활성화 여부 확인 ("NNAPI 가속 활성화" 로그)  
`net_ms`가 높으면 → WiFi 환경 개선 (5GHz 전환, 거리 단축)  
`server_ms`가 높으면 → 서버 GPU 사용 여부 확인

---

### 방법 C — CSV 파일 로깅 (테스트 후 분석)

`MainActivity.kt`의 `sendToServer()` 또는 `processOnDevice()` 안에 추가:

```kotlin
// 성능 데이터를 파일로 기록 (테스트 후 꺼내서 분석)
val logLine = "${System.currentTimeMillis()}," +
              "fps=$fps,total=${roundTripMs}ms," +
              "server=${processMs}ms,net=${netMs}ms\n"
try {
    File(getExternalFilesDir(null), "vg_perf.csv").appendText(logLine)
} catch (_: Exception) {}
```

**파일 위치:** `Android/data/com.voiceguide/files/vg_perf.csv`  
**꺼내는 방법:** Android Studio Device Explorer 또는 `adb pull`  
**분석:** Excel / Google Sheets에서 열어서 평균, 최댓값 확인

---

### 방법 D — 서버 터미널 타이밍 로그

`src/api/routes.py`의 `/detect` 엔드포인트에 이미 `process_ms` 측정이 포함돼 있습니다.

서버 터미널에서 직접 확인하려면:

```python
# routes.py detect() 함수 안에 임시 추가
import time
t_yolo = time.monotonic()
objects, hazards, scene = detect_and_depth(image_bytes)
print(f"[PERF] YOLO+Depth={int((time.monotonic()-t_yolo)*1000)}ms")
```

YOLO ms와 Depth ms를 분리해서 보려면 `depth.py`에도 추가:

```python
# detect_and_depth() 안에
t0 = time.monotonic()
objects, scene = detect_objects(image_bytes)
print(f"[PERF] YOLO={int((time.monotonic()-t0)*1000)}ms")
t1 = time.monotonic()
# ... Depth 코드 ...
print(f"[PERF] Depth={int((time.monotonic()-t1)*1000)}ms")
```

---

## 4. 병목별 해결 흐름

```
Step 1. 앱 오버레이에서 서버처리 vs 네트워크 확인
        │
        ├─ 서버처리가 크면 → Step 2
        └─ 네트워크가 크면 → WiFi 환경 개선 (5GHz, 거리 단축)

Step 2. 서버 터미널에서 YOLO ms vs Depth ms 분리
        │
        ├─ Depth가 1000ms+ → GPU 미사용 가능성 높음
        └─ YOLO가 200ms+  → yolo11n 전환 또는 이미지 해상도 축소

Step 3. GPU 사용 여부 확인
        서버 PC에서:
        nvidia-smi
        python -c "import torch; print(torch.cuda.is_available())"
        │
        └─ False면 → src/depth/depth.py에서 _DEVICE 확인

Step 4. 온디바이스 FPS 낮으면
        Logcat에서 "NNAPI 가속 활성화" 여부 확인
        미표시면 → YoloDetector.kt에서 addNnapi() 예외 로그 확인
```

---

## 5. NNAPI 활성화 확인 (온디바이스)

Logcat에서 앱 시작 시:
```
VG_PERF: NNAPI 가속 활성화 — yolo11m.onnx   ← 정상
VG_PERF: NNAPI 미지원 → CPU 4스레드 — yolo11m.onnx  ← NNAPI 없는 기기
```

NNAPI 미지원 기기에서 속도를 올리려면 `yolo11n.onnx`로 교체가 필요합니다.

---

## 6. 서버 GPU 상태 확인

```bash
# 서버 PC에서
nvidia-smi

# Python에서
python -c "import torch; print('CUDA:', torch.cuda.is_available(), '| GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None')"

# 서버 /health 엔드포인트
curl http://localhost:8000/health
# {"depth_v2":"loaded","device":"cuda"} ← GPU 정상
# {"depth_v2":"loaded","device":"cpu"}  ← CPU 사용 중 → 느림
```

`device: cpu`면 `src/depth/depth.py`의 `_DEVICE` 변수를 확인:
```python
_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
```
`torch.cuda.is_available()`이 False면 PyTorch CUDA 버전 재설치 필요.
