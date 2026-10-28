import importlib
import io
import logging

import pytest


@pytest.fixture
def log_setup():
    module = importlib.import_module("app.log_setup")
    previous_factory = logging.getLogRecordFactory()
    yield module
    logging.setLogRecordFactory(previous_factory)


def _capture(logger_name: str, message: str, module) -> str:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        logging.getLogger(logger_name).info(message)
    finally:
        root.removeHandler(handler)
    return stream.getvalue()


def test_api_key_in_query_masked(log_setup):
    log_setup.configure_logging()
    out = _capture("uvicorn.protocols.websockets",
                   "WebSocket /ws?api_key=sk_fQxBW1hwFOgj-mJ-aAP7g7Dc1s3WgyJmGYZpzEpldIc accepted", log_setup)
    assert "sk_fQxBW1hwFOgj" not in out
    assert "api_key=***" in out


def test_bare_key_masked(log_setup):
    log_setup.configure_logging()
    out = _capture("app.something", "using key sk_t77tT9xQwErTyUiOpAsDfGh to call provider", log_setup)
    assert "sk_t77tT9xQwEr" not in out
    assert "sk_***" in out


def test_stream_token_masked(log_setup):
    log_setup.configure_logging()
    out = _capture("app.auth", "validated token=eyJhbGciOi.abc.def", log_setup)
    assert "eyJhbGciOi" not in out
    assert "token=***" in out


def test_plain_messages_untouched(log_setup):
    log_setup.configure_logging()
    out = _capture("app.intent_service", "Intent classification source=decision", log_setup)
    assert "Intent classification source=decision" in out


def test_configure_logging_idempotent(log_setup):
    log_setup.configure_logging()
    factory_one = logging.getLogRecordFactory()
    log_setup.configure_logging()
    assert logging.getLogRecordFactory() is factory_one


def test_mask_args_too(log_setup):
    log_setup.configure_logging()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logging.getLogger().addHandler(handler)
    try:
        logging.getLogger("app.x").info("connecting %s", "ws://x?api_key=sk_abcdEFGH1234")
    finally:
        logging.getLogger().removeHandler(handler)
    out = stream.getvalue()
    assert "sk_abcdEFGH1234" not in out
    assert "api_key=***" in out
