from fastapi import FastAPI
from src.api.routes import router
from src.api import db

app = FastAPI(title="VoiceGuide API")


@app.on_event("startup")
def startup():
    db.init_db()


app.include_router(router)
