# VoiceGuide ngrok 외부 접속 가이드

로컬 서버를 ngrok으로 외부(다른 네트워크, 폰 LTE 등)에서 접근 가능하게 만드는 방법입니다.

---

## 한 번에 시작 (권장)

프로젝트 루트(`VoiceGuide/`)에서:

```bat
start.bat
```

창 2개가 자동으로 열립니다:
- `VoiceGuide-Server` — FastAPI 서버 (포트 8000)
- `VoiceGuide-ngrok` — ngrok 터널 (외부 URL 생성)

ngrok 창에서 `Forwarding` 줄의 URL을 Android 앱에 입력합니다.

```
Forwarding  https://jubilant-trimmer-reggae.ngrok-free.app -> http://localhost:8000
```

---

## 수동 실행 (두 CMD 창)

### 창 1: FastAPI 서버

```bat
cd /d "C:\VoiceGuide\VoiceGuide"
conda activate ai_env
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

로컬 확인:
- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

> 주의: `http://0.0.0.0:8000`은 브라우저 접속 주소가 아닙니다.

### 창 2: ngrok 터널

서버가 뜬 후(3~4초 대기):

```bat
ngrok http 8000
```

출력 예시:
```
Forwarding  https://jubilant-trimmer-reggae.ngrok-free.app -> http://localhost:8000
```

`https://...ngrok-free.app` 부분이 외부 접속 주소입니다.

---

## Supabase DB 연결 (선택)

DB를 외부 PostgreSQL(Supabase)로 쓰려면 `.env` 파일에 추가:

```bash
DATABASE_URL=postgresql://postgres.XXXXX:비밀번호@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres
```

> `.env` 파일은 절대 git에 커밋하지 마세요 (`.gitignore`에 포함됨).  
> `서버_DB/SUPABASE_DB_CONNECT_GUIDE.md` 참고.

---

## Android 앱 연결

1. ngrok 창에서 `Forwarding https://...` URL 복사
2. 앱 우상단 설정(⚙) → 서버 URL에 붙여넣기
3. "분석 시작" 버튼 탭

| 환경 | URL |
|------|-----|
| 같은 WiFi (빠름) | `http://192.168.x.x:8000` |
| 다른 네트워크/LTE | ngrok URL |

> 참고: Android `장애물`/`찾기` 모드는 서버 URL이 있어도 온디바이스 ONNX를 우선 사용합니다.  
> ngrok URL은 질문, 색상, 신호등, 서버 TTS/대시보드 등 서버 연동 기능이 필요할 때 입력하면 됩니다.

---

## 자주 겪는 문제

| 문제 | 원인 | 해결 |
|------|------|------|
| ngrok URL 변경됨 | 무료 플랜은 재시작마다 URL 변경 | 앱에 새 URL 다시 입력 |
| `/health` 응답 없음 | uvicorn 미시작 또는 포트 충돌 | `stop.bat` 후 `start.bat` 재실행 |
| "DB 비밀번호 없음" 오류 | `.env` 미설정 | `.env`에 `DATABASE_URL` 추가 (없으면 SQLite 자동 사용) |
| ngrok "Your connection..." 화면 | ngrok 브라우저 경고 | API 호출은 정상 — 브라우저로 직접 열면 경고 페이지 표시 |
| 서버 URL 입력 후 장애물 인식이 안 됨 | 예전 APK 또는 잘못된 `android/` 프로젝트 설치 가능 | `C:\VoiceGuide\VoiceGuide\android` 최신 APK를 설치하고, 필요 시 설정 버튼 길게 눌러 디버그 오버레이 확인 |

---

## 빠른 확인 체크리스트

- [ ] `start.bat` 실행 (또는 두 창 수동 실행)
- [ ] `http://127.0.0.1:8000/health` → `{"status":"ok"}` 응답 확인
- [ ] ngrok 창에 `Forwarding https://...` URL 표시 확인
- [ ] `https://[ngrok주소]/health` 외부에서 응답 확인
- [ ] Android 앱 설정에 ngrok URL 입력 후 서버 기능 확인
- [ ] 기본 장애물/찾기 모드는 ngrok 없이도 ONNX 탐지되는지 확인
