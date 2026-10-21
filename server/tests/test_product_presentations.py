import asyncio
import json
from types import SimpleNamespace

import pytest
from agents import Agent, RunItemStreamEvent, ToolCallOutputItem

from app.product_presentations import parse_product_carousel


def envelope(product_id="sku-1"):
    return {"type": "product_carousel", "version": 1, "summary": "พบสินค้า", "products": [{"id": product_id, "title": "หัวเทียน", "part_number": "9807B", "price_text": "250 บาท", "image_url": "https://example.com/product.png"}]}


@pytest.mark.parametrize("changes", [
    {"products": []}, {"version": 2}, {"summary": ""},
    {"products": [{"id": "sku", "title": "x", "image_url": "javascript:alert(1)"}]},
    {"products": [{"id": "sku", "title": "x", "detail_url": "https://127.0.0.1/"}]},
    {"products": [{"id": "sku", "title": "x", "image_url": "https://user:pass@example.com/x"}]},
    {"products": [{"id": "sku", "title": "x"}] * 2},
    {"products": [{"id": "sku", "title": "x", "html": "<script/>"}]},
])
def test_rejects_invalid_source(changes):
    assert parse_product_carousel(envelope() | changes) is None


def test_explicit_envelope_only():
    assert parse_product_carousel(json.dumps(envelope())).products[0].part_number == "9807B"
    assert parse_product_carousel({"data": envelope()}) is None
    assert parse_product_carousel("ordinary answer") is None


class Socket:
    def __init__(self):
        self.messages = []

    async def send_text(self, message):
        self.messages.append(json.loads(message))


class Analytics:
    def start_conversation(self, *args, **kwargs):
        return "conversation"

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def test_real_sdk_outputs_correlate_and_survive_streaming_and_done(monkeypatch):
    from app import db_config
    with monkeypatch.context() as imports:
        imports.setattr(db_config, "init_database", lambda: None)
        from app import utils
    monkeypatch.setattr(utils, "AnalyticsService", Analytics)
    agent = Agent(name="Catalog")
    socket = Socket()
    helper = utils.WebsocketHelper(socket, [], agent, "session")

    async def run():
        for call_id, product_id in [("call-b", "sku-b"), ("call-a", "sku-a")]:
            payload = json.dumps(envelope(product_id), ensure_ascii=False)
            item = ToolCallOutputItem(agent=agent, raw_item={"type": "function_call_output", "call_id": call_id, "output": payload}, output=payload)
            await helper.handle_new_item(RunItemStreamEvent(name="tool_output", item=item))
        await helper.stream_response("Found")
        final_history = list(helper.history)
        output = SimpleNamespace(last_agent=agent, to_input_list=lambda: final_history)
        await helper.text_output_complete(output, is_done=True)
        await helper.show_user_input("next question")
        assert all(set(message["presentations"]) == {"call-b", "call-a"} for message in socket.messages[1:])
        assert helper.presentations["call-a"]["products"][0]["id"] == "sku-a"
        assert all(item["type"] != "product_carousel" for item in helper.history)
        inquiry = helper.resolve_product_inquiry({"call_id": "call-a", "product_id": "sku-a", "price_text": "FREE"})
        assert "9807B" in inquiry and "sku-a" in inquiry and "FREE" not in inquiry
        assert "https://" not in inquiry and "{" not in inquiry
        assert helper.presentations["call-a"]["products"][0]["price_text"] == "250 บาท"
        assert helper.resolve_product_inquiry({"call_id": "call-a", "product_id": "sku-b"}) is None
        other = utils.WebsocketHelper(Socket(), [], agent, "other-session")
        assert other.resolve_product_inquiry({"call_id": "call-a", "product_id": "sku-a"}) is None
        helper.reset_presentations()
        assert helper.resolve_product_inquiry({"call_id": "call-a", "product_id": "sku-a"}) is None
    asyncio.run(run())


def test_custom_api_preserves_envelope_before_text(monkeypatch):
    from app.agent_config import create_custom_api_tool
    from agents import RunContextWrapper
    import requests
    payload = envelope()
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload))
    tool = create_custom_api_tool("catalog", {"endpoint": "https://example.com/catalog", "method": "GET"})
    result = asyncio.run(tool.on_invoke_tool(RunContextWrapper(context=None), '{"query":"spark plug"}'))
    assert parse_product_carousel(result).products[0].id == "sku-1"


def test_example_catalog_api_returns_valid_cards_and_filters_by_product_id():
    from fastapi.testclient import TestClient
    from examples.product_catalog import app
    with TestClient(app) as client:
        response = client.post('/products', json={'query': 'หัวเทียน'})
        assert response.status_code == 200
        cards = parse_product_carousel(response.json())
        assert cards is not None and len(cards.products) == 5
        response = client.post('/products', json={'query': 'DEMO-SPARK-02'})
        cards = parse_product_carousel(response.json())
        assert cards is not None and [product.id for product in cards.products] == ['DEMO-SPARK-02']
