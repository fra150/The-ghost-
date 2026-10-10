# Il Fantasma v0.1.2 — Dockerfile test (+ DeepSeek-V4.1-Flash via env)
# build: docker build -t fantasma:0.1 .
# test (mock, senza chiave): docker run --rm fantasma:0.1
# live (con chiave da .env): docker run --rm --env-file .env fantasma:0.1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    DEEPSEEK_BASE_URL=https://api.deepseek.com \
    DEEPSEEK_MODEL=deepseek-flash \
    DEEPSEEK_REASONING_EFFORT=high \
    DEEPSEEK_THINKING=enabled

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY tests/ ./tests/

# NOTA: .env NON copiato nell'immagine (resta locale).
# Passalo a run-time con --env-file .env se vuoi chiamare DeepSeek reale.

CMD ["pytest", "-v", "tests/"]
