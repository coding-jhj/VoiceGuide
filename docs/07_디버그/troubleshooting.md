# VoiceGuide 트러블슈팅 / 기술스택 / 제한사항

---

## 기술 스택

| 영역 | 라이브러리 | 버전 | 비고 |
|------|----------|------|------|
| 객체 탐지 | Ultralytics YOLO11m | 8.4.x | yolo11m.pt 사전 학습 모델 |
| 깊이 추정 | Depth Anything V2 | vits | ✅ GPU 활성화 (depth_anything_v2_vits.pth 필요) |
| 음성 합성 (서버) | gTTS + pygame | 2.5.3 / 2.6.1 | 무료, 한국어. Naver Clova 키 있으면 자동 전환 |
| 음성 합성 (앱) | Android TTS (내장) | 내장 | 항상 내장 TTS 사용 (ElevenLabs 자동호출 제거 — 2026-04-29) |
| 음성 인식 | SpeechRecognition | 3.10.4 | Google Speech API |
| 딥러닝 | PyTorch | 2.11.0+cu128 | GPU 실행 (RTX 5060 Blackwell 지원) |
| 이미지 처리 | OpenCV (headless) | 4.10.0.84 | 서버 환경용 |
| 수치 연산 | NumPy | 1.26.4 | **반드시 1.x** |
| API 서버 | FastAPI + Uvicorn | 0.115.5 / 0.32.1 | |
| 데모 UI | Gradio | 4.44.1 | **반드시 4.x** |
| DB | SQLite (로컬) / PostgreSQL Supabase (외부, DATABASE_URL 설정 시) | — | 공간 스냅샷 저장 |
| Android ONNX | ONNX Runtime Android | 1.19.0 | opset 18 지원 (PyTorch 2.11 내보내기 호환) |
| Android 카메라 | CameraX | 1.3.1 | 라이브 프리뷰 + 자동 캡처 |
| Android HTTP | OkHttp | 4.12.0 | 서버 통신 |
| 외부 터널 | ngrok / Railway / Render / GCP Cloud Run | 3.38.0+ | 다른 네트워크 연결 시 |
| 보팅 경고 피로 방지 | VotingBuffer | — | 최근 10프레임 60%+ 탐지 시 확정 |
| NNAPI 하드웨어 가속 | ONNX Runtime NNAPI | — | Android DSP/NPU 활용 — 기기 지원 시 자동 활성화 (2026-04-29) |

---

## 알려진 오류 및 해결법

### 0. 소리가 안 나와요 (2026-04-29 수정 완료)

**증상**: 텍스트는 표시되는데 TTS 소리가 안 남

**1차 원인**: 서버 URL 입력 시 ElevenLabs /tts 자동 호출 → API 키 없으면 JSON 에러 → MediaPlayer 실패 → 무음
- 수정: `speak()`가 항상 Android 내장 TTS 사용

**2차 원인(진짜 원인)**: 오토리슨이 항상 켜져서 `isListening=true` → `speak()` 안에서 `return` → TTS 차단
- 수정: `speak()` 호출 시 `speechRecognizer.cancel()`로 STT 즉시 중단 후 TTS 재생
- TTS 끝나면 자동으로 오토리슨 재시작

---

### 1. numpy 버전 오류
```
AttributeError: module 'numpy' has no attribute 'bool'
```
**원인**: NumPy 2.x는 opencv, ultralytics와 호환 불가  
**해결**: `pip install "numpy==1.26.4"`

---

### 2. Gradio / FastAPI 충돌
```
ImportError: cannot import name 'xxx' from 'starlette'
```
**원인**: Gradio 5.x가 FastAPI의 starlette 버전과 충돌  
**해결**: `pip install "gradio==4.44.1"`

---

### 3. Depth Anything V2 모델 파일 없음
```
FileNotFoundError: depth_anything_v2_vits.pth
```
**현재 상태**: `detect_and_depth()`에서 Depth V2 호출이 주석 처리되어 있어 앱 실행에는 영향 없음  
**활성화 방법**: 가중치 파일 다운로드 후 `VoiceGuide/` 루트에 배치, `depth.py` 주석 해제

---

### 4. PyAudio 설치 오류 (Windows)
```
error: Microsoft Visual C++ 14.0 or greater is required
```
**원인**: Windows에서 PyAudio는 C++ 컴파일러 필요  
**해결**: conda 환경에서 설치
```bash
conda install pyaudio
```

---

### 5. ElevenLabs 402 오류
```
[TTS] ElevenLabs 오류 402: {"detail":{"type":"payment_required",...}}
```
**원인**: ElevenLabs 무료 플랜에서 보이스 라이브러리 사용 불가 (정책 변경)  
**해결**: 현재 gTTS(구글)로 전환됨. Naver Clova 사용 시 `.env`에 키 추가:
```
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
```

### 5-1. ElevenLabs SDK websockets 충돌
```
ImportError: The websockets package is required for realtime speech-to-text
ModuleNotFoundError: No module named 'websockets.asyncio'
```
**원인**: ElevenLabs SDK가 내부적으로 `websockets 13+` 요구, gradio-client는 `<13.0` 요구  
**해결**: ElevenLabs SDK 제거 → REST API 직접 호출 방식으로 교체 완료 (재발 없음)

---

### 6. 포트 8000 이미 사용 중
```
[WinError 10048] 각 소켓 주소(프로토콜/네트워크 주소/포트)는 하나만 사용할 수 있습니다
```
**원인**: 이전에 실행한 uvicorn이 종료되지 않고 남아있음  
**해결**:
```cmd
netstat -ano | findstr :8000
taskkill /PID <숫자> /F
```

---

### 7. ngrok 터널 이미 온라인
```
ERROR: failed to start tunnel: The endpoint is already online. ERR_NGROK_334
```
**원인**: 다른 터미널이나 세션에서 ngrok이 이미 실행 중  
**해결**:
```cmd
taskkill /IM ngrok.exe /F
ngrok http 8000
```

---

### 8. winget 명령어 없음
```
'winget'은(는) 내부 또는 외부 명령이 아닙니다
```
**원인**: Windows App Installer가 설치되지 않음  
**해결**: 직접 다운로드
```powershell
Invoke-WebRequest -Uri "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip" -OutFile "$env:TEMP\ngrok.zip"
Expand-Archive "$env:TEMP\ngrok.zip" -DestinationPath "C:\ngrok" -Force
```

---

### 9. TFLite 변환 실패 (Python 3.13)
```
ModuleNotFoundError: No module named 'tensorflow'
ERROR: No matching distribution found for tensorflow<=2.19.0,>=2.0.0
```
**원인**: Python 3.13은 tensorflow 2.19 이하 미지원  
**해결**: ONNX 포맷으로 대체
```bash
pip install onnx onnxruntime
python export_tflite.py  # ONNX로 변환
```

---

### 10. ultralytics 모듈 없음 (서버 실행 시)
```
ModuleNotFoundError: No module named 'ultralytics'
```
**원인**: requirements.txt에 포함되지 않은 별도 패키지  
**해결**:
```bash
pip install ultralytics
```

---

### 11. 앱이 "분석 중..."에서 멈춤
**원인 1**: uvicorn 서버가 실행되지 않은 상태  
**원인 2**: URL이 잘못 입력됨 (http:// 누락, 포트 오류)  
**원인 3**: 폰과 PC가 다른 네트워크에 연결됨  
**해결**: 서버 실행 확인 → URL 재확인 → 같은 Wi-Fi 연결 확인

---

### 12. 없는 물체를 인식하는 오탐
**원인**: 신뢰도 임계값이 낮으면 손/팔 등을 다른 물체로 인식  
**현재 설정**: `CONF_THRESHOLD = 0.50` (`src/vision/detect.py`)  
**클래스별 최소 신뢰도** (`CLASS_MIN_CONF`):
- `stairs`: 0.72 (키보드·에스컬레이터 오탐 방지)
- `tie`: 0.75, `umbrella`: 0.68, `handbag`: 0.65 (실내 오탐 방지)
- `wine glass`/`cup`/`bowl`: 0.65~0.70  
**조정 방법**: 오탐 많으면 해당 클래스 값 올리고 서버 재시작

### 16. 앱 시작 시 "네" 말해도 반응 없음
**원인**: TTS가 말하는 중에 STT 마이크가 켜져서 TTS 목소리를 인식함  
**해결**: TTS 종료 후 600ms 대기 → STT 시작 (폴링 방식, 현재 적용됨)

### 17. 음성 안내 중 내 목소리 인식 실패
**원인**: TTS 재생 중 마이크에 TTS 소리가 들어가 STT 오인식  
**해결**: 음성 명령 버튼 누르면 TTS 즉시 중단 후 STT 시작. STT 활성 중 TTS 차단 (현재 적용됨)

### 18. 탐지 텍스트가 너무 빨리 사라짐
**원인**: 매 1초 분석에서 장애물 없으면 즉시 "장애물 없음"으로 덮어씀  
**해결**: 마지막 탐지 후 3초간 텍스트 유지 (현재 적용됨)

### 13. 계단 앞에서 경고가 안 나올 때
**원인**: hazard 감지 임계값이 너무 높거나 Depth V2 모델 없음  
**확인**: 서버 로그에 `[Depth V2] 모델 파일 확인` 메시지 있는지 확인  
**조정**: `src/depth/hazard.py`에서 `_DROP_THRESH = 1.2` → `0.8`로 낮추면 더 민감

### 14. 계단이 없는데 경고가 나올 때
**원인**: 바닥 패턴이나 그림자가 깊이 변화로 오인됨  
**조정**: `src/depth/hazard.py`에서 `_DROP_THRESH = 1.2` → `1.8`로 높이면 덜 민감

### 15. 거리가 실제와 많이 다를 때
**원인**: `DEPTH_SCALE = 1.0` 미보정  
**해결**: `docs/CALIBRATION_TEST.md` 참조하여 실측 보정

---

### 19. Depth Anything V2가 폰에서는 동작하지 않는 이유

**원인**: Depth V2는 **서버 전용** 기능이라 설계 의도대로 동작하는 것입니다.

| 환경 | 거리 추정 방식 | 속도 |
|------|------------|------|
| 서버 연결 시 | Depth Anything V2 (정확, 상대 깊이 맵) | ~0.3초/장 (GPU) |
| 온디바이스 (서버 없음) | bbox 면적 비율 (YoloDetector.kt + SentenceBuilder.kt) | 즉시 |

**확인 방법**: 서버 실행 후 `GET /health` 호출
```json
{"depth_v2": "loaded", "device": "cuda"}   ← 정상 로드
{"depth_v2": "fallback (bbox)"}             ← 모델 파일 없음
```

**모델 파일 없을 때**: 서버도 bbox 기반으로 자동 전환 — 에러 없이 동작함

---

### 20. TTS가 같은 말을 반복하거나 겹칠 때 (경고 피로)

**원인**: 1초마다 분석 → 같은 장면이면 매초 같은 TTS 발화

**현재 적용된 해결책:**
- **서버 5초 dedup** (`routes.py` `_should_suppress`): 같은 세션에서 동일 문장이 5초 내 반복되면 `alert_mode="silent"`로 낮춤
- **Android 3초 억제** (`suppressPeriodicUntil`): 질문 응답 직후 3초간 periodic TTS를 silent 처리
- **VotingBuffer 10프레임**: 일시적 오탐은 아예 경고 안 함
- `critical` (차량·계단)은 항상 통과 — 안전 우선

**조정 방법**: 너무 조용하면 `routes.py`에서 `_DEDUP_SECS = 5.0` → `2.0`으로 낮추기

---

### 21. Supabase 연결이 안 될 때

**원인 1**: `DATABASE_URL` 환경변수 미설정 → SQLite로 동작 (정상)  
**원인 2**: Direct connection 주소 사용 시 일부 네트워크에서 DNS 실패

**해결**: Session pooler 주소 사용
```
# 잘못된 주소 (Direct connection)
postgresql://postgres:pass@db.xxx.supabase.co:5432/postgres

# 올바른 주소 (Session pooler)
postgresql://postgres.xxx:pass@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres
```
`서버_DB/SUPABASE_DB_CONNECT_GUIDE.md` 참조

**확인**: `GET /health` → `"db_mode": "postgresql"` 이면 연결 성공

---

### 22. Railway/Render 배포 후 첫 요청이 느릴 때 (Cold Start)

**원인**: 무료 플랜은 일정 시간 비활성 시 sleep → 첫 요청에서 30~60초 지연

**해결**:
1. 앱 사용 전 `/health`로 warm-up 요청 먼저 보내기
2. [Uptime Robot](https://uptimerobot.com) 무료 계정 → 5분마다 `/health` ping 설정 (sleep 방지)
3. Railway Hobby 플랜($5/월)은 sleep 없음

---

### 23. 보팅(Voting) 후 경고가 너무 늦게 나올 때

**원인**: `VotingBuffer(window=10, threshold=0.6)` → 10프레임 중 6회 탐지돼야 경고  
1초 간격이면 최대 6초 후 첫 경고 가능

**해결**: `src/api/tracker.py`에서 파라미터 낮추기
```python
_VOTE_WINDOW    = 10   # → 5로 낮추면 더 빠름
_VOTE_THRESHOLD = 0.6  # → 0.4로 낮추면 더 민감
```

**주의**: 차량·계단은 `ALWAYS_CRITICAL`이라 보팅 없이 즉시 통과 — 안전에 영향 없음

---

### 24. Android 앱 "분석 실패 — 주의하세요" 반복

**원인**: ONNX Runtime Android 버전과 모델 opset 불일치

| 상황 | 원인 |
|------|------|
| `onnxruntime-android:1.17.3` + PyTorch 2.11 내보낸 모델 | opset 18 연산자 일부 미지원 → 추론 실패 → `handleFail()` 반복 |

**흐름**: `processOnDevice()` 내부 예외 → `sendToServer()` 호출 → 서버 URL 비어있으면 `handleFail()` 즉시 → 3회 반복 → 경고 표시

**해결**: `android/app/build.gradle`에서 ONNX Runtime 버전 업그레이드
```groovy
// 변경 전
implementation 'com.microsoft.onnxruntime:onnxruntime-android:1.17.3'
// 변경 후
implementation 'com.microsoft.onnxruntime:onnxruntime-android:1.19.0'
```
→ Android Studio에서 **Sync Now** → **▶ Run**

---

### 25. RTX 5060(Blackwell)에서 PyTorch CUDA 인식 안 됨

**증상**: `torch.cuda.is_available()` → `False` / `torch-2.4.1+cpu`로 설치됨

**원인**: RTX 5060은 Blackwell 아키텍처 (SM_120). PyTorch 2.4.x는 Blackwell 미지원

**해결**: CUDA 12.8용 PyTorch 2.11+ 재설치
```bash
pip install "torch>=2.6.0" torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```
확인: `python -c "import torch; print(torch.cuda.get_device_name(0))"`

---

### 26. 목소리 겹침 수정이 적용 안 됨 (구버전 APK)

**원인**: `c:\VoiceGuide\` 아래에 android 폴더가 두 개 존재

| 경로 | 상태 |
|------|------|
| `c:\VoiceGuide\android\` | **구버전** — `suppressPeriodicUntil` 없음, TTS 겹침 수정 미적용 |
| `c:\VoiceGuide\VoiceGuide\android\` | **신버전** — 3초 TTS 억제 적용 ✅ |

**해결**: Android Studio에서 반드시 `c:\VoiceGuide\VoiceGuide\android` 폴더를 열고 빌드

---

### 27. 같은 말 3번 반복

**원인**: `critical` 브랜치가 `!isSpeaking()` 조건으로 TTS 끝날 때마다 같은 문장 재발화

**해결**: critical 5초 쿨다운 + `ttsBusy` AtomicBoolean 완전 잠금 적용 (4차 수정)

---

### 28. 말 끝나기 전에 다음 말 시작

**원인**: `isSpeaking()` 비동기 타이밍 race condition — 찰나에 false 반환 시 두 TTS 동시 시작

**해결**: `ttsBusy` AtomicBoolean 도입
- `speakBuiltIn()`: `compareAndSet(false, true)` 실패 시 즉시 버림
- `onDone` 후 700ms 뒤 잠금 해제
- 차량만 `immediate=true`로 강제 획득 (나머지는 대기)

---

### 29. 비프음이 안 들림

**원인 1**: `ToneGenerator` 볼륨 60%, 120ms — 너무 작고 짧음
**원인 2**: 온디바이스 모드에서 alertMode가 항상 "critical"로 고정돼 beep 브랜치 진입 불가
**원인 3**: `isSpeaking()` 쿨다운에 비프까지 막힘

**해결**:
- 볼륨 60 → 100, 길이 120ms → 400ms, `TONE_PROP_BEEP` → `TONE_PROP_BEEP2`
- 온디바이스 alertMode 계산 추가 (거리 기반)
- 비프는 `tts.isSpeaking` 직접 체크 (쿨다운 무관)

---

### 30. 가까이 있는데 비프음만 나고 음성 안내 없음

**원인**: 거리 기반 분류 로직을 거꾸로 구현 (가까이→beep, 멀리→voice)

**해결**: 올바른 방향으로 수정
- 가까이(bbox 8%+) → 음성 안내 (이미 말해줬어도 계속)
- 멀리(bbox 8% 미만) → 비프
- 차량·칼 등 위험 → 항상 음성

---

### 31. 여러 사물이 있는데 하나만 말함

**원인**: `classify()` 함수가 가까운 사물만 `voiceDetections`에 담고, 문장도 `voiceDetections`만으로 생성 → 멀리 있는 사물은 문장에서 제외됨

**해결**: 문장 생성 기준을 `voted` 전체로 변경 (가까운 순 정렬, 최대 3개)

---

### 32. 벽·스피커를 냉장고·노트북으로 인식

**원인**: COCO 63(laptop), 72(refrigerator)는 직사각형 평면 구조물이면 쉽게 오탐

**해결**: 탐지 대상에서 제거
```kotlin
// VoiceGuideConstants.kt에서 제거됨
// 63 to "노트북"   // 스피커·모니터 오인식
// 72 to "냉장고"   // 벽 오인식
```

---

### 33. 찾기 모드 음성 명령 인식 안 됨

**원인 1**: STT가 "찾아 줘"처럼 공백 포함 → `replace("찾아줘", "")` 미작동
**원인 2**: 클래스 쿨다운이 찾는 대상 물체도 5초간 필터링

**해결**:
- `extractFindTarget()` 공백 정규화 + 키워드 확대 ("어딨어", "어딨나", "어디 있나")
- `voteFilter`: 찾기 모드 진입 시 쿨다운 우회

---

### 34. 분석 중지 버튼 눌러도 계속 분석함 (2026-04-29 수정)

**원인**: `handleSuccess()`가 `isAnalyzing` 체크 없이 실행 → 중지 후에도 백그라운드 Thread 완료 시 TTS 발화, UI 업데이트 계속됨

**해결**: `handleSuccess()` 첫 줄에 `if (!isAnalyzing.get()) return` 추가 (`MainActivity.kt`)

---

### 35. 처음에 장애물 감지가 느리고, 새 물체 전환도 느림 (2026-04-29 수정)

**원인 1**: `startAnalysis()` 재시작 시 `detectionHistory` 미초기화 → 이전 세션 투표 버퍼 잔존 → 첫 감지가 느림

**원인 2**: `VOTE_MIN_COUNT = 2` → 물체가 2프레임 연속 감지돼야 통과 (ONNX 400ms × 2 = 800ms 지연)

**해결**:
- `startAnalysis()`에 `detectionHistory.clear()` 추가
- `VOTE_MIN_COUNT` 2 → 1로 변경 (첫 프레임부터 즉시 통과)

---

### 36. 서버 `/tts` 엔드포인트가 소리 대신 JSON 에러 반환 (2026-04-29 수정)

**증상**: ElevenLabs API 키 없을 때 `/tts` 엔드포인트가 `{"error": "ELEVENLABS_API_KEY not set"}`을 HTTP **200**으로 반환

**문제**: Android가 HTTP 200을 성공으로 보고 JSON 내용을 `.mp3`로 저장 → MediaPlayer가 JSON을 MP3로 재생 시도 → 예외 → 무음

**해결**: API 키 체크 제거, `_generate()` 내부 gTTS 폴백 활용. 진짜 실패 시 HTTP 400/500 반환 (`routes.py`)

---

### 37. 바운딩박스가 물체 없어진 뒤에도 유지됨 (2026-04-29 수정)

**원인**: `sendToServer()` 서버 응답의 `objects` 배열을 완전히 무시 → 온디바이스(`processOnDevice`)와 달리 박스 갱신 코드 없음

**해결**: 서버 응답 `objects` JSON 파싱 → `Detection`(정규화 좌표) 변환 → `boundingBoxOverlay` 즉시 갱신. 빈 배열이면 `clearDetections()` 호출

---

### 38. `isSending` 영구 `true` → 프레임 완전 멈춤

**원인**: `sendToServer()` 예외 경로에서 `handleFail()` 호출 전 예외 발생 시 `isSending`이 `true`로 고착 → `captureAndProcess()` 매번 스킵 → 0fps 현상

**해결**: `sendToServer()` `finally` 블록에 `isSending.set(false)` 추가 (안전망)

---

## FPS 실용 기준선

> 시각장애인 보행 보조 앱의 최소 요구 성능

| 등급 | FPS | 추론 시간 | 평가 |
|------|-----|---------|------|
| 위험 (걷기 부적합) | < 3fps | > 400ms | 실사용 불가 |
| 경계선 | 3~5fps | 200~400ms | 주의 필요 |
| 실용 최소선 ✓ | 5fps | ~200ms | 실내 천천히 보행 가능 |
| 쾌적 ✓✓ | 10fps | ~100ms | 실외 보행 가능 |
| 이상적 ✓✓✓ | 15fps | ~67ms | 자신감 있는 보행 |

### 현재 VoiceGuide 예상 성능

| 환경 | 예상 FPS | 평가 |
|------|---------|------|
| YOLO11n + NNAPI | 8~15fps | 쾌적 |
| YOLO11n + CPU만 | 3~6fps | 실용 최소선 |
| YOLO11m + NNAPI | 4~8fps | 실용권 |
| YOLO11m + CPU만 | 1~3fps | 위험 영역 |
| 서버 모드 (로컬 WiFi) | 3~6fps | 실용권 |
| 서버 모드 (클라우드) | 1~3fps | 보행엔 부적합 |

### tvDebug 화면에서 판단하는 법

```
FPS  : ① 5 이상인지 확인
YOLO : ② 200ms 이하인지 확인
전체 : ③ 300ms 이하인지 확인  ← 가장 중요
탐지수: raw=N → M  (필터 후 줄어드는 게 정상)
```

---

## 현재 알려진 제한사항

| 항목 | 상태 | 내용 |
|------|------|------|
| 거리 실측 보정 | ⚠️ 필요 | DEPTH_SCALE=1.0 미보정. CALIBRATION_TEST.md 참조 |
| 투명 장애물 | ⚠️ 한계 | 유리문·유리벽 탐지 불가 (모든 AI 공통 한계) |
| 연속 스트리밍 | ⚠️ 한계 | 1초 간격 캡처 (연속 영상 처리 아님) |

---

## 환경 세팅 요약

```bash
# Python 패키지 설치
pip install -r requirements.txt
pip install ultralytics

# 서버 실행
cd C:\VoiceGuide\VoiceGuide
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# ngrok (다른 네트워크일 때)
set PATH=%PATH%;C:\ngrok
ngrok config add-authtoken 본인토큰
ngrok http 8000

# Gradio 데모
python app.py           # 로컬
python app.py --share   # 외부 접근
```
