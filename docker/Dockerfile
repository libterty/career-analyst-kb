FROM python:3.11-slim

# System deps (Tesseract OCR + Chinese language pack)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-chi-tra \
    tesseract-ocr-chi-sim \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps (copy src first so hatchling can find the package)
COPY pyproject.toml .
COPY src/ ./src/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[dev]" && \
    python -m spacy download en_core_web_lg
COPY frontend/ ./frontend/
COPY alembic.ini .
COPY migrations/ ./migrations/
COPY .env.example .env

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
