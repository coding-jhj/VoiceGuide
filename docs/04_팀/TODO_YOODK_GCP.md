# 신유득 할 일 — GCP 배포

> 이 파일대로만 하면 됨. 순서대로 진행.

---

## Step 1. Supabase 가입 + DB 주소 받기

1. [supabase.com](https://supabase.com) 접속 → GitHub으로 가입
2. **New Project** 클릭 → 프로젝트 이름 아무거나, 비밀번호 기억해두기
3. 생성 완료 후 (1~2분 기다림):
   - 왼쪽 메뉴 **Project Settings → Database**
   - **Connection string → URI** 탭 클릭
   - **Session pooler** 선택
   - 아래 형태의 주소 복사

```
postgresql://postgres.프로젝트ID:비밀번호@aws-xxx.pooler.supabase.com:5432/postgres
```

> 테이블은 서버가 처음 켜질 때 자동으로 만들어짐. 따로 SQL 실행 안 해도 됨.

---

## Step 2. 프로젝트 루트에 Dockerfile 만들기

`c:\VoiceGuide\VoiceGuide\` 폴더에 `Dockerfile` 파일 새로 만들고 아래 내용 그대로 붙여넣기:

```dockerfile
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

## Step 3. gcloud CLI 설치

1. [cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install) 접속
2. **Windows** 인스톨러 다운로드 → 설치
3. 설치 후 터미널 새로 열기
4. 아래 명령어로 확인:

```bash
gcloud version
# Google Cloud SDK 버전 숫자 나오면 성공
```

---

## Step 4. GCP 로그인 + 프로젝트 생성

```bash
# Google 계정 로그인 (브라우저 열림)
gcloud auth login

# GCP 콘솔(console.cloud.google.com)에서 프로젝트 만들고 프로젝트ID 확인
gcloud config set project 내프로젝트ID
```

---

## Step 5. 배포

터미널에서 프로젝트 폴더로 이동 후 실행:

```bash
cd c:\VoiceGuide\VoiceGuide

gcloud run deploy voiceguide \
  --source . \
  --platform managed \
  --region asia-northeast3 \
  --memory 4Gi \
  --cpu 2 \
  --timeout 120 \
  --min-instances 1 \
  --allow-unauthenticated \
  --set-env-vars "DATABASE_URL=여기에Step1에서복사한주소붙여넣기"
```

> `--source .` 명령어는 GCP가 클라우드에서 알아서 빌드함.
> **도커 데스크탑 켤 필요 없음.**

배포 완료되면 이런 URL 나옴:
```
Service URL: https://voiceguide-xxxx-du.a.run.app
```

---

## Step 6. 정상 동작 확인

```bash
# DB 연결 확인
curl https://voiceguide-xxxx-du.a.run.app/health
# → {"db_mode":"postgresql", "status":"ok"} 나와야 함
# → "sqlite" 나오면 DATABASE_URL 다시 확인

# 저장 모드 테스트
curl -X POST https://voiceguide-xxxx-du.a.run.app/detect \
  -F "mode=저장" \
  -F "query_text=편의점" \
  -F "wifi_ssid=TestWifi"
# → {"sentence":"편의점을 저장했어요.", ...} 나와야 함
```

---

## Step 7. 정환주한테 URL 전달

배포 완료 후 나온 URL을 정환주한테 카톡으로 보내기.

```
https://voiceguide-xxxx-du.a.run.app
```

정환주가 Android 앱 서버 주소 입력창에 넣을 거임.

---

## 자주 나는 오류

| 오류 | 원인 | 해결 |
|------|------|------|
| `db_mode: sqlite` | DATABASE_URL 안 들어감 | `--set-env-vars` 값 다시 확인 |
| `Missing env var: PGHOST` | 환경변수 방식 혼용 | DATABASE_URL 하나만 쓰기 |
| 배포 타임아웃 | 이미지 빌드 오래 걸림 | 기다리기 (첫 배포 5~10분) |
| `Permission denied` | GCP 프로젝트 권한 없음 | 결제 계정 연결 확인 |

---

## 완료 체크리스트

- [ ] Supabase DATABASE_URL 받기
- [ ] Dockerfile 만들기
- [ ] gcloud CLI 설치
- [ ] GCP 로그인 + 프로젝트 설정
- [ ] 배포 명령어 실행
- [ ] `/health` 에서 `"db_mode":"postgresql"` 확인
- [ ] URL 정환주한테 전달
