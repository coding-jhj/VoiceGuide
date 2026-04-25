# VoiceGuide MVP 실행 가이드

## 사전 준비

- Python 3.10+
- Android Studio
- Android 폰 (USB 케이블)

---

## 1단계: 코드 받기

```cmd
git clone https://github.com/coding-jhj/VoiceGuide.git
cd VoiceGuide
```

---

## 2단계: Python 패키지 설치

```cmd
pip install -r requirements.txt
pip install ultralytics
```

> 첫 실행 시 YOLO 모델(yolo11m.pt)이 자동 다운로드됩니다. (약 2분, 인터넷 필요, 약 40MB)

---

## 3단계: 서버 실행

```cmd
cd VoiceGuide
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

→ `Uvicorn running on http://0.0.0.0:8000` 뜨면 성공. 창 닫지 말 것.

---

## 4단계: 서버 URL 확인 (2가지 방법)

### ✅ 방법 A: 로컬 IP (권장 — 빠름)

**폰과 PC가 같은 와이파이에 연결된 경우**

```cmd
ipconfig
```

`IPv4 주소` 항목의 `192.168.x.x` 확인 → 앱에 입력할 URL:

```
http://192.168.x.x:8000
```

### 방법 B: ngrok (폰과 PC가 다른 네트워크인 경우)

1. [https://ngrok.com/download](https://ngrok.com/download) 에서 Windows용 다운로드
2. 압축 해제 후 `C:\ngrok` 폴더에 `ngrok.exe` 저장
3. ngrok.com 가입 후 토큰 연결

```cmd
ngrok config add-authtoken 본인토큰
```

새 터미널에서 실행:

```cmd
set PATH=%PATH%;C:\ngrok
ngrok http 8000
```

→ `Forwarding https://xxxx.ngrok-free.app` URL 복사

---

## 5단계: Android 앱 설치

1. Android Studio 실행
2. `Open` → `VoiceGuide/android` 폴더 선택
3. Gradle sync 완료 대기 (첫 실행 약 3~5분)
4. 폰을 USB로 PC에 연결
5. 폰에서 USB 디버깅 활성화
   - 설정 → 휴대전화 정보 → 소프트웨어 정보 → **빌드번호 7번 탭**
   - 설정 → 개발자 옵션 → **USB 디버깅 ON**
   - USB 연결 후 팝업 → **허용**
6. Android Studio 상단에서 기기 선택 후 ▶ **Run**

---

## 6단계: 앱 사용

1. 앱 실행 후 URL 입력란에 4단계에서 확인한 URL 붙여넣기
2. **분석 시작** 버튼 탭
3. 카메라가 켜지며 4초마다 자동 분석 + 음성 안내 시작
4. **분석 중지** 버튼으로 정지

---

## 주의사항

| 항목 | 내용 |
|------|------|
| 속도 | 로컬 IP가 ngrok보다 훨씬 빠름 — 같은 와이파이면 로컬 IP 사용 권장 |
| ngrok URL | 재실행할 때마다 URL이 바뀜 → 앱에 새 URL 다시 입력 |
| 볼륨 | 음성 안내는 미디어 볼륨으로 출력됨 → 미디어 볼륨 확인 |
| 서버 유지 | 서버 터미널은 데모 중 계속 켜져 있어야 함 |
| 첫 실행 | 서버 시작 시 YOLO 워밍업으로 약 10초 소요 — 이후 빠르게 동작 |
