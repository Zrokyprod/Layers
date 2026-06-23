FROM python:3.11-slim
# build-v2

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts
COPY api-contracts /api-contracts
COPY pricing_config.json ./pricing_config.json
COPY source_truth_manifest.json ./source_truth_manifest.json

RUN chmod +x scripts/start.sh scripts/start-api.sh scripts/start-worker.sh scripts/start-beat.sh

RUN useradd -m -u 1001 appuser \
    && chown -R appuser /app
USER appuser

CMD ["sh", "scripts/start.sh"]
