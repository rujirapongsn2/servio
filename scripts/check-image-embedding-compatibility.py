#!/usr/bin/env python3
"""Compare candidate image embeddings with a read-only stored-vector snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Vector dimensions differ")
    if not all(math.isfinite(value) for value in left + right):
        raise ValueError("Vectors must be finite")
    denominator = math.sqrt(
        sum(value * value for value in left)
        * sum(value * value for value in right)
    )
    if not denominator:
        raise ValueError("Vectors must be nonzero")
    return max(
        -1.0, min(1.0, sum(a * b for a, b in zip(left, right)) / denominator)
    )


def assess_vector(candidate, stored, asset_id, old_vectors, minimum_cosine):
    score = cosine(candidate, stored)
    nearest_asset, _ = max(
        old_vectors, key=lambda row: cosine(candidate, row[1])
    )
    same_asset = nearest_asset == asset_id
    return {
        "stored_dimensions": len(stored),
        "candidate_dimensions": len(candidate),
        "cosine": score,
        "nearest_old_asset_id": nearest_asset,
        "correct_top1": same_asset,
        "compatible": len(candidate) == 768 and score >= minimum_cosine and same_asset,
    }


def image_coverage(concepts):
    images = [
        row for row in concepts
        if row["frontmatter"].get("document_type") in {"jpg", "jpeg", "png"}
    ]
    return images, [
        {
            "bundle_id": row["bundle_id"],
            "concept_id": row["concept_id"],
            "error_type": (
                "MissingImageVector" if row["embedding"] is None
                else "StaleImageVector"
            ),
        }
        for row in images
        if row["embedding"] is None or row["source_hash"] != row["content_hash"]
    ]


def check(args):
    for name in ("DATABASE_URL", "OKF_STORAGE_DIR"):
        if not os.environ.get(name):
            raise ValueError(f"Set {name} explicitly")
    storage_root = Path(os.environ["OKF_STORAGE_DIR"]).resolve(strict=True)
    os.environ["MULTIMODAL_EMBEDDING_BASE_URL"] = args.base_url
    os.environ["MULTIMODAL_EMBEDDING_MODEL"] = args.model
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
    from sqlalchemy import bindparam, text
    from app.db_config import engine
    from app.local_image_rag import LocalImageEmbeddingClient, _asset
    from app.okf_service import _ensure_within, _parse_frontmatter

    statement = text("""
        SELECT c.bundle_id, c.concept_id, v.asset_id, v.source_hash,
               v.space, v.embedding::text AS embedding,
               c.content_hash, c.file_path, b.storage_path
        FROM okf_concept_index c
        JOIN okf_bundles b ON b.id = c.bundle_id
        LEFT JOIN okf_image_vectors v
          ON c.bundle_id = v.bundle_id AND c.concept_id = v.concept_id
        WHERE c.bundle_id IN :bundles
        ORDER BY c.bundle_id, c.concept_id
    """).bindparams(bindparam("bundles", expanding=True))
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        rows = connection.execute(
            statement, {"bundles": sorted(set(args.bundle_id))}
        ).mappings().all()
    sources = []
    for row in rows:
        root = Path(row["storage_path"])
        _ensure_within(storage_root, root)
        source = root / row["file_path"]
        _ensure_within(root, source)
        markdown = source.read_text(encoding="utf-8")
        frontmatter, _ = _parse_frontmatter(markdown, row["file_path"])
        sources.append(dict(row, markdown=markdown, frontmatter=frontmatter))
    images, coverage_errors = image_coverage(sources)
    old_vectors = [
        (row["asset_id"], json.loads(row["embedding"]))
        for row in images if row["embedding"] is not None
    ]
    client = LocalImageEmbeddingClient()
    records = []
    for row in images:
        record = {
            "bundle_id": row["bundle_id"],
            "concept_id": row["concept_id"],
            "asset_id": row["asset_id"],
        }
        try:
            if row["embedding"] is None:
                raise ValueError("Image vector is missing")
            if not row["content_hash"] or row["source_hash"] != row["content_hash"]:
                raise ValueError("Stored source hash is stale")
            root = Path(row["storage_path"])
            markdown = row["markdown"]
            if hashlib.sha256(markdown.encode()).hexdigest() != row["source_hash"]:
                raise ValueError("Source content hash does not match")
            asset_id, original, _ = _asset(root, row["frontmatter"])
            if asset_id != row["asset_id"]:
                raise ValueError("Stored asset hash does not match")
            candidate = client.image(original)
            record.update(assess_vector(
                candidate, json.loads(row["embedding"]), asset_id, old_vectors,
                args.minimum_cosine,
            ))
        except Exception as exc:
            record.update(compatible=False, error_type=type(exc).__name__)
        records.append(record)
    missing = sorted(
        set(args.bundle_id) - {row["bundle_id"] for row in images
                             if row["embedding"] is not None}
    )
    passed = (
        bool(records) and not missing and not coverage_errors
        and all(record["compatible"] for record in records)
    )
    scores = [record["cosine"] for record in records if "cosine" in record]
    return {
        "images": records,
        "summary": {
            "compatible": passed,
            "images_checked": len(records),
            "images_passed": sum(record["compatible"] for record in records),
            "bundles_without_vectors": missing,
            "image_vector_coverage_errors": coverage_errors,
            "minimum_cosine_required": args.minimum_cosine,
            "minimum_cosine_observed": min(scores) if scores else None,
            "stored_spaces": sorted({
                row["space"] for row in images if row["space"] is not None
            }),
            "candidate_space": client.space,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-id", type=int, action="append", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--minimum-cosine", type=float, default=0.995)
    args = parser.parse_args()
    if (
        not math.isfinite(args.minimum_cosine)
        or not 0 <= args.minimum_cosine <= 1
    ):
        parser.error("--minimum-cosine must be between 0 and 1")
    try:
        result = check(args)
    except Exception as exc:
        print(json.dumps({"summary": {"compatible": False, "error_type": type(exc).__name__}}))
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result["summary"]["compatible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
