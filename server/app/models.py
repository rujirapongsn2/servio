from typing import List, Optional, Dict, Any
from pydantic import BaseModel


# Authentication models
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# Agent models
class AgentTool(BaseModel):
    id: int
    name: str
    type: str
    config: Optional[str] = None


class AgentHandoff(BaseModel):
    id: int
    name: str


class AgentLLMProvider(BaseModel):
    id: int
    name: str


class AgentResponse(BaseModel):
    id: int
    name: str
    instructions: str
    model: str
    llm_provider: Optional[AgentLLMProvider] = None
    is_starting_agent: bool
    tools: List[AgentTool]
    handoffs: List[AgentHandoff]
    created_at: str
    updated_at: str


class CreateAgentRequest(BaseModel):
    name: str
    instructions: str
    model: str = "gpt-4o-mini"
    llm_provider_id: Optional[int] = None
    tool_ids: List[int] = []
    handoff_agent_ids: List[int] = []
    is_starting_agent: bool = False


class UpdateAgentRequest(BaseModel):
    name: str
    instructions: str
    model: str
    llm_provider_id: Optional[int] = None
    tool_ids: List[int]
    handoff_agent_ids: List[int]
    is_starting_agent: bool = False


class TestAgentRequest(BaseModel):
    message: str
    class ForceTool(BaseModel):
        name: str
        arguments: Dict[str, Any] = {}

    force_tool: Optional[ForceTool] = None


class TestAgentResponse(BaseModel):
    response: str
    tool_calls: List[Dict[str, Any]] = []
    citations: List[str] = []
    tool_outputs: List[Dict[str, Any]] = []


# Tool models
class ToolResponse(BaseModel):
    id: int
    name: str
    type: str
    config: Optional[str] = None
    icon: str = "Wrench"
    created_at: str


class CreateCustomToolRequest(BaseModel):
    name: str
    config: Dict[str, Any]
    icon: str = "Wrench"


class UpdateCustomToolRequest(BaseModel):
    name: str
    config: Dict[str, Any]
    icon: str = "Wrench"


# Prompt optimizer models
class OptimizePromptRequest(BaseModel):
    instructions: str
    agent_name: str = ""
    model: str = ""
    llm_provider_id: Optional[int] = None


class OptimizePromptResponse(BaseModel):
    optimized_instructions: str


# Generic response
class MessageResponse(BaseModel):
    message: str
    success: bool = True


# System info
class SystemInfoResponse(BaseModel):
    backend_url: str
    frontend_origin: str | None = None
    server_time: str
    python_version: str
    mcp_enabled: bool
    openai_api_key_set: bool
    agents_count: int
    tools_count: int


# File Store models
class FileStoreResponse(BaseModel):
    id: int
    name: str
    gemini_store_id: str
    display_name: Optional[str]
    file_count: int
    created_at: str


class FileStoreFileResponse(BaseModel):
    id: int
    file_store_id: int
    filename: str
    original_filename: str
    file_size: int
    uploaded_at: str


class CreateFileStoreRequest(BaseModel):
    display_name: str
    create_tool: bool = True


class TestFileStoreRequest(BaseModel):
    query: str



class TestFileStoreResponse(BaseModel):
    response: str
    grounding_sources: List[str] = []
    metadata: Optional[Dict[str, Any]] = None
    response_time: float


# VoIP Provider models
class VoIPProviderResponse(BaseModel):
    id: int
    name: str
    type: str
    config: Optional[Dict[str, Any]] = None
    is_active: bool
    created_at: str
    updated_at: str


class CreateVoIPProviderRequest(BaseModel):
    name: str
    type: str = "twilio"
    config: Dict[str, Any]
    is_active: bool = True


class UpdateVoIPProviderRequest(BaseModel):
    name: str
    type: str
    config: Dict[str, Any]
    is_active: bool


class ChannelConfigResponse(BaseModel):
    id: int
    type: str
    name: str
    config: Dict[str, Any] = {}
    is_active: bool
    created_at: str
    updated_at: str


class UpdateChannelConfigRequest(BaseModel):
    name: str
    config: Dict[str, Any]
    is_active: bool = False


# API Key models
class ApiKeyResponse(BaseModel):
    id: int
    name: str
    key: str
    is_active: bool
    usage_count: int
    last_used_at: Optional[str] = None
    expires_at: Optional[str] = None
    created_by: Optional[str] = None
    allowed_domains: Optional[List[str]] = None
    voice_response_enabled: bool = True
    slug: Optional[str] = None
    created_at: str
    updated_at: str


class CreateApiKeyRequest(BaseModel):
    name: str
    expires_days: Optional[int] = None
    allowed_domains: Optional[List[str]] = None  # Number of days until expiration (None = never expires)
    voice_response_enabled: bool = True  # Enable TTS voice responses


# LLM Provider models
class LLMProviderResponse(BaseModel):
    id: int
    name: str
    base_url: str
    api_key: str
    is_default: bool
    created_at: str
    updated_at: str


class CreateLLMProviderRequest(BaseModel):
    name: str
    base_url: str
    api_key: str
    is_default: bool = False


class UpdateLLMProviderRequest(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    is_default: Optional[bool] = None


class LLMModelResponse(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str

class UpdateApiKeyRequest(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    expires_at: Optional[str] = None
    allowed_domains: Optional[List[str]] = None
    voice_response_enabled: Optional[bool] = None


# Intent Rule models
class IntentRuleResponse(BaseModel):
    id: int
    group: str
    color: str
    keywords: List[str]
    description: Optional[str] = None


class CreateIntentRuleRequest(BaseModel):
    group: str
    keywords: List[str]
    color: str
    description: Optional[str] = None


class UpdateIntentRuleRequest(BaseModel):
    group: Optional[str] = None
    color: Optional[str] = None
    keywords: Optional[List[str]] = None


class IntentGroupResponse(BaseModel):
    group: str
    color: str
    description: str
    default_keywords: List[str]

