# Web Chat product carousel

A Custom API capability can return a product carousel as its root JSON response. Both Web Chat and the embedded widget display the source summary and product cards. Ordinary tool responses retain their existing presentation.

```json
{
  "type": "product_carousel",
  "version": 1,
  "summary": "พบสินค้าที่ตรงกับรถของคุณ",
  "products": [
    {
      "id": "spark-9807b",
      "title": "หัวเทียน",
      "part_number": "9807B-561BW",
      "brand": "HONDA",
      "description": "รายละเอียดจากระบบสินค้า",
      "image_url": "https://catalog.example.com/images/9807b.png",
      "detail_url": "https://catalog.example.com/products/9807b"
    }
  ]
}
```

Return 1 to 10 products with unique IDs. Only `id` and `title` are required on each product. Optional `price_text` displays the source price exactly. Omit unavailable information. Image and detail URLs must use public HTTPS addresses without credentials. HTML and LINE Flex JSON are not supported.

Limits are 128 characters for IDs, part numbers and brands, 200 for titles, 100 for prices, 4,000 for descriptions, 2,048 for URLs and 1,000 for the summary. The complete envelope is limited to 64,000 characters. Extra fields and malformed envelopes fall back to ordinary tool output.

The API supplies the cards. The model supplies its conversational answer. Configure the agent to search the product capability before recommending products and to avoid repeating every product field in its answer. Servio does not infer product cards from arbitrary JSON or invent prices.

**ดูรายละเอียด** opens a modal details panel with keyboard focus containment, Escape dismissal and focus return. **สอบถามสินค้านี้** sends the selected call ID and product ID to the server. The server resolves the source facts from that socket's tool-output registry and adds the inquiry to the same conversation. Client-supplied product facts are ignored. Unknown, reset and other-socket selections fail without invoking the model.

Cards remain available across turns in the current connection. New conversations and new socket connections clear them. Up to 50 carousel results are retained per connection. Reload persistence, carts, image recognition and LINE transport are outside this version.

Run backend regression tests with `PYTHONPATH=server server/.venv/bin/python -m pytest server/tests/test_product_presentations.py`. Run frontend tests with `cd frontend && npm run test:regression`. Real integration acceptance should connect a scoped test capability to a product endpoint and exercise actual WebSocket tool output, selection, reset and both desktop and narrow widget layouts.

## Try the example catalog

From `server/`, run `uv run uvicorn examples.product_catalog:app --host 127.0.0.1 --port 8095`. This separate development API contains five explicitly synthetic products. It is not mounted in the main application.

Create a Custom API capability pointing to `http://127.0.0.1:8095/products`, method POST, with payload `{"query":""}`. Assign it to an Agent in the Web Chat's Team Agent and ask that Agent to search the example catalog. The backend must be able to reach the endpoint; a backend in Docker needs an appropriate host or service address instead of its own localhost.

The example also supports `GET /products` and filters when the query contains a demo product ID. Responses use the same validated product contract as Web Chat. Image placeholders and prices are demonstration data, not real inventory.

Web Chat keeps repeated model text after product results under **คำตอบเพิ่มเติม**. Clicking **สอบถามสินค้านี้** sends a short product name/ID/part-number message; the complete source facts remain in the preceding tool result. Changing WebSocket/channel clears pending loading state and old card selections.

## Connect an MCP catalog

MCP Streamable HTTP capabilities can return the same product envelope in `CallToolResult.structuredContent`. A valid product envelope takes precedence over `content` text. A result with `isError: true` never produces cards. Invalid product envelopes return an error instead of displaying conflicting text cards. Text-only JSON envelopes remain supported.

From `server/`, run `uv run python -m examples.product_catalog_mcp`. The example listens at `http://127.0.0.1:8096/mcp` and exposes `search_products` with a `query` string. Its typed product response is serialized by FastMCP into `structuredContent` with a JSON text copy for older clients. Set `PRODUCT_CATALOG_MCP_PORT` to use another port.

Create an MCP Streamable HTTP capability for that endpoint, select `search_products`, and assign the capability to the Web Chat Agent. The backend must be able to reach the endpoint. Ask the Agent to search the example catalog, open **ดูรายละเอียด**, then choose **สอบถามสินค้านี้**. The inquiry should refer to the selected product ID and part number.

The MCP client uses the SDK for initialization, session headers, and JSON/SSE responses. Bearer, custom-header, and query authentication keep their existing configuration. Redirects are disabled. Configured tool names that are absent from the server are refused rather than replaced with another tool.
