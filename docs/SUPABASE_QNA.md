# Supabase 강사님 질문 대비 Q&A

> 강사님이 물어볼 수 있는 두 가지 질문과 답변 준비

---

## Q1. "Docker 기반이야, CLI 기반이야?"

### 한 줄 답변
**"로컬에 Docker로 띄운 게 아니라, Supabase 클라우드 DB에 연결 주소로 붙는 방식입니다."**

### 쉽게 설명하면

```
우리가 쓰는 방식 ✅
  Supabase 웹사이트에서 계정 만들고
  DB 프로젝트 생성 → 연결 주소(URL) 받아서
  코드가 그 주소로 접속

우리가 쓰지 않는 방식 ❌
  내 PC에 Docker 설치해서
  Supabase를 직접 실행 (supabase start 명령어)
```

### 증거로 말할 수 있는 것
- `서버_DB/Fastapi_DB_README.md`에 **"이 프로젝트는 DB를 직접 실행하지 않습니다"** 라고 명시
- 연결 방식: FastAPI + psycopg + `DATABASE_URL` 환경변수

---

## Q2. "외부 접근이 되는 상태야?"

### 한 줄 답변
**"Supabase는 원래 인터넷으로 접속하는 클라우드 서비스라서, 배포 서버나 LTE에서도 같은 연결 주소로 접속 가능한 구조입니다."**

### 쉽게 설명하면

```
Supabase DB = 인터넷 어디서든 접속 가능
  → 집에서도 ✅
  → 학교에서도 ✅
  → LTE에서도 ✅
  → GCP 서버에서도 ✅
    (같은 DATABASE_URL 하나만 넣으면 됨)

단, 학교/회사 네트워크에서 막히는 경우
  → Direct 주소(db.xxx.supabase.co) 대신
  → Pooler 주소(aws-xxx.pooler.supabase.com)로 우회 ← 이미 적용됨
```

### 증거로 말할 수 있는 것
- `src/api/db.py` 주석: **"DATABASE_URL 있으면 PostgreSQL/Supabase, LTE 접속 가능"**
- 실제 확인 방법: GCP/Railway에 서버 올리고 `/health` 응답에서 `"db_mode":"postgresql"` 나오면 증명

---

## 강사님께 바로 쓸 수 있는 답변 문장

> "Supabase는 로컬 Docker로 띄운 게 아니라 클라우드 프로젝트 Postgres에 붙이고 있고,
> 연결은 psycopg로 connection string (Pooler 주소, SSL) 씁니다.
> DB가 원래 외부에서 접속하는 호스티드 서비스라서,
> 배포 서버에 같은 DATABASE_URL 넣으면 외부 접속 가능한 구조이고,
> 실제 동작은 배포 후 /health API로 확인할 예정입니다."

---

## 핵심 키워드 정리

| 용어 | 뜻 |
|------|-----|
| **호스티드(Hosted)** | Supabase 회사 서버에서 운영, 우리가 직접 관리 안 함 |
| **Connection String** | `postgresql://user:pass@host/db` 형태 접속 주소 |
| **Pooler 주소** | 학교망에서도 막히지 않는 우회 접속 주소 |
| **Direct connection** | 일부 네트워크에서 막힐 수 있는 직접 접속 |
| **psycopg** | Python에서 PostgreSQL 접속하는 라이브러리 |
