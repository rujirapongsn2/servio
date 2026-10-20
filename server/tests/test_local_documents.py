"""Offline Office document ingestion tests (no embedding calls or database)."""
import io
import zipfile
from pathlib import Path
import pytest

from app.local_documents import extract_xlsx, extract_pptx, OfficeExtractionError


def _write_zip(path: Path, entries: dict[str, str]):
    with zipfile.ZipFile(path, "w") as z:
        for name, value in entries.items():
            z.writestr(name, value)


def test_spreadsheet_shared_strings_and_numbers(tmp_path):
    p = tmp_path / "sample.xlsx"
    _write_zip(p, {
        "xl/workbook.xml": '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sales" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/sharedStrings.xml": '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>สินค้าไทย</t></si></sst>',
        "xl/worksheets/sheet1.xml": '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>500</v></c></row></sheetData></worksheet>',
    })
    result = extract_xlsx(p)
    assert "Sheet: Sales" in result
    assert "A1: สินค้าไทย" in result
    assert "B1: 500" in result


def test_presentation_slide_text(tmp_path):
    p = tmp_path / "slides.pptx"
    _write_zip(p, {
        "ppt/slides/slide2.xml": '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>นโยบายบริษัท</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>'
    })
    result = extract_pptx(p)
    assert "Slide 2" in result
    assert "นโยบายบริษัท" in result


def test_bad_office_file_rejected(tmp_path):
    p = tmp_path / "bad.xlsx"
    p.write_bytes(b"not a zip")
    with pytest.raises(OfficeExtractionError):
        extract_xlsx(p)
