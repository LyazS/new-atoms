from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from loguru import logger
from sse_starlette.sse import EventSourceResponse

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
    GetSessionResponse,
    MessageRole,
    SessionEventName,
    SessionInputRequest,
    SessionInputResponse,
    Turn,
    TurnState,
    UserMessageInputRequest,
)
from app.services.agent_runner import agent_runner
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


def build_display_messages(
    messages: list[ChatMessage],
    *,
    active_turn: Turn | None,
) -> list[DisplayMessage]:
    display_messages: list[DisplayMessage] = []
    active_message_id = active_turn.streaming_message_id if active_turn else None

    for message in messages:
        if message.role == MessageRole.USER:
            display_messages.append(
                DisplayMessage(
                    id=message.id,
                    role="user",
                    content=message.content,
                )
            )
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


async def _handle_user_message_input(
    session_id: str,
    request: UserMessageInputRequest,
) -> SessionInputResponse:
    logger.debug(
        "route session_input user_message session_id={} content_length={}",
        session_id,
        len(request.content),
    )
    session = session_store.get_session(session_id)
    async with session_store.get_lock(session_id):
        session = session_store.get_session(session_id)
        if session.active_turn:
            logger.debug(
                "route session_input user_message rejected session_id={} active_turn_id={}",
                session_id,
                session.active_turn.id,
            )
            raise HTTPException(status_code=409, detail="active turn already running")

        session_store.append_message(session, ChatMessage(role=MessageRole.USER, content=request.content))
        turn = Turn(user_message=request.content)
        session_store.set_active_turn(session, turn)

    await agent_runner.start_turn(session)
    logger.debug(
        "route session_input user_message accepted session_id={} turn_id={} state={}",
        session_id,
        turn.id,
        turn.state,
    )
    return SessionInputResponse(turn_id=turn.id, state=turn.state)


async def _handle_frontend_tool_result_input(
    session_id: str,
    request: FrontendToolResultInputRequest,
) -> SessionInputResponse:
    logger.debug(
        "route session_input frontend_tool_result session_id={} turn_id={} tool_name={} status={} result={}",
        session_id,
        request.turn_id,
        request.tool_name,
        request.status,
        request.result,
    )
    session_store.get_session(session_id)
    async with session_store.get_lock(session_id):
        session = session_store.get_session(session_id)
        turn = session.active_turn
        pending = session.pending_frontend_tool
        if not turn or turn.id != request.turn_id:
            logger.debug(
                "route session_input frontend_tool_result missing_turn session_id={} turn_id={} active_turn_id={}",
                session_id,
                request.turn_id,
                turn.id if turn else None,
            )
            raise HTTPException(status_code=404, detail="turn not found")
        if turn.state != TurnState.WAITING_FOR_FRONTEND or not pending:
            logger.debug(
                "route session_input frontend_tool_result invalid_state session_id={} turn_id={} turn_state={} pending_tool={}",
                session_id,
                request.turn_id,
                turn.state,
                pending.tool_name if pending else None,
            )
            raise HTTPException(status_code=409, detail="turn is not waiting for frontend")
        if request.tool_name != pending.tool_name:
            logger.debug(
                "route session_input frontend_tool_result tool_mismatch session_id={} turn_id={} request_tool={} pending_tool={}",
                session_id,
                request.turn_id,
                request.tool_name,
                pending.tool_name,
            )
            raise HTTPException(status_code=400, detail="tool name mismatch")

        feedback = CompileFeedback.model_validate(request.model_dump(exclude={"turn_id"}))
        await agent_runner.resume_after_frontend_result(session=session, feedback=feedback)

        updated_turn = session.active_turn
        state = updated_turn.state if updated_turn else None

    logger.debug(
        "route session_input frontend_tool_result accepted session_id={} turn_id={} next_state={}",
        session_id,
        request.turn_id,
        state,
    )
    return SessionInputResponse(turn_id=request.turn_id, state=state)


@router.post("/create", response_model=CreateSessionResponse)
async def create_session() -> CreateSessionResponse:
    session = session_store.create_session()
    logger.debug(
        "route create_session session_id={} message_count={} workspace_file_count={}",
        session.session_id,
        len(session.messages),
        len(session.workspace_files),
    )
    return CreateSessionResponse(session_id=session.session_id)


@router.get("/{session_id}", response_model=GetSessionResponse)
async def get_session(
    session_id: str,
) -> GetSessionResponse:
    session = session_store.get_session(session_id)
    logger.debug(
        "route get_session session_id={} active_turn_id={} pending_frontend_tool={}",
        session_id,
        session.active_turn.id if session.active_turn else None,
        session.pending_frontend_tool.tool_name if session.pending_frontend_tool else None,
    )
    return GetSessionResponse(
        session_id=session.session_id,
        messages=session.messages,
        display_messages=build_display_messages(session.messages, active_turn=session.active_turn),
        workspace=session.workspace_files,
        active_turn=session.active_turn,
        last_compile_feedback=session.last_compile_feedback,
        pending_frontend_tool=session.pending_frontend_tool,
    )


@router.get("/{session_id}/events")
async def session_events(
    session_id: str,
) -> EventSourceResponse:
    session_store.get_session(session_id)
    queue = session_store.subscribe(session_id)
    logger.debug("route session_events subscribed session_id={}", session_id)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        try:
            session = session_store.get_session(session_id)
            turn = session.active_turn
            pending = session.pending_frontend_tool
            if turn and turn.streaming_message_id:
                yield {
                    "event": SessionEventName.ASSISTANT_MESSAGE_STARTED,
                    "data": json.dumps(
                        {
                            "turn_id": turn.id,
                            "message_id": turn.streaming_message_id,
                            "replayed": True,
                        },
                        ensure_ascii=False,
                    ),
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
                logger.debug(
                    "route session_events replay_frontend_tool session_id={} turn_id={} tool_name={}",
                    session_id,
                    turn.id,
                    pending.tool_name,
                )
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
                yield {
                    "event": event.event,
                    "data": json.dumps(event.data, ensure_ascii=False),
                }
        except asyncio.CancelledError:
            raise
        finally:
            session_store.unsubscribe(session_id, queue)
            logger.debug("route session_events unsubscribed session_id={}", session_id)

    return EventSourceResponse(event_generator())


@router.post("/{session_id}/inputs", response_model=SessionInputResponse)
async def submit_session_input(
    session_id: str,
    request: SessionInputRequest,
) -> SessionInputResponse:
    if isinstance(request, UserMessageInputRequest):
        return await _handle_user_message_input(session_id, request)

    if isinstance(request, FrontendToolResultInputRequest):
        return await _handle_frontend_tool_result_input(session_id, request)

    raise HTTPException(status_code=400, detail="unsupported input type")


@router.post("/{session_id}/messages", response_model=CreateMessageResponse)
async def create_message(
    session_id: str,
    request: CreateMessageRequest,
) -> CreateMessageResponse:
    response = await _handle_user_message_input(
        session_id,
        UserMessageInputRequest(type="user_message", content=request.content),
    )
    return CreateMessageResponse(
        turn_id=response.turn_id or "",
        state=response.state or TurnState.FAILED,
    )


@router.post("/{session_id}/turns/{turn_id}/frontend-tool-result", response_model=FrontendToolResultResponse)
async def submit_frontend_tool_result(
    session_id: str,
    turn_id: str,
    request: FrontendToolResultRequest,
) -> FrontendToolResultResponse:
    await _handle_frontend_tool_result_input(
        session_id,
        FrontendToolResultInputRequest(
            type="frontend_tool_result",
            turn_id=turn_id,
            **request.model_dump(),
        ),
    )
    return FrontendToolResultResponse(accepted=True)
