"""Provider model registry and explicit defaults for image processing."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError

from app.db_config import get_db
from app.orm_models import ImageModelDefault, LLMProvider, ProviderModel

ImagePurpose = Literal["image_ocr", "image_qa"]
PURPOSES = ("image_ocr", "image_qa")


class RegisteredModelInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    model_id: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    capabilities: list[Literal["text", "vision"]] = Field(min_length=1, max_length=2)
    enabled: bool = True

    @field_validator("capabilities")
    @classmethod
    def unique_capabilities(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Capabilities must be unique")
        return value


class RegisteredModelResponse(RegisteredModelInput):
    id: int
    provider_id: int


class ImageDefaultsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image_ocr: int | None = Field(ge=1)
    image_qa: int | None = Field(ge=1)


def _serialize(model: ProviderModel) -> dict:
    return {"id": model.id, "provider_id": model.provider_id,
            "model_id": model.model_id, "display_name": model.display_name,
            "capabilities": model.capabilities, "enabled": model.enabled}


def _provider(db, provider_id):
    provider = db.get(LLMProvider, provider_id)
    if provider is None:
        raise LookupError("Provider not found")
    return provider


def list_models(provider_id: int) -> list[dict]:
    with get_db() as db:
        _provider(db, provider_id)
        return [_serialize(row) for row in db.query(ProviderModel).filter_by(
            provider_id=provider_id).order_by(ProviderModel.id).all()]


def save_model(provider_id: int, data: RegisteredModelInput, catalog_id: int | None = None) -> dict:
    try:
        with get_db() as db:
            _provider(db, provider_id)
            if catalog_id is None:
                row = ProviderModel(provider_id=provider_id)
                db.add(row)
            else:
                row = db.get(ProviderModel, catalog_id)
                if row is None or row.provider_id != provider_id:
                    raise LookupError("Registered model not found")
            for key, value in data.model_dump().items():
                setattr(row, key, value)
            if catalog_id is not None and (not row.enabled or "vision" not in row.capabilities):
                db.query(ImageModelDefault).filter_by(model_catalog_id=row.id).delete()
            db.flush()
            return _serialize(row)
    except IntegrityError as exc:
        raise ValueError("Model ID is already registered for this provider") from exc


def delete_model(provider_id: int, catalog_id: int) -> None:
    with get_db() as db:
        _provider(db, provider_id)
        row = db.get(ProviderModel, catalog_id)
        if row is None or row.provider_id != provider_id:
            raise LookupError("Registered model not found")
        db.delete(row)


def get_defaults() -> dict:
    with get_db() as db:
        rows = db.query(ImageModelDefault).join(ProviderModel).join(LLMProvider).filter(
            ProviderModel.enabled.is_(True)).all()
        result = dict.fromkeys(PURPOSES)
        for row in rows:
            if "vision" in row.model.capabilities:
                result[row.purpose] = row.model_catalog_id
        return result


def set_defaults(data: ImageDefaultsInput) -> dict:
    with get_db() as db:
        values = data.model_dump()
        # Validate both selections before mutating either assignment.
        for catalog_id in values.values():
            if catalog_id is None:
                continue
            row = db.get(ProviderModel, catalog_id)
            if row is None or db.get(LLMProvider, row.provider_id) is None:
                raise ValueError("Selected model does not exist")
            if not row.enabled or "vision" not in row.capabilities:
                raise ValueError("Image tasks require an enabled vision model")
        for purpose, catalog_id in values.items():
            row = db.get(ImageModelDefault, purpose)
            if catalog_id is None:
                if row is not None:
                    db.delete(row)
            elif row is None:
                db.add(ImageModelDefault(purpose=purpose, model_catalog_id=catalog_id))
            else:
                row.model_catalog_id = catalog_id
        return values


def get_task_model(purpose: str) -> dict | None:
    """Resolve credentials only for internal execution; never return to the UI."""
    if purpose not in PURPOSES:
        raise ValueError("Unknown image model purpose")
    with get_db() as db:
        selected = db.query(ProviderModel, LLMProvider).join(
            ImageModelDefault, ImageModelDefault.model_catalog_id == ProviderModel.id
        ).join(LLMProvider, ProviderModel.provider_id == LLMProvider.id).filter(
            ImageModelDefault.purpose == purpose, ProviderModel.enabled.is_(True)
        ).first()
        if selected is None:
            return None
        model, provider = selected
        if "vision" not in model.capabilities:
            return None
        return {"model_id": model.model_id, "base_url": provider.base_url,
                "api_key": provider.api_key, "catalog_id": model.id}
