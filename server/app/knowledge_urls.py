"""Bounded public URL downloads with DNS-pinned HTTP and verified TLS."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

import http.client
import ipaddress
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

MAX_URLS = 20
MAX_BYTES = 10 * 1024 * 1024
MAX_BATCH_BYTES = 50 * 1024 * 1024
TIMEOUT = 30
MAX_REDIRECTS = 3
_DNS_WORKERS = ThreadPoolExecutor(max_workers=4, thread_name_prefix="knowledge-dns")
_DNS_SLOTS = threading.BoundedSemaphore(4)


class URLImportError(ValueError):
    pass


@dataclass(frozen=True)
class DownloadedSource:
    url: str
    final_url: str
    suffix: str
    data: bytes


def normalize_url(url: str) -> str:
    if len(url) > 2048 or any(ord(c) < 33 or ord(c) == 127 for c in url):
        raise URLImportError("URLs must not contain whitespace or control characters")
    try:
        parts = urlsplit(url)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            raise ValueError()
        if parts.username is not None or parts.password is not None:
            raise ValueError()
        hostname = parts.hostname.encode("idna").decode("ascii").lower()
        port = parts.port
        if port not in {None, 80, 443}:
            raise ValueError()
        host = f"[{hostname}]" if ":" in hostname else hostname
        default_port = 443 if parts.scheme.lower() == "https" else 80
        authority = host + (f":{port}" if port is not None and port != default_port else "")
        return urlunsplit((parts.scheme.lower(), authority, parts.path or "/", parts.query, ""))
    except (ValueError, UnicodeError) as exc:
        raise URLImportError("Use a public HTTP or HTTPS URL on port 80 or 443 without credentials") from exc


def validate_urls(urls: list[str]) -> list[str]:
    if not 1 <= len(urls) <= MAX_URLS:
        raise URLImportError(f"Enter between 1 and {MAX_URLS} URLs")
    normalized = [normalize_url(url.strip()) for url in urls]
    if len(set(normalized)) != len(normalized):
        raise URLImportError("Each URL must be unique")
    return normalized


def _public_addresses(host: str, port: int, *, deadline: float | None = None) -> list[str]:
    deadline = deadline or time.monotonic() + TIMEOUT
    if not _DNS_SLOTS.acquire(timeout=max(0, deadline - time.monotonic())):
        raise URLImportError("URL DNS resolution timed out")
    try:
        future = _DNS_WORKERS.submit(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM)
    except Exception:
        _DNS_SLOTS.release()
        raise
    future.add_done_callback(lambda completed: _DNS_SLOTS.release())
    try:
        resolved = future.result(timeout=max(0, deadline - time.monotonic()))
        addresses = list(dict.fromkeys(item[4][0] for item in resolved))
    except FutureTimeout as exc:
        raise URLImportError("URL DNS resolution timed out") from exc
    except OSError as exc:
        raise URLImportError("Could not resolve URL hostname") from exc
    if not addresses:
        raise URLImportError("Could not resolve URL hostname")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global or ip.is_multicast or (ip.version == 6 and (ip.is_site_local or ip.sixtofour or ip.teredo or ip in ipaddress.ip_network("64:ff9b::/96") or ip in ipaddress.ip_network("64:ff9b:1::/48") or (ip.ipv4_mapped and not ip.ipv4_mapped.is_global))):
            raise URLImportError("URLs must resolve only to public internet addresses")
    return addresses


def _open_connection(scheme: str, hostname: str, port: int, address: str, timeout: float):
    if scheme == "https":
        connection = http.client.HTTPSConnection(hostname, port, timeout=timeout, context=ssl.create_default_context())
    else:
        connection = http.client.HTTPConnection(hostname, port, timeout=timeout)
    # http.client still uses the original hostname for Host and TLS SNI checks.
    deadline = time.monotonic() + timeout
    def connect_pinned(target, timeout, source_address=None):
        sock = socket.create_connection((address, port), max(0.001, deadline - time.monotonic()), source_address)
        sock.settimeout(max(0.001, deadline - time.monotonic()))
        return sock
    connection._create_connection = connect_pinned
    return connection


CONTENT_SUFFIXES = {
    "text/html": ".html", "application/xhtml+xml": ".html", "text/plain": ".txt",
    "text/markdown": ".md", "text/csv": ".csv", "text/tab-separated-values": ".tsv",
    "application/json": ".json", "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
}


def download_url(url: str, *, deadline: float | None = None) -> DownloadedSource:
    original = normalize_url(url)
    current = original
    deadline = min(deadline or time.monotonic() + TIMEOUT, time.monotonic() + TIMEOUT)
    for redirect in range(MAX_REDIRECTS + 1):
        parts = urlsplit(current)
        port = parts.port or (443 if parts.scheme == "https" else 80)
        addresses = _public_addresses(parts.hostname, port, deadline=deadline)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise URLImportError("URL download timed out")
        connection = _open_connection(parts.scheme, parts.hostname, port, addresses[0], remaining)
        timer = None
        try:
            def expire():
                sock = connection.sock
                if sock is not None:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    sock.close()
            timer = threading.Timer(max(0, deadline - time.monotonic()), expire)
            timer.daemon = True
            timer.start()
            connection.connect()
            if connection.sock is not None:
                connection.sock.settimeout(max(0.001, deadline - time.monotonic()))
            target = quote(urlunsplit(("", "", parts.path or "/", parts.query, "")), safe="/%?:=&+@!$'()*,-._~;")
            connection.request("GET", target, headers={"User-Agent": "Servio-Knowledge/1.0", "Accept-Encoding": "identity"})
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location or redirect == MAX_REDIRECTS:
                    raise URLImportError("URL has too many redirects or no redirect target")
                current = normalize_url(urljoin(current, location))
                continue
            if response.status != 200:
                raise URLImportError(f"URL returned HTTP {response.status}")
            content_type = (response.getheader("Content-Type") or "").split(";", 1)[0].strip().lower()
            suffix = CONTENT_SUFFIXES.get(content_type)
            if not suffix and content_type in {"", "application/octet-stream"}:
                candidate = PurePosixPath(parts.path).suffix.lower()
                suffix = candidate if candidate in set(CONTENT_SUFFIXES.values()) else None
            if not suffix:
                raise URLImportError("URL content type is not supported")
            if (response.getheader("Content-Encoding") or "identity").lower() != "identity":
                raise URLImportError("Compressed HTTP responses are not supported")
            length = response.getheader("Content-Length")
            if length is not None and (not length.isdigit() or int(length) > MAX_BYTES):
                raise URLImportError("URL exceeds the 10MB download limit")
            chunks = []
            size = 0
            while True:
                if time.monotonic() >= deadline:
                    raise URLImportError("URL download timed out")
                chunk = response.read1(min(65536, MAX_BYTES + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_BYTES:
                    raise URLImportError("URL exceeds the 10MB download limit")
            data = b"".join(chunks)
            if length is not None and len(data) != int(length):
                raise URLImportError("URL response was incomplete")
            if not data:
                raise URLImportError("URL returned empty content")
            return DownloadedSource(original, current, suffix, data)
        except (OSError, http.client.HTTPException) as exc:
            raise URLImportError("URL download failed or timed out") from exc
        finally:
            if timer:
                timer.cancel()
            connection.close()
    raise URLImportError("Too many redirects")
