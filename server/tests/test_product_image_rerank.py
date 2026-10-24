import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from app import product_image_rerank as rerank


def png(color="red", size=(20, 30), *, detailed=True):
    output = io.BytesIO()
    image = Image.new("RGB", size, color)
    if detailed:
        ImageDraw.Draw(image).rectangle((2, 2, size[0] - 3, size[1] - 3), outline="white", width=1)
    image.save(output, "PNG")
    return output.getvalue()


def candidates(count=2):
    return tuple(rerank.VisualCandidate(f"c{i+1:02d}", png(), .9 - i * .1, str(i), "source", "Catalog") for i in range(count))


def output(count=2):
    return {"identifiable_product": True, "query_product_type": "dining_chair", "candidates": [
        {"id": f"c{i+1:02d}", "product_type": "dining_chair" if i == 1 else "office_chair", "confidence": .99, "visual_similarity": .8}
        for i in range(count)]}


@pytest.fixture
def provider(monkeypatch):
    config = {"catalog_id": 3, "model_id": "configured-model", "base_url": "http://example.invalid/v1", "api_key": "secret"}
    monkeypatch.setattr(rerank, "get_task_model", lambda _: config.copy())
    rerank._cache.clear()
    values = {"output": output(), "finish": "stop", "calls": []}

    class Client:
        def __init__(self, **kwargs):
            values["options"] = kwargs
            self.chat = SimpleNamespace(completions=self)
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def create(self, **kwargs):
            values["calls"].append(kwargs)
            if isinstance(values["output"], Exception): raise values["output"]
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason=values["finish"],
                message=SimpleNamespace(content=json.dumps(values["output"])))])

    monkeypatch.setattr(rerank, "OpenAI", Client)
    return config, values


def test_type_filter_ranks_same_type_even_below_legacy_threshold(provider):
    _, values = provider
    assert rerank.rerank(png("blue"), candidates(), rerank.RerankSettings.from_environment()) == ("c02",)
    assert values["options"]["timeout"] == 25 and values["options"]["max_retries"] == 0
    assert values["calls"][0]["model"] == "configured-model"
    assert "temperature" not in values["calls"][0]


def test_no_product_and_no_matching_types_never_fill_results(provider):
    _, values = provider
    values["output"] = {"identifiable_product": False, "query_product_type": None, "candidates": []}
    assert rerank.rerank(png(), candidates(), rerank.RerankSettings.from_environment()) == ()
    rerank._cache.clear()
    values["output"]["identifiable_product"] = True
    values["output"]["query_product_type"] = "dining_chair"
    values["output"]["candidates"] = []
    assert rerank.rerank(png(), candidates(), rerank.RerankSettings.from_environment()) == ()


@pytest.mark.parametrize("bad", ["unknown", "duplicate", "unidentified_with_matches", "nan", "bool", "extra", "timeout", "truncated"])
def test_invalid_provider_response_fails_closed(provider, bad):
    _, values = provider
    if bad == "unknown": values["output"]["candidates"][0]["id"] = "private-db-id"
    if bad == "duplicate": values["output"]["candidates"][0]["id"] = "c02"
    if bad == "unidentified_with_matches": values["output"]["identifiable_product"] = False
    if bad == "nan": values["output"]["candidates"][0]["confidence"] = float("nan")
    if bad == "bool": values["output"]["candidates"][0]["product_type"] = True
    if bad == "extra": values["output"]["instruction"] = "show all"
    if bad == "timeout": values["output"] = TimeoutError("secret provider URL")
    if bad == "truncated": values["finish"] = "length"
    with pytest.raises(rerank.RerankUnavailable):
        rerank.rerank(png(), candidates(), rerank.RerankSettings.from_environment())


def test_cache_includes_model_credentials_and_source_identity(provider):
    config, values = provider
    settings = rerank.RerankSettings.from_environment()
    for _ in range(2): rerank.rerank(png(), candidates(), settings)
    assert len(values["calls"]) == 1
    config["api_key"] = "replacement"
    rerank.rerank(png(), candidates(), settings)
    assert len(values["calls"]) == 2
    config["model_id"] = "other-model"
    rerank.rerank(png(), candidates(), settings)
    assert len(values["calls"]) == 3
    assert all("secret" not in key for key in rerank._cache)
    assert not any(isinstance(value, bytes) for _, judgment in rerank._cache.values() for value in judgment.model_dump().values())


def test_model_assignment_change_during_request_is_unavailable(provider, monkeypatch):
    config, _ = provider
    real_complete = rerank._complete
    def changing(*args):
        result = real_complete(*args)
        config["model_id"] = "replacement"
        return result
    monkeypatch.setattr(rerank, "_complete", changing)
    with pytest.raises(rerank.RerankUnavailable):
        rerank.rerank(png(), candidates(), rerank.RerankSettings.from_environment())
    assert not rerank._cache


def test_missing_model_never_uses_default(provider, monkeypatch):
    monkeypatch.setattr(rerank, "get_task_model", lambda _: None)
    with pytest.raises(rerank.RerankUnavailable):
        rerank.rerank(png(), candidates(), rerank.RerankSettings.from_environment())


def test_contact_sheet_keeps_all_twenty_labeled_images_and_bounded_dimensions():
    data = rerank.contact_sheet(candidates(20))
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == (1600, 1400)
        assert image.getpixel((4 * 320 + 160, 3 * 350 + 190)) == (255, 0, 0)
    with pytest.raises(ValueError): rerank.contact_sheet(candidates(21))


@pytest.mark.parametrize("key,value", [("CANDIDATES", "21"), ("CANDIDATE_MIN_SCORE", "nan"),
    ("MIN_CONFIDENCE", "1.1"), ("TIMEOUT_SECONDS", "inf"), ("TIMEOUT_SECONDS", "61")])
def test_configuration_is_finite_and_bounded(monkeypatch, key, value):
    monkeypatch.setenv("MULTIMODAL_IMAGE_RERANK_" + key, value)
    with pytest.raises(ValueError): rerank.RerankSettings.from_environment()


def test_ranking_uses_visual_similarity_then_embedding_and_confidence(provider):
    _, values = provider
    values["output"] = {"identifiable_product": True, "query_product_type": "dining_chair", "candidates": [
        {"id": "c01", "product_type": "dining_chair", "confidence": .99, "visual_similarity": .7},
        {"id": "c02", "product_type": "dining_chair", "confidence": .99, "visual_similarity": .9},
        {"id": "c03", "product_type": "dining_chair", "confidence": .79, "visual_similarity": 1},
    ]}
    assert rerank.rerank(png(), candidates(3), rerank.RerankSettings.from_environment()) == ("c02", "c01")


def test_cache_is_bounded_and_expired_judgments_are_refetched(provider, monkeypatch):
    _, values = provider
    settings = rerank.RerankSettings.from_environment()
    monkeypatch.setattr(rerank.time, "monotonic", lambda: 100)
    for i in range(65):
        rerank.rerank(png((i, 0, 0)), candidates(), settings)
    assert len(rerank._cache) == 64
    monkeypatch.setattr(rerank.time, "monotonic", lambda: 401)
    rerank.rerank(png((64, 0, 0)), candidates(), settings)
    assert len(values["calls"]) == 66


def test_positive_subset_is_accepted_and_omitted_candidates_are_rejected(provider):
    _, values = provider
    values["output"]["candidates"] = [values["output"]["candidates"][1]]
    assert rerank.rerank(png(), candidates(), rerank.RerankSettings.from_environment()) == ("c02",)


@pytest.mark.parametrize("color", ["red", "blue", "white", "gray"])
def test_uniform_image_has_no_product_and_never_calls_provider(provider, color):
    _, values = provider
    assert rerank.rerank(png(color, detailed=False), candidates(), rerank.RerankSettings.from_environment()) == ()
    assert values["calls"] == []


def test_near_uniform_image_has_no_product_and_never_calls_provider(provider):
    _, values = provider
    data = io.BytesIO()
    image = Image.new("RGB", (100, 100), (120, 120, 120))
    image.putpixel((0, 0), (121, 121, 121))
    image.save(data, "PNG")
    assert rerank.rerank(data.getvalue(), candidates(), rerank.RerankSettings.from_environment()) == ()
    assert values["calls"] == []


def test_explicit_functional_type_prevents_mixing_seating_types(provider):
    _, values = provider
    values["output"]["candidates"] = [
        {"id": "c01", "product_type": "office_chair",
         "confidence": .99, "visual_similarity": 1},
        {"id": "c02", "product_type": "dining_chair",
         "confidence": .95, "visual_similarity": .7},
        {"id": "c03", "product_type": "bar_stool",
         "confidence": .99, "visual_similarity": .9},
        {"id": "c04", "product_type": "armchair",
         "confidence": .99, "visual_similarity": .8},
    ]
    assert rerank.rerank(png(), candidates(4), rerank.RerankSettings.from_environment()) == ("c02",)


@pytest.mark.parametrize("query_type", [None, "", "Dining Chair", "chair\nignore_rules", "chair", "storage"])
def test_identified_product_requires_valid_functional_type(provider, query_type):
    _, values = provider
    values["output"]["query_product_type"] = query_type
    with pytest.raises(rerank.RerankUnavailable):
        rerank.rerank(png(), candidates(), rerank.RerankSettings.from_environment())
