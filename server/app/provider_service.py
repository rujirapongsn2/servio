from sqlalchemy.orm import Session
from app.orm_models import LLMProvider
from app.models import CreateLLMProviderRequest, UpdateLLMProviderRequest
from typing import List, Optional, Any
from datetime import datetime
from openai import AsyncOpenAI
import logging

logger = logging.getLogger(__name__)

def create_provider(db: Session, request: CreateLLMProviderRequest) -> LLMProvider:
    """Create a new LLM provider"""
    # If setting as default, unset others
    if request.is_default:
        db.query(LLMProvider).update({"is_default": False})
    
    provider = LLMProvider(
        name=request.name,
        base_url=request.base_url,
        api_key=request.api_key,
        is_default=request.is_default
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return provider

def get_all_providers(db: Session) -> List[LLMProvider]:
    """Get all LLM providers"""
    return db.query(LLMProvider).all()

def get_provider_by_id(db: Session, provider_id: int) -> Optional[LLMProvider]:
    """Get provider by ID"""
    return db.query(LLMProvider).filter(LLMProvider.id == provider_id).first()

def get_default_provider(db: Session) -> Optional[LLMProvider]:
    """Get the default provider"""
    return db.query(LLMProvider).filter(LLMProvider.is_default == True).first()

def update_provider(db: Session, provider_id: int, request: UpdateLLMProviderRequest) -> Optional[LLMProvider]:
    """Update a provider"""
    provider = get_provider_by_id(db, provider_id)
    if not provider:
        return None

    # Handle default flag logic
    if request.is_default is True:
        db.query(LLMProvider).filter(LLMProvider.id != provider_id).update({"is_default": False})

    if request.name:
        provider.name = request.name
    if request.base_url:
        provider.base_url = request.base_url
    if request.api_key:
        provider.api_key = request.api_key
    if request.is_default is not None:
        provider.is_default = request.is_default

    provider.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(provider)
    return provider

def delete_provider(db: Session, provider_id: int) -> bool:
    """Delete a provider"""
    provider = get_provider_by_id(db, provider_id)
    if not provider:
        return False
    db.delete(provider)
    db.commit()
    return True

async def get_available_models(provider: LLMProvider) -> List[Any]:
    """Fetch available models from the provider's API"""
    client = AsyncOpenAI(
        base_url=provider.base_url,
        api_key=provider.api_key
    )
    try:
        response = await client.models.list()
        return response.data
    except Exception as e:
        logger.error(f"Failed to fetch models from {provider.name}: {e}")
        raise Exception(f"Failed to fetch models: {str(e)}")
