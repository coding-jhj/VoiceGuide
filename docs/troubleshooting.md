# VoiceGuide 트러블슈팅 / 기술스택 / 제한사항

---

## 기술 스택

| 영역 | 라이브러리 | 버전 | 비고 |
|------|----------|------|------|
| 객체 탐지 | ultralytics (YOLO11n) | 8.3.2 | yolo11n.pt 사전 학습 모델 |
| 깊이 추정 | Depth Anything V2 | vits | MVP에서는 미활성화 |
| 음성 합성 | gTTS + pygame | 2.5.3 / 2.6.1 | 한국어(ko) |
| 음성 인식 | SpeechRecognition | 3.10.4 | Google Speech API, ko-KR |
| 딥러닝 | PyTorch | 2.4.1 | GPU/CPU 자동 선택 |
| 이미지 처리 | OpenCV (headless) | 4.10.0.84 | 서버 환경용 |
| 수치 연산 | NumPy | 1.26.4 | **반드시 1.x** |
| API 서버 | FastAPI + Uvicorn | 0.115.5 / 0.32.1 | |
| 데모 UI | Gradio | 4.44.1 | **반드시 4.x** |
| DB | SQLite (내장) | — | 공간 스냅샷 저장 |
| Android | OkHttp / WifiManager | — | 미완성 |

---

## 알려진 오류 및 해결법

### 1. `numpy` 버전 오류
```
AttributeError: module 'numpy' has no attribute 'bool'
```
**원인**: NumPy 2.x는 opencv, ultralytics와 호환 안 됨  
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
**원인**: 모델 가중치 파일이 레포에 포함되지 않음 (용량 문제)  
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
**해결**: 로컬 실행 환경에서만 TTS 동작. 서버 배포 시 음성 파일(MP3)을 클라이언트로 전송하는 방식으로 변경 필요

---

### 6. YOLO 모델 자동 다운로드 실패
```
ConnectionError: Failed to download yolo11n.pt
```
**원인**: 인터넷 차단 환경 또는 ultralytics 서버 이슈  
**해결**: `yolo11n.pt` 파일을 수동으로 다운로드 후 `VoiceGuide/` 루트에 배치

---

### 7. `TypeError: argument of type 'bool' is not iterable` (Gradio 실행 중)

```
File "...gradio_client/utils.py", line 863, in get_type
    if "const" in schema:
TypeError: argument of type 'bool' is not iterable
```

**원인**: `gradio_client 1.3.0`이 pydantic이 생성한 JSON Schema의 `additionalProperties: true/false`(bool 값)를 처리하지 못하는 버그  
**해결**: 아래 패치 스크립트를 1회 실행 (`pip install` 후마다 재실행 필요)

```bash
python patch_gradio_client.py
```

> `pip install -r requirements.txt`를 다시 실행하면 패치가 초기화됩니다. 그때마다 위 명령을 다시 실행하세요.

---

### 8. `ValueError: When localhost is not accessible, a shareable link must be created`

```
ValueError: When localhost is not accessible, a shareable link must be created.
Please set share=True or check your proxy settings to allow access to localhost.
```

**원인**: Gradio가 내부적으로 localhost 접근 가능 여부를 확인하는데, 일부 환경(방화벽, VPN, WSL 등)에서 실패  
**해결**: `--share` 플래그로 실행

```bash
python app.py --share
```

→ 터미널에 `https://xxxx.gradio.live` URL이 출력됩니다. 폰 브라우저에서 접속 가능.

---

### 9. `--share` 공개 URL이 연결 안 됨
**원인**: Gradio 터널링 서버가 간헐적으로 불안정  
**대안**: 같은 WiFi 환경에서 PC IP로 접속
```
# PC IP 확인 (Windows)
ipconfig
# 폰 브라우저에서: http://[PC_IP]:7860
```

---

## 설계 상 제한사항

| 항목 | 현재 방식 | 제한 | 개선 방향 |
|------|---------|------|---------|
| 거리 추정 | bbox 면적 비율 | 카메라 높이·각도·렌즈에 따라 오차 큼 | Depth V2 활성화 |
| 카메라 방향 | 정면(front) 고정 | 사용자가 돌아보는 상황 미지원 | Android 나침반 센서 연동 |
| 탐지 클래스 | 6종 | 문, 계단, 턱 등 실외 장애물 미탐지 | 커스텀 데이터셋 파인튜닝 |
| 거리 보정 | CALIB_RATIO=0.12 | 현장 실험 전 임의값 | 실내 환경 측정 후 보정 |
| 실시간성 | 사진 1장 단위 | 연속 프레임 처리 없음 | 영상 스트리밍 파이프라인 추가 |
| 오디오 지연 | gTTS (네트워크 TTS) | 인터넷 필요, 약 1~2초 지연 | 로컬 TTS 엔진 검토 (e.g. pyttsx3) |

---

## 환경 세팅 요약

```bash
# 1. conda 환경 생성
conda create -n voiceguide python=3.10
conda activate voiceguide

# 2. PyAudio (Windows)
conda install pyaudio

# 3. 나머지 패키지
pip install -r requirements.txt

# 4. 환경변수
cp .env.example .env
# .env에 NGROK_AUTH_TOKEN 입력 (선택)

# 5. 실행
python app.py           # 로컬
python app.py --share   # 실기기 테스트
```
