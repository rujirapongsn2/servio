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
    is_super_admin: bool = False
    is_operator_only: bool = False
    is_viewer_only: bool = False
    can_manage_users: bool = False


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
    visibility: Optional[str] = None
    owner_team_agent_id: Optional[int] = None
    created_at: str
    updated_at: Optional[str] = None


class CreateCustomToolRequest(BaseModel):
    name: str
    config: Dict[str, Any]
    icon: str = "Wrench"
    visibility: Optional[str] = None  # "team" or "global", defaults to "team"
    assign_agent_id: Optional[int] = None


class UpdateCustomToolRequest(BaseModel):
    name: str
    config: Dict[str, Any]
    icon: str = "Wrench"
    visibility: Optional[str] = None  # "team" or "global"


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
    assign_agent_id: Optional[int] = None


class FileUploadJobStartResponse(BaseModel):
    job_id: str
    status: str
    message: str


class FileUploadJobResponse(BaseModel):
    job_id: str
    file_store_id: int
    filename: str
    status: str
    progress: int
    stage: str
    error: Optional[str] = None
    uploaded_at: Optional[str] = None
    completed_at: Optional[str] = None


class TestFileStoreRequest(BaseModel):
    query: str



class TestFileStoreResponse(BaseModel):
    response: str
    grounding_sources: List[str] = []
    metadata: Optional[Dict[str, Any]] = None
    response_time: float


# OKF Knowledge models
class OKFBundleResponse(BaseModel):
    id: int
    name: str
    display_name: str
    okf_version: Optional[str] = None
    status: str
    concept_count: int
    link_count: int
    validation_summary: Dict[str, Any] = {}
    visibility: Optional[str] = None
    owner_team_agent_id: Optional[int] = None
    owner_team_name: Optional[str] = None
    created_by_username: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    tool_id: Optional[int] = None


class OKFImportJobResponse(BaseModel):
    job_id: str
    status: str
    message: str
    bundle: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    warnings: List[str] = []
    created_at: str
    updated_at: str


class OKFConceptResponse(BaseModel):
    id: int
    bundle_id: int
    concept_id: str
    file_path: str
    type: str
    title: Optional[str] = None
    description: Optional[str] = None
    resource: Optional[str] = None
    tags: List[str] = []
    timestamp: Optional[str] = None
    updated_at: Optional[str] = None
    markdown: Optional[str] = None
    frontmatter: Optional[Dict[str, Any]] = None
    body: Optional[str] = None
    links: List[Dict[str, Any]] = []


class TestOKFBundleRequest(BaseModel):
    query: str


class TestOKFBundleResponse(BaseModel):
    response: str
    concepts: List[Dict[str, Any]] = []
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
    team_agent_id: Optional[int] = None
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
    team_agent_id: Optional[int] = None
    channel_type: Optional[str] = None
    created_at: str
    updated_at: str


class CreateApiKeyRequest(BaseModel):
    name: str
    expires_days: Optional[int] = None
    allowed_domains: Optional[List[str]] = None  # Number of days until expiration (None = never expires)
    voice_response_enabled: bool = True  # Enable TTS voice responses
    team_agent_id: Optional[int] = None
    channel_type: Optional[str] = "web_widget"


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
    team_agent_id: Optional[int] = None
    channel_type: Optional[str] = None


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


# Team Agent models
class TeamAgentMemberResponse(BaseModel):
    agent_id: int
    agent_name: str
    role: str  # starting, member
    sort_order: int


class TeamAgentResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    status: str
    member_count: int = 0
    members: List[TeamAgentMemberResponse] = []
    created_at: str
    updated_at: str


class TeamAgentListResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    status: str
    member_count: int = 0
    starting_agent_name: Optional[str] = None
    created_at: str
    updated_at: str


class CreateTeamAgentRequest(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None


class UpdateTeamAgentRequest(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None  # active, archived


class UpdateTeamMembersRequest(BaseModel):
    member_agent_ids: List[int]
    starting_agent_id: Optional[int] = None


# User Management models
class AdminUserResponse(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    is_active: bool = True
    is_super_admin: bool = False
    teams: List[dict] = []  # [{team_id, team_name, role}]
    created_at: str


class CreateAdminUserRequest(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    is_super_admin: bool = False


class UpdateAdminUserRequest(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    display_name: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None
    is_super_admin: Optional[bool] = None


class TeamUserResponse(BaseModel):
    admin_id: int
    username: str
    display_name: Optional[str] = None
    role: str  # owner, admin, operator, viewer


class UpdateTeamUsersRequest(BaseModel):
    users: List[dict]  # [{admin_id, role}] — role can be null to remove
