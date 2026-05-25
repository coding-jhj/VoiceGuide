# VoiceGuide FastAPI server image for Google Cloud Run.
# Build: docker build -t voiceguide-server .
# Run:   docker run -p 8080:8080 --env-file .env voiceguide-server
FROM python:3.10-slim

WORKDIR /app

ENV PORT=8080
ENV PYTHONUNBUFFERED=1

COPY requirements-server.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-server.txt

COPY src/ ./src/
COPY templates/ ./templates/
COPY data/processed/voiceguide_scenario/ ./data/processed/voiceguide_scenario/

# Cloud Run injects PORT. This process only handles JSON/state/dashboard work;
# YOLO inference runs on the Android client.
CMD uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT}
