# VoiceGuide 외부 서버 배포 가이드

LTE 환경에서 앱을 테스트하려면 서버를 인터넷에 공개해야 합니다.

---

## 먼저 알아야 할 것 — 서버 RAM 요구량

| 구성 | RAM 필요량 |
|------|----------|
| YOLO11m 모델 로드 | ~400MB |
| Depth Anything V2 모델 | ~300MB |
| FastAPI + 패키지들 | ~200MB |
| **합계** | **~900MB+** |

이 때문에 무료 클라우드 서버에서는 선택지가 갈립니다.

---

## 어떤 걸 선택할까?

```
Depth V2 없어도 괜찮아 (YOLO만, bbox 거리 추정)
  → 방법 A: Railway + Supabase  ← 가장 빠름, 5분 배포

Depth V2 포함 완전 기능이 필요해
  → 방법 B: Oracle Cloud Always Free  ← 무료인데 RAM 24GB, 단 설정 복잡
```

> 발표용 데모라면 **방법 A**로 충분합니다.  
> Depth V2는 PC(RTX 5060)에서만 돌리고, 외부 배포 서버는 API 역할만 해도 됩니다.

---

## 방법 A — Railway + Supabase (추천, 5분 배포)

> YOLO 탐지 + 방향 판단 + 문장 생성 → 정상 동작  
> Depth V2 → bbox 면적 기반 거리 추정으로 자동 대체 (에러 없음)  
> `/health` 응답: `{"depth_v2": "fallback (bbox)"}`  ← 정상

### 1단계: Supabase DB 만들기 (무료)

1. [supabase.com](https://supabase.com) 접속 → GitHub 계정으로 가입
2. **New Project** 생성 (이름, 비밀번호 설정)
3. **Project Settings → Database → Connection string**
4. **Session pooler** 탭 선택 → 연결 문자열 복사

   ```
   postgresql://postgres.xxxx:비밀번호@aws-xxx.pooler.supabase.com:5432/postgres
   ```

5. 프로젝트 루트 `.env` 파일에 붙여넣기:

   ```
   DATABASE_URL=postgresql://postgres.xxxx:비밀번호@aws-xxx.pooler.supabase.com:5432/postgres?sslmode=require
   ```

6. GitHub에 `.env`는 push하지 말 것 (`.gitignore`에 이미 포함됨)

### 2단계: Railway 배포 (무료)

1. [railway.app](https://railway.app) 접속 → GitHub 계정으로 로그인
2. **New Project → Deploy from GitHub repo** → `VoiceGuide` 선택
3. **Variables** 탭 클릭 → 아래 변수 추가:

   | 변수명 | 값 |
   |--------|---|
   | `DATABASE_URL` | Supabase 연결 문자열 |
   | `ELEVENLABS_API_KEY` | (선택, 없어도 됨) |

4. 자동으로 `railway.toml`을 읽고 배포 시작
5. 배포 완료 후 **Settings → Networking → Generate Domain** 클릭
6. 생성된 URL 확인 (예: `https://voiceguide-xxx.up.railway.app`)

### 3단계: 동작 확인

```bash
# 브라우저 또는 터미널에서
curl https://voiceguide-xxx.up.railway.app/health

# 정상 응답
{
  "status": "ok",
  "depth_v2": "fallback (bbox)",   ← 정상 (모델 파일 없어서 bbox 사용)
  "db_mode": "postgresql"           ← Supabase 연결됨
}
```

### 4단계: Android 앱 연결

앱 서버 URL 입력창에 Railway URL 입력:
```
https://voiceguide-xxx.up.railway.app
```

대시보드 접속:
```
https://voiceguide-xxx.up.railway.app/dashboard
```

### Railway 무료 플랜 한도

- 월 500시간 (한 서버 상시 운영 가능)
- 512MB RAM → YOLO11m 로드 가능, Depth V2는 bbox fallback 자동 전환
- sleep 없음 (Render와 달리 항상 켜져 있음)

---

## 방법 B — Oracle Cloud Always Free (완전 기능, Depth V2 포함)

> RAM 24GB → YOLO + Depth V2 완전 동작  
> 영구 무료 (기간 제한 없음)  
> 단점: 계정 생성에 1~2일, 초기 설정 30~60분

### 언제 선택하나

- 발표에서 Depth V2 정확한 거리 추정을 꼭 보여줘야 할 때
- 장기적으로 서버를 운영할 때

### 1단계: Oracle Cloud 계정 생성

1. [cloud.oracle.com](https://cloud.oracle.com) → **Start for free**
2. 신용카드 필요 (청구 안 됨, 본인 확인용)
3. 계정 심사 완료까지 수 시간 ~ 1일 소요

### 2단계: VM 생성

1. 콘솔 로그인 → **Compute → Instances → Create Instance**
2. **Shape** 에서 **VM.Standard.A1.Flex** 선택
   - `Always Free` 표시 확인
   - OCPU: 2, Memory: 12GB (무료 한도 내)
3. **Image**: Ubuntu 22.04
4. **Add SSH keys** → 키 파일 다운로드
5. **Create** 클릭

### 3단계: SSH 접속 및 서버 세팅

```bash
# SSH 접속
ssh -i 다운로드한키.pem ubuntu@VM공인IP

# 패키지 설치
sudo apt update && sudo apt install -y python3-pip python3-venv git

# 코드 복사
git clone https://github.com/coding-jhj/VoiceGuide.git
cd VoiceGuide

# 가상환경 + 패키지 설치 (ARM이라 5~10분 소요)
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Depth V2 모델 다운로드
python3 -c "
import urllib.request
urllib.request.urlretrieve(
    'https://huggingface.co/depth-anything/Depth-Anything-V2-Small/resolve/main/depth_anything_v2_vits.pth',
    'depth_anything_v2_vits.pth')
print('완료')
"

# .env 설정 (DATABASE_URL 등)
nano .env

# 서버 실행 (백그라운드)
nohup uvicorn src.api.main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
```

### 4단계: 방화벽 열기 (중요)

Oracle 콘솔에서도 포트를 열어야 합니다:

1. **Networking → Virtual Cloud Networks → VCN → Security Lists**
2. **Add Ingress Rule**:
   - Source CIDR: `0.0.0.0/0`
   - Destination Port: `8000`

```bash
# VM 내부에서도
sudo iptables -A INPUT -p tcp --dport 8000 -j ACCEPT
```

### 5단계: 확인

```bash
curl http://VM공인IP:8000/health

# 정상 응답
{
  "status": "ok",
  "depth_v2": "loaded",    ← Depth V2 정상 로드
  "device": "cpu",         ← ARM VM은 CPU (GPU 없음)
  "db_mode": "sqlite"      ← 또는 postgresql
}
```

Android 앱 서버 URL: `http://VM공인IP:8000`

---

## 방법 C — 기존 PC 서버 + ngrok (가장 빠른 임시 테스트)

PC에서 서버를 켜고 임시 외부 URL을 만드는 방법입니다.  
Depth V2 GPU 가속이 그대로 동작하고, 설정이 가장 간단합니다.

```bash
# PC에서 서버 실행
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 다른 터미널에서 ngrok 실행 (https://ngrok.com 에서 무료 설치)
ngrok http 8000

# 생성된 URL 예시: https://xxxx.ngrok-free.app
# 이 URL을 Android 앱에 입력 → LTE에서 접속 가능
```

| 장점 | 단점 |
|------|------|
| RTX 5060 GPU 그대로 사용 | PC가 꺼지면 서버도 꺼짐 |
| Depth V2 완전 동작 | URL이 재시작마다 바뀜 |
| 설정 2분 | 발표장에서 PC 들고 가야 함 |

---

## 요약

| 상황 | 추천 |
|------|------|
| 빠른 LTE 테스트, 지금 당장 | **방법 A (Railway)** |
| 발표에서 Depth V2 보여주고 싶음 | **방법 B (Oracle Cloud)** |
| 발표장에 PC 가져갈 수 있음 | **방법 C (ngrok)** |
| 임시 테스트 (오늘만) | **방법 C (ngrok)** |
