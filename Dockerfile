FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp \
    DATA_DIR=/data

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      librsvg2-bin \
      libavif-bin \
      poppler-utils \
      libreoffice-writer libreoffice-calc libreoffice-impress \
      fonts-dejavu-core fonts-liberation fonts-noto-color-emoji \
      fontconfig \
      ca-certificates \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/
RUN mkdir -p /data/files

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--timeout-keep-alive", "75"]
