from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from src.api.routes import router
from src.api import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 서버 시작 시: DB 초기화 + YOLO 워밍업
    db.init_db()
    import numpy as np
    from src.vision.detect import model, CONF_THRESHOLD
    model(np.zeros((640, 640, 3), dtype=np.uint8), conf=CONF_THRESHOLD, verbose=False)
    # EasyOCR 워밍업: 첫 요청 지연 방지 (백그라운드 스레드)
    import threading
    threading.Thread(target=_warmup_ocr,  daemon=True).start()
    threading.Thread(target=_warmup_tts,  daemon=True).start()
    yield


def _warmup_ocr():
    try:
        from src.ocr.bus_ocr import warmup
        warmup()
    except Exception as e:
        print(f"[main] EasyOCR 워밍업 실패: {e}")


def _warmup_tts():
    try:
        from src.voice.tts import warmup_cache
        warmup_cache()
    except Exception:
        pass  # TTS 워밍업 실패해도 서버 동작에 영향 없음 (첫 요청 시 자동 생성)


app = FastAPI(title="VoiceGuide API", lifespan=lifespan)


@app.get("/health")
async def health():
    """서버 상태 + Depth V2 모델 로드 여부 확인."""
    from src.depth.depth import _check_model, _DEVICE
    depth_ok = _check_model()
    return {
        "status":   "ok",
        "depth_v2": "loaded" if depth_ok else "fallback (bbox)",
        "device":   _DEVICE,
        "db_mode":  "postgresql" if db._IS_POSTGRES else "sqlite",
    }


# 예외가 나도 Android가 음성 안내를 받을 수 있도록 안전 응답 반환
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "sentence": "분석 중 오류가 발생했어요. 주의해서 이동하세요.",
            "objects": [],
            "hazards": [],
            "changes": [],
            "depth_source": "error",
        }
    )


app.include_router(router)
