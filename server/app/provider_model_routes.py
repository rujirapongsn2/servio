"""Authenticated administration of model capabilities and image task defaults."""
from fastapi import APIRouter, Depends, HTTPException

from app import database, provider_models as catalog
from app.auth import get_current_user

router = APIRouter(prefix="/api/admin", tags=["provider-models"])


def require_super_admin(current_user: str = Depends(get_current_user)) -> str:
    admin = database.get_admin_by_username(current_user)
    if not admin or not admin.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="Super admin access required")
    return current_user


def _call(operation, *args):
    try:
        return operation(*args)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/llm-providers/{provider_id}/registered-models",
            response_model=list[catalog.RegisteredModelResponse])
def list_models(provider_id: int, user: str = Depends(get_current_user)):
    return _call(catalog.list_models, provider_id)


@router.post("/llm-providers/{provider_id}/registered-models",
             response_model=catalog.RegisteredModelResponse)
def create_model(provider_id: int, data: catalog.RegisteredModelInput,
                 user: str = Depends(require_super_admin)):
    return _call(catalog.save_model, provider_id, data)


@router.put("/llm-providers/{provider_id}/registered-models/{catalog_id}",
            response_model=catalog.RegisteredModelResponse)
def update_model(provider_id: int, catalog_id: int, data: catalog.RegisteredModelInput,
                 user: str = Depends(require_super_admin)):
    return _call(catalog.save_model, provider_id, data, catalog_id)


@router.delete("/llm-providers/{provider_id}/registered-models/{catalog_id}")
def delete_model(provider_id: int, catalog_id: int, user: str = Depends(require_super_admin)):
    _call(catalog.delete_model, provider_id, catalog_id)
    return {"message": "Registered model deleted"}


@router.get("/image-model-defaults", response_model=catalog.ImageDefaultsResponse)
def get_defaults(user: str = Depends(get_current_user)):
    return _call(catalog.get_defaults_response)


@router.put("/image-model-defaults", response_model=catalog.ImageDefaultsInput)
def set_defaults(data: catalog.ImageDefaultsInput, user: str = Depends(require_super_admin)):
    return _call(catalog.set_defaults, data)
