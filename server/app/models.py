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


class AgentResponse(BaseModel):
    id: int
    name: str
    instructions: str
    model: str
    is_starting_agent: bool
    tools: List[AgentTool]
    handoffs: List[AgentHandoff]
    created_at: str
    updated_at: str


class CreateAgentRequest(BaseModel):
    name: str
    instructions: str
    model: str = "gpt-4o-mini"
    tool_ids: List[int] = []
    handoff_agent_ids: List[int] = []
    is_starting_agent: bool = False


class UpdateAgentRequest(BaseModel):
    name: str
    instructions: str
    model: str
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
