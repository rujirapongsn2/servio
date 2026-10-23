"""Validated image references from the authorized local knowledge tool."""
import json
import re
import jwt
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from typing import Literal


class KnowledgeImage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    asset_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str = Field(min_length=1, max_length=1000)
    source_label: str = Field(min_length=1, max_length=2000)
    image_url: str = Field(max_length=4096)

    @field_validator("image_url")
    @classmethod
    def validate_url(cls, value, info):
        asset = info.data.get("asset_id")
        if not re.fullmatch(r"/api/knowledge-images/" + re.escape(asset or "") + r"\?token=[A-Za-z0-9_.-]+", value):
            raise ValueError("Signed local image URL required")
        return value


class KnowledgeImages(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["knowledge_images"]
    version: Literal[1]
    response: str = Field(max_length=64000)
    images: list[KnowledgeImage] = Field(min_length=1, max_length=5)


def parse_knowledge_images(value):
    try:
        if isinstance(value, str):
            if len(value) > 96000:
                return None
            value = json.loads(value)
        if not isinstance(value, dict) or value.get("type") != "knowledge_images" or type(value.get("version")) is not int:
            return None
        presentation = KnowledgeImages.model_validate(value)
        from app.auth import SECRET_KEY, ALGORITHM
        for image in presentation.images:
            claims = jwt.decode(image.image_url.split("?token=", 1)[1], SECRET_KEY, algorithms=[ALGORITHM], options={"require": ["exp", "purpose", "asset"]})
            if claims["purpose"] != "knowledge-image" or claims["asset"] != image.asset_id:
                return None
        return presentation
    except (ValueError, TypeError, ValidationError, jwt.PyJWTError):
        return None


class KnowledgeImageReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    asset_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str = Field(min_length=1, max_length=1000)
    source_label: str = Field(min_length=1, max_length=2000)
    bundle_id: int = Field(gt=0)
    concept_id: str = Field(min_length=1, max_length=1000)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class KnowledgeImageReferences(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["knowledge_image_refs"]
    version: Literal[1]
    response: str = Field(max_length=64000)
    images: list[KnowledgeImageReference] = Field(min_length=1, max_length=5)


def hydrate_knowledge_images(value, team_agent_id, bundle_id):
    if team_agent_id is None:
        return None
    try:
        if isinstance(value, str):
            if len(value) > 96000:
                return None
            value = json.loads(value)
        if not isinstance(value, dict) or value.get("type") != "knowledge_image_refs" or type(value.get("version")) is not int:
            return None
        references = KnowledgeImageReferences.model_validate(value)
        if any(reference.bundle_id != bundle_id for reference in references.images):
            return None
        from app.local_image_rag import enabled, _resolve_asset, _grant
        if not enabled():
            return None
        images = []
        for reference in references.images:
            claims = {"bundle": reference.bundle_id, "concept": reference.concept_id, "source": reference.source_hash,
                      "asset": reference.asset_id, "team": team_agent_id}
            _resolve_asset(claims)
            from app.local_image_rag import get_db
            from app.orm_models import OKFConceptIndex
            with get_db() as db:
                concept = db.query(OKFConceptIndex).filter_by(bundle_id=reference.bundle_id, concept_id=reference.concept_id).first()
                if not concept:
                    return None
                title, label = concept.title, concept.resource or concept.title
            token = _grant(reference.bundle_id, reference.concept_id, reference.asset_id, reference.source_hash, team_agent_id)
            images.append(KnowledgeImage(asset_id=reference.asset_id, title=title, source_label=label,
                image_url=f"/api/knowledge-images/{reference.asset_id}?token={token}"))
        return KnowledgeImages(type="knowledge_images", version=1, response=references.response, images=images)
    except (ValueError, TypeError, OSError, KeyError, ValidationError):
        return None
