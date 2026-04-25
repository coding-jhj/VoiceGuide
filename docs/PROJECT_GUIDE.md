# VoiceGuide 프로젝트 기술 문서

> KDT AI Human 3팀 | 2026-04-24 ~ 2026-05-13  
> 시각장애인을 위한 AI 음성 주변 인지 서비스

---

## 목차

1. [프로젝트 현황 (MVP 체크리스트)](#1-프로젝트-현황)
2. [실기기 데모 가이드](#2-실기기-데모-가이드)
3. [모델 선정 결과](#3-모델-선정-결과)
4. [알고리즘 명세](#4-알고리즘-명세)
5. [기술 스택](#5-기술-스택)
6. [트러블슈팅](#6-트러블슈팅)
7. [구현 애로사항](#7-구현-애로사항)
8. [설계 제한사항](#8-설계-제한사항)
9. [환경 세팅 요약](#9-환경-세팅-요약)

---

## 1. 프로젝트 현황

### MVP 목표

> 시각장애인이 스마트폰 카메라로 주변을 찍으면,  
> AI가 장애물의 **위치·방향·거리·행동 안내**를 한국어 음성으로 실시간 안내한다.

### MVP 완성 기준

```
카메라로 의자를 찍는다
→ YOLO11m이 의자를 탐지한다
→ "왼쪽 앞에 의자가 있어요. 오른쪽으로 피해가세요." 음성 출력
이 흐름 하나가 실기기에서 작동하면 MVP 완성.
```

**현재 상태: ✅ MVP 달성**

---

### 기능 체크리스트

#### 핵심 파이프라인

| 기능 | 상태 | 비고 |
|------|------|------|
| YOLO11m 장애물 탐지 | ✅ 완료 | COCO 80클래스, conf=0.60 |
| 방향 판단 (9구역) | ✅ 완료 | 8시~4시 → 한국어 방향 변환 |
| 거리 추정 (bbox 면적) | ✅ 완료 | 5단계, 미터/센티미터 표현 |
| 위험도 계산 | ✅ 완료 | 방향·거리 가중치 곱 |
| 한국어 문장 생성 | ✅ 완료 | 긴박도별 구조, 이/가 조사 자동화 |
| TTS 음성 출력 | ✅ 완료 | Android 기본 TTS (한국어) |
| 카메라 방향 보정 | ✅ 완료 | front/back/left/right 오프셋 |

#### 서버 / API

| 기능 | 상태 | 비고 |
|------|------|------|
| FastAPI `/detect` 엔드포인트 | ✅ 완료 | 이미지 POST → 문장 반환 |
| `camera_orientation` 파라미터 | ✅ 완료 | front 고정 사용 중 |
| 공간 스냅샷 DB (SQLite) | ✅ 완료 | 장소별 변화 감지 |
| 서버 시작 시 YOLO 워밍업 | ✅ 완료 | 첫 요청 지연 방지 |
| Gradio 데모 UI | ✅ 완료 | localhost:7860 |

#### Android 앱

| 기능 | 상태 | 비고 |
|------|------|------|
| CameraX 라이브 프리뷰 | ✅ 완료 | 실시간 카메라 화면 |
| 2초마다 자동 분석 | ✅ 완료 | 시작 즉시 첫 캡처 |
| 한국어 TTS 음성 안내 | ✅ 완료 | 미디어 볼륨 스트림 |
| 반복 안내 방지 | ✅ 완료 | 동일 문장 필터링 |
| 로컬 IP 직접 연결 | ✅ 완료 | ngrok 없이 빠른 응답 |
| USB 없이 독립 실행 | ✅ 완료 | 설치 후 폰 단독 사용 |

#### 추가 완성 기능 (2026-04-25)

| 기능 | 상태 | 비고 |
|------|------|------|
| Depth Anything V2 거리 추정 | ✅ 완료 | GPU 자동 감지, bbox 자동 fallback |
| **계단/낙차/턱 감지** | ✅ 완료 | depth map 12구역 분석 (YOLO 보완) |
| **YOLO11m 파인튜닝** | ✅ 완료 | 계단 클래스 추가, mAP50=0.992 |
| **객체 추적기 (EMA)** | ✅ 완료 | 프레임 jitter 제거, 접근/소멸 감지 |
| STT 음성 명령 | ✅ 완료 | Android SpeechRecognizer, 3모드 전환 |
| 카메라 방향 자동 감지 | ✅ 완료 | 가속도 센서, front/left/right/back |
| 온디바이스 추론 (ONNX) | ✅ 완료 | yolo11m.onnx 76.8MB, 서버 없이 동작 |
| **Failsafe 음성 경고** | ✅ 완료 | 3회 실패/6초 무응답 → 음성 경고 |

---

## 2. 실기기 데모 가이드

> 에뮬레이터/데스크탑 X — Samsung Galaxy Z Fold 4 실기기 데모

### 데모 환경

| 항목 | 내용 |
|------|------|
| 실기기 | Samsung Galaxy Z Fold 4 (SM-F936N, Android 14) |
| 서버 PC | Intel Core Ultra 7 265K, Windows 11 |
| 연결 방식 | 같은 Wi-Fi 로컬 IP (`http://172.30.1.36:8000`) |
| 온디바이스 모드 | yolo11m.onnx 탑재, 서버 없이 폰 단독 동작 |
| 데모 시나리오 | 폰 들고 장애물 앞 이동 → **1초**마다 자동 분석 → 음성 안내 |

### 실행 순서

**1단계: 서버 실행 (PC)**

```cmd
cd C:\VoiceGuide\VoiceGuide
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

→ `Uvicorn running on http://0.0.0.0:8000` 확인

**2단계: 앱 실행 (폰)**

1. VoiceGuide 앱 실행
2. URL 입력란에 `http://172.30.1.36:8000` 입력
3. **분석 시작** 버튼 탭
4. 카메라가 켜지며 2초마다 자동 분석 + 음성 안내 시작

### 데모 시나리오

| 상황 | 예상 음성 출력 |
|------|--------------|
| 의자가 정면 가까이 | "멈추세요! 바로 앞에 의자가 있어요. 약 50센티미터 거리예요." |
| 사람이 왼쪽 앞 | "왼쪽 앞에 사람이 있어요. 약 1.2미터 거리예요. 오른쪽으로 피해가세요." |
| 가방이 오른쪽 | "오른쪽에 가방이 있어요. 약 2.0미터예요." |
| 장애물 없음 | (음성 없음, 화면에 "장애물 없음" 표시) |

### 앱 구조

```
[CameraX 라이브 프리뷰]
        ↓ 2초마다 자동 캡처
[이미지 → 서버 POST]
        ↓
[YOLO11m 추론 → 방향/거리 계산 → 한국어 문장 생성]
        ↓
[앱 화면 텍스트 + Android TTS 음성 출력]
```

### 주의사항

- 서버 PC와 폰이 **같은 Wi-Fi**에 연결되어 있어야 함
- 서버 터미널은 데모 중 계속 켜져 있어야 함
- 미디어 볼륨이 올라가 있어야 TTS 음성이 들림
- 처음 실행 시 YOLO 워밍업으로 약 10초 소요 (이후 정상 속도)

---

## 3. 모델 선정 결과

### 실험한 모델 비교

| 모델 | 파라미터 | 파일 크기 | mAP50-95 | 비고 |
|------|---------|---------|----------|------|
| YOLO11n | 2.6M | 5.4MB | 39.5 | 초기 채택, 오탐 많음 |
| **YOLO11m** | 20.1M | 38.8MB | 51.5 | **최종 채택** |

### 선정 이유

- **YOLO11n**: 속도는 빠르나 신뢰도 0.15 이하에서 손·팔을 사람으로 오인하는 오탐 다수 발생
- **YOLO11m**: 정확도 약 30% 향상, PC CPU 환경에서 충분히 빠른 응답 속도 확인
- 시각장애인 보행 안전 특성상 오탐보다 **정확한 탐지**를 우선

### 탑재 환경

| 항목 | 내용 |
|------|------|
| 프레임워크 | Ultralytics 8.4.x |
| 모델 포맷 | PyTorch `.pt` (서버 직접 로드) |
| 입력 해상도 | 640 × 640 |
| 실행 환경 | PC CPU (Intel Core Ultra 7 265K) |
| 신뢰도 임계값 | 0.60 (기본) / 클래스별 별도 적용 |
| NMS IoU 임계값 | Ultralytics 기본값 |

### 추론 파이프라인

```
Android 폰 (카메라 캡처, 640px로 리사이즈)
    ↓ HTTP POST (로컬 Wi-Fi)
FastAPI 서버
    ↓
YOLO11m 추론 → [객체, bbox, 신뢰도]
    ↓
방향 계산 (이미지 9구역 → 시계 방향 → 한국어 방향)
    ↓
거리 계산 (bbox 면적 비율 → 미터/센티미터 변환)
    ↓
위험도 점수 산출 (방향 가중치 × 거리 가중치)
    ↓
상위 2개 장애물 선택 → 한국어 문장 생성
    ↓
Android 앱 TTS 출력
```

### 인식 대상 클래스 (COCO 80클래스 전체)

초기에는 6개 클래스(사람·의자·테이블·가방·휴대폰)만 탐지하였으나,  
실제 보행 환경을 고려해 COCO 80클래스 전체로 확장.  
등록된 클래스는 한국어 명칭으로, 미등록 클래스는 **"알 수 없는 물체"** 로 처리.

| 카테고리 | 주요 클래스 |
|---------|------------|
| 사람/동물 | 사람, 개, 고양이 |
| 탈것 | 자전거, 자동차, 오토바이, 버스, 트럭, 기차 |
| 가구 | 의자, 소파, 테이블, 침대, 변기, 세면대, 냉장고 |
| 야외 구조물 | 벤치, 화분, 소화전, 정지 표지판, 신호등 |
| 소지품 | 가방, 여행가방, 우산 |
| 전자기기 | TV, 노트북, 휴대폰, 키보드 |
| 기타 | 병, 컵, 책 등 |

### 추론 결과 예시

| 입력 이미지 상황 | 탐지 결과 | 출력 문장 |
|--------------|---------|---------|
| 정면 60cm 앞 휴대폰 | cell phone, conf=0.82 | "멈추세요! 바로 앞에 휴대폰이 있어요. 약 60센티미터 거리예요." |
| 왼쪽 앞 1.2m 의자 | chair, conf=0.76 | "왼쪽 앞에 의자가 있어요. 약 1.2미터 거리예요. 오른쪽으로 피해가세요." |
| 오른쪽 2.5m 키보드 | keyboard, conf=0.61 | "오른쪽에 키보드가 있어요. 약 2.5미터예요." |
| 탐지 없음 | — | "주변에 장애물이 없어요." |

### 신뢰도 임계값 실험

| CONF 값 | 결과 |
|---------|------|
| 0.15 | 오탐 많음 (손·팔을 사람으로 인식) |
| 0.25 | 이미지 축소 후 일부 물체 미탐지 |
| 0.40 | 오탐 감소, 일부 오탐 잔존 |
| 0.45 | 오탐/미탐 균형점 (초기 채택) |
| **0.60** | 오탐 대폭 감소, 시각장애인 안전 고려 **현재 적용** |

---

## 4. 알고리즘 명세

### 방향 구역 정의

| 이미지 x 비율 | 시계 방향 | 자연어 표현 | 위험도 가중치 |
|-------------|---------|-----------|------------|
| 0.00 ~ 0.11 | 8시 | 왼쪽 | 0.3 |
| 0.11 ~ 0.22 | 9시 | 왼쪽 | 0.5 |
| 0.22 ~ 0.33 | 10시 | 왼쪽 앞 | 0.7 |
| 0.33 ~ 0.44 | 11시 | 왼쪽 앞 | 0.9 |
| 0.44 ~ 0.56 | 12시 | 바로 앞 | 1.0 |
| 0.56 ~ 0.67 | 1시 | 오른쪽 앞 | 0.9 |
| 0.67 ~ 0.78 | 2시 | 오른쪽 앞 | 0.7 |
| 0.78 ~ 0.89 | 3시 | 오른쪽 | 0.5 |
| 0.89 ~ 1.00 | 4시 | 오른쪽 | 0.3 |

### 거리 구역 정의

| bbox 면적 비율 | 대략 거리 | 레이블 | 위험도 가중치 |
|-------------|---------|--------|------------|
| > 0.25 | ~0.5m | 매우 가까이 | 1.0 |
| > 0.12 | ~1.0m | 가까이 | 0.8 |
| > 0.04 | ~2.0m | 보통 | 0.5 |
| > 0.01 | ~4.0m | 멀리 | 0.2 |
| ≤ 0.01 | ~4.0m+ | 매우 멀리 | 0.1 |

### 음성 출력 문장 구조

| 거리 단계 | 문장 구조 | 예시 |
|---------|---------|------|
| 매우 가까이 | `{행동}! {방향}에 {물체}이/가 있어요. {거리} 거리예요.` | "멈추세요! 바로 앞에 의자가 있어요. 약 30센티미터 거리예요." |
| 가까이 | `{방향}에 {물체}이/가 있어요. {거리} 거리예요. {행동}.` | "왼쪽 앞에 의자가 있어요. 약 1.2미터 거리예요. 오른쪽으로 피해가세요." |
| 보통/멀리 | `{방향}에 {물체}이/가 있어요. {거리}예요.` | "오른쪽에 소파가 있어요. 약 2.5미터예요." |

---

## 5. 기술 스택

| 영역 | 라이브러리 | 버전 | 비고 |
|------|----------|------|------|
| 객체 탐지 | Ultralytics YOLO11m | 8.4.x | yolo11m.pt 사전 학습 모델 |
| 깊이 추정 | Depth Anything V2 | vits | ✅ GPU 활성화, depth_source="v2" |
| 딥러닝 | PyTorch | 2.x | CUDA (RTX 5060) |
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

## 6. 트러블슈팅

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

### 3. `TypeError: argument of type 'bool' is not iterable` (Gradio 실행 중)
```
File "...gradio_client/utils.py", line 863, in get_type
    if "const" in schema:
TypeError: argument of type 'bool' is not iterable
```
**원인**: `gradio_client 1.3.0`이 pydantic 생성 JSON Schema의 `additionalProperties: true/false`를 처리하지 못하는 버그  
**해결**: 패치 스크립트 1회 실행 (`pip install -r requirements.txt` 후마다 재실행 필요)
```bash
python patch_gradio_client.py
```

---

### 4. `ValueError: When localhost is not accessible`
```
ValueError: When localhost is not accessible, a shareable link must be created.
Please set share=True or check your proxy settings to allow access to localhost.
```
**원인**: 방화벽·VPN 등 일부 환경에서 Gradio가 localhost 접근 가능 여부 확인 실패  
**해결**: `--share` 플래그로 실행
```bash
python app.py --share
```

---

### 5. Depth Anything V2 모델 파일 없음
```
FileNotFoundError: depth_anything_v2_vits.pth
```
**현재 상태**: `detect_and_depth()`에서 Depth V2 호출이 주석 처리되어 있어 앱 실행에는 영향 없음  
**활성화 방법**: 가중치 파일 다운로드 후 `VoiceGuide/` 루트에 배치, `depth.py` 주석 해제

---

### 6. PyAudio 설치 오류 (Windows)
```
error: Microsoft Visual C++ 14.0 or greater is required
```
**원인**: Windows에서 PyAudio는 C++ 컴파일러 필요  
**해결**: conda 환경에서 설치
```bash
conda install pyaudio
```

---

### 7. gTTS 음성 재생 안 됨
```
pygame.error: No available audio device
```
**원인**: 서버/헤드리스 환경에서 오디오 장치 없음  
**해결**: 로컬 실행 환경에서만 TTS 동작. Android 앱은 기본 TTS 사용으로 해결

---

### 8. 포트 8000 이미 사용 중
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

### 9. ngrok 터널 이미 온라인
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

### 10. winget 명령어 없음
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

### 11. TFLite 변환 실패 (Python 3.13)
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

### 12. ultralytics 모듈 없음
```
ModuleNotFoundError: No module named 'ultralytics'
```
**해결**: `pip install ultralytics`

---

### 13. 앱이 "분석 중..."에서 멈춤
**원인 1**: uvicorn 서버 미실행  
**원인 2**: URL 오입력 (http:// 누락, 포트 오류)  
**원인 3**: 폰과 PC가 다른 네트워크  
**해결**: 서버 실행 확인 → URL 재확인 → 같은 Wi-Fi 연결 확인

---

### 14. 없는 물체를 인식하는 오탐
**원인**: 신뢰도 임계값이 낮으면 손·팔 등을 다른 물체로 오인  
**현재 설정**: `CONF_THRESHOLD = 0.60` (`src/vision/detect.py`)  
**추가 적용**: 병·컵·휴대폰 등 소형 물체는 0.70~0.72 별도 적용

---

## 7. 구현 애로사항

| 항목 | 내용 |
|------|------|
| 브랜치 병합 충돌 | feature/android와 main의 히스토리가 달라 `--allow-unrelated-histories` 필요. 병합 시 routes.py, tts.py, templates.py 등 핵심 파일이 구버전으로 덮어써짐 → 수동 복원 |
| Python 3.13 호환성 | TFLite 변환에 필요한 tensorflow가 Python 3.13 미지원 → ONNX Runtime으로 전환 |
| 방향 오류 | camera_orientation을 "back"으로 전송 시 방향이 180도 반전 → "front"로 수정 |
| 오탐 문제 | 신뢰도 임계값 0.15에서 손·팔을 사람으로 오인. 단계적으로 0.45 → 0.60으로 조정 후 해결 |
| 문장 어색함 | "앞 왼쪽", "휴대폰가" 등 비자연스러운 표현 → 이/가 조사 자동화, 방향 표현 재설계 |
| 응답 반복 | 3초마다 같은 문장 반복 안내 → 동일 문장 필터링 + TTS 중 텍스트 교체 방지 |
| gradio_client 버그 | pydantic 생성 JSON Schema의 bool 값 처리 오류 → 자동 패치 스크립트(`patch_gradio_client.py`) 작성으로 해결 |

---

## 8. 설계 제한사항 (현재 상태 기준)

| 항목 | 현재 방식 | 상태 | 남은 제한 |
|------|---------|------|---------|
| 거리 추정 | Depth Anything V2 | ✅ 활성화 | 실측 캘리브레이션 필요 (CALIBRATION_TEST.md 참조) |
| 카메라 방향 | 가속도 센서 자동 감지 | ✅ 완료 | — |
| 추론 위치 | 서버+온디바이스 이중 | ✅ 완료 | — |
| 연결 방식 | 서버 또는 완전 독립 | ✅ 완료 | — |
| 응답 속도 | 1초 간격 | ✅ 개선 | 연속 스트리밍 아님 |
| 계단 탐지 | YOLO+Depth 이중 | ✅ 완료 | 비정형 계단 일반화 미검증 |
| 투명 장애물 | 미지원 | ⚠️ 한계 | 유리문·유리벽은 탐지 불가 |
| 문장 중복 | 동일 문장 필터링 | ✅ 완료 | — |

---

## 9. 환경 세팅 요약

```bash
# 1. conda 환경 생성
conda create -n voiceguide python=3.10
conda activate voiceguide

# 2. PyAudio (Windows — pip으로 설치 불가)
conda install pyaudio

# 3. 패키지 설치 + gradio_client 패치
pip install -r requirements.txt
python patch_gradio_client.py   # pip 재설치 후마다 재실행

# 4. 환경변수
cp .env.example .env

# 5. 서버 실행
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 6. 로컬 IP 확인 (폰 연결용)
ipconfig

# 7. ngrok (폰과 PC가 다른 네트워크일 때)
set PATH=%PATH%;C:\ngrok
ngrok config add-authtoken 본인토큰
ngrok http 8000

# 8. Gradio 데모 (선택)
python app.py           # 로컬
python app.py --share   # 외부 접근
```
