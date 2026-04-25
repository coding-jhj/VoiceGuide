# VoiceGuide 트러블슈팅 / 기술스택 / 구현 애로사항 / 제한사항

---

## 기술 스택

| 영역 | 라이브러리 | 버전 | 비고 |
|------|----------|------|------|
| 객체 탐지 | Ultralytics YOLO11m | 8.4.x | yolo11m.pt 사전 학습 모델 |
| 깊이 추정 | Depth Anything V2 | vits | MVP에서는 미활성화 |
| 딥러닝 | PyTorch | 2.4.1 | CPU 실행 |
| 이미지 처리 | OpenCV (headless) | 4.10.0.84 | 서버 환경용 |
| 수치 연산 | NumPy | 1.26.4 | **반드시 1.x** |
| 음성 합성 (서버) | gTTS + pygame | 2.5.3 / 2.6.1 | 한국어(ko) |
| 음성 합성 (앱) | Android TTS | 내장 | 미디어 볼륨 스트림 |
| 음성 인식 | SpeechRecognition | 3.10.4 | Google Speech API |
| API 서버 | FastAPI + Uvicorn | 0.115.5 / 0.32.1 | |
| 데모 UI | Gradio | 4.44.1 | **반드시 4.x** |
| DB | SQLite (내장) | — | 공간 스냅샷 저장 |
| Android 카메라 | CameraX | 1.3.1 | 라이브 프리뷰 + 자동 캡처 |
| Android HTTP | OkHttp | 4.12.0 | 서버 통신 |
| 외부 터널 | ngrok | 3.38.0 | 다른 네트워크 연결 시 |

---

## 트러블슈팅

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

### 3. 포트 8000 이미 사용 중
```
[WinError 10048] 각 소켓 주소는 하나만 사용할 수 있습니다
```
**원인**: 이전에 실행한 uvicorn이 종료되지 않고 남아있음  
**해결**:
```cmd
netstat -ano | findstr :8000
taskkill /PID <숫자> /F
```

---

### 4. ngrok 터널 이미 온라인
```
ERROR: failed to start tunnel: The endpoint is already online. ERR_NGROK_334
```
**원인**: 다른 터미널에서 ngrok이 이미 실행 중  
**해결**:
```cmd
taskkill /IM ngrok.exe /F
ngrok http 8000
```

---

### 5. winget 명령어 없음
```
'winget'은(는) 내부 또는 외부 명령이 아닙니다
```
**원인**: Windows App Installer 미설치  
**해결**: PowerShell에서 직접 다운로드
```powershell
Invoke-WebRequest -Uri "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip" -OutFile "$env:TEMP\ngrok.zip"
Expand-Archive "$env:TEMP\ngrok.zip" -DestinationPath "C:\ngrok" -Force
```

---

### 6. TFLite 변환 실패 (Python 3.13)
```
ModuleNotFoundError: No module named 'tensorflow'
ERROR: No matching distribution found for tensorflow<=2.19.0
```
**원인**: Python 3.13은 tensorflow 2.19 이하 미지원  
**해결**: ONNX 포맷으로 대체
```bash
pip install onnx onnxruntime
python export_tflite.py
```

---

### 7. ultralytics 모듈 없음
```
ModuleNotFoundError: No module named 'ultralytics'
```
**원인**: requirements.txt에 미포함  
**해결**: `pip install ultralytics`

---

### 8. 앱이 "분석 중..."에서 멈춤
**원인 1**: uvicorn 서버 미실행  
**원인 2**: URL 오입력 (http:// 누락, 포트 오류)  
**원인 3**: 폰과 PC가 다른 네트워크  
**해결**: 서버 실행 확인 → URL 재확인 → 같은 Wi-Fi 연결 확인

---

### 9. 없는 물체를 인식하는 오탐
**원인**: 신뢰도 임계값이 낮으면 손·팔 등을 다른 물체로 오인  
**현재 설정**: `CONF_THRESHOLD = 0.45` (`src/vision/detect.py:26`)  
**조정**: 오탐 많으면 0.50~0.60으로 올리고 서버 재시작

---

### 10. PyAudio 설치 오류 (Windows)
```
error: Microsoft Visual C++ 14.0 or greater is required
```
**해결**: conda 환경에서 설치
```bash
conda install pyaudio
```

---

## 구현 애로사항

| 항목 | 내용 |
|------|------|
| 브랜치 병합 충돌 | feature/android와 main의 히스토리가 달라 `--allow-unrelated-histories` 필요. 병합 시 routes.py, tts.py, templates.py 등 핵심 파일이 구버전으로 덮어써짐 → 수동 복원 |
| Python 3.13 호환성 | TFLite 변환에 필요한 tensorflow가 Python 3.13 미지원 → ONNX Runtime으로 전환 |
| 방향 오류 | camera_orientation을 "back"으로 전송 시 방향이 180도 반전 → "front"로 수정 |
| 오탐 문제 | 신뢰도 임계값 0.15에서 손·팔을 사람으로 오인. 0.45로 조정 후 해결 |
| 문장 어색함 | "앞 왼쪽", "휴대폰가" 등 비자연스러운 표현 → 이/가 조사 자동화, 방향 표현 재설계 |
| 응답 반복 | 3초마다 같은 문장 반복 안내 → 동일 문장 필터링 + TTS 중 텍스트 교체 방지 |

---

## 설계 제한사항

| 항목 | 현재 방식 | 제한 | 개선 방향 |
|------|---------|------|---------|
| 거리 추정 | bbox 면적 비율 | 카메라 높이·각도에 따라 오차 발생 | Depth Anything V2 활성화 |
| 카메라 방향 | front 고정 | 사용자가 돌아보는 상황 미지원 | 나침반 + 가속도계 연동 |
| 추론 위치 | PC 서버 | PC가 없으면 동작 불가 | 온디바이스 ONNX 추론 |
| 연결 방식 | 로컬 IP / ngrok | 동일 Wi-Fi 또는 인터넷 필요 | 온디바이스로 완전 독립 |
| 응답 속도 | 2초 간격 | 빠르게 움직이는 장애물 대응 어려움 | 온디바이스 추론으로 단축 |
| 모델 정확도 | YOLO11m | 문·계단·턱 등 보행 특화 장애물 미지원 | 커스텀 데이터셋 파인튜닝 |

---

## 환경 세팅 요약

```bash
# 패키지 설치
pip install -r requirements.txt
pip install ultralytics

# 서버 실행
cd C:\VoiceGuide\VoiceGuide
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 로컬 IP 확인
ipconfig

# ngrok (다른 네트워크일 때)
set PATH=%PATH%;C:\ngrok
ngrok config add-authtoken 본인토큰
ngrok http 8000
```
