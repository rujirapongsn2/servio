"""Bounded editable workbook snapshots backed by Queryable Knowledge artifacts."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app import knowledge_tables as tables


class TableRevisionConflict(ValueError):
    pass


class EditableTable(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    table_name: str = Field(pattern=r"^data_[1-9][0-9]*$", max_length=32)
    name: str = Field(min_length=1, max_length=255)
    columns: list[str] = Field(min_length=1, max_length=tables.MAX_COLUMNS)
    rows: list[list[str]] = Field(max_length=tables.MAX_ROWS)

    @field_validator("name")
    @classmethod
    def meaningful_name(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("Table name is required")
        return value.strip()

    @field_validator("columns")
    @classmethod
    def unique_columns(cls, values):
        columns = [value.strip() for value in values]
        if any(not column or len(column.encode("utf-8")) > tables.MAX_HEADER_BYTES or "\x00" in column for column in columns):
            raise ValueError("Column names are required and must fit within 256 bytes")
        if len({column.casefold() for column in columns}) != len(columns):
            raise ValueError("Column names must be unique")
        return columns

    @model_validator(mode="after")
    def rectangular(self):
        if (len(self.rows) + 1) * len(self.columns) > tables.MAX_CELLS:
            raise ValueError("Table exceeds the cell limit")
        for row in self.rows:
            if len(row) != len(self.columns):
                raise ValueError("Every row must match the column count")
            for cell in row:
                if "\x00" in cell or len(cell.encode("utf-8")) > tables.MAX_CELL_BYTES:
                    raise ValueError("A cell is invalid or too large")
        return self


class EditableWorkbook(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    tables: list[EditableTable] = Field(min_length=1, max_length=tables.MAX_SHEETS)

    @model_validator(mode="after")
    def bounded(self):
        if len({table.table_name for table in self.tables}) != len(self.tables):
            raise ValueError("Table IDs must be unique")
        if sum(len(table.rows) for table in self.tables) > tables.MAX_ROWS:
            raise ValueError("Workbook exceeds the row limit")
        if sum((len(table.rows) + 1) * len(table.columns) for table in self.tables) > tables.MAX_CELLS:
            raise ValueError("Workbook exceeds the cell limit")
        if len(self.model_dump_json().encode("utf-8")) > tables.MAX_BYTES:
            raise ValueError("Workbook exceeds 50 MB")
        return self


class SaveEditableWorkbook(EditableWorkbook):
    expected_revision: str = Field(pattern=r"^[0-9a-f]{64}$")


def revision(bundle) -> str:
    raw = f"{bundle.id}:{bundle.storage_path}:{bundle.updated_at.isoformat() if bundle.updated_at else ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def csv_text(table: EditableTable) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(table.columns)
    writer.writerows(table.rows)
    return output.getvalue()


def import_drafts(paths: list[Path]) -> EditableWorkbook:
    if not paths or any(path.suffix.lower() not in {".csv", ".xlsx"} for path in paths):
        raise tables.TableImportError("Choose only CSV or Excel (.xlsx) files")
    if sum(path.stat().st_size for path in paths) > tables.MAX_BYTES:
        raise tables.TableImportError("Spreadsheets exceed 50 MB")
    drafts = []
    total_rows = total_cells = 0
    for path in paths:
        sheets = [(None, tables._csv_rows(path))] if path.suffix.lower() == ".csv" else tables._xlsx_rows(path)
        if not sheets:
            raise tables.TableImportError("Spreadsheet contains no readable worksheets")
        for sheet_name, rows in sheets:
            if not rows:
                raise tables.TableImportError("Spreadsheet requires a header row")
            total_rows += len(rows) - 1
            total_cells += len(rows) * len(rows[0])
            if total_rows > tables.MAX_ROWS or total_cells > tables.MAX_CELLS or len(drafts) >= tables.MAX_SHEETS:
                raise tables.TableImportError("Workbook exceeds the rows, columns or tables limit")
            drafts.append(EditableTable(table_name=f"data_{len(drafts)+1}", name=sheet_name or path.stem,
                                        columns=tables._headers(rows[0]), rows=rows[1:]))
    return EditableWorkbook(tables=drafts)


def read_drafts(source: Path) -> EditableWorkbook:
    catalog = tables.schema(source)
    drafts = []
    total_rows = total_cells = total_bytes = 0
    with closing(sqlite3.connect((source / "queryable.sqlite").resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        for item in catalog:
            rows = []
            for values in connection.execute(f'SELECT * FROM "{item["table_name"]}" ORDER BY rowid'):
                if any(isinstance(value, bytes) for value in values):
                    raise tables.TableImportError("Binary table cells are not supported")
                row = ["" if value is None else str(value) for value in values]
                total_rows += 1
                total_cells += len(row)
                total_bytes += sum(len(value.encode("utf-8")) for value in row)
                if total_rows > tables.MAX_ROWS or total_cells > tables.MAX_CELLS or total_bytes > tables.MAX_BYTES:
                    raise tables.TableImportError("Workbook exceeds the editing size limit")
                rows.append(row)
            drafts.append(EditableTable(table_name=item["table_name"], name=item.get("display_name") or item.get("sheet_name") or Path(item["source_file"]).stem,
                                        columns=[column["name"] for column in item["columns"]], rows=rows))
    return EditableWorkbook(tables=drafts)


def write_drafts(workbook: EditableWorkbook, destination: Path) -> list[dict]:
    for name in ("queryable.sqlite", "queryable.json"):
        (destination / name).unlink(missing_ok=True)
    shutil.rmtree(destination / "table_sources", ignore_errors=True)
    with tempfile.TemporaryDirectory(prefix="editable_tables_") as temporary:
        paths = []
        for table in workbook.tables:
            path = Path(temporary) / f"{table.table_name}.csv"
            path.write_text(csv_text(table), encoding="utf-8-sig")
            paths.append(path)
        catalog = tables.build_database(paths, destination, allow_empty=True)
    with closing(sqlite3.connect(destination / "queryable.sqlite")) as connection:
        for index, item in enumerate(catalog):
            connection.execute(f'ALTER TABLE "{item["table_name"]}" RENAME TO "editing_{index}"')
        for index, (item, table) in enumerate(zip(catalog, workbook.tables)):
            connection.execute(f'ALTER TABLE "editing_{index}" RENAME TO "{table.table_name}"')
            item.update(table_name=table.table_name, display_name=table.name, source_file=table.name + ".csv", sheet_name=None)
        connection.commit()
    encoded = json.dumps(catalog, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > tables.MAX_SCHEMA_BYTES:
        raise tables.TableImportError("Table schema exceeds the size limit")
    (destination / "queryable.json").write_text(encoded, encoding="utf-8")
    return catalog
