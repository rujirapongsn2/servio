"""Server-owned, read-only answer surfaces. Tool output never defines UI or actions."""
from __future__ import annotations

import math
import re
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

CATALOG_ID = "https://servio.ai/a2ui/catalogs/answers/v1"
VERSION = "v0.9.1"
_SECRET = re.compile(r"token|secret|password|authorization|api.?key|cookie|credential", re.I)


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(min_length=1, max_length=300)
    excerpt: str = Field(max_length=2000)


class ReadData(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    columns: list[str] = Field(min_length=1, max_length=8)
    rows: list[list[str]] = Field(max_length=20)
    truncated: bool

    @model_validator(mode="after")
    def bounded_cells(self):
        if any(not key or len(key) > 100 for key in self.columns) or any(
                len(row) != len(self.columns) or any(len(cell) > 500 for cell in row) for row in self.rows):
            raise ValueError("Invalid result dimensions")
        return self


class ReadResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["servio_read_result"] = "servio_read_result"
    version: Literal[1] = 1
    response: str = Field(max_length=64000)
    sources: list[Source] = Field(default_factory=list, max_length=8)
    data: ReadData | None = None


def normalize_data(value) -> ReadData | None:
    """Only flat scalar records have an unambiguous generic reading surface."""
    if isinstance(value, dict):
        # Recognized collection wrappers, not arbitrary nested objects.
        for key in ("items", "results", "records", "data"):
            if isinstance(value.get(key), list):
                return normalize_data(value[key])
        records = [value]
    elif isinstance(value, list) and all(isinstance(row, dict) for row in value):
        records = value
    else:
        return None
    if not records:
        return ReadData(columns=["ผลลัพธ์"], rows=[], truncated=False)
    columns = list(dict.fromkeys(key for row in records[:20] for key in row
                                if isinstance(key, str) and key.strip() and not _SECRET.search(key)))
    if not columns:
        return None
    visible = columns[:8]
    rows, clipped = [], len(records) > 20 or len(columns) > 8
    for row in records[:20]:
        cells = []
        for key in visible:
            cell = row.get(key)
            if cell is not None and type(cell) not in (str, int, float, bool):
                return None
            if isinstance(cell, float) and not math.isfinite(cell):
                return None
            text = "—" if cell is None else ("true" if cell is True else "false" if cell is False else str(cell))
            clipped |= len(text) > 500
            cells.append(text[:500])
        rows.append(cells)
    return ReadData(columns=[key[:100] for key in visible], rows=rows, truncated=clipped)


def read_result(response: str, value=None, sources=()) -> str:
    return ReadResult(response=response[:64000], data=normalize_data(value), sources=list(sources)[:8]).model_dump_json()


def knowledge_result(result: dict) -> str:
    sources = []
    for concept in result.get("concepts", [])[:8]:
        if isinstance(concept, dict) and isinstance(concept.get("title"), str) and concept["title"].strip():
            sources.append(Source(title=concept["title"][:300], excerpt=str(concept.get("excerpt") or "")[:2000]))
    return read_result(str(result.get("response") or "No matching OKF concepts found."), sources=sources)


def parse_read_result(value) -> ReadResult | None:
    try:
        if not isinstance(value, str) or len(value) > 150000:
            return None
        return ReadResult.model_validate_json(value)
    except (ValueError, TypeError, ValidationError):
        return None


class AnswerSession:
    def __init__(self):
        self.enabled = False
        self.snapshots: dict[str, list[dict]] = {}
        self.results: dict[str, tuple[str, ReadResult]] = {}

    def reset(self):
        self.snapshots.clear()
        self.results.clear()

    def capture(self, call_id, label, output):
        result = parse_read_result(output)
        if result is not None:
            self.results[call_id] = (label[:100], result)
            while len(self.results) > 50:
                del self.results[next(iter(self.results))]

    def publish(self, history, *, skip_ids=()):
        if not self.enabled:
            return
        turn = []
        for item in reversed(history):
            if item.get("role") == "user":
                break
            turn.append(item)
        answers = [item for item in turn if item.get("role") == "assistant" and item.get("type") == "message"]
        if not answers:
            return
        item = answers[0]
        sid = item.get("id")
        if sid in skip_ids:
            return
        if not isinstance(sid, str) or not re.fullmatch(r"msg_[A-Za-z0-9_-]{1,100}", sid):
            sid = item["id"] = "msg_" + uuid4().hex
        content = item.get("content", "")
        text = content if isinstance(content, str) else "\n".join(part.get("text", "") for part in content if isinstance(part, dict) and part.get("type") == "output_text")
        if not text.strip() or len(text) > 64000:
            return
        sources, results = [], []
        for event in reversed(turn):
            captured = self.results.get(event.get("call_id")) if event.get("type") == "function_call_output" else None
            if captured is None:
                continue
            label, result = captured
            for source in result.sources:
                if source not in sources and len(sources) < 8:
                    sources.append(source)
            if result.data is not None and len(results) < 5:
                results.append({"label": label, **result.data.model_dump()})
        data = {"text": text, "sources": [source.model_dump() for source in sources], "results": results}
        self.snapshots[sid] = [
            {"version": VERSION, "createSurface": {"surfaceId": sid, "catalogId": CATALOG_ID}},
            {"version": VERSION, "updateComponents": {"surfaceId": sid, "components": [
                {"id": "root", "component": "Answer", "data": {"path": "/answer"}}]}},
            {"version": VERSION, "updateDataModel": {"surfaceId": sid, "path": "/answer", "value": data}},
        ]
        while len(self.snapshots) > 20:
            del self.snapshots[next(iter(self.snapshots))]
