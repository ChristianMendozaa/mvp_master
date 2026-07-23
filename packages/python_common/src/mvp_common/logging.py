import json
import logging
from datetime import UTC, datetime
from typing import Any

SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "password",
    "private_key",
    "secret",
    "token",
}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if any(term in key.lower() for term in SENSITIVE_KEYS)
                else redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        document: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = getattr(record, "context", None)
        if isinstance(context, dict):
            document["context"] = redact(context)
        if record.exc_info:
            document["exception"] = self.formatException(record.exc_info)
        return json.dumps(document, separators=(",", ":"), default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
