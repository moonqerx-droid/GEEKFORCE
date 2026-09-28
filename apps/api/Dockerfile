FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/services/ai \
    HELPFLOW_KB_DIR=/app/knowledge-base

WORKDIR /app

# Tesseract reads error text from attached screenshots (Russian and English).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/api/app ./app
COPY apps/api/alembic.ini .
COPY apps/api/alembic ./alembic
COPY services/ai/helpflow_ai ./services/ai/helpflow_ai
COPY knowledge-base ./knowledge-base

EXPOSE 8000

CMD ["sh", "-c", "alembic -c alembic.ini upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
