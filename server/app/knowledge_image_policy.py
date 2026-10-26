from __future__ import annotations

import math
import os
from typing import Literal

from app import product_image_rerank
from app.orm_models import OKFImageSearchPolicy

SearchMode = Literal["similarity", "rerank"]
_COLUMNS = {"similarity": "similarity_min_score", "rerank": "rerank_candidate_min_score"}
_DEFAULTS = {
    "similarity": ("MULTIMODAL_IMAGE_QUERY_MIN_SCORE", "0.82"),
    "rerank": ("MULTIMODAL_IMAGE_RERANK_CANDIDATE_MIN_SCORE", "0.2"),
}


def active_mode() -> SearchMode:
    return "rerank" if product_image_rerank.enabled() else "similarity"


def default_min_score(mode: SearchMode) -> float:
    name, fallback = _DEFAULTS[mode]
    value = float(os.getenv(name, fallback))
    if not math.isfinite(value) or not -1 <= value <= 1:
        raise ValueError(f"Invalid {name}")
    return value


def describe(db, bundle_id: int, can_edit: bool, mode: SearchMode | None = None) -> dict:
    mode = mode or active_mode()
    default = default_min_score(mode)
    policy = db.get(OKFImageSearchPolicy, bundle_id)
    override = getattr(policy, _COLUMNS[mode]) if policy else None
    return {"mode": mode, "default_min_score": default, "override_min_score": override,
            "effective_min_score": default if override is None else override, "can_edit": can_edit}


def set_override(db, bundle_id: int, mode: SearchMode, value: float | None) -> None:
    policy = db.get(OKFImageSearchPolicy, bundle_id)
    if policy is None:
        if value is None:
            return
        policy = OKFImageSearchPolicy(bundle_id=bundle_id)
        db.add(policy)
    setattr(policy, _COLUMNS[mode], value)
    db.flush()


def thresholds(db, bundle_ids: set[int], mode: SearchMode) -> dict[int, float]:
    default = default_min_score(mode)
    result = dict.fromkeys(bundle_ids, default)
    for policy in db.query(OKFImageSearchPolicy).filter(OKFImageSearchPolicy.bundle_id.in_(bundle_ids)).all():
        value = getattr(policy, _COLUMNS[mode])
        if value is not None:
            result[policy.bundle_id] = value
    return result
