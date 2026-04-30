FROM python:3.10-slim

WORKDIR /app

# OpenCV 실행에 필요한 시스템 라이브러리
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libglib2.0-0 \
    libgl1 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치 (서버 전용)
COPY requirements-server.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-server.txt

# 소스 코드 복사
COPY src/ ./src/
COPY templates/ ./templates/

# YOLO 모델 복사 (있을 때만 — 없으면 ultralytics가 자동 다운로드)
COPY yolo11m.pt ./yolo11m.pt

# Depth 모델은 크기(99MB)로 인해 제외 → bbox fallback 사용
# 필요 시: COPY depth_anything_v2_vits.pth ./depth_anything_v2_vits.pth

# Cloud Run은 PORT 환경변수를 자동 주입 (기본 8080)
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

CMD uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT}
