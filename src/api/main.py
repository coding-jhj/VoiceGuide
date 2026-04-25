from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from src.api.routes import router
from src.api import db

app = FastAPI(title="VoiceGuide API")


@app.on_event("startup")
def startup():
    db.init_db()
    import numpy as np
    from src.vision.detect import model, CONF_THRESHOLD
    model(np.zeros((640, 640, 3), dtype=np.uint8), conf=CONF_THRESHOLD, verbose=False)


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
