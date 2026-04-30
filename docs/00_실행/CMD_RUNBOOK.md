# VoiceGuide CMD 실행 순서

> Windows CMD 기준입니다. PowerShell이 아니라 `cmd.exe`에서 그대로 복붙하면 됩니다.

## 0. 현재 코드 받기

```bat
cd /d C:\VoiceGuide\VoiceGuide
git pull origin main
```

## 1. GCP 서버 재배포

코드를 수정한 뒤에는 GitHub에 push만 해서는 GCP 서버가 자동으로 바뀌지 않습니다.
Cloud Run에 다시 배포해야 서버 로그의 `[LINK]`, `[PERF]`, `request_id`가 보입니다.

```bat
cd /d C:\VoiceGuide\VoiceGuide

gcloud run deploy voiceguide ^
  --source . ^
  --region asia-northeast3 ^
  --memory 2Gi ^
  --cpu 2 ^
  --timeout 120 ^
  --allow-unauthenticated ^
  --port 8080
```

배포가 끝나면 아래 서버 URL을 사용합니다.

```text
https://voiceguide-135456731041.asia-northeast3.run.app
```

한 줄로 실행하고 싶으면:

```bat
gcloud run deploy voiceguide --source . --region asia-northeast3 --memory 2Gi --cpu 2 --timeout 120 --allow-unauthenticated --port 8080
```

## 2. 앱 없이 서버-대시보드 연동 확인

Android를 실행하기 전에 더미 클라이언트로 `/detect`, `/status`, `/dashboard`가 이어지는지 먼저 확인합니다.

```bat
cd /d C:\VoiceGuide\VoiceGuide
python tools\probe_server_link.py --base https://voiceguide-135456731041.asia-northeast3.run.app
```

정상 기준:

```text
[detect] HTTP 200
[status] HTTP 200
[dashboard] HTTP 200
[probe] OK: /detect, /status, and /dashboard are reachable and correlated.
```

이 단계가 성공하면 서버, DB/tracker, 대시보드는 붙어 있는 것입니다.

## 3. GCP 서버 로그 보기

Android 앱에서 요청을 보낼 때 같은 `request_id`가 서버 로그에 찍히는지 확인합니다.

```bat
gcloud run services logs tail voiceguide --region asia-northeast3
```

서버 로그 정상 예:

```text
[LINK] request_id=and-... START mode=질문 session=...
[PERF] request_id=and-... detect=...ms | tracker=...ms | nlg+rest=...ms | TOTAL=...ms | objs=...
```

## 4. Android Studio에서 앱 실행

Android Studio에서 열어야 하는 폴더:

```text
C:\VoiceGuide\VoiceGuide\android
```

주의:

```text
C:\VoiceGuide\android
```

위 폴더는 예전 프로젝트가 섞여 있을 수 있으므로 최신 확인용으로 열지 않습니다.

실행 순서:

1. 휴대폰 USB 연결
2. 휴대폰 개발자 옵션에서 USB 디버깅 ON
3. Android Studio에서 `C:\VoiceGuide\VoiceGuide\android` 열기
4. 상단 `Run` 버튼 실행
5. 앱 우상단 설정에서 서버 URL 입력

```text
https://voiceguide-135456731041.asia-northeast3.run.app
```

## 5. Android Logcat 확인

Android Studio Logcat 필터:

```text
VG_FLOW|VG_LINK|VG_PERF|VG_DETECT
```

정상 기준:

```text
VG_FLOW request_id=and-... route=on_device mode=장애물
VG_PERF request_id|and-...|route|on_device|decode|...|infer|...|total|...
```

질문/색상/서버 기능 정상 기준:

```text
VG_LINK request_id=and-... response_id=and-... status=200 total=...ms server=...ms
VG_PERF request_id|and-...|route|server|server_ms|...|net_ms|...
```

Android Logcat의 `request_id=and-...`와 GCP 로그의 `request_id=and-...`가 같으면 서버-클라이언트 연동이 확인된 것입니다.

## 6. 현재 구조 요약

| 항목 | 현재 상태 |
|---|---|
| 장애물/찾기 | Android ONNX 우선 실행 |
| 질문/색상/서버 기능 | GCP 서버 사용 |
| Android YOLO | TFLite 아님, ONNX Runtime 사용 |
| 서버 YOLO | Python 서버에서 추론 |
| 연동 확인 | `request_id`로 Android 로그와 GCP 로그 매칭 |
| FPS/추론속도 확인 | `VG_PERF`, `[PERF]` 로그 확인 |

## 7. 문제별 판단

| 증상 | 먼저 볼 로그 |
|---|---|
| 장애물 인식이 전혀 안 됨 | Android Logcat `VG_FLOW`, `VG_DETECT`, `VG_PERF` |
| 서버와 붙었는지 모르겠음 | Android `VG_LINK`와 GCP `[LINK]`의 같은 `request_id` |
| FPS가 말이 안 되게 낮음 | `VG_PERF`의 `infer`, `server_ms`, `net_ms`, `total` |
| 서버 응답이 느림 | GCP `[PERF]`의 `detect`, `tracker`, `TOTAL` |
| 앱에서만 안 됨 | `probe_server_link.py` 먼저 성공하는지 확인 |
