# GCP Compute Engine 서버 셋업 가이드

> 강사님 지정 스펙: GPU 없음, 30GB 이하, 서울 리전, Ubuntu 22/24

---

## 스펙 (강사님 지정)

| 항목 | 값 |
|------|-----|
| 인스턴스 타입 | `e2-standard-2` (vCPU 2, RAM 8GB) |
| GPU | **없음** |
| 디스크 | 20GB (30GB 이하) |
| 리전 | `asia-northeast3` (서울) |
| OS | Ubuntu 22.04 LTS |
| 외부 IP | 고정 IP 할당 |

---

## 1단계: GCP 콘솔에서 인스턴스 생성

1. [console.cloud.google.com](https://console.cloud.google.com) 접속
2. **Compute Engine → VM 인스턴스 → 인스턴스 만들기**
3. 아래대로 설정:

```
이름:        voiceguide-server
리전:        asia-northeast3 (서울)
영역:        asia-northeast3-a

머신 구성
  시리즈:    E2
  머신 유형: e2-standard-2 (vCPU 2개, 8GB 메모리)

부팅 디스크
  OS:        Ubuntu 22.04 LTS
  디스크 유형: 표준 영구 디스크
  크기:      20GB

방화벽
  ☑ HTTP 트래픽 허용
  ☑ HTTPS 트래픽 허용
```

4. **만들기** 클릭 → 1~2분 후 인스턴스 생성 완료

---

## 2단계: 외부 IP 고정

```
VPC 네트워크 → 외부 IP 주소 → 임시 → 고정으로 변경
```

이 IP가 Android 앱에서 쓸 서버 주소가 됨.

---

## 3단계: 방화벽 포트 8000 열기

```
VPC 네트워크 → 방화벽 → 방화벽 규칙 만들기

이름:           allow-voiceguide
대상:           모든 인스턴스
소스 IP:        0.0.0.0/0
프로토콜/포트:  tcp:8000
```

---

## 4단계: VS Code SSH 연결

### gcloud SSH 키 등록

```bash
# 로컬 PC에서
gcloud compute ssh voiceguide-server --zone asia-northeast3-a
# 처음 실행 시 SSH 키 자동 생성됨
```

### VS Code Remote SSH 설정

1. VS Code → Extensions → **Remote - SSH** 설치
2. `F1` → `Remote-SSH: Open SSH Configuration File`
3. 아래 추가:

```
Host voiceguide-gcp
    HostName [외부IP]
    User [구글계정 앞부분]
    IdentityFile ~/.ssh/google_compute_engine
```

4. `F1` → `Remote-SSH: Connect to Host` → `voiceguide-gcp` 선택
5. VS Code가 서버에 직접 연결됨

---

## 5단계: 서버에 코드 올리기

```bash
# 방법 A: Git clone (추천)
git clone https://github.com/coding-jhj/VoiceGuide.git
cd VoiceGuide

# 방법 B: gcloud scp로 파일 복사
gcloud compute scp --recurse ./VoiceGuide voiceguide-server:~/ --zone asia-northeast3-a
```

---

## 6단계: Python 환경 설치

```bash
# Ubuntu에서
sudo apt update
sudo apt install -y python3.10 python3-pip python3-venv

cd VoiceGuide
python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

---

## 7단계: 서버 실행

```bash
# .env 파일 설정 (DATABASE_URL 등)
cp .env.example .env
nano .env   # DATABASE_URL 입력

# 서버 실행
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 백그라운드 실행 (SSH 끊겨도 유지)
nohup uvicorn src.api.main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
```

---

## 8단계: 동작 확인

```bash
# 서버에서
curl http://localhost:8000/health

# 로컬 PC에서 (외부 IP로)
curl http://[외부IP]:8000/health
# → {"status":"ok","db_mode":"postgresql"} 나오면 성공
```

---

## 9단계: Android 앱 연결

앱 서버 URL 입력창에:
```
http://[외부IP]:8000
```

LTE 환경에서 연결 확인.

---

## 비용 (참고)

| 항목 | 비용 |
|------|------|
| e2-standard-2 (서울) | 약 $50/월 |
| 디스크 20GB | 약 $1/월 |
| **$300 크레딧으로** | **약 6개월 운영 가능** |

---

## 문제 해결

| 증상 | 원인 | 해결 |
|------|------|------|
| 외부 접속 안 됨 | 방화벽 8000 포트 미오픈 | 3단계 방화벽 규칙 추가 |
| SSH 연결 안 됨 | SSH 키 불일치 | `gcloud compute ssh` 재실행 |
| 서버 느림 | CPU 전용, Depth V2 부하 | Depth 비활성화 또는 bbox fallback |
| 메모리 부족 | 8GB에서 YOLO+Depth 동시 실행 | `--memory-limit` 또는 Depth 비활성화 |
