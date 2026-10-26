"""Web Chat/Bubble theme: validation, palette contrast, logo safety and permissions.

No database or network: database calls are replaced with an in-memory store.
"""
import io
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

with patch("app.db_config.init_database"):
    from app import admin_routes, widget_theme, widget_theme_routes as routes
from app.auth import create_access_token

AA = 4.5


def png_bytes(size=(600, 200), color=(10, 120, 200, 255)):
    out = io.BytesIO()
    Image.new("RGBA", size, color).save(out, format="PNG")
    return out.getvalue()


# --------------------------------------------------------------------------
# Palette and validation
# --------------------------------------------------------------------------

def test_default_palette_is_the_current_servio_theme():
    palette, warnings = widget_theme.derive_palette(None)
    assert palette == widget_theme.DEFAULT_PALETTE
    assert warnings == []
    assert widget_theme.derive_palette("#2786C2")[0] == widget_theme.DEFAULT_PALETTE


@pytest.mark.parametrize("color", ["#ffff00", "#7a7a7a", "#00ff00", "#000000", "#ffffff",
                                    "#e0533d", "#4f46e5", "#0f8a5f", "#334155", "#f3903f", "#fdc70c", "#888"])
def test_derived_palette_always_meets_wcag(color):
    palette, _ = widget_theme.derive_palette(color)
    c = widget_theme.contrast
    assert c(palette["on_bubble"], palette["bubble_from"]) >= AA
    assert c(palette["on_bubble"], palette["bubble_to"]) >= AA - 0.3  # gradient end stays close
    assert c(palette["on_primary"], palette["primary"]) >= 3.0  # icons on buttons / launcher
    assert c(palette["accent_text"], "#f8fbfc") >= AA
    assert c(palette["accent_text"], "#ffffff") >= AA


def test_light_primary_gets_dark_text_and_a_warning_when_adjusted():
    palette, warnings = widget_theme.derive_palette("#ffff00")
    assert palette["on_primary"] == widget_theme.INK
    palette, warnings = widget_theme.derive_palette("#7a7a7a")
    assert warnings, "mid-grey cannot pass AA unadjusted, so the admin must be told"


@pytest.mark.parametrize("bad", ["2786c2", "#12345", "#gggggg", "red", "", "#1234567", "rgb(1,2,3)", None, 5])
def test_invalid_hex_is_rejected(bad):
    with pytest.raises(widget_theme.ThemeValidationError):
        widget_theme.normalize_hex(bad)


def test_greeting_is_cleaned_and_limited():
    req = widget_theme.ThemeUpdateRequest(primary_color="#0F8A5F", greeting={
        "th": {"title": "  สวัสดี\u0000ค่ะ\n\tร้านเรา  ", "subtitle": "<b>ยินดี</b>ต้อนรับ"},
        "en": {"title": "   ", "subtitle": None},
    })
    stored = widget_theme.build_stored_theme(req, None)
    assert stored["primary"] == "#0f8a5f"
    assert stored["greeting"]["th"]["title"] == "สวัสดีค่ะ ร้านเรา"
    # Markup is kept as text; React renders it escaped, nothing interprets it.
    assert stored["greeting"]["th"]["subtitle"] == "<b>ยินดี</b>ต้อนรับ"
    assert "en" not in stored["greeting"]
    too_long = widget_theme.ThemeUpdateRequest(greeting={"th": {"title": "ก" * 81}})
    with pytest.raises(widget_theme.ThemeValidationError):
        widget_theme.build_stored_theme(too_long, None)


def test_unknown_locale_is_rejected():
    with pytest.raises(ValueError):
        widget_theme.ThemeUpdateRequest(greeting={"fr": {"title": "Bonjour"}})


def test_public_theme_ignores_tampered_storage():
    data = widget_theme.public_theme({"primary": "javascript:alert(1)", "logo": "../../etc/passwd",
                                      "greeting": {"th": {"title": 5}}})
    assert data["primary_color"] == widget_theme.DEFAULT_PRIMARY
    assert data["logo_url"] is None
    assert data["greeting"]["th"] == {}


# --------------------------------------------------------------------------
# Logo
# --------------------------------------------------------------------------

def test_logo_is_reencoded_and_bounded():
    out = widget_theme.process_logo(png_bytes((1200, 400)))
    with Image.open(io.BytesIO(out)) as image:
        assert image.format == "PNG"
        assert image.width <= 480 and image.height <= 160


@pytest.mark.parametrize("payload", [
    b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
    b"GIF89a....",
    b"\x89PNG\r\n\x1a\n" + b"not really a png",
    b"",
])
def test_unsafe_or_fake_logos_are_rejected(payload):
    with pytest.raises(widget_theme.ThemeValidationError):
        widget_theme.process_logo(payload)


def test_oversized_logo_is_rejected():
    with pytest.raises(widget_theme.ThemeValidationError):
        widget_theme.process_logo(b"\x89PNG\r\n\x1a\n" + b"0" * (widget_theme.LOGO_MAX_BYTES + 1))


def test_logo_path_refuses_traversal(tmp_path):
    name = widget_theme.save_logo(7, png_bytes(), tmp_path)
    assert widget_theme.logo_path(name, tmp_path) is not None
    for bad in ["../x.png", "k7-..%2f.png", "k7-short.png", name.replace(".png", ".svg"), "/etc/passwd"]:
        assert widget_theme.logo_path(bad, tmp_path) is None


# --------------------------------------------------------------------------
# HTTP: permissions and public surface
# --------------------------------------------------------------------------

KEYS = {
    1: {"id": 1, "key": "sk_team1", "slug": "shop1", "team_agent_id": 1, "is_active": True, "name": "Shop"},
    2: {"id": 2, "key": "sk_team2", "slug": "shop2", "team_agent_id": 2, "is_active": True, "name": "Other"},
    3: {"id": 3, "key": "sk_off", "slug": "off", "team_agent_id": 1, "is_active": False, "name": "Off"},
}


@pytest.fixture
def client(monkeypatch, tmp_path):
    themes = {}
    roles = {("owner", 1): "admin", ("viewer", 1): "viewer", ("other", 2): "admin"}
    db = routes.database
    monkeypatch.setattr(db, "get_default_team_id", lambda: 1)
    monkeypatch.setattr(db, "get_admin_by_username", lambda u: {"is_super_admin": u == "super"})
    monkeypatch.setattr(db, "get_team_access_role", lambda u, t: roles.get((u, t)))
    monkeypatch.setattr(db, "get_api_key_by_id", lambda i: KEYS.get(i))
    monkeypatch.setattr(db, "get_api_key_theme", lambda i: dict(themes[i]) if themes.get(i) else None)
    monkeypatch.setattr(db, "set_api_key_theme", lambda i, t: themes.__setitem__(i, t) or True)

    def public_source(api_key=None, slug=None):
        for key in KEYS.values():
            if (api_key and key["key"] == api_key) or (slug and key["slug"] == slug):
                return {"theme": themes.get(key["id"])} if key["is_active"] else None
        return None
    monkeypatch.setattr(db, "get_public_widget_theme_source", public_source)
    monkeypatch.setattr(widget_theme, "logo_root", lambda: tmp_path)

    app = FastAPI()
    app.include_router(routes.admin_router)
    app.include_router(routes.public_router)
    test_client = TestClient(app)
    test_client.themes = themes
    return test_client


def auth(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': user})}"}


def test_theme_write_requires_team_admin(client):
    body = {"primary_color": "#0f8a5f", "greeting": {"th": {"title": "สวัสดีค่ะ"}}}
    assert client.put("/api/admin/api-keys/1/theme", json=body).status_code in (401, 403)
    assert client.put("/api/admin/api-keys/1/theme", json=body, headers=auth("viewer")).status_code == 403
    assert client.put("/api/admin/api-keys/1/theme", json=body, headers=auth("other")).status_code == 403
    assert client.delete("/api/admin/api-keys/1/theme", headers=auth("viewer")).status_code == 403
    assert client.post("/api/admin/api-keys/1/theme/logo", headers=auth("viewer"),
                       files={"file": ("l.png", png_bytes(), "image/png")}).status_code == 403
    assert 1 not in client.themes
    ok = client.put("/api/admin/api-keys/1/theme", json=body, headers=auth("owner"))
    assert ok.status_code == 200
    assert ok.json()["primary_color"] == "#0f8a5f"
    assert client.get("/api/admin/api-keys/1/theme", headers=auth("viewer")).status_code == 200
    assert client.get("/api/admin/api-keys/2/theme", headers=auth("viewer")).status_code == 403
    assert client.get("/api/admin/api-keys/99/theme", headers=auth("owner")).status_code == 404


def test_invalid_theme_input_returns_422(client):
    for body in ({"primary_color": "blue"}, {"greeting": {"th": {"title": "x" * 200}}},
                 {"greeting": {"de": {"title": "Hallo"}}}):
        assert client.put("/api/admin/api-keys/1/theme", json=body, headers=auth("owner")).status_code == 422


def test_logo_upload_replace_and_remove(client, tmp_path):
    first = client.post("/api/admin/api-keys/1/theme/logo", headers=auth("owner"),
                        files={"file": ("l.png", png_bytes(), "image/png")})
    assert first.status_code == 200
    url = first.json()["logo_url"]
    assert url.startswith("/api/public/widget-logo/k1-")
    served = client.get(url)
    assert served.status_code == 200 and served.headers["content-type"] == "image/png"
    assert served.headers["x-content-type-options"] == "nosniff"
    svg = client.post("/api/admin/api-keys/1/theme/logo", headers=auth("owner"),
                      files={"file": ("l.svg", b"<svg onload='x'/>", "image/svg+xml")})
    assert svg.status_code == 422
    second = client.post("/api/admin/api-keys/1/theme/logo", headers=auth("owner"),
                         files={"file": ("l.png", png_bytes(color=(1, 2, 3, 255)), "image/png")})
    assert client.get(url).status_code == 404, "the replaced logo file is deleted"
    assert client.delete("/api/admin/api-keys/1/theme/logo", headers=auth("owner")).json()["logo_url"] is None
    assert client.get(second.json()["logo_url"]).status_code == 404
    assert list(tmp_path.iterdir()) == []


def test_public_theme_returns_theme_fields_only(client):
    client.put("/api/admin/api-keys/1/theme", headers=auth("owner"),
               json={"primary_color": "#e0533d", "greeting": {"th": {"title": "ยินดีต้อนรับ"}}})
    by_key = client.get("/api/public/widget-theme", params={"api_key": "sk_team1"})
    by_slug = client.get("/api/public/widget-theme", params={"slug": "shop1"})
    assert by_key.status_code == by_slug.status_code == 200
    assert by_key.json() == by_slug.json()
    data = by_key.json()
    assert set(data) == {"version", "is_default", "primary_color", "palette", "logo_url", "launcher_logo", "greeting"}
    assert "sk_team1" not in by_key.text and "Shop" not in by_key.text
    assert data["greeting"]["th"]["title"] == "ยินดีต้อนรับ"
    assert by_key.headers["access-control-allow-origin"] == "*"
    assert client.get("/api/public/widget-theme", params={"api_key": "sk_off"}).status_code == 404
    assert client.get("/api/public/widget-theme", params={"api_key": "nope"}).status_code == 404
    assert client.get("/api/public/widget-theme").status_code == 404
    default = client.get("/api/public/widget-theme", params={"slug": "shop2"}).json()
    assert default["is_default"] and default["palette"] == widget_theme.DEFAULT_PALETTE


def test_reset_restores_default_and_deletes_logo(client, tmp_path):
    client.post("/api/admin/api-keys/1/theme/logo", headers=auth("owner"),
                files={"file": ("l.png", png_bytes(), "image/png")})
    reset = client.delete("/api/admin/api-keys/1/theme", headers=auth("owner"))
    assert reset.status_code == 200 and reset.json()["is_default"]
    assert list(tmp_path.iterdir()) == []


def test_preview_endpoint_needs_login_and_validates(client):
    assert client.post("/api/admin/widget-theme/preview", json={"primary_color": "#ffff00"}).status_code in (401, 403)
    res = client.post("/api/admin/widget-theme/preview", json={"primary_color": "#ffff00"}, headers=auth("viewer"))
    assert res.status_code == 200 and res.json()["palette"]["on_primary"] == widget_theme.INK
    assert client.post("/api/admin/widget-theme/preview", json={"primary_color": "x"},
                       headers=auth("viewer")).status_code == 422
