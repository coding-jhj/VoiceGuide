# VoiceGuide GCP 배포 — 지금 당장 하는 법

> 목적: 오늘 발표/시연에서 서버를 안정적으로 올리기  
> 두 가지 방법: **Cloud Run** (빠름, 30분) / **Compute Engine** (강사님 지정, 1시간)

---

## 어떤 걸 써야 해?

| | Cloud Run ⭐ 빠름 | Compute Engine (강사님 지정) |
|--|--|--|
| 소요 시간 | 약 30분 | 약 1시간 |
| 난이도 | 쉬움 (클릭 위주) | 보통 (명령어 필요) |
| URL | `https://xxx.run.app` | `http://고정IP:8000` |
| CMD 창 | 불필요 | 불필요 |
| 비용 | 무료 한도 내 | $300 크레딧으로 6개월 |
| 강사님 스펙 | ❌ | ✅ |

---

## 방법 A — Cloud Run (오늘 당장 빠르게)

### 준비물
- Google 계정
- GitHub에 코드 push 완료 (이미 됨 ✅)
- 프로젝트에 `Dockerfile` 존재 (이미 있음 ✅)

### 1단계 — gcloud CLI 설치

[https://cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install) 에서 Windows 인스톨러 다운로드 → 설치 → **CMD 재시작**

설치 확인:
```bat
gcloud version
```

### 2단계 — 로그인 + 프로젝트 생성

```bat
gcloud auth login
```
브라우저 창 뜨면 Google 계정으로 로그인.

```bat
gcloud projects create voiceguide-demo-2026 --name="VoiceGuide Demo"
gcloud config set project voiceguide-demo-2026
```

### 3단계 — 결제 계정 연결 + API 활성화

```bat
gcloud services enable run.googleapis.com cloudbuild.googleapis.com
```

> 결제 계정은 GCP 콘솔(console.cloud.google.com) → 결제 → 계정 연결  
> **카드 등록 후 $300 크레딧 자동 지급 → 12개월간 무료**

### 4단계 — 배포 (명령어 딱 하나)

```bat
cd C:\VoiceGuide\VoiceGuide
gcloud run deploy voiceguide ^
  --source . ^
  --region asia-northeast3 ^
  --memory 2Gi ^
  --cpu 2 ^
  --timeout 120 ^
  --allow-unauthenticated ^
  --port 8080
```

빌드 시작 → 약 5~10분 대기

### 5단계 — URL 확인 + 앱 연결

배포 완료 시:
```
Service URL: https://voiceguide-135456731041.asia-northeast3.run.app
```
> ✅ 현재 이 URL로 운영 중 (2026-04-30 배포 완료)

브라우저에서 확인:
```
https://voiceguide-xxxx-an.a.run.app/health
→ {"status":"ok","db":"ok"} 나오면 성공
```

Android 앱 서버 URL 입력창에 해당 URL 붙여넣기.

### 코드 수정 후 재배포

```bat
cd C:\VoiceGuide\VoiceGuide
gcloud run deploy voiceguide --source . --region asia-northeast3
```

---

## 방법 B — Compute Engine VM (강사님 지정 스펙)

> 강사님 지정: GPU 없음, 20GB 이하, 서울 리전, Ubuntu 22.04

### 1단계 — VM 생성 (GCP 콘솔)

[console.cloud.google.com](https://console.cloud.google.com) 접속  
→ **Compute Engine → VM 인스턴스 → 인스턴스 만들기**

```
이름:        voiceguide-server
리전:        asia-northeast3 (서울)
영역:        asia-northeast3-a

머신 구성
  시리즈:    E2
  머신 유형: e2-standard-2  (vCPU 2개, RAM 8GB)

부팅 디스크
  OS:        Ubuntu 22.04 LTS
  크기:      20GB

방화벽
  ☑ HTTP 트래픽 허용
  ☑ HTTPS 트래픽 허용
```

→ 만들기

### 2단계 — 방화벽 포트 8000 열기

```
VPC 네트워크 → 방화벽 → 방화벽 규칙 만들기

이름:         allow-voiceguide-8000
대상 태그:    voiceguide
소스 IP 범위: 0.0.0.0/0
프로토콜/포트: TCP 8000
```

VM 인스턴스 → 네트워크 태그에 `voiceguide` 추가.

### 3단계 — SSH 접속

```bat
gcloud compute ssh voiceguide-server --zone asia-northeast3-a
```
(처음 실행 시 SSH 키 자동 생성됨)

### 4단계 — VM에서 환경 설치

```bash
# Ubuntu VM 안에서 실행
sudo apt update && sudo apt install -y python3.10 python3-pip python3-venv git

# 코드 다운로드
git clone https://github.com/coding-jhj/VoiceGuide.git
cd VoiceGuide

# Python 환경 설정
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-server.txt
```

### 5단계 — 서버 실행 (백그라운드)

```bash
# .env 파일 생성 (필요 시)
echo "DATABASE_URL=" > .env

# 백그라운드 실행 — SSH 끊겨도 계속 동작
nohup uvicorn src.api.main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &

# 실행 확인
curl http://localhost:8000/health
```

### 6단계 — 외부 IP 확인 + 앱 연결

```bat
# 로컬 PC에서
gcloud compute instances describe voiceguide-server \
  --zone asia-northeast3-a \
  --format "get(networkInterfaces[0].accessConfigs[0].natIP)"
```

나온 IP를 Android 앱에:
```
http://[외부IP]:8000
```

### 서버 로그 확인

```bash
# SSH 접속 후
tail -f server.log

# 또는 원격으로
gcloud compute ssh voiceguide-server --zone asia-northeast3-a -- "tail -f ~/VoiceGuide/server.log"
```

### 서버 재시작 (코드 업데이트 후)

```bash
# SSH 접속 후
cd ~/VoiceGuide
git pull
pkill -f uvicorn
source venv/bin/activate
nohup uvicorn src.api.main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
```

---

## 공통 확인 사항

### /health 응답 확인

```json
{
  "status": "ok",
  "depth_v2": "fallback (bbox)",
  "db": "ok",
  "db_mode": "sqlite"
}
```

> `depth_v2: fallback` 은 정상입니다.  
> Depth 모델 파일(99MB)이 서버에 없어서 bbox 기반으로 거리 추정합니다.  
> 객체 탐지, 음성 안내, 공간 기억 등 모든 기능은 정상 동작합니다.

### 자주 쓰는 명령어

```bat
# Cloud Run 서비스 목록
gcloud run services list

# Cloud Run 실시간 로그
gcloud run services logs tail voiceguide --region asia-northeast3

# Cloud Run 환경변수 추가
gcloud run services update voiceguide ^
  --set-env-vars DATABASE_URL=postgresql://... ^
  --region asia-northeast3

# VM 중지 (비용 절약)
gcloud compute instances stop voiceguide-server --zone asia-northeast3-a

# VM 시작
gcloud compute instances start voiceguide-server --zone asia-northeast3-a
```

---

## 문제 해결

| 증상 | 원인 | 해결 |
|------|------|------|
| 첫 요청 10~30초 걸림 | Cloud Run 콜드스타트 | 정상 — 두 번째부터 빠름 |
| `/health` 에서 500 오류 | 서버 시작 실패 | `gcloud run services logs tail voiceguide` 로 원인 확인 |
| 폰에서 연결 안 됨 | URL 끝에 `/` 있음 | URL 마지막 `/` 제거 |
| 메모리 초과 | 기본 512MB 부족 | `--memory 2Gi` 로 재배포 |
| VM SSH 안 됨 | 방화벽 22 포트 | GCP 콘솔 → 방화벽 → SSH(22) 허용 |
| `gcloud` 명령 없음 | CLI 미설치 | cloud.google.com/sdk 에서 설치 |
