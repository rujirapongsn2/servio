"""HTTP API for the Web Chat / Bubble theme.

Public (no auth, cross-site safe): read a theme by widget key or slug, fetch a logo.
Admin: read/update/reset a key's theme and upload/remove its logo. Writes need
the ``admin`` role on the key's Team Agent (legacy keys resolve to the default team).
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app import database, widget_theme
from app.auth import get_current_user

admin_router = APIRouter(prefix="/api/admin", tags=["widget-theme"])
public_router = APIRouter(prefix="/api/public", tags=["public"])

_PUBLIC_HEADERS = {
    "Cache-Control": "public, max-age=60",
    "X-Content-Type-Options": "nosniff",
    "Access-Control-Allow-Origin": "*",
}


def _key_or_404(key_id: int) -> dict:
    key = database.get_api_key_by_id(key_id)
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return key


def _authorize(current_user: str, key: dict, min_role: str) -> None:
    from app.admin_routes import _require_resolved_team_access

    _require_resolved_team_access(current_user, key.get("team_agent_id"), min_role)


def _invalid(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


# ----------------------------------------------------------------------------
# Public
# ----------------------------------------------------------------------------

@public_router.get("/widget-theme")
async def get_public_widget_theme(
    response: Response,
    api_key: Optional[str] = Query(default=None, max_length=255),
    slug: Optional[str] = Query(default=None, max_length=50),
):
    """Theme for an active widget. Returns theme fields only, never key data."""
    source = database.get_public_widget_theme_source(api_key=api_key, slug=slug)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Widget not found")
    response.headers.update(_PUBLIC_HEADERS)
    return widget_theme.public_theme(source["theme"])


@public_router.get("/widget-logo/{filename}")
async def get_public_widget_logo(filename: str):
    path = widget_theme.logo_path(filename)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Logo not found")
    data = await run_in_threadpool(path.read_bytes)
    return Response(content=data, media_type="image/png", headers={
        # Each upload gets a new random name, so the URL is immutable.
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Cross-Origin-Resource-Policy": "cross-origin",
    })


# ----------------------------------------------------------------------------
# Admin
# ----------------------------------------------------------------------------

@admin_router.post("/widget-theme/preview")
async def preview_widget_theme(
    request: widget_theme.ThemePreviewRequest,
    current_user: str = Depends(get_current_user),
):
    """Derive the palette for a draft colour so the admin preview matches the widget."""
    try:
        palette, warnings = widget_theme.derive_palette(request.primary_color or None)
    except widget_theme.ThemeValidationError as exc:
        raise _invalid(exc)
    return {"palette": palette, "warnings": warnings}


@admin_router.get("/api-keys/{key_id}/theme")
async def get_api_key_theme(key_id: int, current_user: str = Depends(get_current_user)):
    key = _key_or_404(key_id)
    _authorize(current_user, key, "viewer")
    return widget_theme.admin_theme(database.get_api_key_theme(key_id))


@admin_router.put("/api-keys/{key_id}/theme")
async def update_api_key_theme(
    key_id: int,
    request: widget_theme.ThemeUpdateRequest,
    current_user: str = Depends(get_current_user),
):
    key = _key_or_404(key_id)
    _authorize(current_user, key, "admin")
    try:
        stored = widget_theme.build_stored_theme(request, database.get_api_key_theme(key_id))
    except widget_theme.ThemeValidationError as exc:
        raise _invalid(exc)
    database.set_api_key_theme(key_id, stored)
    return widget_theme.admin_theme(stored)


@admin_router.delete("/api-keys/{key_id}/theme")
async def reset_api_key_theme(key_id: int, current_user: str = Depends(get_current_user)):
    """Restore the default Servio theme and remove the uploaded logo."""
    key = _key_or_404(key_id)
    _authorize(current_user, key, "admin")
    previous = database.get_api_key_theme(key_id) or {}
    database.set_api_key_theme(key_id, None)
    widget_theme.delete_logo(previous.get("logo"))
    return widget_theme.admin_theme(None)


@admin_router.post("/api-keys/{key_id}/theme/logo")
async def upload_api_key_logo(
    key_id: int,
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
):
    key = _key_or_404(key_id)
    _authorize(current_user, key, "admin")
    data = await file.read(widget_theme.LOGO_MAX_BYTES + 1)
    try:
        png = await run_in_threadpool(widget_theme.process_logo, data)
    except widget_theme.ThemeValidationError as exc:
        raise _invalid(exc)
    stored = database.get_api_key_theme(key_id) or {"version": widget_theme.THEME_VERSION}
    previous = stored.get("logo")
    stored["logo"] = await run_in_threadpool(widget_theme.save_logo, key_id, png)
    database.set_api_key_theme(key_id, stored)
    widget_theme.delete_logo(previous)
    return widget_theme.admin_theme(stored)


@admin_router.delete("/api-keys/{key_id}/theme/logo")
async def delete_api_key_logo(key_id: int, current_user: str = Depends(get_current_user)):
    key = _key_or_404(key_id)
    _authorize(current_user, key, "admin")
    stored = database.get_api_key_theme(key_id) or {}
    previous = stored.pop("logo", None)
    stored.pop("launcher_logo", None)
    database.set_api_key_theme(key_id, stored or None)
    widget_theme.delete_logo(previous)
    return widget_theme.admin_theme(stored)
