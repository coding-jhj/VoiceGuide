# 신유득 서버 코드 이해 + VoiceGuide 연결 가이드

> 신유득이 만든 서버 코드가 뭔지, 어떻게 메인 프로젝트에 연결해서 쓰는지 설명

---

## 신유득이 만든 파일 2개

```
서버_DB/        ← 1단계: Supabase 연결 기본 테스트 서버
서버_DB_수정/   ← 2단계: 기능 확장 버전 (blur, lane wear 추가)
```

---

## 서버_DB/ — 1단계: Supabase 연결 테스트

### 이게 왜 필요했나?

VoiceGuide 메인 서버(`src/api/`)는 기본적으로 **SQLite(로컬 파일)** 를 씀.
SQLite는 같은 PC에서만 접근 가능 → **LTE에서 Android 앱이 접속하면 데이터가 안 남음.**

LTE에서도 장소 저장·GPS 기록이 유지되려면 **외부 DB(Supabase)** 가 필요함.
신유득이 이 Supabase 연결이 제대로 동작하는지 **검증하기 위해** 만든 서버.

```
[신유득 역할]
Supabase 연결 방식 검증 → 메인 서버에 DB 연결 코드 통합
```

### 이 서버가 하는 일

```
GET  /health      → DB 연결 살아있는지 확인
GET  /items       → items 테이블 목록 조회
POST /items       → items 테이블에 데이터 추가
GET  /items/{id}  → 특정 항목 조회
PATCH /items/{id} → 특정 항목 수정
DELETE /items/{id}→ 특정 항목 삭제
POST /detect      → DB 저장 테스트 (YOLO 없음, 저장만)
```

> `/detect`는 이름만 같고 메인 서버 `/detect`와 완전히 다름.
> YOLO 추론 없이 그냥 `{"mode": 1}` 이런 값을 DB에 저장만 함.

### 핵심 코드 이해

**DB 연결 주소 결정 방식:**

```python
def _get_db_url():
    direct = os.getenv("DATABASE_URL")
    if direct:
        return direct          # .env에 DATABASE_URL이 있으면 그걸 씀

    # 없으면 개별 환경변수로 조립
    host     = os.getenv("PGHOST")
    port     = os.getenv("PGPORT", "5432")
    dbname   = os.getenv("PGDATABASE", "postgres")
    user     = os.getenv("PGUSER", "postgres")
    password = os.getenv("PGPASSWORD")
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}?sslmode=require"
```

두 가지 방식 모두 지원:
- 방식 A: `DATABASE_URL=postgresql://...` 한 줄로 설정
- 방식 B: `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD` 각각 설정

**커넥션 풀:**

```python
pool = ConnectionPool(db_url, min_size=1, max_size=10, open=True)
```

연결을 미리 여러 개 만들어두는 것. 요청이 올 때마다 DB 연결을 새로 만들면 느리니까,
풀에서 꺼내 쓰고 반납하는 방식. `min_size=1`은 항상 최소 1개 연결 유지.

**SQL Injection 방지:**

```python
if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", ITEMS_TABLE):
    raise RuntimeError("Invalid table name")
```

테이블 이름을 환경변수로 받을 때 영문자/숫자/밑줄만 허용. 해킹 방지.

---

## 서버_DB_수정/ — 2단계: 기능 확장 버전

### 서버_DB에서 뭐가 추가됐나?

| 기능 | 설명 |
|------|------|
| `/blur` ⭐ | 사진에서 **얼굴·번호판 자동 블러** 처리 후 반환 |
| `/lane_wear_infer` | 도로 차선 마모도 분석 (YOLO 세그멘테이션) |
| `/lane_wear/*` | 마모 분석 결과 조회/이미지 반환 |
| `/stats/summary` | 마모 통계 집계 |
| `lane_wear_results` 테이블 | 분석 결과 DB 저장 |

서버 시작 시 테이블 **자동 생성** (수동으로 SQL 실행 불필요):

```python
def _ensure_tables():
    # items 테이블
    # lane_wear_results 테이블 (GPS, 마모도, 이미지 경로 등 저장)
    → 서버 켜질 때 없으면 자동으로 만들어줌
```

### /blur — 얼굴·번호판 자동 블러 ⭐

VoiceGuide에서 활용 가능한 기능.

```
사진 업로드
  ↓
YOLO(얼굴 감지) + YOLO(번호판 감지)
  ↓
감지된 영역에 가우시안 블러 or 픽셀화
  ↓
블러 처리된 이미지 반환
```

```python
# 사용 예시
POST /blur?method=gaussian&blur_strength=31
  - file: 이미지 파일
→ 블러 처리된 JPEG 이미지 반환
```

옵션:
- `method=gaussian` 또는 `method=pixelate`
- `blur_strength`: 블러 강도 (3~199, 홀수)
- `pixel_size`: 픽셀화 크기 (2~128)

### /lane_wear_infer — 차선 마모 분석

```
사진 + GPS 좌표 + 기기 ID 업로드
  ↓
얼굴·번호판 블러 (개인정보 보호)
  ↓
YOLO 세그멘테이션으로 차선 마스크 추출
  ↓
마모 점수 계산 (0~100, 높을수록 심함)
  ↓
DB 저장 + 원본/오버레이 이미지 저장
  ↓
결과 반환 (wear_score, 이미지 URL 등)
```

마모 계산 방식 (5가지 지표 가중 합산):

| 지표 | 가중치 | 의미 |
|------|--------|------|
| 주요 영역 비율 | 28% | 차선이 연속적인가 |
| 연결 성분 수 | 22% | 차선이 끊겨있나 |
| 두께 | 22% | 차선이 얇아졌나 |
| 경계 대비 | 18% | 차선이 흐릿한가 |
| 탐지 신뢰도 | 10% | YOLO 확신도 |

---

## VoiceGuide 메인 프로젝트와 연결하는 법

### 연결 방법 A: Supabase DB 연결 (필수)

신유득이 검증한 Supabase 연결 방식을 메인 서버에 적용하는 방법.

**1. 서버_DB 로 Supabase 연결 확인:**

```bash
cd 서버_DB

# 환경변수 설정 (CMD에서)
set "PGHOST=aws-1-ap-northeast-2.pooler.supabase.com"
set "PGPORT=5432"
set "PGDATABASE=postgres"
set "PGUSER=postgres.프로젝트ID"
set "PGPASSWORD=비밀번호"
set "PGSSLMODE=require"

uvicorn main:app --reload --port 8001
```

```bash
# 연결 확인
curl http://localhost:8001/health
# → {"status":"ok"} 나오면 성공
```

**2. 연결 성공하면 메인 서버에 적용:**

프로젝트 루트의 `.env` 파일에 추가:

```
DATABASE_URL=postgresql://postgres.프로젝트ID:비밀번호@aws-xxx.pooler.supabase.com:5432/postgres?sslmode=require
```

**3. 메인 서버 재시작 → 자동으로 Supabase 사용:**

```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 확인
curl http://localhost:8000/health
# → {"db_mode":"postgresql"} ← Supabase 연결됨!
```

이렇게 하면 Android 앱이 LTE로 접속해도 장소 저장·GPS 기록이 유지됨.

---

### 연결 방법 B: /blur 기능을 메인 서버에서 호출

서버_DB_수정의 `/blur`를 VoiceGuide에서 쓰고 싶을 때.

**방법 1: 서버_DB_수정 서버를 별도로 실행하고 메인 서버에서 호출**

```
Android 앱
  ↓ 이미지
메인 서버 (src/api/, 포트 8000)
  ↓ 내부 HTTP 요청
서버_DB_수정 (포트 8002)  ← 블러 처리
  ↓ 블러된 이미지 반환
메인 서버
  ↓ 블러된 이미지로 YOLO 분석
Android 앱
```

서버_DB_수정 실행:
```bash
cd 서버_DB_수정

set "DATABASE_URL=postgresql://..."
set "YOLO_MODEL=yolov11n-face.pt"      # 얼굴 감지 모델
set "YOLO_LP_MODEL=license-plate-v1x.pt"  # 번호판 감지 모델

uvicorn main:app --port 8002
```

**방법 2: 블러 코드를 메인 서버에 직접 추가**

`서버_DB_수정/main.py`의 `apply_blur()`, `_detect_boxes()` 함수를 복사해서 `src/api/routes.py`에 붙여넣으면 하나의 서버에서 처리 가능.

---

## Supabase 직접 연결이 안 될 때 (학교 네트워크 등)

신유득이 `SUPABASE_DB_CONNECT_GUIDE.md`에 이미 정리해둔 내용.

**증상:**
```
getaddrinfo failed
Ping 요청에서 호스트를 찾을 수 없습니다
```

**원인:** `db.프로젝트ID.supabase.co` 주소가 일부 네트워크에서 막힘

**해결:** Direct connection 대신 **Session Pooler 주소** 사용

```
Supabase 콘솔 → Project Settings → Database → Connection string
→ Session pooler 선택
→ Host: aws-1-ap-northeast-2.pooler.supabase.com  ← 이 주소 사용
```

**자주 나는 오류:**

```
RuntimeError: Missing required env var: PGHOST
```
→ 환경변수 설정한 CMD 창과 서버 실행 창이 **다른 창**이면 발생.
반드시 **같은 CMD 창**에서 `set ...` 한 다음 바로 `uvicorn` 실행.

---

## 두 서버 한눈에 비교

| | 서버_DB | 서버_DB_수정 |
|--|---------|------------|
| **주 목적** | Supabase 연결 검증 | 블러 + 마모 분석 |
| **실행 포트** | 8001 | 8002 |
| **YOLO 필요** | 없음 | 있음 (얼굴·번호판·차선 모델) |
| **테이블 자동 생성** | 없음 (수동) | 있음 (자동) |
| **VoiceGuide 연결** | DB 연결 방식 제공 | 블러 기능 선택 활용 |

---

## 정리: 신유득 코드가 메인 프로젝트에 기여한 것

```
신유득이 서버_DB에서 검증한 것
  └─ Supabase 연결 방식 (ConnectionPool, _get_db_url, 환경변수 패턴)
        ↓ 반영됨
  src/api/db.py (_get_pool, DATABASE_URL 기반 자동 전환)

신유득이 서버_DB_수정에서 추가한 것
  └─ /blur (얼굴·번호판 자동 블러)
        ↓ 필요 시 적용 가능
  src/api/routes.py에 추가하거나 내부 호출로 연결
```
