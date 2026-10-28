import importlib

import pytest

from app.carousel_marker import MARKER, build_carousel_message, strip_marker


@pytest.fixture
def helper(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-no-network")
    import app.db_config

    monkeypatch.setattr(app.db_config, "init_database", lambda: None)
    module = importlib.import_module("app.utils")
    monkeypatch.setattr(module.AnalyticsService, "start_conversation", lambda self, *args, **kwargs: None)
    websocket = pytest.importorskip("fastapi").WebSocket
    instance = module.WebsocketHelper(websocket, [], None, "session-1", team_agent_id=7)
    return module, instance


def _fake_image(asset):
    return {
        "asset_id": asset,
        "title": f"product {asset[:4]}",
        "source_label": f"source {asset[:4]}",
        "image_url": f"/api/knowledge-images/{asset}?token=abc.def",
    }


def _fake_ref(asset):
    from app.knowledge_image_search import KnowledgeCardRef

    return KnowledgeCardRef(bundle=15, concept="concept-1", source="0" * 64, asset=asset)


def test_strip_marker_from_string():
    cleaned, had = strip_marker(f"เลือกดูได้เลยครับ\n\n{MARKER}")
    assert had is True
    assert MARKER not in cleaned
    assert cleaned == "เลือกดูได้เลยครับ"


def test_strip_marker_from_content_parts():
    parts = [{"type": "output_text", "text": "ภาพประกอบ", "annotations": []},
             {"type": "output_text", "text": f"โชว์สินค้า {MARKER}", "annotations": []}]
    cleaned, had = strip_marker(parts)
    assert had is True
    assert all(MARKER not in part["text"] for part in cleaned)


def test_strip_marker_without_marker_is_noop():
    cleaned, had = strip_marker("คำตอบธรรมดา")
    assert had is False and cleaned == "คำตอบธรรมดา"


def test_build_carousel_message_pairs_cards_with_refs():
    images = [_fake_image("a" * 64), _fake_image("b" * 64)]
    refs = [_fake_ref("a" * 64), _fake_ref("b" * 64)]
    built = build_carousel_message(images, refs, "แนะนำ 2 รุ่น")
    assert built is not None
    message_id, presentation, card_refs = built
    assert message_id.startswith("msg_")
    assert presentation["type"] == "knowledge_product_carousel"
    assert len(presentation["products"]) == 2
    assert presentation["summary"] == "แนะนำ 2 รุ่น"
    assert set(card_refs) == {product["id"] for product in presentation["products"]}
    for product in presentation["products"]:
        assert product["image_url"].startswith("/api/knowledge-images/")


def test_build_carousel_rejects_length_mismatch():
    assert build_carousel_message([_fake_image("a" * 64)], [], "summary") is None
    assert build_carousel_message([], [], "summary") is None


def test_convert_images_to_carousel_swaps_presentation(helper):
    module, instance = helper
    call_id = "call_1"
    images = [_fake_image("a" * 64)]
    instance.presentations[call_id] = {"type": "knowledge_images", "version": 1, "response": "r", "images": images}
    instance._knowledge_image_refs[call_id] = [_fake_ref("a" * 64)]

    item = {"type": "message", "role": "assistant", "content": f"เลือกได้เลย {MARKER}"}
    instance._convert_images_to_carousel(item)

    assert call_id not in instance.presentations
    message_id = item["id"]
    assert message_id.startswith("msg_")
    assert instance.presentations[message_id]["type"] == "knowledge_product_carousel"
    assert instance._last_carousel_message_id == message_id
    # inquiry refs registered so "สอบถามสินค้านี้" resolves
    registered = instance.image_search_session.refs[message_id][1]
    assert set(registered) == {p["id"] for p in instance.presentations[message_id]["products"]}


def test_convert_without_images_presentation_is_noop(helper):
    module, instance = helper
    item = {"type": "message", "role": "assistant", "content": f"ธรรมดา {MARKER}"}
    instance._convert_images_to_carousel(item)
    assert "id" not in item
    assert instance.presentations == {}


def test_convert_knowledge_media_keeps_audio(helper):
    module, instance = helper
    call_id = "call_9"
    images = [_fake_image("c" * 64)]
    instance.presentations[call_id] = {
        "type": "knowledge_media", "version": 1, "response": "r",
        "images": images, "audio": [{"source_label": "clip"}],
    }
    instance._knowledge_image_refs[call_id] = [_fake_ref("c" * 64)]
    item = {"type": "message", "role": "assistant", "content": f"เลือกได้เลย {MARKER}"}
    instance._convert_images_to_carousel(item)

    # audio stays at the tool call, images move to the carousel
    assert instance.presentations[call_id]["type"] == "knowledge_media"
    assert instance.presentations[call_id]["images"] == []
    assert instance.presentations[call_id]["audio"] == [{"source_label": "clip"}]
    message_id = item["id"]
    assert instance.presentations[message_id]["type"] == "knowledge_product_carousel"


def test_knowledge_media_refs_output_parses(helper):
    module, instance = helper
    import json
    output = json.dumps({
        "type": "knowledge_media_refs", "version": 1, "response": "r",
        "images": [{"asset_id": "d" * 64, "title": "t", "source_label": "s",
                    "bundle_id": 15, "concept_id": "c1", "source_hash": "0" * 64}],
        "audio": [],
    })
    refs = instance._knowledge_image_card_refs(output, 15)
    assert refs is not None and refs[0].asset == "d" * 64 and refs[0].bundle == 15
