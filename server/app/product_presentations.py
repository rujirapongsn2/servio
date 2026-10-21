"""Source-backed product cards carried alongside SDK history."""
import ipaddress
import json
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

MAX_PAYLOAD = 64000


def safe_product_url(value: str) -> str:
    if any(ord(char) <= 32 or ord(char) == 127 or char == "\\" for char in value):
        raise ValueError("Invalid URL characters")
    parsed = urlsplit(value)
    host = (parsed.hostname or "").rstrip(".")
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise ValueError("Public HTTPS URL required")
    if host.lower() == "localhost" or host.lower().endswith((".localhost", ".local", ".internal")) or "." not in host or ":" in host:
        raise ValueError("Public HTTPS URL required")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if all(char.isdigit() or char == "." for char in host):
            raise ValueError("Invalid IP address")
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Public HTTPS URL required")
    return value


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)
    id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    image_url: str | None = Field(default=None, max_length=2048)
    part_number: str | None = Field(default=None, max_length=128)
    brand: str | None = Field(default=None, max_length=128)
    price_text: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=4000)
    detail_url: str | None = Field(default=None, max_length=2048)

    @field_validator("image_url", "detail_url")
    @classmethod
    def validate_url(cls, value):
        return safe_product_url(value) if value is not None else value


class ProductCarousel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)
    type: Literal["product_carousel"]
    version: Literal[1]
    summary: str = Field(min_length=1, max_length=1000)
    products: list[Product] = Field(min_length=1, max_length=10)

    @field_validator("products")
    @classmethod
    def unique_ids(cls, products):
        if len({product.id for product in products}) != len(products):
            raise ValueError("Duplicate product ID")
        return products


def parse_product_carousel(value) -> ProductCarousel | None:
    try:
        if isinstance(value, str):
            if len(value) > MAX_PAYLOAD:
                return None
            value = json.loads(value)
        if not isinstance(value, dict) or value.get("type") != "product_carousel" or type(value.get("version")) is not int:
            return None
        if len(json.dumps(value, ensure_ascii=False)) > MAX_PAYLOAD:
            return None
        return ProductCarousel.model_validate(value)
    except (ValueError, TypeError, ValidationError):
        return None


def product_inquiry(product: Product) -> str:
    lines = [f"ขอสอบถามสินค้า {product.title}", f"รหัสสินค้า: {product.id}"]
    if product.part_number:
        lines.append(f"เลขอะไหล่: {product.part_number}")
    return "\n".join(lines)
