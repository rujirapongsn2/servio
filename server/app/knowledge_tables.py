"""Bounded spreadsheet import and read-only queries over one Knowledge bundle."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import shutil
import sqlite3
import tempfile
import time
import zipfile
from contextlib import closing
from pathlib import Path

from app.local_documents import OfficeExtractionError, _read_xml, _spreadsheet_sheets, _S

MAX_BYTES = 50 * 1024 * 1024
MAX_XML_BYTES_TOTAL = 64 * 1024 * 1024
# The text importer also counts the header in its 20,000-row workbook limit.
MAX_ROWS = 19_999
MAX_COLUMNS = 200
MAX_CELLS = 2_000_000
MAX_SHEETS = 50
MAX_CELL_BYTES = 32_768
MAX_RESULT_BYTES = 65_536
MAX_RESULT_ROWS = 200
MAX_SQL_BYTES = 16_384
MAX_HEADER_BYTES = 256
MAX_SCHEMA_BYTES = 65_536
QUERY_SECONDS = 2.0
MAX_QUERY_STEPS = 2_000_000
_TABLE_NAME = re.compile(r"data_[1-9][0-9]*\Z")
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")
_INTEGER = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")
_FUNCTIONS = frozenset({
    "abs", "avg", "count", "sum", "total", "min", "max", "round", "coalesce", "ifnull", "nullif",
    "iif", "length", "lower", "upper", "trim", "ltrim", "rtrim", "substr", "substring", "replace",
    "instr", "like", "glob", "typeof", "unicode", "char", "concat", "concat_ws", "group_concat",
    "date", "time", "datetime", "julianday", "unixepoch", "strftime", "timediff",
    "row_number", "rank", "dense_rank", "percent_rank", "cume_dist", "ntile", "lag", "lead",
    "first_value", "last_value", "nth_value", "ceil", "ceiling", "floor", "sqrt", "power", "pow",
    "mod", "sign", "log", "log10", "ln", "exp",
})


class TableImportError(ValueError):
    pass


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _cell(value: str) -> str:
    if "\x00" in value or len(value.encode("utf-8")) > MAX_CELL_BYTES:
        raise TableImportError("A spreadsheet cell is invalid or too large")
    return value


def _csv_rows(path: Path) -> list[list[str]]:
    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = data.decode("cp874")
        except UnicodeDecodeError as exc:
            raise TableImportError("CSV must use UTF-8 or Thai Windows encoding") from exc
    try:
        dialect = csv.Sniffer().sniff(text[:65536], delimiters=",;\t|")
    except csv.Error:
        first_line = next((line for line in text.splitlines() if line.strip()), "")
        delimiter = max(",;\t|", key=lambda candidate: len(next(csv.reader([first_line], delimiter=candidate))))
        dialect = csv.excel
        dialect = type("DetectedCSV", (dialect,), {"delimiter": delimiter})
    rows = []
    try:
        for row in csv.reader(io.StringIO(text, newline=""), dialect, strict=True):
            if not row or not any(value.strip() for value in row):
                continue
            if len(row) > MAX_COLUMNS or len(rows) > MAX_ROWS:
                raise TableImportError("Spreadsheet exceeds the row or column limit")
            if (len(rows) + 1) * len(row) > MAX_CELLS:
                raise TableImportError("Spreadsheet exceeds the cell limit")
            if rows and len(row) != len(rows[0]):
                raise TableImportError("CSV rows must have the same number of columns as the header")
            rows.append([_cell(value) for value in row])
    except csv.Error as exc:
        raise TableImportError("CSV structure is invalid") from exc
    return rows


def _column_index(reference: str) -> int:
    match = re.fullmatch(r"([A-Z]+)[1-9][0-9]*", reference)
    if not match:
        raise TableImportError("XLSX contains an invalid cell reference")
    number = 0
    for letter in match[1]:
        number = number * 26 + ord(letter) - ord("A") + 1
    if number > MAX_COLUMNS:
        raise TableImportError("Spreadsheet exceeds the column limit")
    return number - 1


def _xlsx_rows(path: Path) -> list[tuple[str, list[list[str]]]]:
    try:
        with zipfile.ZipFile(path) as archive:
            if sum(info.file_size for info in archive.infolist()) > MAX_XML_BYTES_TOTAL:
                raise TableImportError("Expanded XLSX exceeds the size limit")
            shared = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = _read_xml(archive, "xl/sharedStrings.xml")
                shared = [_cell("".join(node.text or "" for node in item.iter(f"{_S}t")))
                          for item in root.findall(f"{_S}si")]
            sheets = _spreadsheet_sheets(archive)
            if len(sheets) > MAX_SHEETS:
                raise TableImportError("Workbook exceeds the worksheet limit")
            result = []
            total_rows = total_cells = 0
            for name, target in sheets:
                rows = []
                width = 0
                root = _read_xml(archive, target)
                if root.find(f".//{_S}mergeCell") is not None:
                    raise TableImportError("Merged cells are not supported; unmerge cells before importing as a table")
                for row in root.iter(f"{_S}row"):
                    values: dict[int, str] = {}
                    for position, cell in enumerate(row.findall(f"{_S}c")):
                        index = _column_index(cell.attrib["r"]) if "r" in cell.attrib else position
                        if index >= MAX_COLUMNS or index in values:
                            raise TableImportError("XLSX contains invalid or duplicate columns")
                        kind = cell.attrib.get("t", "")
                        value_node = cell.find(f"{_S}v")
                        raw = value_node.text if value_node is not None else None
                        if cell.find(f"{_S}f") is not None and raw is None:
                            raise TableImportError("Excel formula has no cached result; recalculate and save the workbook first")
                        if kind == "inlineStr":
                            value = "".join(node.text or "" for node in cell.iter(f"{_S}t"))
                        elif kind == "s" and raw is not None:
                            try:
                                string_index = int(raw)
                                if string_index < 0:
                                    raise ValueError()
                                value = shared[string_index]
                            except (ValueError, IndexError) as exc:
                                raise TableImportError("XLSX shared string index is invalid") from exc
                        elif kind == "b":
                            value = "TRUE" if raw == "1" else "FALSE"
                        elif kind == "e":
                            raise TableImportError("Excel contains an error value; fix the workbook before importing")
                        else:
                            value = raw or ""
                        values[index] = _cell(value)
                    if not values or not any(value.strip() for value in values.values()):
                        continue
                    width = max(width, max(values) + 1)
                    if total_cells + (len(rows) + 1) * width > MAX_CELLS:
                        raise TableImportError("Workbook exceeds the cell limit")
                    rows.append(values)
                    if total_rows + len(rows) > MAX_ROWS + 1:
                        raise TableImportError("Workbook exceeds the row limit")
                if rows:
                    result.append((name, [[row.get(index, "") for index in range(width)] for row in rows]))
                    total_rows += len(rows) - 1
                    total_cells += len(rows) * width
            return result
    except (OSError, zipfile.BadZipFile, OfficeExtractionError) as exc:
        raise TableImportError("XLSX workbook cannot be read") from exc


def _headers(row: list[str]) -> list[str]:
    result = []
    seen = set()
    for index, value in enumerate(row, 1):
        base = value.strip() or f"column_{index}"
        if len(base.encode("utf-8")) > MAX_HEADER_BYTES:
            raise TableImportError("Spreadsheet column names must be no more than 256 bytes")
        name = base
        suffix = 2
        while name.casefold() in seen:
            name = f"{base}_{suffix}"
            suffix += 1
        seen.add(name.casefold())
        result.append(name)
    return result


def _type(values: list[str]) -> str:
    nonempty = [value for value in values if value != ""]
    if not nonempty or any(not _NUMBER.fullmatch(value) for value in nonempty):
        return "TEXT"
    if all(_INTEGER.fullmatch(value) and len(value.lstrip("-")) <= 19 and -(2**63) <= int(value) < 2**63 for value in nonempty):
        return "INTEGER"
    if all(math.isfinite(float(value)) and len(value.replace("-", "").replace(".", "")) <= 15 for value in nonempty):
        return "REAL"
    return "TEXT"


def build_database(source_paths: list[Path], destination: Path, *, allow_empty: bool = False) -> list[dict]:
    paths = [path for path in source_paths if path.suffix.lower() in {".csv", ".xlsx"}]
    if not paths:
        raise TableImportError("Queryable knowledge requires at least one CSV or XLSX file")
    if sum(path.stat().st_size for path in paths) > MAX_BYTES:
        raise TableImportError("Spreadsheets exceed the upload size limit")
    destination.mkdir(parents=True, exist_ok=True)
    if any((destination / name).exists() for name in ("queryable.sqlite", "queryable.json", "table_sources")):
        raise TableImportError("Queryable knowledge already exists")
    catalog = []
    total_rows = total_cells = 0
    with tempfile.TemporaryDirectory(prefix=".tables-", dir=destination) as temporary:
        stage = Path(temporary)
        originals = stage / "table_sources"
        originals.mkdir()
        with closing(sqlite3.connect(stage / "queryable.sqlite")) as connection:
            for source_index, path in enumerate(paths, 1):
                sheets = [(None, _csv_rows(path))] if path.suffix.lower() == ".csv" else _xlsx_rows(path)
                if not sheets:
                    raise TableImportError("Spreadsheet contains no readable worksheets")
                shutil.copyfile(path, originals / f"{source_index}{path.suffix.lower()}")
                for sheet_name, rows in sheets:
                    if not rows or (len(rows) < 2 and not allow_empty):
                        raise TableImportError("Spreadsheet requires a header row and at least one data row")
                    total_rows += len(rows) - 1
                    total_cells += len(rows) * len(rows[0])
                    if total_rows > MAX_ROWS or total_cells > MAX_CELLS or len(catalog) >= MAX_SHEETS:
                        raise TableImportError("Spreadsheets exceed the total rows, cells or tables limit")
                    headers = _headers(rows[0])
                    types = [_type([row[index] for row in rows[1:]]) for index in range(len(headers))]
                    table_name = f"data_{len(catalog) + 1}"
                    definition = ", ".join(f"{_quote(name)} {kind}" for name, kind in zip(headers, types))
                    connection.execute(f"CREATE TABLE {_quote(table_name)} ({definition})")
                    connection.executemany(f"INSERT INTO {_quote(table_name)} VALUES ({','.join('?' for _ in headers)})",
                                           [[None if value == "" else value for value in row] for row in rows[1:]])
                    catalog.append({"table_name": table_name, "source_file": path.name, "sheet_name": sheet_name,
                                    "columns": [{"name": name, "type": kind} for name, kind in zip(headers, types)],
                                    "row_count": len(rows) - 1})
                    if len(json.dumps(catalog, ensure_ascii=False).encode("utf-8")) > MAX_SCHEMA_BYTES:
                        raise TableImportError("Spreadsheet schema exceeds the size limit; use fewer tables or shorter column names")
            connection.commit()
        (stage / "queryable.json").write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
        for name in ("table_sources", "queryable.json", "queryable.sqlite"):
            (stage / name).replace(destination / name)
    return catalog


def _contained(source_dir: Path, name: str) -> Path:
    source = source_dir.resolve()
    path = source_dir / name
    if not path.is_file() or path.is_symlink() or path.resolve().parent != source:
        raise TableImportError("Queryable knowledge is unavailable; reimport the original spreadsheet")
    return path.resolve()


def schema(source_dir: Path) -> list[dict]:
    manifest = _contained(source_dir, "queryable.json")
    database = _contained(source_dir, "queryable.sqlite")
    if manifest.stat().st_size > MAX_SCHEMA_BYTES:
        raise TableImportError("Queryable schema exceeds the size limit")
    try:
        catalog = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(catalog, list) or not 1 <= len(catalog) <= MAX_SHEETS:
            raise ValueError()
        names = set()
        for table in catalog:
            if not isinstance(table, dict) or not isinstance(table.get("table_name"), str) or not _TABLE_NAME.fullmatch(table["table_name"]):
                raise ValueError()
            if table["table_name"] in names or not isinstance(table.get("source_file"), str) or len(table["source_file"]) > 1024:
                raise ValueError()
            names.add(table["table_name"])
            if table.get("sheet_name") is not None and not isinstance(table["sheet_name"], str):
                raise ValueError()
            if not isinstance(table.get("row_count"), int) or not 0 <= table["row_count"] <= MAX_ROWS:
                raise ValueError()
            columns = table.get("columns")
            if not isinstance(columns, list) or not 1 <= len(columns) <= MAX_COLUMNS:
                raise ValueError()
            if any(not isinstance(column, dict) or not isinstance(column.get("name"), str)
                   or len(column["name"].encode("utf-8")) > MAX_HEADER_BYTES + 16
                   or column.get("type") not in {"TEXT", "INTEGER", "REAL"} for column in columns):
                raise ValueError()
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
            objects = connection.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if set(objects) != {(name, "table") for name in names}:
                raise ValueError()
            for table in catalog:
                actual = connection.execute(f"PRAGMA table_info({_quote(table['table_name'])})").fetchall()
                if [(item[1], item[2]) for item in actual] != [(item["name"], item["type"]) for item in table["columns"]]:
                    raise ValueError()
        return catalog
    except (ValueError, KeyError, TypeError, UnicodeError, sqlite3.Error, OSError) as exc:
        raise TableImportError("Queryable schema is invalid; reimport the original spreadsheet") from exc


def schema_signature(catalog: list[dict]) -> str:
    definitions = [{"table_name": table["table_name"], "columns": table["columns"]}
                   for table in sorted(catalog, key=lambda item: item["table_name"])]
    return hashlib.sha256(json.dumps(definitions, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def query(source_dir: Path, sql: str) -> dict:
    if not isinstance(sql, str) or not sql.strip() or len(sql.encode("utf-8")) > MAX_SQL_BYTES:
        raise TableImportError("Enter one SELECT query within the SQL size limit")
    catalog = schema(source_dir)
    tables = {item["table_name"] for item in catalog}
    database = _contained(source_dir, "queryable.sqlite")
    started = time.monotonic()
    steps = 0

    def progress():
        nonlocal steps
        steps += 1000
        return int(steps > MAX_QUERY_STEPS or time.monotonic() - started > QUERY_SECONDS)

    def authorize(action, first, second, db_name, context):
        if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE}:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ and first in tables:
            # SQLite's COUNT(*) fast path reports an empty column and no database.
            if db_name == "main" or (db_name is None and second == ""):
                return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (second or "").lower() in _FUNCTIONS:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    try:
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=1)) as connection:
            connection.enable_load_extension(False)
            connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_RESULT_BYTES)
            connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, MAX_SQL_BYTES)
            connection.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, MAX_COLUMNS)
            connection.setlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 100)
            connection.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 20)
            connection.set_authorizer(authorize)
            connection.set_progress_handler(progress, 1000)
            cursor = connection.execute(sql)
            if cursor.description is None:
                raise TableImportError("Only read-only SELECT queries are allowed")
            columns = [item[0] for item in cursor.description]
            result = {"columns": columns, "rows": [], "row_count": 0, "truncated": False}
            size = len(json.dumps(result, ensure_ascii=False).encode("utf-8"))
            if size > MAX_RESULT_BYTES:
                raise TableImportError("Query column names exceed the result size limit")
            for raw in cursor:
                row = list(raw)
                if any(isinstance(value, bytes) for value in row):
                    raise TableImportError("Binary query results are not supported")
                if any(isinstance(value, float) and not math.isfinite(value) for value in row):
                    raise TableImportError("Query produced a non-finite number")
                added = len(json.dumps(row, ensure_ascii=False).encode("utf-8")) + 3
                if len(result["rows"]) >= MAX_RESULT_ROWS or size + added + 32 > MAX_RESULT_BYTES:
                    result["truncated"] = True
                    break
                result["rows"].append(row)
                result["row_count"] += 1
                size += added
            return result
    except sqlite3.Error as exc:
        raise TableImportError("Query rejected or exceeded its limits. Use one read-only SELECT over the listed tables and columns") from exc
