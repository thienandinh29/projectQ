"""Local structured logs; no external credentials or telemetry required."""

import json
import logging


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "level": record.levelname,
                "message": record.getMessage(),
                "request_id": getattr(record, "request_id", None),
                "topic_id": getattr(record, "topic_id", None),
                "tier": getattr(record, "tier", None),
                "status": getattr(record, "status", None),
                "latency_ms": getattr(record, "latency_ms", None),
                "exception": self.formatException(record.exc_info) if record.exc_info else None,
            },
            ensure_ascii=False,
        )


def configure_logging() -> None:
    logger = logging.getLogger("app")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
