# GCP (Google Cloud Platform) 완전 가이드

> VoiceGuide 팀 전용 — GCP 처음 쓰는 사람 기준으로 작성

---

## GCP가 뭐야? 한 줄로

> **Google이 운영하는 클라우드 컴퓨터 임대 서비스.**
> 내 PC가 꺼져도 24시간 돌아가는 서버를 빌리는 것.

지금 VoiceGuide는 팀원 PC에서 서버를 돌리고 있어서, 같은 WiFi가 아니면 Android 앱이 서버에 못 붙음.
GCP에 올리면 **LTE 환경에서도 어디서나 접속 가능한 고정 HTTPS 주소**가 생김.

---

## GCP 주요 서비스 — 어떤 걸 써야 해?

| 서비스 | 쉽게 말하면 | VoiceGuide 적합? |
|--------|-----------|----------------|
| **Cloud Run** ⭐ | Docker 컨테이너 올리면 URL 자동 생성. 요청 없으면 꺼짐 (비용↓) | 입문용 최적 |
| **Compute Engine** | 진짜 VM(가상 컴퓨터) 빌리기. GPU도 붙일 수 있음 | GPU 필요 시 |
| **App Engine** | 코드만 올리면 알아서 배포. 커스터마이징 제한 있음 | 굳이 비추 |
| **GKE** | 도커 여러 개 관리하는 쿠버네티스. 복잡함 | 학생 프로젝트엔 과함 |

**결론: Cloud Run으로 시작, GPU 필요하면 Compute Engine으로 이동**

---

## 비용 현실 (솔직하게)

### 무료 한도 (매달 리셋, 기간 제한 없음)

| 항목 | 무료 한도 |
|------|---------|
| Cloud Run 요청 수 | 200만 건/월 |
| Cloud Run vCPU 시간 | 180,000 vCPU-초/월 (~50시간) |
| Cloud Run 아웃바운드 | 1 GB/월 |
| Compute Engine e2-micro VM | 1대 × 730시간/월 (항상 무료, us-central1 등) |

### GPU는 유료 (주의!)

| 옵션 | 월 비용 |
|------|--------|
| Cloud Run + L4 GPU (24/7) | 약 **35~40만원/월** |
| Compute Engine + T4 GPU (24/7) | 약 **20~25만원/월** |
| Cloud Run CPU만 (무료 한도 내) | **$0** |

> ⚠️ GPU 없이 CPU만 쓰면 YOLO 추론이 느림 (요청당 10~30초).
> 데모/발표용으로는 충분히 쓸 만함.

### 학생 무료 크레딧 꼭 받기

1. [Google Cloud 콘솔](https://console.cloud.google.com) 접속
2. 상단 "무료로 시작하기" 클릭
3. **$300 (약 40만원) 크레딧 12개월** 자동 지급
4. 이 크레딧으로 GPU도 테스트 가능

---

## 단계별 사용법 (Cloud Run 기준)

### 1단계: 준비물 설치

```bash
# gcloud CLI 설치
# Windows: https://cloud.google.com/sdk/docs/install 에서 인스톨러 다운로드
# 설치 후 터미널 재시작

# 설치 확인
gcloud version

# 로그인 (브라우저 뜸)
gcloud auth login

# 프로젝트 설정
gcloud init
```

### 2단계: Docker 설치 확인

```bash
docker --version
# Docker Desktop이 없으면 https://www.docker.com/products/docker-desktop 에서 설치
```

### 3단계: Dockerfile 만들기

프로젝트 루트(`c:\VoiceGuide\VoiceGuide\`)에 `Dockerfile` 생성:

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# 시스템 패키지 (opencv 등 필요)
RUN apt-get update && apt-get install -y \
    libglib2.0-0 libsm6 libxext6 libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run은 8080 포트 사용
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 4단계: 배포 (명령어 딱 하나)

```bash
# 프로젝트 폴더에서 실행
cd c:\VoiceGuide\VoiceGuide

gcloud run deploy voiceguide \
  --source . \
  --platform managed \
  --region asia-southeast1 \
  --memory 4Gi \
  --cpu 2 \
  --timeout 120 \
  --allow-unauthenticated
```

> **asia-southeast1** = 싱가포르 리전. 한국 기준 GPU 지원하는 가장 가까운 곳.
> 서울(asia-northeast3)은 GPU 미지원.

### 5단계: 배포 완료 → URL 확인

```
Service URL: https://voiceguide-abc123-as.a.run.app
```

이 URL을 Android 앱 서버 입력창에 붙여넣으면 끝.
`https://voiceguide-xxx.run.app/health` 로 동작 확인.

---

## 자주 쓰는 gcloud 명령어

```bash
# 배포된 서비스 목록
gcloud run services list

# 서비스 URL 확인
gcloud run services describe voiceguide --region asia-southeast1

# 실시간 로그 보기
gcloud run services logs tail voiceguide --region asia-southeast1

# 환경변수 설정 (예: DATABASE_URL)
gcloud run services update voiceguide \
  --set-env-vars DATABASE_URL=postgresql://... \
  --region asia-southeast1

# 서비스 삭제
gcloud run services delete voiceguide --region asia-southeast1

# 새 버전 재배포 (코드 수정 후)
gcloud run deploy voiceguide --source . --region asia-southeast1
```

---

## VoiceGuide 프로젝트 특이사항

### Depth Anything V2 모델 파일 문제

`depth_anything_v2_vits.pth` 파일이 크기 때문에 Docker 이미지에 포함하면 빌드 시간이 오래 걸림.
두 가지 방법:

**방법 A (간단):** Dockerfile에서 모델 자동 다운로드

```dockerfile
# Dockerfile 맨 끝에 추가
RUN python -c "
import urllib.request
urllib.request.urlretrieve(
  'https://huggingface.co/depth-anything/Depth-Anything-V2-Small/resolve/main/depth_anything_v2_vits.pth',
  'depth_anything_v2_vits.pth')
"
```

**방법 B (권장):** GCS(Google Cloud Storage)에 모델 올려두고 시작 시 다운로드

### GPU 없을 때 bbox fallback

Cloud Run 무료(CPU만)로 배포하면 Depth V2 추론이 느리지만, 코드에 이미 bbox 면적 기반 fallback이 구현돼 있어서 서버가 죽지는 않음.

### 포트 번호

로컬에서는 `--port 8000` 썼는데, Cloud Run은 기본 **8080** 포트를 씀.
Dockerfile CMD에서 `--port 8080`으로 바꾸거나, 환경변수로 처리:

```bash
gcloud run services update voiceguide \
  --set-env-vars PORT=8080 \
  --region asia-southeast1
```

---

## 비용 절감 팁

```bash
# 요청 없을 때 인스턴스 0으로 줄이기 (기본값, 확인용)
gcloud run services update voiceguide \
  --min-instances 0 \
  --max-instances 3 \
  --region asia-southeast1

# 최소 인스턴스 1로 올리면 콜드스타트 없어지지만 항상 과금됨
# 데모 직전에만 min-instances=1로 올리고, 끝나면 다시 0으로 내리기
```

---

## 전체 흐름 요약

```
1. gcloud auth login          ← Google 계정 연결
2. gcloud init                ← 프로젝트 선택
3. Dockerfile 작성            ← 서버 실행 방법 정의
4. gcloud run deploy          ← 빌드 + 배포 한 번에
5. HTTPS URL 생성             ← Android 앱에 입력
6. /health 확인               ← 정상 동작 체크
```

---

## 지역(Region) 선택 가이드

| 상황 | 추천 Region | 이유 |
|------|-----------|------|
| CPU만 (무료 테스트) | `asia-northeast3` (서울) | 한국에서 가장 빠름 |
| GPU 필요 | `asia-southeast1` (싱가포르) | 한국 기준 GPU 지원 가장 가까운 곳 |
| 발표 데모 | `asia-northeast3` | 레이턴시 최소화 |

---

## 문제 해결

| 증상 | 원인 | 해결 |
|------|------|------|
| 첫 요청이 10초 걸림 | 콜드스타트 (인스턴스 0→1) | `--min-instances 1` 설정 |
| 메모리 초과 오류 | 기본 512MB 부족 | `--memory 4Gi` 로 올리기 |
| 타임아웃 오류 | 기본 60초 초과 | `--timeout 300` |
| 포트 오류 | 8000 vs 8080 불일치 | Dockerfile CMD에서 8080 사용 |
| GPU 없는 리전 오류 | 서울에 GPU 없음 | asia-southeast1 으로 변경 |
