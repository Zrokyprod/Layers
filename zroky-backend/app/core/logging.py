import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.core.security_logging import install_sensitive_data_filters
from app.observability.context import get_correlation_id, get_request_id, get_tenant_id


_BASE_LOG_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__.keys())


class StructuredJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
            "correlation_id": get_correlation_id(),
            "tenant_id": get_tenant_id(),
        }

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _BASE_LOG_RECORD_FIELDS and not key.startswith("_")
        }
        if extras:
            payload["context"] = extras

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, separators=(",", ":"), default=str)


def setup_logging(level: str, log_format: str = "json") -> None:
    handler = logging.StreamHandler()
    if log_format.strip().lower() == "json":
        handler.setFormatter(StructuredJsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)

    # Install security filters to prevent sensitive data exposure
    install_sensitive_data_filters()
