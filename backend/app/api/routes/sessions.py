from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Response
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_current_user
from app.schemas.auth import UserPublic
from app.schemas.session import (
    ChatMessage,
    CompileFeedback,
    CreateMessageRequest,
    CreateMessageResponse,
    CreateSessionResponse,
    DisplayMessage,
    FrontendToolResultInputRequest,
    FrontendToolResultRequest,
    FrontendToolResultResponse,
    GetPublishStateResponse,
    GetSessionResponse,
    MessageRole,
    PublishSessionResponse,
    SessionEventName,
    SessionInputRequest,
    SessionInputResponse,
    SessionListItem,
    Turn,
    TurnState,
    UserMessageInputRequest,
)
from app.services.agent_runner import agent_runner
from app.services.publish_service import publish_service
from app.services.session_store import session_store

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def build_display_tool_calls(tool_calls: list[dict[str, object]] | None) -> list[str]:
    if not tool_calls:
        return []

    display_tool_calls: list[str] = []
    for tool_call in tool_calls:
        function = tool_call.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if isinstance(name, str) and name:
            display_tool_calls.append(name)
    return display_tool_calls


def build_display_messages(messages: list[ChatMessage], *, active_turn: Turn | None) -> list[DisplayMessage]:
    display_messages: list[DisplayMessage] = []
    active_message_id = active_turn.streaming_message_id if active_turn else None

    for message in messages:
        if message.role == MessageRole.USER:
            display_messages.append(DisplayMessage(id=message.id, role="user", content=message.content))
            continue
        if message.role == MessageRole.ASSISTANT:
            display_messages.append(
                DisplayMessage(
                    id=message.id,
                    role="assistant",
                    content=message.content,
                    reasoning_content=message.reasoning_content,
                    tool_calls=build_display_tool_calls(message.tool_calls),
                    is_in_progress=message.id == active_message_id,
                )
            )

    if (
        active_turn
        and active_turn.state in (TurnState.RUNNING, TurnState.WAITING_FOR_FRONTEND)
        and active_message_id
        and not any(message.id == active_message_id for message in display_messages)
    ):
        display_messages.append(
            DisplayMessage(
                id=active_message_id,
                role="assistant",
                content="",
                reasoning_content=None,
                tool_calls=active_turn.streaming_tool_calls,
                is_in_progress=True,
            )
        )
    return display_messages


async def _handle_user_message_input(session_id: str, request: UserMessageInputRequest) -> SessionInputResponse:
    logger.debug("route session_input user_message session_id={} content_length={}", session_id, len(request.content))
    session = session_store.get_session(session_id)
    async with session_store.get_lock(session_id):
        session = session_store.get_session(session_id)
        if session.active_turn:
            raise HTTPException(status_code=409, detail="active turn already running")

        session_store.append_message(
            session,
            ChatMessage(
                role=MessageRole.USER,
                content=request.content,
                selection_context=request.selection_context,
            ),
        )
        turn = Turn(user_message=request.content)
        session_store.set_active_turn(session, turn)

    await agent_runner.start_turn(session)
    return SessionInputResponse(turn_id=turn.id, state=turn.state)


async def _handle_frontend_tool_result_input(
    session_id: str,
    request: FrontendToolResultInputRequest,
) -> SessionInputResponse:
    async with session_store.get_lock(session_id):
        session = session_store.get_session(session_id)
        turn = session.active_turn
        pending = session.pending_frontend_tool
        if not turn or turn.id != request.turn_id:
            raise HTTPException(status_code=404, detail="turn not found")
        if turn.state != TurnState.WAITING_FOR_FRONTEND or not pending:
            raise HTTPException(status_code=409, detail="turn is not waiting for frontend")
        if request.tool_name != pending.tool_name:
            raise HTTPException(status_code=400, detail="tool name mismatch")

        feedback = CompileFeedback.model_validate(request.model_dump(exclude={"turn_id"}))
        await agent_runner.resume_after_frontend_result(session=session, feedback=feedback)
        updated_turn = session.active_turn
        state = updated_turn.state if updated_turn else None

    return SessionInputResponse(turn_id=request.turn_id, state=state)


@router.get("", response_model=list[SessionListItem])
async def list_sessions(current_user: UserPublic = Depends(get_current_user)) -> list[SessionListItem]:
    return session_store.list_sessions(user_id=current_user.id)


@router.post("", response_model=CreateSessionResponse)
async def create_session(current_user: UserPublic = Depends(get_current_user)) -> CreateSessionResponse:
    session = session_store.create_session(user_id=current_user.id)
    return CreateSessionResponse(session_id=session.session_id)


@router.get("/{session_id}", response_model=GetSessionResponse)
async def get_session(session_id: str, current_user: UserPublic = Depends(get_current_user)) -> GetSessionResponse:
    session = session_store.get_user_session(session_id=session_id, user_id=current_user.id)
    return GetSessionResponse(
        session_id=session.session_id,
        title=session.title,
        messages=session.messages,
        display_messages=build_display_messages(session.messages, active_turn=session.active_turn),
        workspace=session.workspace_files,
        active_turn=session.active_turn,
        last_compile_feedback=session.last_compile_feedback,
        pending_frontend_tool=session.pending_frontend_tool,
    )


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str, current_user: UserPublic = Depends(get_current_user)) -> Response:
    session_store.delete_session(session_id=session_id, user_id=current_user.id)
    publish_service.cleanup_session_artifacts(session_id)
    return Response(status_code=204)


@router.get("/{session_id}/publish", response_model=GetPublishStateResponse)
async def get_publish_state(
    session_id: str,
    current_user: UserPublic = Depends(get_current_user),
) -> GetPublishStateResponse:
    session_store.get_user_session(session_id=session_id, user_id=current_user.id)
    state = publish_service.get_state(session_id)
    return GetPublishStateResponse(
        session_id=state.session_id,
        status=state.status,
        job_id=state.job_id,
        current_version=state.current_version,
        public_url=state.public_url,
        started_at=state.started_at,
        finished_at=state.finished_at,
        error_message=state.error_message,
        logs=state.build_log,
    )


@router.post("/{session_id}/publish", response_model=PublishSessionResponse)
async def publish_session(
    session_id: str,
    current_user: UserPublic = Depends(get_current_user),
) -> PublishSessionResponse:
    session_store.get_user_session(session_id=session_id, user_id=current_user.id)
    state = await publish_service.queue_publish(session_id)
    return PublishSessionResponse(job_id=state.job_id or "", status=state.status)


@router.get("/{session_id}/events")
async def session_events(session_id: str, current_user: UserPublic = Depends(get_current_user)) -> EventSourceResponse:
    session_store.get_user_session(session_id=session_id, user_id=current_user.id)
    queue = session_store.subscribe(session_id)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        try:
            session = session_store.get_session(session_id)
            turn = session.active_turn
            pending = session.pending_frontend_tool
            if turn and turn.streaming_message_id:
                yield {
                    "event": SessionEventName.ASSISTANT_MESSAGE_STARTED,
                    "data": json.dumps({"turn_id": turn.id, "message_id": turn.streaming_message_id, "replayed": True}, ensure_ascii=False),
                }
                if turn.streaming_tool_calls:
                    yield {
                        "event": SessionEventName.ASSISTANT_TOOL_CALLS_UPDATED,
                        "data": json.dumps(
                            {
                                "turn_id": turn.id,
                                "message_id": turn.streaming_message_id,
                                "tool_calls": turn.streaming_tool_calls,
                                "replayed": True,
                            },
                            ensure_ascii=False,
                        ),
                    }
            if turn and turn.state == TurnState.WAITING_FOR_FRONTEND and pending:
                yield {
                    "event": SessionEventName.FRONTEND_TOOL_CALL,
                    "data": json.dumps(
                        {
                            "turn_id": turn.id,
                            "tool_name": pending.tool_name,
                            "tool_call_id": pending.tool_call_id,
                            "arguments": pending.arguments,
                            "replayed": True,
                        },
                        ensure_ascii=False,
                    ),
                }
            while True:
                event = await queue.get()
                yield {"event": event.event, "data": json.dumps(event.data, ensure_ascii=False)}
        except asyncio.CancelledError:
            raise
        finally:
            session_store.unsubscribe(session_id, queue)

    return EventSourceResponse(event_generator())


@router.post("/{session_id}/inputs", response_model=SessionInputResponse)
async def submit_session_input(
    session_id: str,
    request: SessionInputRequest,
    current_user: UserPublic = Depends(get_current_user),
) -> SessionInputResponse:
    session_store.get_user_session(session_id=session_id, user_id=current_user.id)
    if isinstance(request, UserMessageInputRequest):
        return await _handle_user_message_input(session_id, request)
    if isinstance(request, FrontendToolResultInputRequest):
        return await _handle_frontend_tool_result_input(session_id, request)
    raise HTTPException(status_code=400, detail="unsupported input type")


@router.post("/{session_id}/messages", response_model=CreateMessageResponse)
async def create_message(
    session_id: str,
    request: CreateMessageRequest,
    current_user: UserPublic = Depends(get_current_user),
) -> CreateMessageResponse:
    session_store.get_user_session(session_id=session_id, user_id=current_user.id)
    response = await _handle_user_message_input(
        session_id,
        UserMessageInputRequest(type="user_message", content=request.content, selection_context=None),
    )
    return CreateMessageResponse(turn_id=response.turn_id or "", state=response.state or TurnState.FAILED)


@router.post("/{session_id}/turns/{turn_id}/frontend-tool-result", response_model=FrontendToolResultResponse)
async def submit_frontend_tool_result(
    session_id: str,
    turn_id: str,
    request: FrontendToolResultRequest,
    current_user: UserPublic = Depends(get_current_user),
) -> FrontendToolResultResponse:
    session_store.get_user_session(session_id=session_id, user_id=current_user.id)
    await _handle_frontend_tool_result_input(
        session_id,
        FrontendToolResultInputRequest(type="frontend_tool_result", turn_id=turn_id, **request.model_dump()),
    )
    return FrontendToolResultResponse(accepted=True)
