"""Customer-facing Web Chat / Bubble theme: validation, palette and logo storage.

A theme belongs to one widget API key (``api_keys.theme``). Only the primary
colour, an optional logo and the greeting are stored; every other colour is
derived here so the admin preview, ``/widget``, ``/c/<slug>`` and ``embed.js``
all render the same palette and every text/background pair meets WCAG AA.
"""
from __future__ import annotations

import io
import re
import secrets
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator

THEME_VERSION = 1
DEFAULT_PRIMARY = "#2786c2"
INK = "#0d1b2a"
WHITE = "#ffffff"
AA = 4.5
NON_TEXT = 3.0

GREETING_TITLE_MAX = 80
GREETING_SUBTITLE_MAX = 140
LOCALES = ("th", "en")

LOGO_MAX_BYTES = 512 * 1024
LOGO_MAX_PIXELS = 4096 * 4096
LOGO_MAX_BOX = (480, 160)
LOGO_FILENAME = re.compile(r"^k\d{1,10}-[A-Za-z0-9_-]{16,64}\.png$")
_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

# The current Servio look. Kept verbatim so an un-themed widget is unchanged.
DEFAULT_PALETTE: Dict[str, str] = {
    "primary": "#2786c2",
    "primary_strong": "#1a5a8a",
    "on_primary": WHITE,
    "accent_text": "#1a5a8a",
    "bubble_from": "#2479b3",
    "bubble_to": "#236fa7",
    "on_bubble": WHITE,
    "tint_1": "#b9e8ed",
    "tint_2": "#bad9f4",
    "tint_3": "#ccece0",
    "base_1": "#e8f5f6",
    "base_2": "#eaf1fb",
    "base_3": "#e1f3ed",
    "frame_border": "#dce8f1",
    "frame_bg": "#f5faff",
}

PRESETS: List[Dict[str, str]] = [
    {"id": "servio", "primary": "#2786c2"},
    {"id": "emerald", "primary": "#0f8a5f"},
    {"id": "indigo", "primary": "#4f46e5"},
    {"id": "coral", "primary": "#e0533d"},
    {"id": "graphite", "primary": "#334155"},
]


class ThemeValidationError(ValueError):
    """Raised with a user-facing message when theme input is invalid."""


# --------------------------------------------------------------------------
# Colour maths (WCAG 2.x relative luminance)
# --------------------------------------------------------------------------

def normalize_hex(value: str) -> str:
    if not isinstance(value, str) or not _HEX.match(value.strip()):
        raise ThemeValidationError("สีต้องเป็นรหัส hex เช่น #2786c2")
    value = value.strip().lower()
    if len(value) == 4:
        value = "#" + "".join(ch * 2 for ch in value[1:])
    return value


def _rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb: Tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def luminance(hex_color: str) -> float:
    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(hex_color)
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def mix(a: str, b: str, weight_a: float) -> str:
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(ra[i] * weight_a + rb[i] * (1 - weight_a) for i in range(3)))


def _toward(color: str, target: str, against: str, minimum: float) -> str:
    """Mix ``color`` toward ``target`` until it reaches ``minimum`` contrast with ``against``."""
    if contrast(color, against) >= minimum:
        return color
    for step in range(1, 101):
        candidate = mix(target, color, step / 100)
        if contrast(candidate, against) >= minimum:
            return candidate
    return target


def _readable_on(background: str) -> str:
    return WHITE if contrast(WHITE, background) >= contrast(INK, background) else INK


def derive_palette(primary: Optional[str]) -> Tuple[Dict[str, str], List[str]]:
    """Return (palette, warnings). Warnings are Thai, user-facing, for the admin."""
    if primary is None or normalize_hex(primary) == DEFAULT_PRIMARY:
        return dict(DEFAULT_PALETTE), []
    primary = normalize_hex(primary)
    warnings: List[str] = []

    on_primary = _readable_on(primary)
    # Buttons and the launcher carry icons (non-text, 3:1); bubbles carry text (4.5:1).
    dark_text = on_primary == INK
    toward = WHITE if dark_text else "#000000"
    button = _toward(primary, toward, on_primary, NON_TEXT)
    bubble = _toward(primary, toward, on_primary, AA)
    if bubble != primary:
        warnings.append("ปรับสีฟองข้อความของลูกค้าให้เข้มขึ้นเล็กน้อยเพื่อให้ตัวอักษรอ่านง่าย (WCAG AA)")
    if button != primary:
        warnings.append("ปรับสีปุ่มให้ตัดกับไอคอนมากขึ้น")
    strong = mix("#000000", button, 0.18) if not dark_text else mix(WHITE, button, 0.22)
    # Accent text (links, header icons) sits on near-white glass.
    accent = _toward(mix("#000000", primary, 0.12), "#000000", "#f8fbfc", AA)

    palette = {
        "primary": button,
        "primary_strong": strong,
        "on_primary": on_primary,
        "accent_text": accent,
        "bubble_from": bubble,
        "bubble_to": mix("#000000", bubble, 0.06) if not dark_text else mix(WHITE, bubble, 0.08),
        "on_bubble": on_primary,
        "tint_1": mix(primary, WHITE, 0.30),
        "tint_2": mix(primary, WHITE, 0.22),
        "tint_3": mix(primary, WHITE, 0.16),
        "base_1": mix(primary, WHITE, 0.08),
        "base_2": mix(primary, WHITE, 0.06),
        "base_3": mix(primary, WHITE, 0.10),
        "frame_border": mix(primary, WHITE, 0.16),
        "frame_bg": mix(primary, WHITE, 0.04),
    }
    if contrast(palette["on_bubble"], palette["bubble_from"]) < AA:
        warnings.append("สีนี้ทำให้ตัวอักษรในฟองข้อความอ่านยาก กรุณาเลือกสีที่เข้มหรืออ่อนกว่านี้")
    return palette, warnings


# --------------------------------------------------------------------------
# Greeting
# --------------------------------------------------------------------------

def clean_text(value: Optional[str], limit: int, field: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ThemeValidationError(f"{field} ต้องเป็นข้อความ")
    value = re.sub(r"\s+", " ", unicodedata.normalize("NFC", value))
    # Drop remaining control/format characters except ZWJ/ZWNJ.
    value = "".join(
        ch for ch in value
        if ch in "\u200c\u200d" or not unicodedata.category(ch).startswith("C")
    )
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > limit:
        raise ThemeValidationError(f"{field} ยาวได้ไม่เกิน {limit} ตัวอักษร")
    return value or None


class GreetingText(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None


class ThemeUpdateRequest(BaseModel):
    primary_color: Optional[str] = None
    greeting: Dict[str, GreetingText] = Field(default_factory=dict)
    launcher_logo: bool = False

    @field_validator("greeting")
    @classmethod
    def _locales(cls, value: Dict[str, GreetingText]) -> Dict[str, GreetingText]:
        unknown = set(value) - set(LOCALES)
        if unknown:
            raise ValueError("รองรับคำทักทายเฉพาะภาษา th และ en")
        return value


class ThemePreviewRequest(BaseModel):
    primary_color: Optional[str] = None


def build_stored_theme(request: ThemeUpdateRequest, existing: Optional[dict]) -> dict:
    """Validate an admin update and return the JSON to persist (logo is kept)."""
    primary = normalize_hex(request.primary_color) if request.primary_color else None
    greeting: Dict[str, Dict[str, str]] = {}
    for locale, text in request.greeting.items():
        entry = {
            "title": clean_text(text.title, GREETING_TITLE_MAX, "หัวข้อคำทักทาย"),
            "subtitle": clean_text(text.subtitle, GREETING_SUBTITLE_MAX, "ข้อความรอง"),
        }
        entry = {k: v for k, v in entry.items() if v}
        if entry:
            greeting[locale] = entry
    stored: Dict[str, Any] = {"version": THEME_VERSION}
    if primary and primary != DEFAULT_PRIMARY:
        stored["primary"] = primary
    if greeting:
        stored["greeting"] = greeting
    logo = (existing or {}).get("logo")
    if logo:
        stored["logo"] = logo
    if request.launcher_logo and logo:
        stored["launcher_logo"] = True
    return stored


def public_theme(stored: Optional[dict]) -> dict:
    """Serialize only what a public widget needs. Never includes key data."""
    stored = stored or {}
    primary = stored.get("primary")
    try:
        palette, warnings = derive_palette(primary)
    except ThemeValidationError:
        primary, (palette, warnings) = None, derive_palette(None)
    logo = stored.get("logo")
    logo_url = f"/api/public/widget-logo/{logo}" if isinstance(logo, str) and LOGO_FILENAME.match(logo) else None
    greeting = {}
    for locale in LOCALES:
        entry = (stored.get("greeting") or {}).get(locale) or {}
        greeting[locale] = {k: entry[k] for k in ("title", "subtitle") if isinstance(entry.get(k), str)}
    return {
        "version": THEME_VERSION,
        "is_default": not primary and not logo_url and not any(greeting.values()),
        "primary_color": primary or DEFAULT_PRIMARY,
        "palette": palette,
        "logo_url": logo_url,
        "launcher_logo": bool(stored.get("launcher_logo") and logo_url),
        "greeting": greeting,
    }


def admin_theme(stored: Optional[dict]) -> dict:
    data = public_theme(stored)
    data["warnings"] = derive_palette(None if data["primary_color"] == DEFAULT_PRIMARY else data["primary_color"])[1]
    data["presets"] = PRESETS
    data["limits"] = {
        "greeting_title": GREETING_TITLE_MAX,
        "greeting_subtitle": GREETING_SUBTITLE_MAX,
        "logo_bytes": LOGO_MAX_BYTES,
        "logo_types": ["image/png", "image/jpeg", "image/webp"],
    }
    return data


# --------------------------------------------------------------------------
# Logo storage (same on-disk pattern as OKF bundles: server/data/<area>)
# --------------------------------------------------------------------------

def logo_root() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "widget_logos"


def _sniff(data: bytes) -> Optional[str]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def process_logo(data: bytes) -> bytes:
    """Validate an uploaded logo and re-encode it as a metadata-free PNG.

    SVG is refused on purpose: it can carry script and external references,
    and we have no sanitizer we trust on a public, cross-site asset.
    """
    if not data:
        raise ThemeValidationError("ไฟล์โลโก้ว่างเปล่า")
    if len(data) > LOGO_MAX_BYTES:
        raise ThemeValidationError("โลโก้ต้องมีขนาดไม่เกิน 512 KB")
    kind = _sniff(data)
    if kind is None:
        raise ThemeValidationError("รองรับเฉพาะไฟล์ PNG, JPG หรือ WebP (ไม่รับ SVG)")
    from PIL import Image, UnidentifiedImageError

    Image.MAX_IMAGE_PIXELS = LOGO_MAX_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if (probe.format or "").lower() not in {"png", "jpeg", "webp"}:
                raise ThemeValidationError("รองรับเฉพาะไฟล์ PNG, JPG หรือ WebP (ไม่รับ SVG)")
            probe.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if image.width * image.height > LOGO_MAX_PIXELS:
                raise ThemeValidationError("ภาพโลโก้ใหญ่เกินไป")
            image = image.convert("RGBA")
            image.thumbnail(LOGO_MAX_BOX)
            out = io.BytesIO()
            image.save(out, format="PNG", optimize=True)
            return out.getvalue()
    except ThemeValidationError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError) as exc:
        raise ThemeValidationError("อ่านไฟล์โลโก้ไม่ได้ กรุณาลองไฟล์อื่น") from exc


def save_logo(key_id: int, png: bytes, root: Optional[Path] = None) -> str:
    root = root or logo_root()
    root.mkdir(parents=True, exist_ok=True)
    name = f"k{int(key_id)}-{secrets.token_urlsafe(18)}.png"
    target = root / name
    tmp = root / (name + ".tmp")
    tmp.write_bytes(png)
    tmp.replace(target)
    return name


def logo_path(filename: str, root: Optional[Path] = None) -> Optional[Path]:
    if not isinstance(filename, str) or not LOGO_FILENAME.match(filename):
        return None
    root = (root or logo_root()).resolve()
    path = (root / filename).resolve()
    if path.parent != root or not path.is_file():
        return None
    return path


def delete_logo(filename: Optional[str], root: Optional[Path] = None) -> None:
    path = logo_path(filename or "", root)
    if path:
        path.unlink(missing_ok=True)
