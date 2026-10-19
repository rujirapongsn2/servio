"""Local file-backed Open Knowledge Format (OKF) storage and retrieval."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional
from xml.etree import ElementTree as ET

import yaml
from sqlalchemy import or_

from app.db_config import get_db
from app.orm_models import (
    Admin,
    AgentTool,
    OKFBundle,
    OKFConceptIndex,
    OKFLinkIndex,
    TeamAgent,
    TeamToolAssignment,
    Tool,
)


RESERVED_FILENAMES = {"index.md", "log.md"}
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_BYTES = 200 * 1024 * 1024
MAX_CONCEPT_FILES = 2000
OKF_TOOL_TYPE = "okf_knowledge_graph"
SUPPORTED_KNOWLEDGE_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".tsv",
    ".json",
    ".html",
    ".htm",
    ".docx",
    ".pdf",
}
SUPPORTED_ARCHIVE_EXTENSIONS = {".zip", ".tar", ".tgz", ".gz"}

QUERY_STOPWORD_FRAGMENTS = (
    "สอบถาม",
    "ข้อมูล",
    "หน่อย",
    "ครับ",
    "ค่ะ",
    "คะ",
    "รองรับ",
    "อะไรบ้าง",
    "อะไร",
    "แบบใด",
    "ได้บ้าง",
    "บ้าง",
    "มี",
    "การ",
)
LOW_VALUE_QUERY_TERMS = {"softnix", "logger", "slg"}


def _query_terms(query: str) -> List[str]:
    raw_terms = [term.lower() for term in re.findall(r"[\w\u0E00-\u0E7F]+", query) if len(term) > 1]
    expanded: List[str] = []
    for term in raw_terms:
        expanded.append(term)
        stripped = term
        for fragment in QUERY_STOPWORD_FRAGMENTS:
            stripped = stripped.replace(fragment, "")
        stripped = stripped.strip("_- ")
        if len(stripped) > 1:
            expanded.append(stripped)

    unique: List[str] = []
    for term in expanded:
        if term and term not in unique:
            unique.append(term)
    return unique


def _excerpt_terms(terms: Iterable[str]) -> List[str]:
    useful = [term for term in terms if term not in LOW_VALUE_QUERY_TERMS and len(term) > 2]
    return useful or list(terms)

FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)(.*)\Z", re.S)
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")
HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)


class OKFValidationError(ValueError):
    """Raised when a bundle is not conformant enough to import."""


@dataclass
class ParsedConcept:
    concept_id: str
    file_path: str
    frontmatter: Dict[str, Any]
    body: str
    content_hash: str


@dataclass
class ExtractedKnowledge:
    title: str
    source_file: str
    document_type: str
    text: str
    content_hash: str
    warnings: List[str]


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: List[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() in {"script", "style", "noscript"}:
            self.skip_depth += 1
        if tag.lower() in {"p", "br", "div", "section", "article", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str):
        if tag.lower() in {"script", "style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
        if tag.lower() in {"p", "div", "section", "article", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str):
        if self.skip_depth:
            return
        cleaned = re.sub(r"\s+", " ", data).strip()
        if cleaned:
            self.parts.append(cleaned)

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "\n".join(self.parts)).strip()


def get_okf_storage_root() -> Path:
    configured = os.getenv("OKF_STORAGE_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "data" / "okf_bundles"


def sanitize_bundle_name(name: str) -> str:
    ascii_name = name.encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^A-Za-z0-9_-]+", "_", ascii_name).strip("_")
    return ascii_name.lower() or "okf_bundle"


def _safe_relative_path(path: str) -> Optional[Path]:
    pure = PurePosixPath(path.replace("\\", "/"))
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        return None
    return Path(*pure.parts)


def _ensure_within(root: Path, candidate: Path) -> None:
    root_resolved = root.resolve()
    candidate_resolved = candidate.resolve()
    if root_resolved != candidate_resolved and root_resolved not in candidate_resolved.parents:
        raise OKFValidationError("Archive contains an unsafe path")


def _safe_extract_archive(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    extracted_bytes = 0

    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                rel = _safe_relative_path(info.filename)
                if rel is None:
                    raise OKFValidationError("Archive contains an unsafe path")
                extracted_bytes += info.file_size
                if extracted_bytes > MAX_EXTRACTED_BYTES:
                    raise OKFValidationError("Archive is too large after extraction")
                target = destination / rel
                _ensure_within(destination, target)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as sink:
                    shutil.copyfileobj(source, sink)
        return

    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path) as archive:
            for member in archive.getmembers():
                if member.isdir():
                    continue
                if not member.isfile():
                    raise OKFValidationError("Archive contains unsupported entries")
                rel = _safe_relative_path(member.name)
                if rel is None:
                    raise OKFValidationError("Archive contains an unsafe path")
                extracted_bytes += member.size
                if extracted_bytes > MAX_EXTRACTED_BYTES:
                    raise OKFValidationError("Archive is too large after extraction")
                target = destination / rel
                _ensure_within(destination, target)
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    continue
                with source, target.open("wb") as sink:
                    shutil.copyfileobj(source, sink)
        return

    raise OKFValidationError("Unsupported OKF archive. Use .zip, .tar, .tar.gz, or .tgz")


def _find_bundle_root(extracted_dir: Path) -> Path:
    md_files = list(extracted_dir.rglob("*.md"))
    if not md_files:
        raise OKFValidationError("OKF bundle must contain markdown files")

    direct_md = list(extracted_dir.glob("*.md"))
    if direct_md:
        return extracted_dir

    children = [p for p in extracted_dir.iterdir() if p.is_dir()]
    if len(children) == 1 and list(children[0].rglob("*.md")):
        return children[0]
    return extracted_dir


def _parse_frontmatter(markdown: str, rel_path: str) -> tuple[Dict[str, Any], str]:
    match = FRONTMATTER_RE.match(markdown)
    if not match:
        raise OKFValidationError(f"{rel_path} is missing parseable YAML frontmatter")
    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise OKFValidationError(f"{rel_path} has invalid YAML frontmatter: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise OKFValidationError(f"{rel_path} frontmatter must be a YAML mapping")
    concept_type = str(frontmatter.get("type", "")).strip()
    if not concept_type:
        raise OKFValidationError(f"{rel_path} frontmatter must include a non-empty type")
    frontmatter["type"] = concept_type
    return frontmatter, match.group(2)


def _concept_id_from_relative_path(rel_path: Path) -> str:
    return rel_path.with_suffix("").as_posix()


def _title_from_concept_id(concept_id: str) -> str:
    leaf = concept_id.rsplit("/", 1)[-1]
    return " ".join(part.capitalize() for part in re.split(r"[_\-\s]+", leaf) if part)


def _title_from_filename(path: Path) -> str:
    stem = re.sub(r"[_\-\s]+", " ", path.stem).strip()
    return stem[:1].upper() + stem[1:] if stem else "Knowledge document"


def _safe_generated_filename(title: str, index: int) -> str:
    ascii_name = title.encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^A-Za-z0-9_-]+", "_", ascii_name).strip("_").lower()
    return f"{index:03d}_{ascii_name or 'knowledge'}.md"


def _is_archive_path(path: Path) -> bool:
    lowered = path.name.lower()
    return lowered.endswith((".zip", ".tar", ".tar.gz", ".tgz"))


def _decode_text_file(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp874", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _strip_existing_frontmatter(markdown: str) -> str:
    match = FRONTMATTER_RE.match(markdown)
    return match.group(2).strip() if match else markdown.strip()


def _extract_html_text(path: Path) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(_decode_text_file(path))
    return html.unescape(parser.text())


def _extract_docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as docx:
            xml = docx.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise OKFValidationError(f"{path.name} is not a readable Word document") from exc

    root = ET.fromstring(xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: List[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        line = "".join(texts).strip()
        if line:
            paragraphs.append(line)
    return "\n\n".join(paragraphs)


def _extract_pdf_text(path: Path) -> tuple[str, List[str]]:
    warnings: List[str] = []
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return "", [
            f"{path.name} is a PDF, but PDF text extraction is not installed in this runtime.",
        ]

    try:
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(page.strip() for page in pages if page.strip())
        if not text.strip():
            warnings.append(f"{path.name} appears to be scanned or image-only. OCR is required before import.")
        return text, warnings
    except Exception as exc:
        return "", [f"Could not read text from {path.name}: {exc}"]


def _extract_knowledge_file(path: Path, rel_path: Optional[Path] = None) -> ExtractedKnowledge:
    rel = (rel_path or Path(path.name)).as_posix()
    suffix = path.suffix.lower()
    warnings: List[str] = []
    title = _title_from_filename(path)

    if suffix in {".txt", ".csv", ".tsv"}:
        text = _decode_text_file(path).strip()
    elif suffix in {".md", ".markdown"}:
        text = _strip_existing_frontmatter(_decode_text_file(path))
    elif suffix == ".json":
        try:
            payload = json.loads(_decode_text_file(path))
            text = "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"
        except json.JSONDecodeError:
            text = _decode_text_file(path).strip()
            warnings.append(f"{path.name} is not valid JSON, so it was imported as plain text.")
    elif suffix in {".html", ".htm"}:
        text = _extract_html_text(path)
    elif suffix == ".docx":
        text = _extract_docx_text(path)
    elif suffix == ".pdf":
        text, warnings = _extract_pdf_text(path)
    else:
        raise OKFValidationError(f"{path.name} is not a supported knowledge file")

    if not text.strip():
        raise OKFValidationError(f"{path.name} does not contain readable text")

    return ExtractedKnowledge(
        title=title,
        source_file=rel,
        document_type=suffix.lstrip(".") or "text",
        text=text.strip(),
        content_hash=hashlib.sha256(text.strip().encode("utf-8")).hexdigest(),
        warnings=warnings,
    )


def _write_generated_okf_bundle(
    destination: Path,
    display_name: str,
    sources: List[ExtractedKnowledge],
    created_by_username: Optional[str],
    team_agent_id: Optional[int],
    visibility: str,
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.utcnow().isoformat() + "Z"
    index_frontmatter = {
        "okf_version": "generated-0.1",
        "type": "knowledge_bundle",
        "title": display_name,
        "generated_at": generated_at,
        "generated_by": created_by_username,
        "team_agent_id": team_agent_id,
        "visibility": visibility,
        "source_count": len(sources),
    }
    (destination / "index.md").write_text(
        "---\n"
        + yaml.safe_dump(index_frontmatter, allow_unicode=True, sort_keys=False)
        + "---\n\n"
        + f"# {display_name}\n\n"
        + "This OKF bundle was generated from user-friendly knowledge uploads.\n",
        encoding="utf-8",
    )

    used_names: set[str] = set()
    for index, source in enumerate(sources, start=1):
        filename = _safe_generated_filename(source.title, index)
        while filename in used_names:
            filename = _safe_generated_filename(f"{source.title}_{index}", index)
        used_names.add(filename)
        frontmatter = {
            "type": "knowledge",
            "title": source.title,
            "description": f"Imported from {source.source_file}",
            "resource": source.source_file,
            "source_file": source.source_file,
            "document_type": source.document_type,
            "tags": ["imported", source.document_type],
            "timestamp": generated_at,
        }
        body = f"# {source.title}\n\n{source.text}\n"
        (destination / filename).write_text(
            "---\n"
            + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
            + "---\n\n"
            + body,
            encoding="utf-8",
        )


def _collect_knowledge_sources(source_paths: List[Path]) -> tuple[List[ExtractedKnowledge], List[str]]:
    with tempfile.TemporaryDirectory(prefix="okf_expand_") as tmp_name:
        expanded_dir = Path(tmp_name)
        candidate_files: List[tuple[Path, Path]] = []
        warnings: List[str] = []

        for source_path in source_paths:
            if _is_archive_path(source_path):
                archive_target = expanded_dir / source_path.stem
                _safe_extract_archive(source_path, archive_target)
                for extracted in sorted(archive_target.rglob("*")):
                    if extracted.is_file() and extracted.suffix.lower() in SUPPORTED_KNOWLEDGE_EXTENSIONS:
                        candidate_files.append((extracted, extracted.relative_to(archive_target)))
            elif source_path.is_file() and source_path.suffix.lower() in SUPPORTED_KNOWLEDGE_EXTENSIONS:
                candidate_files.append((source_path, Path(source_path.name)))
            elif source_path.is_file():
                raise OKFValidationError(f"{source_path.name} is not a supported knowledge file")

        if len(candidate_files) > MAX_CONCEPT_FILES:
            raise OKFValidationError(f"Too many knowledge files ({len(candidate_files)}). Maximum is {MAX_CONCEPT_FILES}.")

        sources: List[ExtractedKnowledge] = []
        seen_hashes: Dict[str, str] = {}
        for file_path, rel_path in candidate_files:
            try:
                extracted = _extract_knowledge_file(file_path, rel_path)
                warnings.extend(extracted.warnings)
                duplicate_source = seen_hashes.get(extracted.content_hash)
                if duplicate_source:
                    warnings.append(
                        f"{extracted.source_file} has the same readable content as {duplicate_source} and was skipped."
                    )
                    continue
                seen_hashes[extracted.content_hash] = extracted.source_file
                sources.append(extracted)
            except OKFValidationError as exc:
                warnings.append(str(exc))

        if not sources:
            if warnings:
                raise OKFValidationError("No readable knowledge files found. " + " ".join(warnings[:3]))
            raise OKFValidationError("No readable knowledge files found")
        return sources, warnings


def _normalize_tags(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def parse_okf_directory(bundle_root: Path) -> tuple[List[ParsedConcept], Dict[str, Any]]:
    concepts: List[ParsedConcept] = []
    warnings: List[str] = []

    concept_files = [
        path
        for path in sorted(bundle_root.rglob("*.md"))
        if path.name not in RESERVED_FILENAMES
    ]
    if len(concept_files) > MAX_CONCEPT_FILES:
        raise OKFValidationError(f"OKF bundle has too many concept files ({len(concept_files)})")

    for path in concept_files:
        rel_path = path.relative_to(bundle_root)
        rel_posix = rel_path.as_posix()
        markdown = path.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(markdown, rel_posix)
        concepts.append(
            ParsedConcept(
                concept_id=_concept_id_from_relative_path(rel_path),
                file_path=rel_posix,
                frontmatter=frontmatter,
                body=body,
                content_hash=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            )
        )

    if not concepts:
        raise OKFValidationError("OKF bundle must contain at least one concept document")

    root_index = bundle_root / "index.md"
    okf_version = None
    if root_index.exists():
        try:
            text = root_index.read_text(encoding="utf-8")
            match = FRONTMATTER_RE.match(text)
            if match:
                metadata = yaml.safe_load(match.group(1)) or {}
                if isinstance(metadata, dict) and metadata.get("okf_version"):
                    okf_version = str(metadata["okf_version"])
        except Exception as exc:
            warnings.append(f"Could not inspect root index.md metadata: {exc}")

    return concepts, {"okf_version": okf_version, "warnings": warnings}


def _target_concept_id(raw_target: str, source_file_path: str) -> tuple[bool, Optional[str]]:
    target = raw_target.split("#", 1)[0].split("?", 1)[0].strip()
    if not target or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
        return True, None
    if target.startswith("/"):
        rel = target.lstrip("/")
    else:
        source_dir = PurePosixPath(source_file_path).parent
        rel = (source_dir / target).as_posix()
    rel = PurePosixPath(rel)
    normalized_parts: List[str] = []
    for part in rel.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if normalized_parts:
                normalized_parts.pop()
            continue
        normalized_parts.append(part)
    if not normalized_parts:
        return False, None
    normalized = PurePosixPath(*normalized_parts)
    if normalized.name == "index.md":
        return False, None
    return False, normalized.with_suffix("").as_posix() if normalized.suffix == ".md" else normalized.as_posix()


def _extract_links(concept: ParsedConcept, known_concept_ids: set[str]) -> List[Dict[str, Any]]:
    citation_start = concept.body.lower().find("# citations")
    links: List[Dict[str, Any]] = []
    for match in MARKDOWN_LINK_RE.finditer(concept.body):
        label = re.sub(r"\s+", " ", match.group(1)).strip()
        raw_target = match.group(2).strip()
        is_external, target_concept_id = _target_concept_id(raw_target, concept.file_path)
        is_citation = citation_start != -1 and match.start() >= citation_start
        links.append(
            {
                "source_concept_id": concept.concept_id,
                "target": raw_target,
                "target_concept_id": target_concept_id,
                "label": label[:500],
                "is_external": is_external,
                "is_citation": is_citation,
                "is_broken": bool(target_concept_id and target_concept_id not in known_concept_ids),
            }
        )
    return links


def _bundle_to_dict(bundle: OKFBundle, owner_team_name: Optional[str] = None, created_by_username: Optional[str] = None) -> Dict[str, Any]:
    return {
        "id": bundle.id,
        "name": bundle.name,
        "display_name": bundle.display_name,
        "okf_version": bundle.okf_version,
        "status": bundle.status,
        "concept_count": bundle.concept_count,
        "link_count": bundle.link_count,
        "validation_summary": bundle.validation_summary or {},
        "visibility": bundle.visibility,
        "owner_team_agent_id": bundle.owner_team_agent_id,
        "owner_team_name": owner_team_name,
        "created_by_username": created_by_username,
        "created_at": bundle.created_at.isoformat() if bundle.created_at else None,
        "updated_at": bundle.updated_at.isoformat() if bundle.updated_at else None,
    }


def _bundle_available_to_team(db, bundle: OKFBundle, team_agent_id: Optional[int]) -> bool:
    if team_agent_id is None:
        default_team = db.query(TeamAgent).filter_by(slug="default").first()
        team_agent_id = default_team.id if default_team else None
    if bundle.visibility == "global" or bundle.owner_team_agent_id == team_agent_id:
        return True
    if team_agent_id is None:
        return False
    okf_tools = db.query(Tool).filter(Tool.type == OKF_TOOL_TYPE).all()
    for tool in okf_tools:
        if not isinstance(tool.config, dict) or tool.config.get("okf_bundle_id") != bundle.id:
            continue
        if tool.visibility == "global" or tool.owner_team_agent_id == team_agent_id:
            return True
        shared = db.query(TeamToolAssignment).filter_by(
            team_agent_id=team_agent_id,
            tool_id=tool.id,
            relationship="shared_in",
        ).first()
        if shared:
            return True
    return False


class OKFService:
    """Coordinates OKF file storage, indexing, and local retrieval."""

    def __init__(self, storage_root: Optional[Path] = None):
        self.storage_root = storage_root or get_okf_storage_root()

    def import_archive(
        self,
        archive_path: Path,
        display_name: str,
        team_agent_id: Optional[int],
        visibility: str,
        created_by_username: Optional[str],
    ) -> Dict[str, Any]:
        if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
            raise OKFValidationError("Archive exceeds 50MB")

        with tempfile.TemporaryDirectory(prefix="okf_import_") as tmp_name:
            tmp_dir = Path(tmp_name)
            extracted_dir = tmp_dir / "extracted"
            _safe_extract_archive(archive_path, extracted_dir)
            bundle_root = _find_bundle_root(extracted_dir)
            concepts, metadata = parse_okf_directory(bundle_root)

            with get_db() as db:
                creator = db.query(Admin).filter_by(username=created_by_username).first() if created_by_username else None
                bundle = OKFBundle(
                    name=sanitize_bundle_name(display_name),
                    display_name=display_name,
                    storage_path="",
                    okf_version=metadata.get("okf_version"),
                    status="indexing",
                    validation_summary={"warnings": metadata.get("warnings", [])},
                    owner_team_agent_id=team_agent_id,
                    visibility=visibility,
                    created_by_admin_id=creator.id if creator else None,
                )
                db.add(bundle)
                db.flush()

                bundle_dir = self.storage_root / str(bundle.id)
                source_dir = bundle_dir / "source"
                if bundle_dir.exists():
                    shutil.rmtree(bundle_dir)
                source_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(bundle_root, source_dir)

                bundle.storage_path = str(source_dir)
                self._replace_index(db, bundle, concepts)
                bundle.status = "ready"
                bundle.updated_at = datetime.utcnow()

                owner_team_name = None
                created_by = None
                if bundle.owner_team_agent_id:
                    team = db.query(TeamAgent).filter_by(id=bundle.owner_team_agent_id).first()
                    owner_team_name = team.name if team else None
                if creator:
                    created_by = creator.username
                return _bundle_to_dict(bundle, owner_team_name, created_by)

    def import_knowledge_files(
        self,
        source_paths: List[Path],
        display_name: str,
        team_agent_id: Optional[int],
        visibility: str,
        created_by_username: Optional[str],
    ) -> Dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="okf_generate_") as tmp_name:
            tmp_dir = Path(tmp_name)
            generated_dir = tmp_dir / "generated_okf"
            sources, warnings = _collect_knowledge_sources(source_paths)
            duplicate_warnings = self._existing_duplicate_warnings(
                [source.content_hash for source in sources],
                team_agent_id=team_agent_id,
            )
            warnings.extend(duplicate_warnings)

            _write_generated_okf_bundle(
                destination=generated_dir,
                display_name=display_name,
                sources=sources,
                created_by_username=created_by_username,
                team_agent_id=team_agent_id,
                visibility=visibility,
            )
            concepts, metadata = parse_okf_directory(generated_dir)
            metadata_warnings = metadata.get("warnings", [])
            metadata_warnings.extend(warnings)

            with get_db() as db:
                creator = db.query(Admin).filter_by(username=created_by_username).first() if created_by_username else None
                bundle = OKFBundle(
                    name=sanitize_bundle_name(display_name),
                    display_name=display_name,
                    storage_path="",
                    okf_version=metadata.get("okf_version") or "generated-0.1",
                    status="indexing",
                    validation_summary={
                        "warnings": metadata_warnings,
                        "generated": True,
                        "source_count": len(sources),
                    },
                    owner_team_agent_id=team_agent_id,
                    visibility=visibility,
                    created_by_admin_id=creator.id if creator else None,
                )
                db.add(bundle)
                db.flush()

                bundle_dir = self.storage_root / str(bundle.id)
                source_dir = bundle_dir / "source"
                if bundle_dir.exists():
                    shutil.rmtree(bundle_dir)
                source_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(generated_dir, source_dir)

                bundle.storage_path = str(source_dir)
                self._replace_index(db, bundle, concepts)
                bundle.status = "ready"
                bundle.updated_at = datetime.utcnow()

                owner_team_name = None
                created_by = None
                if bundle.owner_team_agent_id:
                    team = db.query(TeamAgent).filter_by(id=bundle.owner_team_agent_id).first()
                    owner_team_name = team.name if team else None
                if creator:
                    created_by = creator.username
                return _bundle_to_dict(bundle, owner_team_name, created_by)

    def preview_knowledge_files(
        self,
        source_paths: List[Path],
        team_agent_id: Optional[int],
    ) -> Dict[str, Any]:
        sources, warnings = _collect_knowledge_sources(source_paths)
        warnings.extend(
            self._existing_duplicate_warnings(
                [source.content_hash for source in sources],
                team_agent_id=team_agent_id,
            )
        )
        documents = []
        for source in sources:
            excerpt = re.sub(r"\s+", " ", source.text).strip()[:260]
            documents.append(
                {
                    "title": source.title,
                    "source_file": source.source_file,
                    "document_type": source.document_type,
                    "character_count": len(source.text),
                    "excerpt": excerpt,
                    "content_hash": source.content_hash,
                }
            )
        return {
            "source_count": len(sources),
            "concept_count": len(sources),
            "warnings": warnings,
            "documents": documents,
        }

    def reindex_bundle(self, bundle_id: int, team_agent_id: Optional[int] = None) -> Dict[str, Any]:
        with get_db() as db:
            bundle = db.query(OKFBundle).filter_by(id=bundle_id).first()
            if not bundle or not _bundle_available_to_team(db, bundle, team_agent_id):
                raise KeyError("OKF bundle not found")
            try:
                bundle.status = "indexing"
                concepts, metadata = parse_okf_directory(Path(bundle.storage_path))
                bundle.okf_version = metadata.get("okf_version")
                bundle.validation_summary = {"warnings": metadata.get("warnings", []), "reindexed_at": datetime.utcnow().isoformat() + "Z"}
                self._replace_index(db, bundle, concepts)
                bundle.status = "ready"
                bundle.updated_at = datetime.utcnow()
                return _bundle_to_dict(bundle)
            except Exception as exc:
                bundle.status = "failed"
                bundle.validation_summary = {"warnings": [], "error": str(exc), "reindexed_at": datetime.utcnow().isoformat() + "Z"}
                bundle.updated_at = datetime.utcnow()
                raise

    def _replace_index(self, db, bundle: OKFBundle, concepts: List[ParsedConcept]) -> None:
        db.query(OKFLinkIndex).filter_by(bundle_id=bundle.id).delete()
        db.query(OKFConceptIndex).filter_by(bundle_id=bundle.id).delete()

        known_ids = {concept.concept_id for concept in concepts}
        link_rows: List[OKFLinkIndex] = []
        for concept in concepts:
            frontmatter = concept.frontmatter
            title = str(frontmatter.get("title") or _title_from_concept_id(concept.concept_id))
            description = str(frontmatter.get("description") or "")
            tags = _normalize_tags(frontmatter.get("tags"))
            timestamp = frontmatter.get("timestamp")
            if timestamp is not None:
                timestamp = str(timestamp)

            search_text = "\n".join(
                [
                    title,
                    description,
                    str(frontmatter.get("type") or ""),
                    " ".join(tags),
                    HEADING_RE.sub("", concept.body),
                ]
            )
            db.add(
                OKFConceptIndex(
                    bundle_id=bundle.id,
                    concept_id=concept.concept_id,
                    file_path=concept.file_path,
                    type=str(frontmatter["type"]),
                    title=title,
                    description=description,
                    resource=str(frontmatter.get("resource") or "") or None,
                    tags=tags,
                    timestamp=timestamp,
                    content_hash=concept.content_hash,
                    search_text=search_text,
                )
            )
            for link in _extract_links(concept, known_ids):
                link_rows.append(OKFLinkIndex(bundle_id=bundle.id, **link))

        for link in link_rows:
            db.add(link)
        bundle.concept_count = len(concepts)
        bundle.link_count = len(link_rows)

    def _existing_duplicate_warnings(self, content_hashes: List[str], team_agent_id: Optional[int]) -> List[str]:
        if not content_hashes:
            return []
        warnings: List[str] = []
        with get_db() as db:
            rows = (
                db.query(OKFConceptIndex, OKFBundle)
                .join(OKFBundle, OKFConceptIndex.bundle_id == OKFBundle.id)
                .filter(OKFConceptIndex.content_hash.in_(content_hashes))
                .all()
            )
            seen: set[tuple[int, str]] = set()
            for concept, bundle in rows:
                if not _bundle_available_to_team(db, bundle, team_agent_id):
                    continue
                key = (bundle.id, concept.content_hash)
                if key in seen:
                    continue
                seen.add(key)
                warnings.append(
                    f"Similar content already exists in \"{bundle.display_name}\" as \"{concept.title}\"."
                )
        return warnings

    def list_bundles(self, team_agent_id: Optional[int]) -> List[Dict[str, Any]]:
        with get_db() as db:
            bundles = db.query(OKFBundle).order_by(OKFBundle.created_at.desc()).all()
            result: List[Dict[str, Any]] = []
            for bundle in bundles:
                if not _bundle_available_to_team(db, bundle, team_agent_id):
                    continue
                owner_team_name = None
                created_by_username = None
                if bundle.owner_team_agent_id:
                    team = db.query(TeamAgent).filter_by(id=bundle.owner_team_agent_id).first()
                    owner_team_name = team.name if team else None
                if bundle.created_by_admin_id:
                    admin = db.query(Admin).filter_by(id=bundle.created_by_admin_id).first()
                    created_by_username = admin.username if admin else None
                result.append(_bundle_to_dict(bundle, owner_team_name, created_by_username))
            return result

    def get_bundle(self, bundle_id: int, team_agent_id: Optional[int]) -> Optional[Dict[str, Any]]:
        with get_db() as db:
            bundle = db.query(OKFBundle).filter_by(id=bundle_id).first()
            if not bundle or not _bundle_available_to_team(db, bundle, team_agent_id):
                return None
            owner_team_name = None
            created_by_username = None
            if bundle.owner_team_agent_id:
                team = db.query(TeamAgent).filter_by(id=bundle.owner_team_agent_id).first()
                owner_team_name = team.name if team else None
            if bundle.created_by_admin_id:
                admin = db.query(Admin).filter_by(id=bundle.created_by_admin_id).first()
                created_by_username = admin.username if admin else None
            return _bundle_to_dict(bundle, owner_team_name, created_by_username)

    def list_concepts(
        self,
        bundle_id: int,
        team_agent_id: Optional[int],
        query: Optional[str] = None,
        concept_type: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        with get_db() as db:
            bundle = db.query(OKFBundle).filter_by(id=bundle_id).first()
            if not bundle or not _bundle_available_to_team(db, bundle, team_agent_id):
                return []
            q = db.query(OKFConceptIndex).filter_by(bundle_id=bundle_id)
            if concept_type:
                q = q.filter(OKFConceptIndex.type == concept_type)
            if query:
                like = f"%{query.strip()}%"
                q = q.filter(
                    or_(
                        OKFConceptIndex.title.ilike(like),
                        OKFConceptIndex.description.ilike(like),
                        OKFConceptIndex.search_text.ilike(like),
                    )
                )
            concepts = q.order_by(OKFConceptIndex.title).limit(min(limit, 500)).all()
            rows = [self._concept_to_dict(concept) for concept in concepts]
            if tag:
                tag_lower = tag.lower()
                rows = [row for row in rows if tag_lower in [t.lower() for t in row.get("tags", [])]]
            return rows

    def get_concept(self, bundle_id: int, concept_id: str, team_agent_id: Optional[int]) -> Optional[Dict[str, Any]]:
        with get_db() as db:
            bundle = db.query(OKFBundle).filter_by(id=bundle_id).first()
            if not bundle or not _bundle_available_to_team(db, bundle, team_agent_id):
                return None
            concept = db.query(OKFConceptIndex).filter_by(bundle_id=bundle_id, concept_id=concept_id).first()
            if not concept:
                return None
            data = self._concept_to_dict(concept)
            markdown = self._read_concept_markdown(bundle, concept)
            data["markdown"] = markdown
            frontmatter, body = _parse_frontmatter(markdown, concept.file_path)
            data["frontmatter"] = frontmatter
            data["body"] = body
            data["links"] = self._links_for_concept(db, bundle_id, concept_id)
            return data

    def update_concept(
        self,
        bundle_id: int,
        concept_id: str,
        team_agent_id: Optional[int],
        title: Optional[str],
        description: Optional[str],
        tags: Optional[List[str]],
        body: str,
        expected_updated_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not body or not body.strip():
            raise OKFValidationError("Content cannot be empty")

        with get_db() as db:
            bundle = db.query(OKFBundle).filter_by(id=bundle_id).first()
            if not bundle or not _bundle_available_to_team(db, bundle, team_agent_id):
                raise KeyError("OKF bundle not found")

            concept = db.query(OKFConceptIndex).filter_by(bundle_id=bundle_id, concept_id=concept_id).first()
            if not concept:
                raise KeyError("OKF concept not found")

            current_updated_at = concept.updated_at.isoformat() if concept.updated_at else None
            if expected_updated_at and current_updated_at and expected_updated_at != current_updated_at:
                raise OKFValidationError("This document changed since it was opened. Reload it before saving.")

            source = Path(bundle.storage_path)
            path = source / concept.file_path
            _ensure_within(source, path)

            markdown = path.read_text(encoding="utf-8")
            frontmatter, _ = _parse_frontmatter(markdown, concept.file_path)
            original_markdown = markdown
            if title is not None:
                cleaned_title = title.strip()
                if not cleaned_title:
                    raise OKFValidationError("Title cannot be empty")
                frontmatter["title"] = cleaned_title
            if description is not None:
                frontmatter["description"] = description.strip()
            if tags is not None:
                frontmatter["tags"] = _normalize_tags(tags)

            next_markdown = (
                "---\n"
                + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
                + "---\n\n"
                + body.strip()
                + "\n"
            )
            _parse_frontmatter(next_markdown, concept.file_path)
            path.write_text(next_markdown, encoding="utf-8")

            try:
                bundle.status = "indexing"
                concepts, metadata = parse_okf_directory(source)
                bundle.okf_version = metadata.get("okf_version")
                bundle.validation_summary = {
                    "warnings": metadata.get("warnings", []),
                    "edited_at": datetime.utcnow().isoformat() + "Z",
                }
                self._replace_index(db, bundle, concepts)
                bundle.status = "ready"
                bundle.updated_at = datetime.utcnow()
                db.flush()
            except Exception as exc:
                path.write_text(original_markdown, encoding="utf-8")
                bundle.status = "failed"
                bundle.validation_summary = {
                    "warnings": [],
                    "error": str(exc),
                    "edited_at": datetime.utcnow().isoformat() + "Z",
                }
                bundle.updated_at = datetime.utcnow()
                raise

            updated = db.query(OKFConceptIndex).filter_by(bundle_id=bundle_id, concept_id=concept_id).first()
            if not updated:
                raise OKFValidationError("Updated document could not be found after re-indexing")
            data = self._concept_to_dict(updated)
            updated_markdown = self._read_concept_markdown(bundle, updated)
            updated_frontmatter, updated_body = _parse_frontmatter(updated_markdown, updated.file_path)
            data["markdown"] = updated_markdown
            data["frontmatter"] = updated_frontmatter
            data["body"] = updated_body
            data["links"] = self._links_for_concept(db, bundle_id, concept_id)
            return data

    def delete_bundle(self, bundle_id: int, team_agent_id: Optional[int]) -> bool:
        with get_db() as db:
            bundle = db.query(OKFBundle).filter_by(id=bundle_id).first()
            if not bundle:
                return False
            if team_agent_id is None:
                default_team = db.query(TeamAgent).filter_by(slug="default").first()
                team_agent_id = default_team.id if default_team else None
            if bundle.owner_team_agent_id is not None and bundle.owner_team_agent_id != team_agent_id:
                return False

            tools = db.query(Tool).filter(Tool.type == OKF_TOOL_TYPE).all()
            for tool in tools:
                if isinstance(tool.config, dict) and tool.config.get("okf_bundle_id") == bundle_id:
                    db.query(TeamToolAssignment).filter_by(tool_id=tool.id).delete()
                    db.query(AgentTool).filter_by(tool_id=tool.id).delete()
                    db.delete(tool)
            storage_path = Path(bundle.storage_path) if bundle.storage_path else self.storage_root / str(bundle.id) / "source"
            bundle_dir = storage_path.parent if storage_path.name == "source" else storage_path
            _ensure_within(self.storage_root, bundle_dir)
            db.delete(bundle)
        if bundle_dir.exists():
            shutil.rmtree(bundle_dir)
        return True

    def query_bundle(
        self,
        bundle_id: int,
        query: str,
        team_agent_id: Optional[int] = None,
        limit: int = 5,
        expand_links: bool = True,
    ) -> Dict[str, Any]:
        terms = _query_terms(query)
        excerpt_terms = _excerpt_terms(terms)
        with get_db() as db:
            bundle = db.query(OKFBundle).filter_by(id=bundle_id).first()
            if not bundle or not _bundle_available_to_team(db, bundle, team_agent_id):
                return {"response": "OKF bundle not found or not available.", "concepts": []}
            concepts = db.query(OKFConceptIndex).filter_by(bundle_id=bundle_id).all()
            scored = []
            for concept in concepts:
                title_text = (concept.title or "").lower()
                description_text = (concept.description or "").lower()
                tag_text = " ".join(concept.tags or []).lower()
                type_text = (concept.type or "").lower()
                search_text = (concept.search_text or "").lower()
                text = " ".join([title_text, description_text, type_text, tag_text, search_text])
                score = 1 if not terms else 0
                reasons = []
                for term in terms:
                    if term in title_text:
                        score += 4
                        reasons.append("title")
                    if term in description_text:
                        score += 3
                        reasons.append("description")
                    if term in tag_text:
                        score += 2
                        reasons.append("tag")
                    if term in search_text:
                        score += max(1, search_text.count(term))
                        reasons.append("body")
                if query.lower() in text:
                    score += 5
                    reasons.append("exact phrase")
                if score > 0 or not terms:
                    scored.append((score, concept, reasons))
            scored.sort(key=lambda item: item[0], reverse=True)
            selected = scored[: max(1, min(limit, 10))]

            result_concepts = []
            for score, concept, reasons in selected:
                item = self._concept_to_dict(concept)
                markdown = self._read_concept_markdown(bundle, concept)
                try:
                    _, body = _parse_frontmatter(markdown, concept.file_path)
                except OKFValidationError:
                    body = markdown
                item["excerpt"] = self._excerpt(body, excerpt_terms)
                item["score"] = score
                item["match_reason"] = self._format_match_reason(reasons)
                if expand_links:
                    item["links"] = self._links_for_concept(db, bundle_id, concept.concept_id, limit=8)
                result_concepts.append(item)

            return {
                "response": self._retrieval_answer(result_concepts),
                "concepts": result_concepts,
            }

    def _concept_to_dict(self, concept: OKFConceptIndex) -> Dict[str, Any]:
        return {
            "id": concept.id,
            "bundle_id": concept.bundle_id,
            "concept_id": concept.concept_id,
            "file_path": concept.file_path,
            "type": concept.type,
            "title": concept.title,
            "description": concept.description,
            "resource": concept.resource,
            "tags": concept.tags or [],
            "timestamp": concept.timestamp,
            "updated_at": concept.updated_at.isoformat() if concept.updated_at else None,
        }

    def _read_concept_markdown(self, bundle: OKFBundle, concept: OKFConceptIndex) -> str:
        source = Path(bundle.storage_path)
        path = source / concept.file_path
        _ensure_within(source, path)
        return path.read_text(encoding="utf-8")

    def _links_for_concept(self, db, bundle_id: int, concept_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        links = db.query(OKFLinkIndex).filter_by(
            bundle_id=bundle_id,
            source_concept_id=concept_id,
        ).limit(limit).all()
        return [
            {
                "source_concept_id": link.source_concept_id,
                "target": link.target,
                "target_concept_id": link.target_concept_id,
                "label": link.label,
                "is_external": link.is_external,
                "is_citation": link.is_citation,
                "is_broken": link.is_broken,
            }
            for link in links
        ]

    def _excerpt(self, body: str, terms: Iterable[str], size: int = 1800) -> str:
        plain = re.sub(r"\s+", " ", body).strip()
        if not plain:
            return ""

        ordered_terms = sorted(set(terms), key=len, reverse=True)
        paragraphs = [
            re.sub(r"\s+", " ", paragraph).strip()
            for paragraph in re.split(r"\n\s*\n+", body)
            if paragraph.strip()
        ]
        matched_paragraphs = []
        for paragraph in paragraphs:
            lower_paragraph = paragraph.lower()
            if any(term in lower_paragraph for term in ordered_terms):
                matched_paragraphs.append(paragraph)

        if matched_paragraphs:
            excerpt = " ".join(matched_paragraphs)
            if len(excerpt) > size:
                excerpt = excerpt[: size - 3].rstrip() + "..."
            return excerpt

        lower = plain.lower()
        position = -1
        for term in ordered_terms:
            position = lower.find(term)
            if position >= 0:
                break
        start = max(0, position - 180) if position >= 0 else 0
        excerpt = plain[start : start + size]
        if start > 0:
            excerpt = "..." + excerpt
        if start + size < len(plain):
            excerpt += "..."
        return excerpt

    def _format_match_reason(self, reasons: Iterable[str]) -> str:
        ordered = []
        for reason in reasons:
            if reason not in ordered:
                ordered.append(reason)
        if not ordered:
            return "fallback match"
        return "matched " + ", ".join(ordered[:4])

    def _retrieval_answer(self, concepts: List[Dict[str, Any]]) -> str:
        if not concepts:
            return "No matching OKF concepts found."

        lines = [
            "Use only the source excerpts below to answer. "
            "If the excerpts do not contain the requested detail, say that the local knowledge does not specify it."
        ]
        lines.append(f"Found {len(concepts)} relevant source document{'s' if len(concepts) != 1 else ''}:")
        for index, concept in enumerate(concepts, start=1):
            excerpt = re.sub(r"\s+", " ", str(concept.get("excerpt") or "")).strip()
            if len(excerpt) > 1600:
                excerpt = excerpt[:1597].rstrip() + "..."
            description = re.sub(r"\s+", " ", str(concept.get("description") or "")).strip()
            lines.append(f"{index}. {concept.get('title') or concept.get('concept_id')}")
            if description:
                lines.append(f"Source: {description}")
            lines.append(f"Excerpt: {excerpt or 'No excerpt available.'}")

        return "\n".join(lines)
