"""Actual spreadsheet imports and SQLite queries; no external services."""
import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

from app import knowledge_tables as tables


def csv(path: Path, text: str, encoding="utf-8-sig") -> Path:
    path.write_bytes(text.encode(encoding))
    return path


def xlsx(path: Path, sheets: dict[str, str]) -> Path:
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + ''.join(f'<sheet name="{escape(name)}" r:id="r{index}"/>' for index, name in enumerate(sheets, 1)) + '</sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(f'<Relationship Id="r{index}" Target="worksheets/sheet{index}.xml"/>' for index in range(1, len(sheets)+1)) + '</Relationships>')
        for index, body in enumerate(sheets.values(), 1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", f'<worksheet xmlns="{ns}"><sheetData>{body}</sheetData></worksheet>')
    return path


@pytest.fixture
def bundle(tmp_path):
    source = csv(tmp_path / "ยอดขาย.csv", "รหัส,สินค้า,จำนวน,ราคา\n001,โต๊ะ,2,100.5\n002,เก้าอี้,3,50\n003,โต๊ะ,4,100.5\n")
    target = tmp_path / "source"
    tables.build_database([source], target)
    return target


def test_csv_thai_aggregates_types_and_reopen(bundle):
    catalog = tables.schema(bundle)
    assert catalog[0]["source_file"] == "ยอดขาย.csv"
    assert [column["type"] for column in catalog[0]["columns"]] == ["TEXT", "TEXT", "INTEGER", "REAL"]
    result = tables.query(bundle, 'SELECT "สินค้า", SUM("จำนวน" * "ราคา") AS total FROM data_1 WHERE "จำนวน" >= 2 GROUP BY "สินค้า" ORDER BY total DESC')
    assert result == {"columns": ["สินค้า", "total"], "rows": [["โต๊ะ", 603.0], ["เก้าอี้", 150.0]], "row_count": 2, "truncated": False}
    assert tables.query(bundle, 'SELECT "รหัส" FROM data_1 ORDER BY "รหัส" LIMIT 1')["rows"] == [["001"]]
    assert (bundle / "table_sources/1.csv").read_bytes().startswith(b"\xef\xbb\xbf")


def test_count_star_fast_path_is_allowed_after_reopen(bundle):
    assert tables.query(bundle, "SELECT COUNT(*) AS total FROM data_1")["rows"] == [[3]]
    assert tables.schema(bundle)[0]["row_count"] == 3
    assert tables.query(bundle, "SELECT COUNT(*) FROM data_1 WHERE จำนวน >= 3")["rows"] == [[2]]
    assert tables.query(bundle, "WITH counts AS (SELECT COUNT(*) AS n FROM data_1) SELECT n FROM counts")["rows"] == [[3]]
    with pytest.raises(tables.TableImportError):
        tables.query(bundle, "SELECT COUNT(*) FROM sqlite_master")


def test_csv_thai_encoding_quoted_fields_duplicate_headers(tmp_path):
    source = csv(tmp_path / "thai.csv", 'ชื่อ;ชื่อ;;ยอด\n"โต๊ะ;ใหญ่";"มี\nบรรทัด";;12\n', "cp874")
    destination = tmp_path / "knowledge"
    catalog = tables.build_database([source], destination)
    assert [item["name"] for item in catalog[0]["columns"]] == ["ชื่อ", "ชื่อ_2", "column_3", "ยอด"]
    assert tables.query(destination, "SELECT * FROM data_1")["rows"] == [["โต๊ะ;ใหญ่", "มี\nบรรทัด", None, 12]]


def test_xlsx_multiple_sheets_sparse_columns_and_cached_formula(tmp_path):
    source = xlsx(tmp_path / "book.xlsx", {
        "ยอดขาย": '<row r="1"><c r="A1" t="inlineStr"><is><t>สินค้า</t></is></c><c r="C1" t="inlineStr"><is><t>ยอด</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>โต๊ะ</t></is></c><c r="C2"><f>100*2</f><v>200</v></c></row>',
        "ต้นทุน": '<row r="1"><c r="A1" t="inlineStr"><is><t>ต้นทุน</t></is></c></row><row r="2"><c r="A2"><v>50</v></c></row>',
    })
    destination = tmp_path / "source"
    catalog = tables.build_database([source], destination)
    assert [item["sheet_name"] for item in catalog] == ["ยอดขาย", "ต้นทุน"]
    assert tables.query(destination, 'SELECT SUM("ยอด") - (SELECT SUM("ต้นทุน") FROM data_2) FROM data_1')["rows"] == [[150]]
    assert tables.query(destination, "SELECT * FROM data_1")["rows"] == [["โต๊ะ", None, 200]]


def test_formula_missing_cache_rejected_without_partial_artifacts(tmp_path):
    source = xlsx(tmp_path / "formula.xlsx", {"Sheet": '<row><c r="A1" t="inlineStr"><is><t>Total</t></is></c></row><row><c r="A2"><f>1+1</f></c></row>'})
    destination = tmp_path / "source"
    with pytest.raises(tables.TableImportError, match="cached result"):
        tables.build_database([source], destination)
    assert list(destination.iterdir()) == []


@pytest.mark.parametrize("sql", [
    'DELETE FROM data_1', 'UPDATE data_1 SET "จำนวน"=0', 'DROP TABLE data_1',
    "ATTACH DATABASE ':memory:' AS other", 'PRAGMA table_info(data_1)',
    'SELECT * FROM sqlite_master', 'SELECT * FROM sqlite_schema',
    "SELECT load_extension('malicious')", "SELECT randomblob(100000000)",
    'SELECT 1; SELECT 2', 'CREATE TABLE test(x)', "SELECT writefile('/tmp/escape','x')",
])
def test_query_rejects_mutation_and_escape(bundle, sql):
    with pytest.raises(tables.TableImportError, match="read-only SELECT"):
        tables.query(bundle, sql)
    assert tables.query(bundle, 'SELECT SUM("จำนวน") FROM data_1')["rows"] == [[9]]


def test_cte_and_math_allowed_but_recursion_bounded(bundle, monkeypatch):
    assert tables.query(bundle, 'WITH totals AS (SELECT SUM("จำนวน") AS n FROM data_1) SELECT round(n / 2.0, 1) FROM totals')["rows"] == [[4.5]]
    monkeypatch.setattr(tables, "MAX_QUERY_STEPS", 5000)
    with pytest.raises(tables.TableImportError):
        tables.query(bundle, 'WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n) SELECT sum(x) FROM n')


def test_output_rows_truncated_but_aggregate_uses_all_rows(tmp_path):
    source = csv(tmp_path / "many.csv", "จำนวน\n" + "\n".join(str(value) for value in range(1, 501)))
    destination = tmp_path / "source"
    tables.build_database([source], destination)
    result = tables.query(destination, "SELECT * FROM data_1")
    assert result["row_count"] == 200
    assert result["truncated"] is True
    assert tables.query(destination, "SELECT SUM(จำนวน),COUNT(*) FROM data_1")["rows"] == [[125250, 500]]


def test_utf8_result_byte_limit(tmp_path):
    source = csv(tmp_path / "wide.csv", "ข้อความ\n" + "\n".join("ก" * 1000 for _ in range(100)))
    destination = tmp_path / "source"
    tables.build_database([source], destination)
    result = tables.query(destination, "SELECT * FROM data_1")
    assert result["truncated"] is True
    assert len(json.dumps(result, ensure_ascii=False).encode("utf-8")) <= tables.MAX_RESULT_BYTES


@pytest.mark.parametrize("text", ["x,y\n1\n", "x,y\n1,2,3\n", "x;y\n1\n", "x,y\n", ""])
def test_invalid_rows_and_empty_files_fail(tmp_path, text):
    source = csv(tmp_path / "bad.csv", text)
    with pytest.raises(tables.TableImportError):
        tables.build_database([source], tmp_path / "source")


def test_total_limits_and_unsupported_files(tmp_path, monkeypatch):
    source = csv(tmp_path / "data.csv", "x,y\n1,2\n3,4\n")
    monkeypatch.setattr(tables, "MAX_ROWS", 1)
    with pytest.raises(tables.TableImportError):
        tables.build_database([source], tmp_path / "source")
    with pytest.raises(tables.TableImportError, match="CSV or XLSX"):
        tables.build_database([tmp_path / "doc.pdf"], tmp_path / "other")


def test_mixed_files_ignore_nontabular_inputs(tmp_path):
    source = csv(tmp_path / "data.csv", "x\n1\n")
    catalog = tables.build_database([tmp_path / "doc.pdf", source], tmp_path / "source")
    assert len(catalog) == 1


def test_schema_tampering_and_symlink_rejected(bundle, tmp_path):
    manifest = bundle / "queryable.json"
    original = manifest.read_text()
    catalog = json.loads(original)
    catalog[0]["table_name"] = "sqlite_master"
    manifest.write_text(json.dumps(catalog))
    with pytest.raises(tables.TableImportError, match="schema is invalid"):
        tables.schema(bundle)
    manifest.write_text(original)
    external = tmp_path / "external.sqlite"
    (bundle / "queryable.sqlite").replace(external)
    (bundle / "queryable.sqlite").symlink_to(external)
    with pytest.raises(tables.TableImportError, match="unavailable"):
        tables.query(bundle, "SELECT * FROM data_1")


def test_sql_error_does_not_expose_paths(bundle):
    with pytest.raises(tables.TableImportError) as error:
        tables.query(bundle, "SELECT missing FROM data_1")
    assert str(bundle) not in str(error.value)


def test_large_integer_is_preserved_as_text(tmp_path):
    value = "9" * 5000
    source = csv(tmp_path / "large.csv", f"reference\n{value}\n")
    destination = tmp_path / "source"
    tables.build_database([source], destination)
    assert tables.query(destination, "SELECT * FROM data_1")["rows"] == [[value]]


def test_xlsx_merged_cells_rejected(tmp_path):
    source = xlsx(tmp_path / "merged.xlsx", {"Sheet": '<row><c r="A1" t="inlineStr"><is><t>Total</t></is></c></row><row><c r="A2"><v>2</v></c></row><mergeCells><mergeCell ref="A1:B1"/></mergeCells>'})
    with pytest.raises(tables.TableImportError, match="Merged cells"):
        tables.build_database([source], tmp_path / "source")


def test_schema_and_header_limits_fail_before_ready(tmp_path, monkeypatch):
    source = csv(tmp_path / "long.csv", "ก" * 100 + "\n1\n")
    with pytest.raises(tables.TableImportError, match="column names"):
        tables.build_database([source], tmp_path / "long")
    source = csv(tmp_path / "simple.csv", "value\n1\n")
    monkeypatch.setattr(tables, "MAX_SCHEMA_BYTES", 10)
    destination = tmp_path / "source"
    with pytest.raises(tables.TableImportError, match="schema exceeds"):
        tables.build_database([source], destination)
    assert list(destination.iterdir()) == []


def test_xlsx_sparse_matrix_is_bounded_during_parse(tmp_path, monkeypatch):
    source = xlsx(tmp_path / "sparse.xlsx", {"Sheet": '<row><c r="A1" t="inlineStr"><is><t>Total</t></is></c></row><row><c r="GR2"><v>2</v></c></row>'})
    monkeypatch.setattr(tables, "MAX_CELLS", 100)
    with pytest.raises(tables.TableImportError, match="cell limit"):
        tables.build_database([source], tmp_path / "source")
