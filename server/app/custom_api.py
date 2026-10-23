"""Versioned Custom API requests. Configurations without `request` remain legacy.

JSON bodies persist a parsed JSON value, never a JSON-encoded template string.
Only explicit {{query}} placeholders bind the agent's input.
"""
import math
import re
from urllib.parse import urlsplit

import requests


_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
_HEADER = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


def validate_custom_api_config(config):
    """Validate only the opt-in versioned request; errors never include input."""
    if config.get("type", "custom_api") != "custom_api" or "request" not in config:
        return
    try:
        endpoint = config["endpoint"]
        if not isinstance(endpoint, str):
            raise ValueError()
        url = urlsplit(endpoint)
        if (not isinstance(endpoint, str) or url.scheme not in ("http", "https")
                or not url.hostname or url.username is not None or url.password is not None
                or any(c.isspace() or ord(c) < 32 for c in endpoint) or url.fragment):
            raise ValueError()
        _ = url.port
        if config.get("method") not in _METHODS:
            raise ValueError()
        timeout = config.get("timeout_seconds", 60)
        if isinstance(timeout, bool) or not isinstance(timeout, (float, int)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError()
        token = config.get("auth_token", "")
        if not isinstance(token, str) or '\r' in token or '\n' in token:
            raise ValueError()
        request = config["request"]
        if not isinstance(request, dict) or type(request.get("version")) is not int or request["version"] != 1:
            raise ValueError()
        if set(request) != {"version", "headers", "query", "body"}:
            raise ValueError()
        seen = set()
        for key in ("headers", "query"):
            rows = request[key]
            if not isinstance(rows, list):
                raise ValueError()
            for row in rows:
                if not isinstance(row, dict) or set(row) != {"name", "value"} or not all(isinstance(row[k], str) for k in row):
                    raise ValueError()
                if not row["name"]:
                    raise ValueError()
                if key == "headers":
                    name = row["name"].lower()
                    if not _HEADER.fullmatch(row["name"]) or name in seen or any(c in row["value"] for c in '\r\n'):
                        raise ValueError()
                    if name == "authorization" and token:
                        raise ValueError()
                    seen.add(name)
        body = request["body"]
        if not isinstance(body, dict):
            raise ValueError()
        kind = body.get("kind")
        if kind == "none":
            if set(body) != {"kind"}:
                raise ValueError()
        elif kind in ("json", "text"):
            if set(body) != {"kind", "value"}:
                raise ValueError()
            if kind == "text" and not isinstance(body["value"], str):
                raise ValueError()
            if kind == "json":
                import json
                json.dumps(body["value"], allow_nan=False)
        elif kind == "form":
            if set(body) != {"kind", "fields"} or not isinstance(body["fields"], list):
                raise ValueError()
            for row in body["fields"]:
                if not isinstance(row, dict) or set(row) != {"name", "value"} or not all(isinstance(row[k], str) for k in row) or not row["name"]:
                    raise ValueError()
        else:
            raise ValueError()
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise ValueError("Invalid Custom API request. Check URL, method, headers, body and timeout.") from None


def _bind(value, query):
    if isinstance(value, str):
        return value.replace("{{query}}", query)
    if isinstance(value, list):
        return [_bind(item, query) for item in value]
    if isinstance(value, dict):
        return {key: _bind(item, query) for key, item in value.items()}
    return value


def execute_custom_api_request(config, query):
    validate_custom_api_config(config)
    request = config["request"]
    headers = {row["name"]: _bind(row["value"], query) for row in request["headers"]}
    if any('\r' in value or '\n' in value for value in headers.values()):
        raise ValueError("Invalid request header value.")
    token = config.get("auth_token", "")
    if token:
        headers["Authorization"] = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    kwargs = {"headers": headers, "params": [(row["name"], _bind(row["value"], query)) for row in request["query"]], "timeout": config.get("timeout_seconds", 60), "allow_redirects": False}
    body = request["body"]
    if body["kind"] == "json":
        # requests' json=None means no body, whereas JSON null is a real body.
        import json
        kwargs["data"] = json.dumps(_bind(body["value"], query), ensure_ascii=False, allow_nan=False).encode("utf-8")
        if not any(key.lower() == "content-type" for key in headers):
            headers["Content-Type"] = "application/json"
    elif body["kind"] == "text":
        kwargs["data"] = _bind(body["value"], query).encode("utf-8")
    elif body["kind"] == "form":
        from urllib.parse import urlencode
        kwargs["data"] = urlencode([(row["name"], _bind(row["value"], query)) for row in body["fields"]]).encode("utf-8")
        if not any(key.lower() == "content-type" for key in headers):
            headers["Content-Type"] = "application/x-www-form-urlencoded"
    response = requests.request(config["method"], config["endpoint"], **kwargs)
    if 300 <= response.status_code < 400:
        raise ValueError("Redirects are not supported.")
    response.raise_for_status()
    return response
