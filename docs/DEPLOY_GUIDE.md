# VoiceGuide 외부 서버 배포 가이드 (LTE 테스트용)

WiFi 없이 LTE 환경에서 앱을 테스트하려면 서버를 인터넷에 공개해야 합니다.  
아래 방법 중 하나를 선택하세요. **모두 무료**입니다.

---

## 먼저 알고 선택하기 — RAM 요구량

VoiceGuide 서버의 모델 크기를 미리 파악해야 서버를 고를 수 있습니다.

| 구성 요소 | RAM |
|----------|-----|
| YOLO11m 모델 로드 | ~400MB |
| Depth Anything V2 | ~300MB |
| FastAPI + 패키지 | ~200MB |
| **합계** | **~900MB+** |

| 내가 원하는 것 | 선택 |
|--------------|------|
| 빠르게 LTE 테스트만 (Depth V2 없어도 됨) | **방법 1 Railway** — GitHub 연동, 5분 배포 |
| Depth V2 포함 완전 기능, 영구 무료 | **방법 4 Oracle Cloud** — RAM 24GB, 설정 복잡 |
| PC 가져갈 수 있음 (RTX 5060 그대로 쓰기) | **방법 7 ngrok** — 2분 설정 |

> Railway/Render(512MB)는 YOLO만 동작, Depth V2는 bbox fallback 자동 전환 — 에러 없음

---

## 무료 서버 비교 표

| 서비스 | 무료 한도 | RAM | Sleep | FastAPI 배포 | 특이사항 |
|--------|---------|-----|-------|------------|---------|
| **Railway** | 월 500시간 | 512MB | 없음 | ✅ 매우 쉬움 | GitHub 연동 1분 배포 |
| **Render** | 월 750시간 | 512MB | ✅ 있음 (15분) | ✅ 쉬움 | sleep 주의 |
| **Fly.io** | 무료 3VM | 256MB | 없음 | ✅ CLI | 글로벌 엣지 |
| **Oracle Cloud** | 기간 없음 | 최대 24GB | 없음 | ✅ VM 직접 | 가장 넉넉 |
| **GCP Cloud Run** | 월 180만 vCPU-초 | 가변 | ✅ 있음 | ✅ Docker | 컨테이너 기반 |
| **AWS EC2 Free** | 750시간/월 (12개월) | 1GB | 없음 | ✅ VM 직접 | t2.micro, 1년 한정 |
| **AWS Lambda** | 100만 요청/월 | 가변 | ✅ 있음 | ✅ Mangum | 요청당 과금, 영구 무료 |
| **Koyeb** | Eco 1개 | 512MB | ✅ 있음 | ✅ GitHub | 간단 |
| **ngrok** | 임시 URL | PC 사양 | PC 종료 시 | — | 빠른 임시 테스트 |

> 추천 순서: Railway (가장 간단) → Oracle Cloud (가장 넉넉, 기간 없음) → AWS EC2 → GCP Cloud Run

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

## 방법 2 — Render

[render.com](https://render.com) — GitHub 연동으로 FastAPI 자동 배포.

### 무료 한도
- 750시간/월 (한 서비스 상시 운영 가능)
- 512MB RAM
- **주의**: 15분 비활성 시 sleep → 첫 요청에서 30~60초 지연 발생

### 배포 방법

1. [render.com](https://render.com) → GitHub 계정으로 로그인
2. **New → Web Service** → `VoiceGuide` 레포 선택
3. 설정:
   ```
   Environment:  Python 3
   Build Command: pip install -r requirements.txt
   Start Command: uvicorn src.api.main:app --host 0.0.0.0 --port $PORT
   ```
4. **Environment Variables** 탭에서 `DATABASE_URL` 추가
5. 배포 완료 후 생성된 URL을 Android 앱에 입력

### 장단점

| 장점 | 단점 |
|------|------|
| GitHub push → 자동 재배포 | 15분 비활성 시 sleep |
| 무료 750시간 | 첫 요청 30~60초 지연 |
| 환경변수 UI 편리 | Depth V2 모델 파일 없음 |

### FastAPI 주의사항

```bash
# Render의 PORT는 환경변수로 주입됨 — 고정 8000 사용 불가
uvicorn src.api.main:app --host 0.0.0.0 --port $PORT
```

> Sleep 문제 해결: [Uptime Robot](https://uptimerobot.com) 무료 계정으로 5분마다 `/health` ping 설정

---

## 방법 3 — Fly.io

[fly.io](https://fly.io) — 글로벌 엣지 네트워크 기반 컨테이너 배포.

### 무료 한도
- 무료 VM 3개 (공유 CPU)
- 256MB RAM / VM
- 무료 플랜에서 sleep 없음 (상시 실행)

### 배포 방법

```bash
# Fly CLI 설치 (Windows)
curl -L https://fly.io/install.ps1 | powershell

# 로그인
fly auth login

# 프로젝트 루트에서
fly launch   # Dockerfile 자동 감지 또는 생성
fly deploy   # 배포
fly open     # 브라우저에서 앱 열기
```

Dockerfile이 없으면 아래 내용으로 생성:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 장단점

| 장점 | 단점 |
|------|------|
| 글로벌 엣지 (한국 리전 가능) | RAM 256MB — YOLO 로드 한계 |
| sleep 없음 | CLI 배포, 초보자 어려움 |
| 빠른 응답 | Depth V2 모델 탑재 불가 |

### FastAPI 주의사항

- RAM 256MB로 YOLO 모델 로드 시 OOM 가능 → `yolo11n.onnx` (소형 모델) 사용 권장
- `fly.toml`에서 메모리 설정 확인:
  ```toml
  [[vm]]
    memory = "256mb"
    cpu_kind = "shared"
    cpus = 1
  ```

---

## 방법 4 — Oracle Cloud Always Free

[cloud.oracle.com](https://cloud.oracle.com) — 기업 클라우드이지만 Always Free 티어가 매우 넉넉합니다.

### 무료 한도 (기간 제한 없음)
- **VM.Standard.A1.Flex** (ARM): 최대 4 OCPU + 24GB RAM — 가장 넉넉한 무료 티어
- **VM.Standard.E2.1.Micro**: 1 OCPU + 1GB RAM (x86)
- 월 10TB 아웃바운드 트래픽
- 고정 공인 IP 가능

### 배포 방법

1. [cloud.oracle.com](https://cloud.oracle.com) → 계정 생성 (신용카드 필요, 청구 없음)
2. **Compute → Instances → Create Instance**
3. **Always Free** 표시 VM 선택 (A1.Flex 권장)
4. SSH 키 생성 후 다운로드
5. VM 생성 후 SSH 접속:

```bash
ssh -i 다운로드한키.pem ubuntu@VM_공인IP

# 서버 세팅
sudo apt update && sudo apt install -y python3-pip git
git clone https://github.com/yourrepo/VoiceGuide.git
cd VoiceGuide
pip3 install -r requirements.txt

# 방화벽 허용 (Oracle 콘솔에서도 Security List 8000 포트 허용 필요)
sudo iptables -A INPUT -p tcp --dport 8000 -j ACCEPT

# 서버 실행 (백그라운드)
nohup uvicorn src.api.main:app --host 0.0.0.0 --port 8000 &
```

6. Android 앱에 `http://VM_공인IP:8000` 입력

### 장단점

| 장점 | 단점 |
|------|------|
| 24GB RAM → Depth V2 모델 탑재 가능 | 초기 설정 복잡 (보안그룹, 방화벽) |
| sleep 없음, 기간 제한 없음 | 계정 생성 느림 (심사 1~2일) |
| GPU 인스턴스도 Always Free 포함 | ARM VM — pip 패키지 일부 미지원 가능 |

### FastAPI 주의사항

- Oracle 보안 그룹(Security List)에서 TCP 8000 인바운드 허용 필수
- ARM VM에서 `torch` 설치 시 시간 오래 걸림 (CPU 빌드)
- 24GB RAM 환경에서는 Depth Anything V2 정상 탑재 가능:
  ```bash
  python -c "
  import urllib.request
  urllib.request.urlretrieve(
      'https://huggingface.co/depth-anything/Depth-Anything-V2-Small/resolve/main/depth_anything_v2_vits.pth',
      'depth_anything_v2_vits.pth')
  "
  ```

---

## 방법 5 — GCP Cloud Run

[cloud.google.com/run](https://cloud.google.com/run) — Google Cloud의 서버리스 컨테이너 플랫폼.

### 무료 한도 (월)
- 180만 vCPU-초
- 360만 GB-초 (메모리)
- 200만 요청
- 아웃바운드 1GB

### 배포 방법

```bash
# Google Cloud CLI 설치 후
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Dockerfile 필요 (방법 3 참조)
# 이미지 빌드 + 푸시
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/voiceguide

# Cloud Run 배포
gcloud run deploy voiceguide \
  --image gcr.io/YOUR_PROJECT_ID/voiceguide \
  --platform managed \
  --region asia-northeast3 \
  --allow-unauthenticated \
  --memory 512Mi \
  --set-env-vars DATABASE_URL=postgresql://...
```

### 장단점

| 장점 | 단점 |
|------|------|
| 요청 없으면 비용 0 | 컨테이너 콜드 스타트 (~5초) |
| 자동 스케일링 | Docker 필수 지식 필요 |
| 한국 리전(asia-northeast3) | 메모리 한계 512MB~1GB |

### FastAPI 주의사항

- Cloud Run은 요청이 없으면 컨테이너를 종료 (콜드 스타트 발생)
- `--min-instances 1` 옵션으로 항상 켜두면 콜드 스타트 제거 (비용 발생)
- PORT 환경변수 자동 주입:
  ```python
  # main.py에서
  import os
  port = int(os.getenv("PORT", 8000))
  ```

---

## 방법 6 — AWS (Amazon Web Services)

AWS는 **12개월 무료 EC2**와 **영구 무료 Lambda** 두 가지 방식으로 사용 가능합니다.

### 6-A. EC2 t2.micro (12개월 무료)

- 1 vCPU, 1GB RAM, Ubuntu
- 750시간/월 무료 (12개월) → 이후 유료

```bash
# 1. AWS 계정 생성 후 EC2 콘솔 → Launch Instance
# 2. t2.micro (Free tier eligible) 선택 → Ubuntu 22.04
# 3. Key pair 생성 후 다운로드 (.pem)
# 4. Security Group: 인바운드 8000 포트 허용

# SSH 접속
ssh -i 키파일.pem ubuntu@EC2_공인IP

# 서버 세팅
sudo apt update && sudo apt install -y python3-pip git
git clone https://github.com/yourrepo/VoiceGuide.git
cd VoiceGuide
pip3 install -r requirements.txt

# 백그라운드 실행
nohup uvicorn src.api.main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
```

**Android 앱에** `http://EC2_공인IP:8000` 입력하면 LTE에서 접속 가능.

### 6-B. AWS Lambda + API Gateway (영구 무료)

- 100만 요청/월 영구 무료
- 요청 없으면 자동 종료 (콜드 스타트 발생)
- FastAPI를 Lambda에 올리려면 **Mangum** 라이브러리 필요

```bash
pip install mangum

# main.py에 추가
from mangum import Mangum
handler = Mangum(app)  # Lambda 핸들러
```

> 이미지 업로드(detect 엔드포인트)는 Lambda payload 6MB 제한 있음 — S3 presigned URL 우회 필요

---

## 방법 7 — Koyeb

[koyeb.com](https://koyeb.com) — GitHub 연동 간단 배포.

### 무료 한도
- Eco 인스턴스 1개 (공유 CPU, 512MB RAM)
- sleep 있음 (비활성 시 종료)

### 배포 방법

1. [koyeb.com](https://koyeb.com) → GitHub 계정 로그인
2. **Create App → GitHub** → VoiceGuide 선택
3. **Run command**: `uvicorn src.api.main:app --host 0.0.0.0 --port 8000`
4. 환경변수 설정 후 배포

### 장단점

| 장점 | 단점 |
|------|------|
| 설정 매우 간단 | 응답 속도 느림 |
| GitHub 자동 배포 | sleep 있음 |
| HTTPS 자동 | 무료 티어 제한적 |

---

## 방법 7 — ngrok (빠른 임시 테스트)

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
