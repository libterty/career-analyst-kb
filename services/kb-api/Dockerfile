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

# Install Python deps — copy only pyproject.toml first so pip layer is cached
# independently of source changes. A stub src/career_kb/__init__.py satisfies
# hatchling's package discovery without invalidating the layer on every edit.
COPY services/kb-api/pyproject.toml ./pyproject.toml
RUN mkdir -p src/career_kb && touch src/career_kb/__init__.py && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[dev]" && \
    python -m spacy download en_core_web_lg

# Copy source after pip so edits don't bust the expensive install layer
COPY services/kb-api/src/ ./src/
COPY frontend/ ./frontend/
COPY services/kb-api/alembic.ini ./alembic.ini
COPY services/kb-api/migrations/ ./migrations/
COPY .env.example .env

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
