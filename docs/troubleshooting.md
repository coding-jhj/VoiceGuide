# VoiceGuide 트러블슈팅 / 기술스택 / 제한사항

---

## 기술 스택

| 영역 | 라이브러리 | 버전 | 비고 |
|------|----------|------|------|
| 객체 탐지 | Ultralytics YOLO11m | 8.4.x | yolo11m.pt 사전 학습 모델 |
| 깊이 추정 | Depth Anything V2 | vits | MVP에서는 미활성화 |
| 음성 합성 (서버) | gTTS + pygame | 2.5.3 / 2.6.1 | 한국어(ko) |
| 음성 합성 (앱) | Android TTS | 내장 | 미디어 볼륨 스트림 |
| 음성 인식 | SpeechRecognition | 3.10.4 | Google Speech API |
| 딥러닝 | PyTorch | 2.4.1 | CPU 실행 |
| 이미지 처리 | OpenCV (headless) | 4.10.0.84 | 서버 환경용 |
| 수치 연산 | NumPy | 1.26.4 | **반드시 1.x** |
| API 서버 | FastAPI + Uvicorn | 0.115.5 / 0.32.1 | |
| 데모 UI | Gradio | 4.44.1 | **반드시 4.x** |
| DB | SQLite (내장) | — | 공간 스냅샷 저장 |
| Android 카메라 | CameraX | 1.3.1 | 라이브 프리뷰 + 자동 캡처 |
| Android HTTP | OkHttp | 4.12.0 | 서버 통신 |
| 외부 터널 | ngrok | 3.38.0 | 다른 네트워크 연결 시 |

---

## 알려진 오류 및 해결법

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

### 5. gTTS 음성 재생 안 됨
```
pygame.error: No available audio device
```
**원인**: 서버/헤드리스 환경에서 오디오 장치 없음  
**해결**: 로컬 실행 환경에서만 TTS 동작. Android 앱은 기본 TTS 사용으로 해결

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
**현재 설정**: `CONF_THRESHOLD = 0.60` (`src/vision/detect.py`) — 소형 물체는 0.65~0.72  
**조정 방법**: 오탐 많으면 0.65~0.70으로 올리고 서버 재시작

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

## 현재 알려진 제한사항

| 항목 | 상태 | 내용 |
|------|------|------|
| 거리 실측 보정 | ⚠️ 필요 | DEPTH_SCALE=1.0 미보정. CALIBRATION_TEST.md 참조 |
| 투명 장애물 | ⚠️ 한계 | 유리문·유리벽 탐지 불가 (모든 AI 공통 한계) |
| 비정형 계단 | ⚠️ 미검증 | 나선형·야외 계단은 실환경 테스트 필요 |
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
