"""Local PDF text extraction with page-preserving Thai and English OCR."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time

from pypdf import PdfReader

MAX_PAGES = 200
MAX_CHARACTERS = 2_000_000
RASTER_LONG_EDGE = 2400
RENDER_TIMEOUT = 30
OCR_TIMEOUT = 60
OCR_DEADLINE = 300
_OCR_SLOT = threading.BoundedSemaphore(1)


class PDFExtractionError(ValueError):
    def __init__(self, path: Path, cause: str, page: int | None = None):
        self.filename = path.name
        self.page = page
        self.cause = cause
        location = f"{path.name}, page {page}" if page is not None else path.name
        super().__init__(f"{location}: {cause}")


def _command(args: list[str], timeout: float, path: Path, page: int) -> str:
    if timeout <= 0:
        raise PDFExtractionError(path, "OCR document deadline exceeded", page)
    try:
        with tempfile.TemporaryFile() as output:
            capture = "--list-langs" in args
            subprocess.run(
                args, stdout=output if capture else subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=timeout, check=True,
                env={**os.environ, "OMP_THREAD_LIMIT": "1"},
            )
            if not capture:
                return ""
            if output.tell() > 65536:
                raise PDFExtractionError(path, "oversized OCR command output", page)
            output.seek(0)
            return output.read(65536).decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired as exc:
        raise PDFExtractionError(path, "OCR command timed out", page) from exc
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PDFExtractionError(path, f"{Path(args[0]).name} failed", page) from exc


def _is_blank_pgm(path: Path) -> bool:
    with path.open("rb") as image:
        tokens: list[bytes] = []
        while len(tokens) < 4:
            line = image.readline()
            if not line:
                return False
            if not line.startswith(b"#"):
                tokens.extend(line.split())
        if tokens[0] != b"P5" or tokens[3] != b"255":
            return False
        width, height = int(tokens[1]), int(tokens[2])
        pixels = image.read(width * height + 1)
    return len(pixels) == width * height and all(pixel == 255 for pixel in pixels)


def _has_images(page) -> bool:
    resources = page.get("/Resources", {})
    if hasattr(resources, "get_object"):
        resources = resources.get_object()
    objects = resources.get("/XObject", {})
    if hasattr(objects, "get_object"):
        objects = objects.get_object()
    if objects:
        return True
    annotations = page.get("/Annots", [])
    if hasattr(annotations, "get_object"):
        annotations = annotations.get_object()
    if isinstance(annotations, list):
        for annotation in annotations:
            annotation = annotation.get_object()
            if not isinstance(annotation, dict):
                continue
            appearance = annotation.get("/AP")
            if appearance is None:
                continue
            appearance = appearance.get_object()
            if isinstance(appearance, dict):
                normal = appearance.get("/N")
                if normal is not None and isinstance(normal.get_object(), dict):
                    return True
    contents = page.get_contents()
    return contents is not None and any(operator == b"INLINE IMAGE" for _, operator in contents.operations)


def _merge_native(native: str, recognized: str) -> str:
    normalize = lambda text: re.sub(r"\s+", "", text).casefold()
    ocr_normalized = normalize(recognized)
    missing = [line for line in native.splitlines() if normalize(line) and normalize(line) not in ocr_normalized]
    return "\n".join([*missing, recognized]).strip()


def extract_pdf(path: Path) -> tuple[str, list[str]]:
    """Fail the whole PDF if a nonblank scanned page cannot be read.

    The deadline bounds OCR subprocesses and their queue wait. Native pypdf parsing
    runs in process and is not covered by that deadline.
    """
    page_number: int | None = None
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise PDFExtractionError(path, "encrypted PDFs are not supported")
        if len(reader.pages) > MAX_PAGES:
            raise PDFExtractionError(path, f"maximum {MAX_PAGES} pages exceeded")
        sections: list[str] = []
        ocr_pages: list[int] = []
        nul_pages: dict[int, int] = {}

        def clean_extracted_text(text: str, page: int) -> str:
            count = text.count("\x00")
            if count:
                nul_pages[page] = nul_pages.get(page, 0) + count
                text = text.replace("\x00", "")
            return text.strip()

        size = 0
        deadline: float | None = None
        tools: tuple[str, str] | None = None
        for page_number, page in enumerate(reader.pages, 1):
            try:
                native = clean_extracted_text(page.extract_text() or "", page_number)
                has_images = _has_images(page)
            except Exception:
                native = ""
                has_images = True
            readable = sum(character.isalnum() for character in native)
            if not native and not has_images and page.get_contents() is None:
                continue
            needs_ocr = not native or (readable < 80 and has_images)
            if needs_ocr:
                if deadline is None:
                    deadline = time.monotonic() + OCR_DEADLINE
                remaining = deadline - time.monotonic()
                if not _OCR_SLOT.acquire(timeout=max(0, remaining)):
                    raise PDFExtractionError(path, "OCR is busy; retry this document", page_number)
                try:
                    if tools is None:
                        renderer = shutil.which("pdftoppm")
                        tesseract = shutil.which("tesseract")
                        if not renderer or not tesseract:
                            raise PDFExtractionError(path, "OCR requires Poppler and Tesseract with tha and eng languages", page_number)
                        languages = _command([tesseract, "--list-langs"], min(RENDER_TIMEOUT, deadline - time.monotonic()), path, page_number)
                        if not {"tha", "eng"}.issubset(set(languages.split())):
                            raise PDFExtractionError(path, "OCR requires Tesseract tha and eng languages", page_number)
                        tools = renderer, tesseract
                    with tempfile.TemporaryDirectory(prefix="servio_ocr_") as temporary:
                        prefix = Path(temporary) / "page"
                        _command([tools[0], "-f", str(page_number), "-l", str(page_number),
                                  "-singlefile", "-scale-to", str(RASTER_LONG_EDGE), "-gray",
                                  str(path.resolve()), str(prefix)],
                                 min(RENDER_TIMEOUT, deadline - time.monotonic()), path, page_number)
                        image = prefix.with_suffix(".pgm")
                        if not image.is_file() or image.stat().st_size > RASTER_LONG_EDGE ** 2 + 4096:
                            raise PDFExtractionError(path, "invalid or oversized OCR raster", page_number)
                        if _is_blank_pgm(image):
                            recognized = ""
                        else:
                            output = Path(temporary) / "recognized"
                            _command([tools[1], str(image), str(output), "-l", "tha+eng", "--psm", "3"],
                                     min(OCR_TIMEOUT, deadline - time.monotonic()), path, page_number)
                            output_file = output.with_suffix(".txt")
                            if not output_file.is_file() or output_file.stat().st_size > MAX_CHARACTERS * 4:
                                raise PDFExtractionError(path, "invalid or oversized OCR output", page_number)
                            recognized = clean_extracted_text(output_file.read_text(encoding="utf-8"), page_number)
                            if not any(character.isalnum() for character in recognized):
                                raise PDFExtractionError(path, "nonblank scanned page has no readable OCR text", page_number)
                            ocr_pages.append(page_number)
                        native = _merge_native(native, recognized)
                finally:
                    _OCR_SLOT.release()
            if native:
                section = f"### Page {page_number}\n{native}"
                size += len(section) + (2 if sections else 0)
                if size > MAX_CHARACTERS:
                    raise PDFExtractionError(path, f"maximum {MAX_CHARACTERS} extracted characters exceeded", page_number)
                sections.append(section)
        warnings = []
        if ocr_pages:
            warnings.append(f"{path.name}: local OCR used on pages {', '.join(map(str, ocr_pages))}. Verify recognition against the original.")
        if nul_pages:
            count = sum(nul_pages.values())
            unit = "character" if count == 1 else "characters"
            warnings.append(f"{path.name}: removed {count} NUL {unit} from pages {', '.join(map(str, nul_pages))}.")
        return "\n\n".join(sections), warnings
    except PDFExtractionError:
        raise
    except Exception as exc:
        raise PDFExtractionError(path, f"could not read PDF ({type(exc).__name__})", page_number) from exc
