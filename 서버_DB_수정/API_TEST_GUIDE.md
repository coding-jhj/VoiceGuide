# API Test Guide

이 문서는 `서버_DB/main.py`의 **Voice Guard API**를 실행하고 테스트하는 방법을 정리한 문서입니다.

## 1) 서버 실행

먼저 `서버_DB` 폴더에서 서버를 실행합니다.

```bat
cd /d "C:\Users\User\OneDrive\Desktop\AI 휴먼 1차 프로젝트_서버_db\서버_DB"
python -m pip install -r requirements.txt

set DATABASE_URL=
set "PGHOST=aws-1-ap-northeast-2.pooler.supabase.com"
set "PGPORT=5432"
set "PGDATABASE=postgres"
set "PGUSER=postgres.frelaihwuacofvvukphv"
set "PGPASSWORD=YOUR_PASSWORD"
set "PGSSLMODE=require"

REM 모델 파일이 있으면 경로 지정
set "YOLO_MODEL=C:\path\to\yolov11n-face.pt"
set "YOLO_LANE_MODEL=C:\path\to\best_model.pt"
set "YOLO_LP_MODEL=C:\path\to\license-plate-v1x.pt"

python -m uvicorn main:app --reload --host 127.0.0.1 --port 8002
```

정상 실행되면 아래 로그가 보입니다.

```txt
INFO:     Uvicorn running on http://127.0.0.1:8002
INFO:     Application startup complete.
```

## 2) Swagger 확인

브라우저에서 아래 주소를 엽니다.

- `http://127.0.0.1:8002/docs`

Swagger 상단 제목이 **`Voice Guard API`**로 보이면 정상입니다.

## 3) 테스트는 다른 CMD 창에서 실행

서버 실행 창은 그대로 두고, **새 CMD 창**에서 아래 명령어를 실행합니다.

## 4) Health Check

```bat
curl http://127.0.0.1:8002/health
```

정상 예시:

```json
{
  "status": "ok",
  "db": {"ok": 1},
  "models": {
    "face": {"path": "...", "exists": true},
    "lane": {"path": "...", "exists": true},
    "license_plate": {"path": "...", "exists": true}
  }
}
```

## 5) 기본 detect 테스트

```bat
curl -X POST http://127.0.0.1:8002/detect -H "Content-Type: application/json" -d "{\"mode\":1}"
```

## 6) 최근 데이터 조회

```bat
curl http://127.0.0.1:8002/lane_wear/recent
```

## 7) 최신 데이터 1건 조회

```bat
curl http://127.0.0.1:8002/lane_wear/latest
```

## 8) 특정 ID 조회

```bat
curl http://127.0.0.1:8002/lane_wear/1
```

## 9) 통계 요약 조회

```bat
curl "http://127.0.0.1:8002/stats/summary?window_h=24&warning=40&critical=70"
```

## 10) 이미지 blur 테스트

아래는 예시이며, `sample.jpg`를 실제 테스트 이미지 경로로 바꿔야 합니다.

```bat
curl -X POST "http://127.0.0.1:8002/blur?conf=0.25&iou=0.5&method=gaussian&blur_strength=31&pixel_size=16&max_size=1280&jpeg_quality=90" ^
  -H "Content-Type: multipart/form-data" ^
  -F "file=@sample.jpg"
```

성공하면 blur 처리된 JPEG 이미지가 응답됩니다.

## 11) lane_wear 추론 + 저장 테스트

이 API는 **JSON이 아니라 multipart/form-data**를 사용합니다.

```bat
curl -X POST "http://127.0.0.1:8002/lane_wear_infer?conf=0.25&iou=0.5&max_size=1280" ^
  -H "Content-Type: multipart/form-data" ^
  -F "file=@sample.jpg" ^
  -F "gps_lat=37.5665" ^
  -F "gps_lon=126.9780" ^
  -F "timestamp=2026-04-28T16:00:00+09:00" ^
  -F "device_id=device-01"
```

정상 예시:

```json
{
  "status": "success",
  "model": "best_model.pt",
  "db_id": 1,
  "orig_url": "http://127.0.0.1:8002/lane_wear/image/1/orig",
  "overlay_url": "http://127.0.0.1:8002/lane_wear/image/1/overlay"
}
```

## 12) 저장된 이미지 확인

```bat
curl http://127.0.0.1:8002/lane_wear/image/1/orig
curl http://127.0.0.1:8002/lane_wear/image/1/overlay
```

브라우저에서는 아래 형식으로 바로 열 수 있습니다.

- `http://127.0.0.1:8002/lane_wear/image/1/orig`
- `http://127.0.0.1:8002/lane_wear/image/1/overlay`

## 성공 기준

- `/docs` 제목이 `Voice Guard API`
- `/health` 응답 정상
- `/blur`가 이미지 응답 반환
- `/lane_wear_infer`가 `"status":"success"` 반환
- `/lane_wear/recent`에서 저장한 데이터 확인 가능
- `/stats/summary`에서 `detections` 값 증가 확인

