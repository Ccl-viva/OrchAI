from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LLMSettingsInput(BaseModel):
    provider: str = Field(default="openai")
    model: str | None = None
    api_key: str | None = None


class LLMSettingsView(BaseModel):
    provider: str = "openai"
    model: str | None = None
    enabled: bool = False
    source: str = "rules"


class TaskCreateRequest(BaseModel):
    goal: str = Field(..., min_length=2, description="User goal in natural language")
    llm: LLMSettingsInput | None = None


class ExecuteRequest(BaseModel):
    workflow_id: str
    confirm_value: str | None = None


class NodeChatRequest(BaseModel):
    workflow_id: str
    node_id: str
    message: str = Field(..., min_length=1, description="Natural language instruction to modify node behavior")


class Preview(BaseModel):
    type: str
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)


class PendingConfirmation(BaseModel):
    message: str
    options: list[str]


class NodeView(BaseModel):
    id: str
    order_index: int
    type: str
    status: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class WorkflowView(BaseModel):
    id: str
    goal: str
    status: str
    source_type: str = "excel"
    llm_settings: LLMSettingsView = Field(default_factory=LLMSettingsView)
    parsed_goal: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)
    adapter_state: dict[str, Any] = Field(default_factory=dict)
    nodes: list[NodeView] = Field(default_factory=list)
    created_at: str


class TaskCreateResponse(BaseModel):
    workflow_id: str
    workflow: WorkflowView


class UploadResponse(BaseModel):
    workflow_id: str
    file_name: str
    workflow: WorkflowView


class ExecuteEvent(BaseModel):
    node_id: str
    node_type: str
    status: str
    message: str
    preview: Preview | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ExecuteResponse(BaseModel):
    workflow: WorkflowView
    events: list[ExecuteEvent] = Field(default_factory=list)
    pending_confirmation: PendingConfirmation | None = None


class NodeChatResponse(BaseModel):
    workflow: WorkflowView
    node_id: str
    reply: str
    applied_updates: dict[str, Any] = Field(default_factory=dict)
