# VoiceGuide 외부 서버 배포 가이드 (LTE 테스트용)

WiFi 없이 LTE 환경에서 앱을 테스트하려면 서버를 인터넷에 공개해야 합니다.  
아래 방법 중 하나를 선택하세요. **모두 무료**입니다.

---

## 방법 1 — Railway (추천, 가장 간단)

### 1단계: Supabase DB 세팅

Supabase는 무료 PostgreSQL DB를 제공합니다.

1. [supabase.com](https://supabase.com) → 무료 계정 생성
2. New Project 생성
3. **Project Settings → Database → Connection string** → **Session pooler** 탭 선택
4. 연결 문자열 복사 (형식: `postgresql://postgres.xxx:password@aws-xxx.pooler.supabase.com:5432/postgres`)
5. 프로젝트 루트 `.env` 파일에 붙여넣기:
   ```
   DATABASE_URL=postgresql://postgres.xxx:PASSWORD@aws-xxx.pooler.supabase.com:5432/postgres?sslmode=require
   ```
6. 서버 재시작 → 자동으로 Supabase에 테이블 생성됨

> ⚠️ 테이블은 서버 처음 시작 시 자동 생성됩니다. Supabase SQL Editor에서 수동 생성 불필요.

### 2단계: Railway 배포

Railway는 FastAPI 앱을 무료로 호스팅해줍니다.

1. [railway.app](https://railway.app) → GitHub 계정으로 로그인
2. **New Project → Deploy from GitHub repo** → `VoiceGuide` 선택
3. **Variables** 탭에서 환경변수 추가:
   ```
   DATABASE_URL = (Supabase 연결 문자열)
   ELEVENLABS_API_KEY = (선택)
   ```
4. 배포 완료 후 **Settings → Networking → Generate Domain** 클릭
5. 생성된 URL (예: `https://voiceguide-xxx.up.railway.app`)을 Android 앱 서버 URL에 입력

> Railway 무료 플랜: 월 500시간, 512MB RAM  
> ⚠️ Depth Anything V2 모델(76MB)은 Railway에 포함되지 않으므로 bbox 기반 거리 추정으로 자동 전환됩니다.

### 3단계: 확인

```bash
# 서버 상태 확인
curl https://voiceguide-xxx.up.railway.app/health

# 예상 응답
{
  "status": "ok",
  "depth_v2": "fallback (bbox)",  # 외부 서버에서는 정상
  "db_mode": "postgresql"
}
```

---

## 방법 2 — ngrok (빠른 임시 테스트)

PC에서 서버를 켜고 임시 공개 URL을 만듭니다.

```bash
# 서버 실행
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 다른 터미널에서 (ngrok 설치 필요: https://ngrok.com)
ngrok http 8000

# 생성된 URL 예시: https://xxxx.ngrok-free.app
```

- 장점: 즉시 사용, Depth V2 GPU 가속 가능
- 단점: PC가 켜져 있어야 함, URL이 재시작마다 바뀜

---

## DB 모드 확인

서버 시작 로그에서 확인:
```
[DB] 초기화 완료 (SQLite)        ← 로컬
[DB] 초기화 완료 (PostgreSQL/Supabase) ← 외부
```

또는 `/health` 엔드포인트:
```json
{
  "db_mode": "postgresql"   ← Supabase 연결됨
  "db_mode": "sqlite"       ← 로컬 SQLite
}
```

---

## Depth Anything V2 상태 확인

```bash
curl http://localhost:8000/health
```

```json
{
  "depth_v2": "loaded"          ← 모델 정상 로드 (GPU 있을 때)
  "depth_v2": "fallback (bbox)" ← 모델 없음, bbox 거리 추정 사용
}
```

모델 파일이 없으면 자동으로 bbox 기반으로 전환됩니다. 별도 에러 없이 정상 동작합니다.

### 모델 수동 다운로드

```bash
python -c "
import urllib.request
urllib.request.urlretrieve(
    'https://huggingface.co/depth-anything/Depth-Anything-V2-Small/resolve/main/depth_anything_v2_vits.pth',
    'depth_anything_v2_vits.pth')
print('다운로드 완료')
"
```
