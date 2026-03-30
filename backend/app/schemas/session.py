from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class TurnState(StrEnum):
    RUNNING = "running"
    WAITING_FOR_FRONTEND = "waiting_for_frontend"
    COMPLETED = "completed"
    FAILED = "failed"


class FrontendToolName(StrEnum):
    RUN_DIAGNOSTICS = "run_diagnostics"


class SessionEventName(StrEnum):
    ASSISTANT_MESSAGE_STARTED = "assistant.message_started"
    ASSISTANT_MESSAGE_RESET = "assistant.message_reset"
    ASSISTANT_DELTA = "assistant.delta"
    ASSISTANT_REASONING_DELTA = "assistant.reasoning_delta"
    ASSISTANT_TOOL_CALLS_UPDATED = "assistant.tool_calls_updated"
    ASSISTANT_MESSAGE_COMPLETED = "assistant.message_completed"
    WORKSPACE_PATCH = "workspace.patch"
    FRONTEND_TOOL_CALL = "frontend.tool_call"
    TURN_COMPLETED = "turn.completed"
    TURN_FAILED = "turn.failed"
    PUBLISH_STATUS_CHANGED = "publish.status_changed"
    PUBLISH_LOG = "publish.log"
    PUBLISH_COMPLETED = "publish.completed"
    PUBLISH_FAILED = "publish.failed"


class WorkspacePatchOpName(StrEnum):
    UPSERT = "upsert"
    DELETE = "delete"


class CompileStatus(StrEnum):
    SUCCESS = "success"
    COMPILE_ERROR = "compile_error"
    RUNTIME_ERROR = "runtime_error"
    TIMEOUT = "timeout"


class CompileResult(StrEnum):
    DONE = "done"
    TIMEOUT = "timeout"


class PublishStatus(StrEnum):
    IDLE = "idle"
    QUEUED = "queued"
    BUILDING = "building"
    SUCCESS = "success"
    FAILED = "failed"


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    role: MessageRole
    content: str
    reasoning_content: str | None = None
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class DisplayMessage(BaseModel):
    id: str
    role: Literal["assistant", "user"]
    content: str
    reasoning_content: str | None = None
    tool_calls: list[str] = Field(default_factory=list)
    is_in_progress: bool = False


class WorkspacePatchOp(BaseModel):
    op: WorkspacePatchOpName
    path: str
    code: str | None = None


class WorkspacePatch(BaseModel):
    ops: list[WorkspacePatchOp]


class CompileFeedback(BaseModel):
    status: CompileStatus
    result: CompileResult
    server_logs: list[str] = Field(default_factory=list)
    client_logs: list[Any] = Field(default_factory=list)
    error_summary: str | None = None


class PendingFrontendTool(BaseModel):
    tool_name: FrontendToolName
    tool_call_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class Turn(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_message: str
    state: TurnState = TurnState.RUNNING
    streaming_message_id: str | None = None
    streaming_tool_calls: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    retries_for_missing_tool: int = 0


class Session(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    title: str = "New Project"
    messages: list[ChatMessage]
    workspace_files: dict[str, str]
    active_turn: Turn | None = None
    last_compile_feedback: CompileFeedback | None = None
    pending_frontend_tool: PendingFrontendTool | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SessionPublishState(BaseModel):
    session_id: str
    status: PublishStatus = PublishStatus.IDLE
    job_id: str | None = None
    current_version: str | None = None
    public_url: str | None = None
    build_log: str = ""
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class PublishSessionResponse(BaseModel):
    job_id: str
    status: PublishStatus


class GetPublishStateResponse(BaseModel):
    session_id: str
    status: PublishStatus
    job_id: str | None = None
    current_version: str | None = None
    public_url: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    logs: str = ""


class CreateSessionResponse(BaseModel):
    session_id: str


class SessionListItem(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    last_active_at: datetime
    preview: str | None = None


class GetSessionResponse(BaseModel):
    session_id: str
    title: str
    messages: list[ChatMessage]
    display_messages: list[DisplayMessage]
    workspace: dict[str, str]
    active_turn: Turn | None
    last_compile_feedback: CompileFeedback | None
    pending_frontend_tool: PendingFrontendTool | None


class CreateMessageRequest(BaseModel):
    content: str


class CreateMessageResponse(BaseModel):
    turn_id: str
    state: TurnState


class FrontendToolResultRequest(BaseModel):
    tool_name: FrontendToolName
    status: CompileStatus
    result: CompileResult
    server_logs: list[str] = Field(default_factory=list)
    client_logs: list[Any] = Field(default_factory=list)
    error_summary: str | None = None


class FrontendToolResultResponse(BaseModel):
    accepted: bool


class UserMessageInputRequest(BaseModel):
    type: Literal["user_message"]
    content: str


class FrontendToolResultInputRequest(FrontendToolResultRequest):
    type: Literal["frontend_tool_result"]
    turn_id: str


SessionInputRequest = Annotated[
    UserMessageInputRequest | FrontendToolResultInputRequest,
    Field(discriminator="type"),
]


class SessionInputResponse(BaseModel):
    accepted: bool = True
    turn_id: str | None = None
    state: TurnState | None = None


class SessionEvent(BaseModel):
    event: SessionEventName
    data: dict[str, Any]
