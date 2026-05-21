from __future__ import annotations

from collections.abc import Iterable

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

HTTP_REQUESTS_TOTAL = Counter(
    "zroky_http_requests_total",
    "Total HTTP requests handled by API server.",
    ("method", "path", "status_code"),
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "zroky_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ("method", "path"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

DIAGNOSIS_JOBS_TOTAL = Counter(
    "zroky_diagnosis_jobs_total",
    "Diagnosis job outcomes by status.",
    ("status",),
)

DIAGNOSIS_RULE_HITS_TOTAL = Counter(
    "zroky_diagnosis_rule_hits_total",
    "Detected diagnosis rule hits by category.",
    ("category",),
)

RETENTION_RUNS_TOTAL = Counter(
    "zroky_retention_runs_total",
    "Retention enforcement runs by status.",
    ("status",),
)

RETENTION_ROWS_TOTAL = Counter(
    "zroky_retention_rows_total",
    "Rows evaluated/deleted by retention enforcement table.",
    ("table", "mode"),
)



def record_http_request(*, method: str, path: str, status_code: int, duration_seconds: float) -> None:
    normalized_method = method.upper() if method else "UNKNOWN"
    normalized_path = path if path else "unknown"
    HTTP_REQUESTS_TOTAL.labels(
        method=normalized_method,
        path=normalized_path,
        status_code=str(status_code),
    ).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=normalized_method, path=normalized_path).observe(
        max(duration_seconds, 0.0)
    )


def record_diagnosis_job(status: str) -> None:
    normalized = status.strip().lower() if status else "unknown"
    DIAGNOSIS_JOBS_TOTAL.labels(status=normalized).inc()


def record_diagnosis_rule_hits(categories: Iterable[str]) -> None:
    for category in categories:
        normalized = category.strip().upper() if category else "UNKNOWN"
        DIAGNOSIS_RULE_HITS_TOTAL.labels(category=normalized).inc()


def record_retention_run(status: str) -> None:
    normalized = status.strip().lower() if status else "unknown"
    RETENTION_RUNS_TOTAL.labels(status=normalized).inc()


def record_retention_rows(table_name: str, rows: int, *, dry_run: bool) -> None:
    normalized_table = table_name.strip().lower() if table_name else "unknown"
    mode = "dry_run" if dry_run else "delete"
    RETENTION_ROWS_TOTAL.labels(table=normalized_table, mode=mode).inc(max(0, int(rows)))



def render_metrics() -> bytes:
    return generate_latest()


def metrics_content_type() -> str:
    return CONTENT_TYPE_LATEST
