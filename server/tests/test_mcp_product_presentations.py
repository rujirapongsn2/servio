import asyncio
import json
from contextlib import asynccontextmanager

import pytest
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from app import agent_config
from app.product_presentations import parse_product_carousel
from examples.product_catalog import search_catalog
from examples.product_catalog_mcp import mcp, search_products


def carousel(product_id="DEMO-SPARK-02"):
    return search_catalog(product_id).model_dump(exclude_none=True)


def result(text="Catalog result", structured=None, is_error=False):
    return CallToolResult(
        content=[TextContent(type="text", text=text)] if text else [],
        structuredContent=structured,
        isError=is_error,
    )


def run_call(monkeypatch, response, tools=None, **options):
    observed = {}
    available = tools if tools is not None else [Tool(
        name="search_products", inputSchema={
            "type": "object", "properties": {"query": {"type": "string"}},
        },
    )]

    @asynccontextmanager
    async def transport(endpoint, **kwargs):
        observed.update(endpoint=endpoint, transport=kwargs)
        async with kwargs["httpx_client_factory"]() as client:
            observed["follow_redirects"] = client.follow_redirects
        yield (object(), object(), lambda: "session-test")

    class Session:
        def __init__(self, read, write, **kwargs):
            observed["session_options"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def initialize(self):
            observed["initialized"] = True

        async def list_tools(self):
            assert observed["initialized"]
            return ListToolsResult(tools=available)

        async def call_tool(self, name, arguments):
            observed["call"] = (name, arguments)
            return response

    monkeypatch.setattr(agent_config, "streamablehttp_client", transport)
    monkeypatch.setattr(agent_config, "ClientSession", Session)
    parameters = dict(
        endpoint="https://catalog.example/mcp", auth_token=None,
        auth_mode="bearer", auth_param_name="apikey", auth_header_name="X-API-Key",
        timeout_s=5, query="หัวเทียน", tool_names=["search_products"],
    )
    parameters.update(options)
    return asyncio.run(agent_config._call_mcp_server(**parameters)), observed


def test_structured_content_wins_conflicting_text(monkeypatch):
    output, observed = run_call(monkeypatch, result(json.dumps(carousel("DEMO-SPARK-01")), carousel()))
    assert parse_product_carousel(output).products[0].id == "DEMO-SPARK-02"
    assert observed["call"] == ("search_products", {"query": "หัวเทียน"})
    assert observed["transport"]["sse_read_timeout"] == 5
    assert observed["session_options"]["read_timeout_seconds"].total_seconds() == 5
    assert observed["follow_redirects"] is False


@pytest.mark.parametrize("structured", [None, {"status": "ok"}])
def test_text_only_carousel_remains_compatible(monkeypatch, structured):
    output, _ = run_call(monkeypatch, result(json.dumps(carousel()), structured))
    assert parse_product_carousel(output).products[0].id == "DEMO-SPARK-02"


def test_malformed_declared_structured_carousel_cannot_fall_back_to_other_cards(monkeypatch):
    output, _ = run_call(monkeypatch, result(json.dumps(carousel()), {"type": "product_carousel", "version": 1}))
    assert output.startswith("MCP Error: Invalid product carousel")
    assert parse_product_carousel(output) is None


@pytest.mark.parametrize("structured", [None, {"status": "ok"}, {"products": []}])
def test_ordinary_text_preserved(monkeypatch, structured):
    output, _ = run_call(monkeypatch, result("Stock service unavailable", structured))
    assert output == "Stock service unavailable"


def test_nonproduct_structured_result_retained_without_creating_cards(monkeypatch):
    output, _ = run_call(monkeypatch, result("", {"stock": 42}))
    assert json.loads(output)["structuredContent"] == {"stock": 42}
    assert parse_product_carousel(output) is None


@pytest.mark.parametrize("text", ["", "Lookup failed", json.dumps(carousel())])
def test_error_result_never_becomes_cards(monkeypatch, text):
    output, _ = run_call(monkeypatch, result(text, carousel(), is_error=True))
    assert output.startswith("MCP Error:")
    assert parse_product_carousel(output) is None


@pytest.mark.parametrize("mode,endpoint,header", [
    ("bearer", "https://catalog.example/mcp", {"Authorization": "Bearer test-secret"}),
    ("header", "https://catalog.example/mcp", {"X-Catalog-Key": "test-secret"}),
    ("query", "https://catalog.example/mcp?tenant=demo&token=test-secret", {}),
])
def test_auth_modes_preserved(monkeypatch, mode, endpoint, header):
    output, observed = run_call(
        monkeypatch, result(), auth_token="test-secret", auth_mode=mode,
        endpoint="https://catalog.example/mcp?tenant=demo" if mode == "query" else endpoint,
        auth_param_name="token", auth_header_name="X-Catalog-Key",
    )
    assert output == "Catalog result"
    assert observed["endpoint"] == endpoint
    assert observed["transport"]["headers"] == header


def test_query_auth_preserves_existing_token(monkeypatch):
    _, observed = run_call(monkeypatch, result(), endpoint="https://catalog.example/mcp?apikey=existing", auth_token="replacement", auth_mode="query")
    assert observed["endpoint"] == "https://catalog.example/mcp?apikey=existing"


def test_selects_only_configured_tool_and_refuses_missing_name(monkeypatch):
    tools = [Tool(name="other", inputSchema={}), Tool(name="search_products", inputSchema={"type": "object", "properties": {"text": {"type": "string"}}})]
    _, observed = run_call(monkeypatch, result(), tools=tools)
    assert observed["call"] == ("search_products", {"text": "หัวเทียน"})
    output, observed = run_call(monkeypatch, result(), tools=tools, tool_names=["missing"])
    assert output.startswith("Requested tools not found")
    assert "call" not in observed


def test_unconfigured_tools_uses_first_and_empty_list_is_explicit(monkeypatch):
    _, observed = run_call(monkeypatch, result(), tool_names=[])
    assert observed["call"][0] == "search_products"
    output, observed = run_call(monkeypatch, result(), tools=[])
    assert output == "No tools available from MCP server"
    assert "call" not in observed


def test_example_mcp_serialization_returns_root_structured_cards():
    content, structured = asyncio.run(mcp.call_tool("search_products", {"query": "DEMO-SPARK-02"}))
    parsed = parse_product_carousel(structured)
    assert [product.id for product in parsed.products] == ["DEMO-SPARK-02"]
    assert parsed.products[0].part_number == "DEMO-9807-B"
    assert content[0].type == "text"


def test_example_error_cannot_return_product_cards():
    with pytest.raises(ValueError, match="MCP sample catalog lookup failed"):
        search_products("MCP_TEST_ERROR")


def test_sdk_tool_invocation_awaits_mcp_inside_running_event_loop(monkeypatch):
    from agents import RunContextWrapper

    async def call(**kwargs):
        assert kwargs["query"] == "หัวเทียน"
        return json.dumps(carousel())

    monkeypatch.setattr(agent_config, "_call_mcp_server", call)
    tool = agent_config.create_mcp_tool("search_catalog", {"endpoint": "https://catalog.example/mcp", "description": "Search catalog"})
    output = asyncio.run(tool.on_invoke_tool(RunContextWrapper(context=None), '{"query":"หัวเทียน"}'))
    assert parse_product_carousel(output).products[0].id == "DEMO-SPARK-02"
    assert tool.name == "search_catalog"
    assert tool.description == "Search catalog"
