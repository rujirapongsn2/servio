"""Central logging setup for the Servio backend.

Two jobs:
1. Give the root logger a handler — app loggers (intent classification
   source, tool calls, OKF hydration) log at INFO and previously went
   nowhere because nothing configured a handler.
2. Mask secrets in EVERY emitted record via the log record factory, which
   applies to all loggers regardless of who configured them (uvicorn,
   websockets, app code). WebSocket URLs carry `?api_key=sk_...` in query
   strings and those lines used to land verbatim in log files.
"""

import logging
import os
import re

_SENSITIVE_QUERY = re.compile(r"(api_key=|token=)[A-Za-z0-9_.\-]+")
_BARE_KEY = re.compile(r"\bsk_[A-Za-z0-9_\-]{8,}\b")


def _mask(text: str) -> str:
    text = _SENSITIVE_QUERY.sub(r"\1***", text)
    return _BARE_KEY.sub("sk_***", text)


def _masked_record_factory(previous):
    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        if isinstance(record.msg, str):
            record.msg = _mask(record.msg)
        if record.args:
            record.args = tuple(_mask(arg) if isinstance(arg, str) else arg for arg in record.args)
        return record

    return factory


def configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
    previous = logging.getLogRecordFactory()
    if getattr(previous, "_servio_masked", False):
        return
    factory = _masked_record_factory(previous)
    factory._servio_masked = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)
