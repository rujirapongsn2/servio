"""Safe, dependency-free OOXML text extraction for Local Knowledge.

This is *text retrieval*, not formula evaluation or spreadsheet analytics.
ZIP XML parts and output are bounded to prevent decompression bombs.
"""
from __future__ import annotations

import posixpath
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

MAX_XML_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_CHARS = 2_000_000
MAX_ROWS = 20_000

_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


class OfficeExtractionError(ValueError):
    pass


def _read_xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    try:
        info = archive.getinfo(name)
        if info.file_size > MAX_XML_BYTES:
            raise OfficeExtractionError(f"Office XML part exceeds {MAX_XML_BYTES} bytes: {name}")
        with archive.open(info) as source:
            data = source.read(MAX_XML_BYTES + 1)
        if len(data) > MAX_XML_BYTES:
            raise OfficeExtractionError(f"Office XML part too large: {name}")
        return ET.fromstring(data)
    except (KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
        raise OfficeExtractionError(f"Cannot read Office XML part: {name}") from exc


def _append_bounded(parts: list[str], value: str, total: int) -> int:
    total += len(value)
    if total > MAX_OUTPUT_CHARS:
        raise OfficeExtractionError(
            f"Extracted text exceeds {MAX_OUTPUT_CHARS} characters; split the source document first"
        )
    parts.append(value)
    return total


def _spreadsheet_sheets(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = _read_xml(archive, "xl/workbook.xml")
    rels = _read_xml(archive, "xl/_rels/workbook.xml.rels")
    paths = {}
    for rel in rels.findall(f"{_REL}Relationship"):
        target = rel.attrib.get("Target", "")
        if target.startswith("/"):
            path = posixpath.normpath(target.lstrip("/"))
        else:
            path = posixpath.normpath(posixpath.join("xl", target))
        if path.startswith("xl/worksheets/") and path.endswith(".xml"):
            paths[rel.attrib.get("Id", "")] = path
    sheets = []
    for sheet in workbook.findall(f".//{_S}sheet"):
        rid = sheet.attrib.get(f"{_R}id", "")
        if rid in paths:
            sheets.append((sheet.attrib.get("name") or "Sheet", paths[rid]))
    return sheets


def extract_xlsx(path: Path) -> str:
    parts: list[str] = []
    total = 0
    rows_seen = 0
    try:
        with zipfile.ZipFile(path) as archive:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                strings = _read_xml(archive, "xl/sharedStrings.xml")
                for item in strings.findall(f"{_S}si"):
                    shared.append("".join((t.text or "") for t in item.iter(f"{_S}t")))
            sheets = _spreadsheet_sheets(archive)
            if not sheets:
                raise OfficeExtractionError("Workbook has no readable worksheets")
            for name, target in sheets:
                total = _append_bounded(parts, f"### Sheet: {name}\n", total)
                root = _read_xml(archive, target)
                for row in root.iter(f"{_S}row"):
                    cells: list[str] = []
                    for cell in row.findall(f"{_S}c"):
                        kind = cell.attrib.get("t", "")
                        ref = cell.attrib.get("r", "")
                        if kind == "inlineStr":
                            value = "".join(t.text or "" for t in cell.iter(f"{_S}t"))
                        else:
                            v = cell.find(f"{_S}v")
                            raw = v.text if v is not None else ""
                            if kind == "s" and raw:
                                try:
                                    value = shared[int(raw)]
                                except (ValueError, IndexError) as exc:
                                    raise OfficeExtractionError("Invalid XLSX shared string index") from exc
                            elif kind == "b":
                                value = "TRUE" if raw == "1" else "FALSE"
                            else:
                                value = raw or ""
                        formula = cell.find(f"{_S}f")
                        if not value and formula is not None:
                            value = f"formula: {formula.text or ''} (cached result unavailable)"
                        if value:
                            cells.append(f"{ref}: {value}" if ref else value)
                    if cells:
                        rows_seen += 1
                        if rows_seen > MAX_ROWS:
                            raise OfficeExtractionError(
                                f"Workbook exceeds {MAX_ROWS} readable rows; split the source or use a data-query tool"
                            )
                        total = _append_bounded(parts, " | ".join(cells) + "\n", total)
    except (OSError, zipfile.BadZipFile) as exc:
        raise OfficeExtractionError(f"Unreadable XLSX file: {path.name}") from exc
    if rows_seen == 0:
        raise OfficeExtractionError("Workbook contains no readable cells")
    return "".join(parts).strip()


def extract_pptx(path: Path) -> str:
    parts: list[str] = []
    total = 0
    try:
        with zipfile.ZipFile(path) as archive:
            slides = []
            for name in archive.namelist():
                match = re.fullmatch(r"ppt/slides/slide([0-9]+)\.xml", name)
                if match:
                    slides.append((int(match.group(1)), name))
            for number, name in sorted(slides):
                root = _read_xml(archive, name)
                paragraphs: list[str] = []
                for paragraph in root.iter(f"{_A}p"):
                    line = "".join(t.text or "" for t in paragraph.iter(f"{_A}t")).strip()
                    if line:
                        paragraphs.append(line)
                if paragraphs:
                    total = _append_bounded(parts, f"### Slide {number}\n", total)
                    total = _append_bounded(parts, "\n".join(paragraphs) + "\n\n", total)
    except (OSError, zipfile.BadZipFile) as exc:
        raise OfficeExtractionError(f"Unreadable PPTX file: {path.name}") from exc
    if not parts:
        raise OfficeExtractionError("Presentation contains no readable slide text")
    return "".join(parts).strip()
