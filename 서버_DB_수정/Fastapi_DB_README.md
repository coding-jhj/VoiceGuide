# Voice Guard API 서버

## 1) 설치

`서버_DB` 폴더에서 실행합니다.

```bat
cd /d "C:\Users\User\OneDrive\Desktop\AI 휴먼 1차 프로젝트_서버_db\서버_DB"
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
```

## 2) 환경변수 설정

CMD 기준 예시:

```bat
set DATABASE_URL=
set "PGHOST=aws-1-ap-northeast-2.pooler.supabase.com"
set "PGPORT=5432"
set "PGDATABASE=postgres"
set "PGUSER=postgres.frelaihwuacofvvukphv"
set "PGPASSWORD=YOUR_PASSWORD"
set "PGSSLMODE=require"

REM 선택: 모델 파일 경로
set "YOLO_MODEL=C:\path\to\yolov11n-face.pt"
set "YOLO_LANE_MODEL=C:\path\to\best_model.pt"
set "YOLO_LP_MODEL=C:\path\to\license-plate-v1x.pt"
```

## 3) 실행

```bat
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8002
```

실행 후 문서:

- `http://127.0.0.1:8002/docs`

Swagger 제목은 **`Voice Guard API`** 입니다.

## 4) DB 테이블

서버 시작 시 아래 테이블이 자동 생성됩니다.

- `items`
- `lane_wear_results`

별도 수동 생성은 필수가 아닙니다.

## 5) 주요 API

- `GET /health`
- `GET /items`
- `GET /items/{item_id}`
- `POST /items`
- `PATCH /items/{item_id}`
- `DELETE /items/{item_id}`
- `POST /detect`
- `POST /blur`
- `POST /lane_wear_infer`
- `GET /lane_wear/latest`
- `GET /lane_wear/recent`
- `GET /lane_wear/{result_id}`
- `GET /lane_wear/image/{result_id}/orig`
- `GET /lane_wear/image/{result_id}/overlay`
- `GET /stats/summary`

## 6) 주의사항

- `/blur`, `/lane_wear_infer`는 모델 파일이 있어야 정상 동작합니다.
- `lane_wear_infer`는 JSON이 아니라 **multipart/form-data 업로드 API**입니다.

