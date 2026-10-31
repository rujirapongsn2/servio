"""Tak's bounded A2UI v0.9.1 catalog and server-owned image search surfaces."""
from __future__ import annotations

import base64
import io
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.knowledge_image_search import ImageSearchRequest, SurfaceRefinement

CATALOG_ID = "https://servio.ai/a2ui/catalogs/product-discovery/v1"
VERSION = "v0.9.1"


class RefineAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: Literal["discovery.refine"]
    surfaceId: str = Field(pattern=r"^msg_[a-f0-9]{32}$")
    sourceComponentId: Literal["root"]
    timestamp: str = Field(max_length=40)
    context: SurfaceRefinement


class InquiryContext(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    card_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class InquireAction(RefineAction):
    name: Literal["discovery.inquire"]
    context: InquiryContext


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["a2ui.action"]
    version: Literal["v0.9.1"]
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    action: Annotated[RefineAction | InquireAction, Field(discriminator="name")]

    @field_validator("action")
    @classmethod
    def timestamp_is_valid(cls, action):
        parsed = datetime.fromisoformat(action.timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Timestamp must include a timezone")
        return action


def enabled_for_team(team_id: int | None) -> bool:
    from app.db_config import get_db
    from app.orm_models import TeamAgent
    with get_db() as db:
        team = db.get(TeamAgent, team_id) if team_id else None
        return bool(team and team.status == "active" and team.name.strip().casefold() == "tak")


@dataclass
class QueryContext:
    created: float
    surface_id: str
    request: ImageSearchRequest


class DiscoverySession:
    def __init__(self):
        self.enabled = False
        self.query: QueryContext | None = None
        self.snapshots: dict[str, list[dict]] = {}

    def reset(self):
        self.query = None
        self.snapshots.clear()

    def require(self, surface_id: str) -> ImageSearchRequest:
        if (not self.enabled or self.query is None or self.query.surface_id != surface_id
                or time.monotonic() - self.query.created >= 900):
            raise ValueError("Search expired")
        return self.query.request

    def publish(self, surface_id: str, request: ImageSearchRequest, presentation, *, refining=False, facets=None):
        if not self.enabled:
            return
        if not refining:
            for messages in self.snapshots.values():
                messages[-1]["updateDataModel"]["value"]["active"] = False
            self.query = QueryContext(time.monotonic(), surface_id, request)
        else:
            self.require(surface_id)
        # Only a small preview reaches the renderer; original bytes remain session-local.
        with Image.open(io.BytesIO(request.image_bytes())) as image:
            image = image.convert("RGB")
            image.thumbnail((160, 160))
            preview = io.BytesIO()
            image.save(preview, "JPEG", quality=75)
        data = {
            "active": True,
            "summary": presentation.summary if presentation else "ไม่พบสินค้าตามเงื่อนไขนี้ ลองปรับสีหรือลาย",
            "products": [product.model_dump() for product in presentation.products] if presentation else [],
            "facets": facets or {},
            "filters": (request.refinement or SurfaceRefinement()).model_dump(),
            "queryImage": "data:image/jpeg;base64," + base64.b64encode(preview.getvalue()).decode(),
        }
        self.snapshots[surface_id] = [
            {"version": VERSION, "createSurface": {"surfaceId": surface_id, "catalogId": CATALOG_ID}},
            {"version": VERSION, "updateComponents": {"surfaceId": surface_id, "components": [
                {"id": "root", "component": "ProductDiscovery", "data": {"path": "/discovery"},
                 "refineAction": {"event": {"name": "discovery.refine"}},
                 "inquireAction": {"event": {"name": "discovery.inquire"}}}]}},
            {"version": VERSION, "updateDataModel": {"surfaceId": surface_id, "path": "/discovery", "value": data}},
        ]
        while len(self.snapshots) > 20:
            del self.snapshots[next(iter(self.snapshots))]


def catalog_facets(refs: dict, team_id: int) -> dict:
    from app.db_config import get_db
    from app.orm_models import OKFBundle, OKFConceptIndex
    from app.okf_service import OKFService
    from app.knowledge_products import ProductMetadata
    from app.knowledge_image_search import assigned_bundles
    from pydantic import ValidationError
    patterns = {"wood_grain": "ลายไม้", "stone_veined": "ลายหินเส้น", "solid": "สีพื้น",
                "stone_speckled": "ลายหินเม็ด", "geometric": "ลายเรขาคณิต", "mixed": "ลายผสม"}
    result = {}
    allowed = assigned_bundles(team_id)
    service = OKFService()
    with get_db() as db:
        for card_id, ref in refs.items():
            if ref.bundle not in allowed:
                continue
            bundle = db.get(OKFBundle, ref.bundle)
            concept = db.query(OKFConceptIndex).filter_by(bundle_id=ref.bundle,
                concept_id=ref.concept, content_hash=ref.source).first()
            if not bundle or not concept:
                continue
            fm = service._concept_image_frontmatter(bundle, concept)
            if not fm or fm.get("image_asset_id") != ref.asset:
                continue
            try:
                metadata = ProductMetadata.model_validate(fm.get("image_products"))
            except ValidationError:
                continue
            if len(metadata.products) != 1 or metadata.asset_id != ref.asset:
                continue
            product = metadata.products[0]
            if product.review_status != "confirmed":
                continue
            result[card_id] = {
                "color": ", ".join(dict.fromkeys(color.label for color in product.colors))[:300] or "ไม่ระบุ",
                "pattern": (product.pattern_description or patterns.get(product.surface_pattern) or "ไม่ระบุ")[:300],
                "category": (product.category_th or product.category or "ไม่ระบุ")[:100],
            }
    return result
