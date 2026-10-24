"""The compatibility gate checks vector agreement and retrieval identity."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-image-embedding-compatibility.py"
spec = importlib.util.spec_from_file_location("image_embedding_compatibility", SCRIPT)
compatibility = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compatibility)


def vector(first, second=0):
    return [first, second] + [0] * 766


class CompatibilityTests(unittest.TestCase):
    def test_partial_image_vector_coverage_fails_and_pdf_is_excluded(self):
        common = {"bundle_id": 16, "content_hash": "current"}
        sources = [
            dict(common, concept_id="image-ready",
                 frontmatter={"document_type": "jpg"},
                 embedding="[1,0]", source_hash="current"),
            dict(common, concept_id="image-missing",
                 frontmatter={"document_type": "png"},
                 embedding=None, source_hash=None),
            dict(common, concept_id="document",
                 frontmatter={"document_type": "pdf"},
                 embedding=None, source_hash=None),
        ]
        images, errors = compatibility.image_coverage(sources)
        self.assertEqual(len(images), 2)
        self.assertEqual(errors, [{
            "bundle_id": 16,
            "concept_id": "image-missing",
            "error_type": "MissingImageVector",
        }])

    def test_stale_image_vector_is_reported_as_incomplete_coverage(self):
        _, errors = compatibility.image_coverage([{
            "bundle_id": 16, "concept_id": "image-stale",
            "frontmatter": {"document_type": "jpg"},
            "embedding": "[1,0]", "source_hash": "old",
            "content_hash": "current",
        }])
        self.assertEqual(errors[0]["error_type"], "StaleImageVector")

    def test_same_asset_under_duplicate_concepts_passes(self):
        original = vector(1)
        result = compatibility.assess_vector(original, original, "asset-a", [("asset-a", original), ("asset-a", original)], 0.995)
        self.assertTrue(result["compatible"])
        self.assertEqual(result["candidate_dimensions"], 768)
        self.assertAlmostEqual(result["cosine"], 1)

    def test_cosine_threshold_rejects_encoder_drift(self):
        result = compatibility.assess_vector(vector(1, 1), vector(1), "asset-a", [("asset-a", vector(1))], 0.995)
        self.assertTrue(result["correct_top1"])
        self.assertFalse(result["compatible"])

    def test_wrong_nearest_asset_fails_even_when_similarity_passes(self):
        candidate = vector(1, 0.02)
        result = compatibility.assess_vector(candidate, vector(1), "asset-a", [("asset-a", vector(1)), ("asset-b", candidate)], 0.995)
        self.assertGreater(result["cosine"], 0.995)
        self.assertEqual(result["nearest_old_asset_id"], "asset-b")
        self.assertFalse(result["compatible"])

    def test_wrong_dimension_cannot_pass(self):
        short = [1.0, 0.0]
        result = compatibility.assess_vector(short, short, "asset-a", [("asset-a", short)], 0.995)
        self.assertFalse(result["compatible"])
        with self.assertRaises(ValueError):
            compatibility.cosine(short, vector(1))

    def test_zero_or_nonfinite_vector_is_rejected(self):
        for invalid in (vector(0), vector(float("nan")), vector(float("inf"))):
            with self.assertRaises(ValueError):
                compatibility.cosine(invalid, vector(1))


if __name__ == "__main__":
    unittest.main()
