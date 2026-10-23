"""PDF extraction boundaries without external OCR or database writes."""
import asyncio
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import threading

import pytest
from pypdf import PdfWriter

from app import local_pdf as pdf


class Page(dict):
    def __init__(self, text="", image=False, contents=True):
        super().__init__({"/Resources": {"/XObject": {"scan": object()}}} if image else {})
        self.text = text
        self.contents = SimpleNamespace(operations=[]) if contents else None

    def extract_text(self):
        return self.text

    def get_contents(self):
        return self.contents


@pytest.fixture
def document(monkeypatch, tmp_path):
    path = tmp_path / "policy.pdf"
    path.write_bytes(b"mock PDF boundary")
    def pages(*items):
        monkeypatch.setattr(pdf, "PdfReader", lambda _: SimpleNamespace(pages=list(items), is_encrypted=False))
        return path
    return pages


@pytest.fixture
def ocr(monkeypatch):
    state = {"text": "นโยบายบริษัท Company policy", "blank": False, "commands": [], "temps": []}
    monkeypatch.setattr(pdf.shutil, "which", lambda name: "/bin/" + name)
    def command(args, timeout, path, page):
        state["commands"].append(args)
        if args[-1] == "--list-langs":
            return "List of available languages (2):\neng\ntha\n"
        if "pdftoppm" in args[0]:
            output = Path(args[-1]).with_suffix(".pgm")
            state["temps"].append(output.parent)
            output.write_bytes(b"P5\n2 2\n255\n" + (b"\xff" * 4 if state["blank"] else b"\x00" * 4))
        else:
            Path(args[2]).with_suffix(".txt").write_text(state["text"], encoding="utf-8")
        return ""
    monkeypatch.setattr(pdf, "_command", command)
    return state


def test_native_text_unchanged_without_ocr_tools(document, monkeypatch):
    path = document(Page("Hello native ไทย"), Page(contents=False), Page("Second"))
    monkeypatch.setattr(pdf.shutil, "which", lambda _: pytest.fail("native PDF must not need OCR tools"))
    assert pdf.extract_pdf(path) == ("### Page 1\nHello native ไทย\n\n### Page 3\nSecond", [])


def test_real_pdf_nul_is_removed_before_knowledge_hashing(tmp_path, monkeypatch):
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    from app.okf_service import _collect_knowledge_sources

    path = tmp_path / "furniture.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
    })
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 10 90 Td (Furniture\\000catalog) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    writer.write(path)
    monkeypatch.setattr(pdf.shutil, "which", lambda _: pytest.fail("native PDF must not need OCR"))

    expected = "### Page 1\nFurniturecatalog"
    text, warnings = pdf.extract_pdf(path)
    assert text == expected
    assert warnings == ["furniture.pdf: removed 1 NUL character from pages 1."]
    preview, preview_warnings = _collect_knowledge_sources([path], preview=True)
    imported, import_warnings = _collect_knowledge_sources([path])
    assert preview[0].text == imported[0].text == expected
    assert preview[0].content_hash == imported[0].content_hash == hashlib.sha256(expected.encode()).hexdigest()
    assert preview_warnings == import_warnings == warnings


def test_native_and_ocr_nul_preserve_thai_whitespace_and_pages(document, ocr):
    ocr["text"] = "สินค้า\x00  ไทย\nราคา\t100"
    text, warnings = pdf.extract_pdf(document(
        Page("ข้อความ\x00  ไทย\nราคา\t200"), Page(contents=False), Page("หัว\x00ข้อ", image=True),
    ))
    assert text == "### Page 1\nข้อความ  ไทย\nราคา\t200\n\n### Page 3\nหัวข้อ\nสินค้า  ไทย\nราคา\t100"
    assert "local OCR used on pages 3" in warnings[0]
    assert warnings[1] == "policy.pdf: removed 3 NUL characters from pages 1, 3."


def test_nul_only_native_text_uses_ocr(document, ocr):
    text, warnings = pdf.extract_pdf(document(Page("\x00\x00")))
    assert text == "### Page 1\nนโยบายบริษัท Company policy"
    assert "local OCR used on pages 1" in warnings[0]
    assert warnings[1] == "policy.pdf: removed 2 NUL characters from pages 1."


def test_nul_only_native_blank_page_is_omitted(document, ocr):
    ocr["blank"] = True
    text, warnings = pdf.extract_pdf(document(Page("\x00"), Page("Next")))
    assert text == "### Page 2\nNext"
    assert warnings == ["policy.pdf: removed 1 NUL character from pages 1."]


def test_nul_only_ocr_text_is_not_readable(document, ocr):
    ocr["text"] = "\x00\x00"
    with pytest.raises(pdf.PDFExtractionError, match="page 1: nonblank scanned page has no readable OCR text"):
        pdf.extract_pdf(document(Page(image=True)))


def test_scan_uses_local_thai_english_and_cleans_temp(document, ocr):
    result, warnings = pdf.extract_pdf(document(Page(image=True)))
    assert result == "### Page 1\nนโยบายบริษัท Company policy"
    assert "pages 1" in warnings[0]
    assert any("tha+eng" in cmd for cmd in ocr["commands"])
    assert all(not path.exists() for path in ocr["temps"])


def test_mixed_pages_preserve_original_numbers_and_native_header(document, ocr):
    path = document(Page("Digital text"), Page("Header", image=True), Page("Last"))
    text, warnings = pdf.extract_pdf(path)
    assert text == "### Page 1\nDigital text\n\n### Page 2\nHeader\nนโยบายบริษัท Company policy\n\n### Page 3\nLast"
    assert "pages 2" in warnings[0]


def test_native_header_not_duplicated(document, ocr):
    ocr["text"] = "Header\nScanned body ไทย"
    text, _ = pdf.extract_pdf(document(Page("Header", image=True)))
    assert text.count("Header") == 1


def test_blank_scan_omitted_without_renumbering(document, ocr):
    ocr["blank"] = True
    text, warnings = pdf.extract_pdf(document(Page(image=True), Page("Next")))
    assert text == "### Page 2\nNext"
    assert warnings == []


def test_nonblank_empty_ocr_fails_entire_mixed_document(document, ocr):
    ocr["text"] = ""
    with pytest.raises(pdf.PDFExtractionError, match="policy.pdf, page 2: nonblank"):
        pdf.extract_pdf(document(Page("Digital"), Page(image=True)))
    assert all(not path.exists() for path in ocr["temps"])


def test_missing_tools_fail_with_filename_and_page(document, monkeypatch):
    monkeypatch.setattr(pdf.shutil, "which", lambda _: None)
    with pytest.raises(pdf.PDFExtractionError, match="policy.pdf, page 2: OCR requires Poppler"):
        pdf.extract_pdf(document(Page("Digital"), Page(image=True)))


def test_missing_language_rejected(document, ocr, monkeypatch):
    monkeypatch.setattr(pdf, "_command", lambda *args: "eng")
    with pytest.raises(pdf.PDFExtractionError, match="tha and eng"):
        pdf.extract_pdf(document(Page(image=True)))


def test_bad_and_encrypted_pdf(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"broken")
    with pytest.raises(pdf.PDFExtractionError, match="broken.pdf: could not read PDF"):
        pdf.extract_pdf(path)
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("secret")
    writer.write(path)
    with pytest.raises(pdf.PDFExtractionError, match="encrypted"):
        pdf.extract_pdf(path)


def test_page_limit(document, monkeypatch):
    monkeypatch.setattr(pdf, "MAX_PAGES", 1)
    with pytest.raises(pdf.PDFExtractionError, match="maximum 1 pages"):
        pdf.extract_pdf(document(Page("One"), Page("Two")))


def test_text_limit(document, monkeypatch):
    monkeypatch.setattr(pdf, "MAX_CHARACTERS", 12)
    with pytest.raises(pdf.PDFExtractionError, match="extracted characters"):
        pdf.extract_pdf(document(Page("too much text")))


def test_command_timeout_is_typed_and_threads_bounded(tmp_path, monkeypatch):
    import subprocess
    def timeout(args, **kwargs):
        assert kwargs["env"]["OMP_THREAD_LIMIT"] == "1"
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])
    monkeypatch.setattr(pdf.subprocess, "run", timeout)
    with pytest.raises(pdf.PDFExtractionError, match="policy.pdf, page 3: OCR command timed out"):
        pdf._command(["tesseract"], 0.01, tmp_path / "policy.pdf", 3)


def test_ocr_failure_cleans_temp_and_releases_slot(document, ocr, monkeypatch):
    original = pdf._command
    def fail(args, timeout, path, page):
        if "tesseract" in args[0] and "--list-langs" not in args:
            raise pdf.PDFExtractionError(path, "OCR command timed out", page)
        return original(args, timeout, path, page)
    monkeypatch.setattr(pdf, "_command", fail)
    with pytest.raises(pdf.PDFExtractionError, match="timed out"):
        pdf.extract_pdf(document(Page(image=True)))
    assert all(not path.exists() for path in ocr["temps"])
    assert pdf._OCR_SLOT.acquire(blocking=False)
    pdf._OCR_SLOT.release()


def test_document_deadline_includes_queue_wait(document, ocr, monkeypatch):
    monkeypatch.setattr(pdf, "OCR_DEADLINE", 0.01)
    assert pdf._OCR_SLOT.acquire(blocking=False)
    try:
        with pytest.raises(pdf.PDFExtractionError, match="OCR is busy"):
            pdf.extract_pdf(document(Page(image=True)))
    finally:
        pdf._OCR_SLOT.release()


def test_failed_pdf_skipped_with_visible_warning_in_batch(document, monkeypatch, tmp_path):
    from app.okf_service import _collect_knowledge_sources
    path = document(Page("Digital"), Page(image=True))
    monkeypatch.setattr(pdf.shutil, "which", lambda _: None)
    text = tmp_path / "valid.txt"
    text.write_text("Valid knowledge")
    sources, warnings = _collect_knowledge_sources([path, text])
    assert [source.source_file for source in sources] == ["valid.txt"]
    assert any("policy.pdf, page 2" in warning for warning in warnings)


@pytest.mark.parametrize("endpoint", ["preview", "import"])
def test_upload_extraction_does_not_block_event_loop(monkeypatch, endpoint):
    with patch("app.db_config.init_database"):
        from app import admin_routes as routes
    started = threading.Event()
    release = threading.Event()
    def slow(**kwargs):
        started.set()
        assert release.wait(5)
        return {"source_count": 1, "id": 1}
    class Service:
        preview_knowledge_files = staticmethod(slow)
        import_knowledge_files = staticmethod(slow)
    async def save(**kwargs):
        return []
    monkeypatch.setattr(routes, "OKFService", Service)
    monkeypatch.setattr(routes, "_require_resolved_team_access", lambda *args: 1)
    monkeypatch.setattr(routes, "_save_okf_upload_sources", save)
    import app.local_rag as rag
    monkeypatch.setattr(rag, "enabled", lambda: False)
    async def run():
        if endpoint == "preview":
            request = routes.preview_okf_knowledge(team_agent_id=1, display_name="x", import_mode="knowledge", urls=None, pasted_text=None, file=None, files=None, current_user="admin")
        else:
            request = routes.import_okf_bundle(team_agent_id=1, display_name="x", visibility="team", import_mode="knowledge", urls=None, pasted_text=None, create_tool=False, assign_agent_id=None, file=None, files=None, current_user="admin")
        task = asyncio.create_task(request)
        try:
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(0.01)
            assert started.is_set()
            assert not task.done()
        finally:
            release.set()
        await task
    asyncio.run(run())


def test_render_failure_fails_whole_pdf(document, ocr, monkeypatch):
    original = pdf._command
    def fail(args, timeout, path, page):
        if "pdftoppm" in args[0]:
            raise pdf.PDFExtractionError(path, "pdftoppm failed", page)
        return original(args, timeout, path, page)
    monkeypatch.setattr(pdf, "_command", fail)
    with pytest.raises(pdf.PDFExtractionError, match="policy.pdf, page 2: pdftoppm failed"):
        pdf.extract_pdf(document(Page("native"), Page(image=True)))


def test_oversized_raster_rejected_and_cleaned(document, ocr, monkeypatch):
    original = pdf._command
    def huge(args, *rest):
        result = original(args, *rest)
        if "pdftoppm" in args[0]:
            with Path(args[-1]).with_suffix(".pgm").open("wb") as image:
                image.truncate(pdf.RASTER_LONG_EDGE ** 2 + 4097)
        return result
    monkeypatch.setattr(pdf, "_command", huge)
    with pytest.raises(pdf.PDFExtractionError, match="oversized OCR raster"):
        pdf.extract_pdf(document(Page(image=True)))
    assert all(not path.exists() for path in ocr["temps"])


def test_oversized_ocr_output_rejected(document, ocr, monkeypatch):
    monkeypatch.setattr(pdf, "MAX_CHARACTERS", 5)
    ocr["text"] = "a" * 21
    with pytest.raises(pdf.PDFExtractionError, match="oversized OCR output"):
        pdf.extract_pdf(document(Page(image=True)))


def test_expired_deadline_starts_no_command(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf.subprocess, "run", lambda *args, **kwargs: pytest.fail("expired deadline must not run"))
    with pytest.raises(pdf.PDFExtractionError, match="deadline exceeded"):
        pdf._command(["tesseract"], 0, tmp_path / "policy.pdf", 1)


@pytest.mark.parametrize("image", [False, True])
def test_native_extraction_failure_falls_back_to_ocr(document, ocr, image):
    class BrokenText(Page):
        def extract_text(self):
            raise ValueError("broken text encoding")
    text, warnings = pdf.extract_pdf(document(BrokenText(image=image)))
    assert text == "### Page 1\nนโยบายบริษัท Company policy"
    assert "pages 1" in warnings[0]


def test_faint_nonwhite_scan_is_not_silently_blank(document, ocr, monkeypatch):
    original = pdf._command
    def faint(args, *rest):
        result = original(args, *rest)
        if "pdftoppm" in args[0]:
            Path(args[-1]).with_suffix(".pgm").write_bytes(b"P5\n2 2\n255\n" + b"\xfe" * 4)
        return result
    monkeypatch.setattr(pdf, "_command", faint)
    ocr["text"] = ""
    with pytest.raises(pdf.PDFExtractionError, match="nonblank scanned page"):
        pdf.extract_pdf(document(Page(image=True)))


@pytest.mark.parametrize("header", [False, True])
def test_inline_scan_preserved(tmp_path, ocr, header):
    from pypdf.generic import DecodedStreamObject, NameObject, DictionaryObject
    path = tmp_path / "inline.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    content = DecodedStreamObject()
    content.set_data(b"q 100 0 0 100 0 0 cm BI /W 1 /H 1 /BPC 8 /CS /G ID \x00 EI Q")
    if header:
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        content.set_data(content.get_data() + b" BT /F1 12 Tf 10 90 Td (Header) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    writer.write(path)
    text, warnings = pdf.extract_pdf(path)
    assert "นโยบายบริษัท Company policy" in text
    assert "pages 1" in warnings[0]
    if header:
        assert "Header" in text


@pytest.mark.parametrize("header", [False, True])
@pytest.mark.parametrize("mixed", [False, True])
def test_annotation_scan_preserved(tmp_path, ocr, header, mixed):
    from pypdf.generic import (
        ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject,
    )
    writer = PdfWriter()

    def add_native(page, value):
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
        })
        content = DecodedStreamObject()
        content.set_data(b"BT /F1 12 Tf 10 90 Td (" + value.encode() + b") Tj ET")
        page[NameObject("/Contents")] = writer._add_object(content)

    if mixed:
        add_native(writer.add_blank_page(width=100, height=100), "Native source")
    page = writer.add_blank_page(width=100, height=100)
    if header:
        add_native(page, "Header")
    bounds = ArrayObject([NumberObject(value) for value in (0, 0, 100, 100)])
    appearance = DecodedStreamObject()
    appearance.set_data(b"q 100 0 0 100 0 0 cm BI /W 1 /H 1 /BPC 8 /CS /G ID \x00 EI Q")
    appearance.update({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Form"),
        NameObject("/BBox"): bounds,
    })
    annotation = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/Stamp"),
        NameObject("/Rect"): bounds,
        NameObject("/F"): NumberObject(4),
        NameObject("/AP"): DictionaryObject({NameObject("/N"): writer._add_object(appearance)}),
    })
    page[NameObject("/Annots")] = ArrayObject([writer._add_object(annotation)])
    path = tmp_path / "annotation.pdf"
    writer.write(path)

    result, warnings = pdf.extract_pdf(path)
    page_number = 2 if mixed else 1
    expected = f"### Page {page_number}\n" + ("Header\n" if header else "") + ocr["text"]
    if mixed:
        expected = "### Page 1\nNative source\n\n" + expected
    assert result == expected
    assert f"pages {page_number}" in warnings[0]


@pytest.mark.parametrize("kind", ["null_annots", "no_ap", "null_ap", "null_normal"])
def test_nonrendering_annotations_need_no_ocr(document, monkeypatch, kind):
    from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NullObject
    annotation = DictionaryObject({NameObject("/Subtype"): NameObject("/Link")})
    if kind == "null_ap":
        annotation[NameObject("/AP")] = NullObject()
    elif kind == "null_normal":
        annotation[NameObject("/AP")] = DictionaryObject({NameObject("/N"): NullObject()})
    page = Page("Native text")
    page["/Annots"] = NullObject() if kind == "null_annots" else ArrayObject([annotation])
    monkeypatch.setattr(pdf.shutil, "which", lambda _: pytest.fail("annotation has no rendered content"))
    assert pdf.extract_pdf(document(page)) == ("### Page 1\nNative text", [])


def test_commands_discard_unused_output(tmp_path):
    import sys
    result = pdf._command([sys.executable, "-c", "import sys; print('x' * 1000000); sys.stderr.write('e' * 1000000)"], 5, tmp_path / "policy.pdf", 1)
    assert result == ""


def test_language_listing_output_is_bounded(tmp_path, monkeypatch):
    import sys
    original = pdf.subprocess.run
    def emit(args, **kwargs):
        return original([sys.executable, "-c", "print('x' * 100000)"], **kwargs)
    monkeypatch.setattr(pdf.subprocess, "run", emit)
    with pytest.raises(pdf.PDFExtractionError, match="oversized OCR command output"):
        pdf._command(["tesseract", "--list-langs"], 5, tmp_path / "policy.pdf", 1)


def test_command_output_streams_do_not_use_memory_pipes(tmp_path, monkeypatch):
    def run(args, **kwargs):
        assert kwargs["stdout"] == pdf.subprocess.DEVNULL
        assert kwargs["stderr"] == pdf.subprocess.DEVNULL
        assert "capture_output" not in kwargs
    monkeypatch.setattr(pdf.subprocess, "run", run)
    assert pdf._command(["tesseract", "image.pgm", "recognized"], 1, tmp_path / "policy.pdf", 1) == ""
