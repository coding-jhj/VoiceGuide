# VoiceGuide 실행 가이드

## 사전 준비

- Python 3.10 (anaconda `ai_env` 환경)
- Android Studio (앱 빌드용, 최초 1회)
- Samsung Galaxy Z Fold 4 (또는 Android 8.0+)

---

## 1단계: 코드 받기

```bash
git clone https://github.com/coding-jhj/VoiceGuide.git
cd VoiceGuide/VoiceGuide
```

---

## 2단계: 패키지 설치

```bash
conda activate ai_env
pip install -r requirements.txt
python patch_gradio_client.py   # gradio_client 버그 패치 (1회)
```

---

## 3단계: AI 모델 다운로드 (최초 1회)

### Depth Anything V2 가중치 (94MB)

```bash
python -c "
import urllib.request
urllib.request.urlretrieve(
    'https://huggingface.co/depth-anything/Depth-Anything-V2-Small/resolve/main/depth_anything_v2_vits.pth',
    'depth_anything_v2_vits.pth')
print('완료')
"
```

> YOLO11m 가중치(`yolo11m_indoor.pt`, `yolo11m.pt`)는 저장소에 없음 (용량 큼).  
> `yolo11m.pt`는 서버 첫 실행 시 Ultralytics가 자동 다운로드.  
> `yolo11m_indoor.pt`(파인튜닝 모델)는 팀원에게 직접 받을 것.

---

## 4단계: 서버 실행

```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

→ `Uvicorn running on http://0.0.0.0:8000` 뜨면 성공. 터미널 닫지 말 것.

**서버 시작 시 자동으로:**
- DB 초기화
- YOLO 워밍업 (첫 요청 지연 방지)
- Depth V2 모델 파일 확인 (없으면 bbox 기반으로 자동 전환)

---

## 5단계: 서버 주소 확인

### 방법 A: 로컬 IP (권장 — 빠름, 같은 WiFi)

```bash
ipconfig   # Windows
```

`IPv4 주소` 항목의 `192.168.x.x` 확인 → 앱 URL:
```
http://192.168.x.x:8000
```

### 방법 B: ngrok (다른 네트워크)

```bash
ngrok http 8000
```
→ `https://xxxx.ngrok-free.app` URL 복사

---

## 6단계: Gradio 데모 실행 (발표·시연용)

```bash
# 로컬 브라우저
python app.py

# 폰·외부에서 접속 (공개 URL 생성)
python app.py --share
```

→ `http://localhost:7860` 브라우저에서 열림  
→ 이미지 업로드 → 장애물/찾기/확인 모드 선택 → 분석 결과 + 음성 출력

---

## 7단계: Android 앱 설치

### 케이블 없이 설치하는 방법 (권장)

```
Android Studio → Build → Build APK(s)
→ android/app/build/outputs/apk/debug/app-debug.apk 생성
→ 카카오톡/구글드라이브로 폰에 전송
→ 폰에서 파일 열어 설치
  (설정 → 보안 → 출처를 알 수 없는 앱 허용)
```

### 케이블로 설치하는 방법

```
Android Studio → 폰 USB 연결 → USB 디버깅 ON → ▶ Run
```

---

## 8단계: 앱 사용

| 모드 | 사용법 |
|------|--------|
| 서버 모드 | URL 입력 → 분석 시작 → 1초마다 자동 안내 |
| 온디바이스 모드 | 서버 없어도 자동 감지 (yolo11m.onnx 필요) |
| 음성 명령 | "음성 명령" 버튼 → "주변 알려줘 / 찾아줘 / 이거 뭐야" |

---

## 주의사항

| 항목 | 내용 |
|------|------|
| 속도 | 로컬 IP가 ngrok보다 훨씬 빠름 |
| 볼륨 | 음성 안내는 미디어 볼륨 → 미디어 볼륨 확인 |
| 서버 유지 | 서버 터미널은 데모 중 계속 켜져 있어야 함 |
| 서버 끊김 | 자동으로 "서버 연결 끊겼어요. 주의해서 이동하세요." 음성 출력 |
| 모델 경로 | yolo11m_indoor.pt 있으면 자동 로드, 없으면 yolo11m.pt 자동 fallback |
