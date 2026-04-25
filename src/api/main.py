from fastapi import FastAPI
from src.api.routes import router
from src.api import db

app = FastAPI(title="VoiceGuide API")


@app.on_event("startup")
def startup():
    db.init_db()
    import numpy as np
    from src.vision.detect import model, CONF_THRESHOLD
    model(np.zeros((640, 640, 3), dtype=np.uint8), conf=CONF_THRESHOLD, verbose=False)


app.include_router(router)
