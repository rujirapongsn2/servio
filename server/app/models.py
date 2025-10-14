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


class TestAgentResponse(BaseModel):
    response: str
    tool_calls: List[Dict[str, Any]] = []


# Tool models
class ToolResponse(BaseModel):
    id: int
    name: str
    type: str
    config: Optional[str] = None
    created_at: str


class CreateCustomToolRequest(BaseModel):
    name: str
    config: Dict[str, Any]


class UpdateCustomToolRequest(BaseModel):
    name: str
    config: Dict[str, Any]


# Generic response
class MessageResponse(BaseModel):
    message: str
    success: bool = True
