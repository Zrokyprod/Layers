# Deployment

## Local development

```bash
cd zroky-backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and set DATABASE_URL, REDIS_URL, and AUTH_JWT_SECRET

alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

## Environment variables

### Required

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Postgres URL (or `sqlite:///...` for tests) |
| `REDIS_URL` | `redis://host:port/db` — broker + cache |
| `AUTH_JWT_SECRET` | HS256 secret for JWT tokens |
| `ENCRYPTION_SECRET_KEY` | Master secret for Fernet (PII encryption, tokens) |
| `PII_ENCRYPTION_KEY` | Separate key for user PII at rest |

### Optional / operational

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_READ_REPLICA_URL` | — | Read-only Postgres replica for analytics endpoints |
| `DB_POOL_SIZE` | 10 | Primary engine connection pool size |
| `DB_MAX_OVERFLOW` | 20 | Extra transient connections |
| `DB_POOL_TIMEOUT` | 30 s | Seconds to wait for a connection |
| `DB_POOL_RECYCLE` | 1800 s | Close connections older than this |
| `DB_STATEMENT_TIMEOUT_MS` | 30 000 | Kill long-running queries (Postgres only) |
| `SECURITY_CONTACT_EMAIL` | `security@zroky.com` | Published in `/.well-known/security.txt` |
| `APP_DOMAIN` | — | Used in `security.txt` policy URL |

## Production checklist

- [ ] Run migrations (`alembic upgrade head`) before deployment.
- [ ] Configure `DATABASE_READ_REPLICA_URL` so heavy analytics queries do not
      compete with writes.
- [ ] Enable time-series partitioning by running migration `0025` (Postgres
      only; no-op on SQLite).
- [ ] Schedule `partition_maintenance` daily so new monthly partitions are
      created ahead of time:
      ```python
      # app/services/partition_maintenance.py
      from app.services.partition_maintenance import run_partition_maintenance
      from app.db.session import SessionLocal

      def daily_partition_job():
          with SessionLocal() as session:
              run_partition_maintenance(session)
      ```
- [ ] Monitor the `/healthz` endpoint (checks Postgres + Redis).
- [ ] Set up log aggregation for structured JSON logs (see
      `app/core/logging.py`).

## Docker (minimal)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t zroky-backend .
docker run -p 8000:8000 --env-file .env zroky-backend
```

## Railway / Heroku

Set the `DATABASE_URL` and `REDIS_URL` config vars. The app detects
`DEPLOY_TARGET=railway` and switches to a 12-factor-friendly config layout.

## Celery workers

Start the worker pool:

```bash
celery -A app.worker.celery_app worker --loglevel=info -Q diagnosis,ingest
```

Start the beat scheduler (for partition maintenance, retention cleanup):

```bash
celery -A app.worker.celery_app beat --loglevel=info
```
