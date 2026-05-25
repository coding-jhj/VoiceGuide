from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv
load_dotenv()  # .env 파일에서 DATABASE_URL, API_KEY 등 로드

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from src.api.routes import router
from src.api import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.config.policy import init_policy
    init_policy()
    print("[main] policy.json 적재 완료")
    # DB 초기화는 동기적으로 (빠름)
    db.init_db()
    removed_private = db.purge_private_address_identifiers()
    if removed_private:
        print(f"[main] removed private address-like sessions: {removed_private}")
    db.start_event_writer()
    # 서버는 온디바이스 탐지 결과 JSON만 처리한다.
    # 추가 모델성 기능은 서버 런타임에서 실행하지 않는다.
    yield  # 서버 실행 중 (이 이후는 종료 시 실행)
    db.stop_event_writer()


app = FastAPI(title="VoiceGuide API", lifespan=lifespan)

# CORS: Android 앱은 CORS가 필요 없고, 브라우저 대시보드 origin만 허용합니다.
# ALLOWED_ORIGINS 환경변수로 추가 허용 origin을 지정할 수 있습니다.
# 예) ALLOWED_ORIGINS=https://myapp.ngrok-free.app,http://localhost:8000
_default_origins = (
    "http://localhost:8000,"
    "http://127.0.0.1:8000,"
    "https://voiceguide-1063164560758.asia-northeast3.run.app"
)
_origins = os.getenv("ALLOWED_ORIGINS", _default_origins)
_allow_origins = ["*"] if _origins == "*" else [
    origin.strip() for origin in _origins.split(",") if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """서버 상태 + DB 연결 확인."""
    db_status = _check_db()
    overall = "ok" if db_status == "ok" else "degraded"
    return {
        "status":    overall,
        "role":      "json-router",
        "inference": "disabled",
        "db_mode":   "postgresql" if db._IS_POSTGRES else "sqlite",
        "db":        db_status,
        "db_writer": db.get_event_writer_stats(),
    }


def _check_db() -> str:
    """DB에 간단한 쿼리를 날려 연결 상태를 확인한다."""
    try:
        from src.api.db import _conn, _IS_POSTGRES
        with _conn() as conn:
            if _IS_POSTGRES:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            else:
                conn.execute("SELECT 1")
        return "ok"
    except Exception as e:
        return f"error: {e}"


@app.get("/")
async def root():
    """배포 URL 루트로 접속하면 대시보드로 안내한다."""
    return RedirectResponse(url="/dashboard", status_code=307)


# 예외가 나도 Android가 음성 안내를 받을 수 있도록 안전 응답 반환
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "sentence": "분석 중 오류가 발생했어요. 주의해서 이동하세요.",
            "alert_mode": "normal",
            "objects": [],
            "hazards": [],
            "changes": [],
            "depth_source": "error",
        }
    )


app.include_router(router)
