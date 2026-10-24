from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import logging
import os
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import bindparam, text

from app import product_image_rerank as reranker
from app import local_image_rag as images
from app.db_config import get_db
from app.orm_models import AgentTool, OKFBundle, OKFConceptIndex, TeamAgent, TeamAgentMember, TeamToolAssignment, Tool


class InvalidSearchImage(ValueError):
    pass


class SearchImage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mime: Literal["image/jpeg", "image/png"]
    base64: str = Field(min_length=4, max_length=4 * ((images.MAX_BYTES + 2) // 3))


class ImageSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["knowledge.image.search"]
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    image: SearchImage
    query: str = Field(default="", max_length=2000)

    @field_validator("query")
    @classmethod
    def trim_query(cls, value: str) -> str:
        return value.strip()

    def image_bytes(self) -> bytes:
        try:
            data = base64.b64decode(self.image.base64, validate=True)
        except (ValueError, binascii.Error):
            raise InvalidSearchImage("Use a valid JPG or PNG image") from None
        try:
            _, mime = images.validated_image(data)
        except ValueError as exc:
            raise InvalidSearchImage(str(exc)) from None
        if mime != self.image.mime:
            raise InvalidSearchImage("Image type does not match its contents")
        return data


class KnowledgeCard(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str
    asset_id: str
    title: str
    source_label: str
    description: str
    image_url: str


class KnowledgeCarousel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["knowledge_product_carousel"] = "knowledge_product_carousel"
    version: Literal[1] = 1
    summary: str
    products: list[KnowledgeCard] = Field(min_length=1, max_length=5)


class KnowledgeInquiryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["knowledge.product.inquire"]
    message_id: str = Field(pattern=r"^msg_[a-f0-9]{32}$")
    card_id: str = Field(pattern=r"^[a-f0-9]{32}$")


@dataclass(frozen=True)
class KnowledgeCardRef:
    bundle: int
    concept: str
    source: str
    asset: str


@dataclass(frozen=True)
class SearchMatch:
    reference: KnowledgeCardRef
    title: str
    source_label: str
    description: str
    score: float


@dataclass(frozen=True)
class SearchResult:
    status: Literal["matched", "no_match", "unavailable"]
    matches: tuple[SearchMatch, ...] = ()


def assigned_bundles(team_id: int | None) -> set[int]:
    if team_id is None or not images.enabled():
        return set()
    from app.okf_service import _bundle_available_to_team
    with get_db() as db:
        team = db.query(TeamAgent).filter_by(id=team_id, status="active").first()
        if team is None:
            return set()
        tools = db.query(Tool).join(AgentTool, AgentTool.tool_id == Tool.id).join(
            TeamAgentMember, TeamAgentMember.agent_id == AgentTool.agent_id
        ).filter(TeamAgentMember.team_agent_id == team_id, Tool.type == "okf_knowledge_graph").all()
        shared_ids = {row.tool_id for row in db.query(TeamToolAssignment).filter_by(
            team_agent_id=team_id, relationship="shared_in").all()}
        result = set()
        for tool in tools:
            if tool.owner_team_agent_id != team_id and tool.visibility != "global" and tool.id not in shared_ids:
                continue
            config = tool.config
            bundle_id = config.get("okf_bundle_id") if isinstance(config, dict) else None
            if not isinstance(bundle_id, int) or isinstance(bundle_id, bool):
                continue
            bundle = db.query(OKFBundle).filter_by(id=bundle_id, status="ready").first()
            if bundle and _bundle_available_to_team(db, bundle, team_id):
                result.add(bundle_id)
        return result


def _nearest(bundle_ids: set[int], space: str, vector: list[float], text_vector: list[float] | None = None):
    text_score = ",1-(v.embedding <=> CAST(:text_vector AS vector)) AS text_score" if text_vector is not None else ""
    statement = text(f"""SELECT v.bundle_id,v.concept_id,v.asset_id,v.source_hash,
        k.title,k.resource,k.description,1-(v.embedding <=> CAST(:vector AS vector)) AS score{text_score}
        FROM okf_image_vectors v JOIN okf_concept_index k ON k.bundle_id=v.bundle_id
          AND k.concept_id=v.concept_id AND k.content_hash=v.source_hash
        WHERE v.bundle_id IN :bundles AND v.space=:space
        ORDER BY v.embedding <=> CAST(:vector AS vector),v.bundle_id,v.concept_id LIMIT 100""").bindparams(bindparam("bundles", expanding=True))
    parameters = {"bundles": sorted(bundle_ids), "space": space, "vector": images._literal(vector)}
    if text_vector is not None:
        parameters["text_vector"] = images._literal(text_vector)
    with images.engine.connect() as conn:
        return conn.execute(statement, parameters).mappings().all()


def search_image(team_id: int | None, request: ImageSearchRequest) -> SearchResult:
    data = request.image_bytes()
    bundles = assigned_bundles(team_id)
    if not bundles:
        return SearchResult("unavailable")
    images.ensure_schema()
    client = images.LocalImageEmbeddingClient()
    vector = client.image(data)
    use_reranker = reranker.enabled()
    text_vector = client.query(request.query) if request.query and not use_reranker else None
    bundles &= assigned_bundles(team_id)
    if not bundles:
        return SearchResult("unavailable")
    rows = _nearest(bundles, client.space, vector, text_vector) if text_vector is not None else _nearest(bundles, client.space, vector)
    if use_reranker:
        return _reranked_search(team_id, data, rows, request.query) if request.query else _reranked_search(team_id, data, rows)
    threshold = float(os.getenv("MULTIMODAL_IMAGE_QUERY_MIN_SCORE", "0.82"))
    score_gap = float(os.getenv("MULTIMODAL_IMAGE_QUERY_MAX_SCORE_GAP", "0.06"))
    if not math.isfinite(threshold) or not -1 <= threshold <= 1:
        raise ValueError("Invalid image similarity threshold")
    if not math.isfinite(score_gap) or not 0 <= score_gap <= 2:
        raise ValueError("Invalid image similarity score gap")
    limit = min(5, max(1, int(os.getenv("MULTIMODAL_IMAGE_QUERY_MAX_RESULTS", "5"))))
    matches = []
    text_scores = {}
    seen = set()
    current = assigned_bundles(team_id)
    for row in rows:
        score = float(row["score"])
        if (row["bundle_id"] not in current or not math.isfinite(score)
                or not -1 <= score <= 1 or score < threshold or row["asset_id"] in seen):
            continue
        ref = KnowledgeCardRef(row["bundle_id"], row["concept_id"], row["source_hash"], row["asset_id"])
        try:
            images._resolve_asset({"bundle": ref.bundle, "concept": ref.concept, "source": ref.source, "asset": ref.asset, "team": team_id})
        except (ValueError, OSError, KeyError):
            continue
        matches.append(SearchMatch(ref, row["title"][:1000], (row["resource"] or row["title"])[:2000], (row["description"] or "")[:8000], score))
        seen.add(ref.asset)
        if text_vector is not None:
            text_scores[ref.asset] = float(row["text_score"])
    matches.sort(key=lambda match: match.score, reverse=True)
    if matches:
        cutoff = max(threshold, matches[0].score - score_gap)
        matches = [match for match in matches if match.score >= cutoff]
        if text_vector is not None:
            matches.sort(key=lambda match: (text_scores[match.reference.asset], match.score), reverse=True)
        matches = matches[:limit]
    return SearchResult("matched" if matches else "no_match", tuple(matches))


def _reranked_search(team_id: int | None, data: bytes, rows, query: str = "") -> SearchResult:
    settings = reranker.RerankSettings.from_environment()
    limit = min(5, max(1, int(os.getenv("MULTIMODAL_IMAGE_QUERY_MAX_RESULTS", "5"))))
    current = assigned_bundles(team_id)
    candidates = []
    matches = {}
    seen = set()
    exact = []
    query_hash = hashlib.sha256(data).hexdigest()
    for row in rows:
        score = float(row["score"])
        if (row["bundle_id"] not in current or row["asset_id"] in seen
                or not math.isfinite(score) or not -1 <= score <= 1 or score < settings.candidate_min_score):
            continue
        ref = KnowledgeCardRef(row["bundle_id"], row["concept_id"], row["source_hash"], row["asset_id"])
        try:
            original, _ = images._resolve_asset({"bundle": ref.bundle, "concept": ref.concept,
                "source": ref.source, "asset": ref.asset, "team": team_id})
        except (ValueError, OSError, KeyError):
            continue
        actual_hash = hashlib.sha256(original).hexdigest()
        if actual_hash != ref.asset:
            continue
        seen.add(ref.asset)
        match = SearchMatch(ref, row["title"][:1000], (row["resource"] or row["title"])[:2000],
                            (row["description"] or "")[:8000], score)
        if actual_hash == query_hash:
            exact.append(match)
        if len(candidates) < settings.candidates:
            candidate_id = f"c{len(candidates) + 1:02d}"
            candidates.append(reranker.VisualCandidate(candidate_id, original, score, actual_hash,
                                                       ref.source, match.title))
            matches[candidate_id] = match
    if exact and not query:
        selected = exact[:limit]
    elif candidates:
        try:
            ranked = reranker.rerank(data, tuple(candidates), settings, query=query) if query else reranker.rerank(data, tuple(candidates), settings)
        except reranker.RerankUnavailable:
            logging.getLogger(__name__).warning("Product image comparison unavailable")
            return SearchResult("unavailable")
        selected = [matches[candidate_id] for candidate_id in ranked]
    else:
        selected = []
    current = assigned_bundles(team_id)
    if not current:
        return SearchResult("unavailable")
    valid = []
    for match in selected:
        ref = match.reference
        if ref.bundle not in current:
            continue
        try:
            original, _ = images._resolve_asset({"bundle": ref.bundle, "concept": ref.concept,
                "source": ref.source, "asset": ref.asset, "team": team_id})
        except (ValueError, OSError, KeyError):
            continue
        if hashlib.sha256(original).hexdigest() == ref.asset:
            valid.append(match)
    return SearchResult("matched" if valid else "no_match", tuple(valid[:limit]))


def resolve_inquiry(team_id: int | None, ref: KnowledgeCardRef) -> tuple[str, str]:
    if ref.bundle not in assigned_bundles(team_id):
        raise ValueError("Product is no longer available; search again")
    images._resolve_asset({"bundle": ref.bundle, "concept": ref.concept, "source": ref.source, "asset": ref.asset, "team": team_id})
    from app.okf_service import _ensure_within, _parse_frontmatter
    with get_db() as db:
        bundle = db.query(OKFBundle).filter_by(id=ref.bundle).first()
        concept = db.query(OKFConceptIndex).filter_by(bundle_id=ref.bundle, concept_id=ref.concept, content_hash=ref.source).first()
        if not bundle or not concept:
            raise ValueError("Product is no longer available; search again")
        root = Path(bundle.storage_path)
        path = root / concept.file_path
        _ensure_within(root, path)
        markdown = path.read_text(encoding="utf-8")
        if hashlib.sha256(markdown.encode()).hexdigest() != ref.source:
            raise ValueError("Product source changed; search again")
        _, body = _parse_frontmatter(markdown, concept.file_path)
        source = json.dumps({"title": concept.title, "source": concept.resource, "description": concept.description, "content": body[:16000]}, ensure_ascii=False)
        title = concept.title
    if ref.bundle not in assigned_bundles(team_id):
        raise ValueError("Product is no longer available; search again")
    return f"สอบถามสินค้านี้ {title}", source


class ImageSearchSession:
    def __init__(self):
        self.generation = 0
        self.refs: OrderedDict[str, tuple[float, dict[str, KnowledgeCardRef]]] = OrderedDict()
        self.requests: OrderedDict[str, float] = OrderedDict()

    def reset(self):
        self.generation += 1
        self.refs.clear()
        self.requests.clear()

    def begin(self, request_id: str):
        now = time.monotonic()
        self.requests = OrderedDict((key, created) for key, created in self.requests.items() if now - created < 900)
        if request_id in self.requests:
            raise ValueError("This image request was already received")
        self.requests[request_id] = now
        while len(self.requests) > 100:
            self.requests.popitem(last=False)
        return self.generation

    def presentation(self, result: SearchResult, team_id: int):
        now = time.monotonic()
        self.refs = OrderedDict((key, value) for key, value in self.refs.items() if now - value[0] < 900)
        message_id = "msg_" + uuid.uuid4().hex
        refs = {}
        products = []
        for match in result.matches:
            card_id = uuid.uuid4().hex
            ref = match.reference
            refs[card_id] = ref
            token = images._grant(ref.bundle, ref.concept, ref.asset, ref.source, team_id)
            products.append(KnowledgeCard(id=card_id, asset_id=ref.asset, title=match.title, source_label=match.source_label,
                description=match.description, image_url=f"/api/knowledge-images/{ref.asset}?token={token}"))
        self.refs[message_id] = (now, refs)
        while len(self.refs) > 20:
            self.refs.popitem(last=False)
        return message_id, KnowledgeCarousel(summary=f"พบสินค้าที่ใกล้เคียง {len(products)} รายการ", products=products)

    def reference(self, request: KnowledgeInquiryRequest) -> KnowledgeCardRef:
        entry = self.refs.get(request.message_id)
        if entry is None or time.monotonic() - entry[0] >= 900 or request.card_id not in entry[1]:
            raise ValueError("Product selection expired; search again")
        return entry[1][request.card_id]
