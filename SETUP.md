# VoiceGuide 실행 가이드

## 사전 준비

- Python 3.10 (anaconda `ai_env` 환경)
- Android Studio (앱 빌드용, 최초 1회)
- Samsung Galaxy Z Fold 4 (또는 Android 8.0+)

---

## 1단계: 코드 받기

**처음 받는 경우:**
```bash
git clone https://github.com/coding-jhj/VoiceGuide.git
cd VoiceGuide/VoiceGuide
```

**이미 받은 경우 (최신으로 업데이트):**
```bash
git pull origin main
pip install -r requirements.txt   # 새 패키지 있을 수 있음
```

---

## 2단계: 패키지 설치

```bash
conda activate ai_env
pip install -r requirements.txt
python tools/patch_gradio_client.py   # gradio_client 버그 패치 (1회)
```

---

## 2.5단계: 환경변수 설정 (.env)

```bash
# .env.example을 복사해서 .env 생성
copy .env.example .env   # Windows
```

`.env` 파일을 열고 아래 값을 채워주세요:

```
ELEVENLABS_API_KEY=받은_키_입력   # Gradio 데모 TTS용 (앱은 없어도 됨)
OPENAI_API_KEY=                   # 옷 매칭 기능 사용 시만 필요
```

> Android 앱 기본 동작(YOLO+TTS)에는 API 키 불필요. Gradio 데모 음성 기능만 키 필요.

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

## 6단계: Android 앱 설치 (실제 사용)

### 방법 A: APK 직접 설치 (권장 — 가장 빠름)

```
1. 조장에게 APK 파일 받기 (카카오톡 또는 구글드라이브)
2. 폰에서 APK 파일 열기
3. 설정 → 보안 → 출처를 알 수 없는 앱 허용
4. 설치 완료
```

### 방법 B: Android Studio로 직접 빌드

```
Android Studio → android/ 폴더 열기 → Build → Build APK(s)
→ android/app/build/outputs/apk/debug/app-debug.apk 생성
→ 카카오톡/구글드라이브로 폰에 전송 후 설치
```

### 방법 C: USB 케이블로 바로 설치

```
Android Studio → 폰 USB 연결 → USB 디버깅 ON → ▶ Run
```

---

## 7단계: 앱 사용

| 기능 | 사용법 |
|------|--------|
| 기본 분석 | 앱 실행 → "분석 시작" 버튼 (서버 URL 불필요) |
| 서버 연동 (선택) | 우상단 설정(⚙) → 서버 URL 입력 |
| 장애물/찾기 모드 | 서버 URL이 있어도 ONNX 우선 사용 → 서버 없이도 동작 |
| 디버그 모드 | 설정에서 켜기 또는 설정 버튼 길게 누르기 |
| 음성 명령 — 장애물 | "주변 알려줘", "앞에 뭐 있어" |
| 음성 명령 — 찾기 | "의자 찾아줘", "가방 어디있어" |
| 음성 명령 — 저장 | "여기 저장해줘 편의점" |
| 음성 명령 — 목록 | "저장된 곳 알려줘" |

---

## [선택] Gradio 데모 실행 (강사님 시연용)

서버 화면에서 이미지 업로드로 테스트하고 싶을 때만 사용합니다.

```bash
python app.py           # 로컬 브라우저
python app.py --share   # 외부 접속 URL 생성
```

---

## 주의사항

| 항목 | 내용 |
|------|------|
| 속도 | 로컬 IP가 ngrok보다 훨씬 빠름 |
| 볼륨 | 음성 안내는 미디어 볼륨 → 미디어 볼륨 확인 |
| 서버 유지 | 서버 터미널은 데모 중 계속 켜져 있어야 함 |
| 서버 끊김 | 장애물/찾기는 ONNX로 계속 동작, 서버 전용 기능은 실패 안내 |
| 모델 경로 | yolo11m_indoor.pt 있으면 자동 로드, 없으면 yolo11m.pt 자동 fallback |
