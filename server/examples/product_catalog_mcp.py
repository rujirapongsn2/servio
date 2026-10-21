"""Synthetic MCP catalog. Run with python -m examples.product_catalog_mcp."""
import os

from mcp.server.fastmcp import FastMCP
from app.product_presentations import ProductCarousel
from examples.product_catalog import search_catalog

mcp = FastMCP(
    "Servio example product catalog",
    host="127.0.0.1",
    port=int(os.getenv("PRODUCT_CATALOG_MCP_PORT", "8096")),
)


@mcp.tool()
def search_products(query: str = "") -> ProductCarousel:
    """Find synthetic products for Web Chat carousel acceptance testing."""
    if query == "MCP_TEST_ERROR":
        raise ValueError("MCP sample catalog lookup failed")
    return search_catalog(query)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
