from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import timezone, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import SessionMessageModel, SessionModel, SessionRuntimeStateModel
from app.db.session import SessionLocal
from app.schemas.session import (
    ChatMessage,
    CompileFeedback,
    MessageRole,
    PendingFrontendTool,
    Session,
    SessionEvent,
    SessionEventName,
    SessionListItem,
    Turn,
    WorkspacePatch,
    WorkspacePatchOpName,
)


DEFAULT_WORKSPACE_FILES = {
    "/src/App.vue": """<template>
  <main></main>
</template>
""",
    "/src/main.js": """import { createApp } from "vue";
import App from "./App.vue";
import "./styles.css";

createApp(App).mount("#app");
""",
    "/src/styles.css": """body {
  margin: 0;
}
""",
}


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._subscribers: dict[str, list[asyncio.Queue[SessionEvent]]] = defaultdict(list)

    def create_session(self, *, user_id: str, title: str = "New Project") -> Session:
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            session_row = SessionModel(user_id=user_id, title=title, last_active_at=now)
            db.add(session_row)
            db.flush()
            runtime_row = SessionRuntimeStateModel(
                session_id=session_row.id,
                workspace_files_json=json.dumps(DEFAULT_WORKSPACE_FILES, ensure_ascii=False),
            )
            db.add(runtime_row)
            db.commit()
            db.refresh(session_row)

        session = Session(
            session_id=session_row.id,
            user_id=user_id,
            title=title,
            messages=[],
            workspace_files=dict(DEFAULT_WORKSPACE_FILES),
            created_at=session_row.created_at,
            updated_at=session_row.updated_at,
        )
        self._sessions[session.session_id] = session
        return session

    def list_sessions(self, *, user_id: str) -> list[SessionListItem]:
        with SessionLocal() as db:
            session_rows = db.scalars(
                select(SessionModel)
                .where(SessionModel.user_id == user_id)
                .options(selectinload(SessionModel.messages))
                .order_by(SessionModel.last_active_at.desc(), SessionModel.created_at.desc())
            ).all()

        items: list[SessionListItem] = []
        for row in session_rows:
            preview = None
            for message in reversed(row.messages):
                if message.role in {"user", "assistant"} and message.content.strip():
                    preview = message.content.strip()[:140]
                    break
            items.append(
                SessionListItem(
                    id=row.id,
                    title=row.title,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    last_active_at=row.last_active_at,
                    preview=preview,
                )
            )
        return items

    def get_session(self, session_id: str) -> Session:
        cached = self._sessions.get(session_id)
        if cached:
            return cached

        session = self._load_session(session_id)
        self._sessions[session_id] = session
        return session

    def get_user_session(self, *, session_id: str, user_id: str) -> Session:
        session = self.get_session(session_id)
        if session.user_id != user_id:
            raise HTTPException(status_code=404, detail="session not found")
        return session

    def delete_session(self, *, session_id: str, user_id: str) -> None:
        with SessionLocal() as db:
            row = db.get(SessionModel, session_id)
            if row is None or row.user_id != user_id:
                raise HTTPException(status_code=404, detail="session not found")
            db.delete(row)
            db.commit()

        self._sessions.pop(session_id, None)
        self._subscribers.pop(session_id, None)

    def get_lock(self, session_id: str) -> asyncio.Lock:
        return self._locks[session_id]

    async def publish_event(self, session_id: str, event: SessionEventName, data: dict[str, Any]) -> None:
        payload = SessionEvent(event=event, data=data)
        for queue in list(self._subscribers[session_id]):
            await queue.put(payload)

    def subscribe(self, session_id: str) -> asyncio.Queue[SessionEvent]:
        queue: asyncio.Queue[SessionEvent] = asyncio.Queue()
        self._subscribers[session_id].append(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue[SessionEvent]) -> None:
        subscribers = self._subscribers.get(session_id, [])
        if queue in subscribers:
            subscribers.remove(queue)

    def append_message(self, session: Session, message: ChatMessage) -> None:
        session.messages.append(message)
        session.updated_at = datetime.now(timezone.utc)
        self._persist_message(session, message)

        if len([item for item in session.messages if item.role == "user"]) == 1 and message.role == "user":
            session.title = self._build_title_from_content(message.content)
            self._persist_session_meta(session)

    def set_active_turn(self, session: Session, turn: Turn | None) -> None:
        session.active_turn = turn
        session.updated_at = datetime.now(timezone.utc)
        self._persist_runtime_state(session)

    def set_turn_streaming_message_id(self, session: Session, message_id: str | None) -> None:
        if session.active_turn:
            session.active_turn.streaming_message_id = message_id
            session.active_turn.updated_at = datetime.now(timezone.utc)
        session.updated_at = datetime.now(timezone.utc)
        self._persist_runtime_state(session)

    def set_turn_streaming_tool_calls(self, session: Session, tool_calls: list[str]) -> None:
        if session.active_turn:
            session.active_turn.streaming_tool_calls = tool_calls
            session.active_turn.updated_at = datetime.now(timezone.utc)
        session.updated_at = datetime.now(timezone.utc)
        self._persist_runtime_state(session)

    def set_pending_frontend_tool(self, session: Session, pending: PendingFrontendTool | None) -> None:
        session.pending_frontend_tool = pending
        session.updated_at = datetime.now(timezone.utc)
        self._persist_runtime_state(session)

    def set_compile_feedback(self, session: Session, feedback: CompileFeedback | None) -> None:
        session.last_compile_feedback = feedback
        session.updated_at = datetime.now(timezone.utc)
        self._persist_runtime_state(session)

    def apply_workspace_patch(self, session: Session, patch: WorkspacePatch) -> None:
        for op in patch.ops:
            if op.op == WorkspacePatchOpName.UPSERT:
                session.workspace_files[op.path] = op.code or ""
            else:
                session.workspace_files.pop(op.path, None)
        session.updated_at = datetime.now(timezone.utc)
        self._persist_runtime_state(session)

    def _load_session(self, session_id: str) -> Session:
        with SessionLocal() as db:
            row = db.scalar(
                select(SessionModel)
                .where(SessionModel.id == session_id)
                .options(selectinload(SessionModel.messages), selectinload(SessionModel.runtime_state))
            )
            if row is None:
                raise HTTPException(status_code=404, detail="session not found")
            runtime = row.runtime_state
            if runtime is None:
                runtime = SessionRuntimeStateModel(
                    session_id=row.id,
                    workspace_files_json=json.dumps(DEFAULT_WORKSPACE_FILES, ensure_ascii=False),
                )
                db.add(runtime)
                db.commit()
                row.runtime_state = runtime

        return Session(
            session_id=row.id,
            user_id=row.user_id,
            title=row.title,
            messages=[self._to_chat_message(message) for message in row.messages],
            workspace_files=json.loads(runtime.workspace_files_json) if runtime else dict(DEFAULT_WORKSPACE_FILES),
            active_turn=Turn.model_validate(json.loads(runtime.active_turn_json)) if runtime and runtime.active_turn_json else None,
            last_compile_feedback=CompileFeedback.model_validate(json.loads(runtime.last_compile_feedback_json)) if runtime and runtime.last_compile_feedback_json else None,
            pending_frontend_tool=PendingFrontendTool.model_validate(json.loads(runtime.pending_frontend_tool_json)) if runtime and runtime.pending_frontend_tool_json else None,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _to_chat_message(self, row: SessionMessageModel) -> ChatMessage:
        return ChatMessage(
            id=row.id,
            role=MessageRole(row.role),
            content=row.content,
            reasoning_content=row.reasoning_content,
            tool_call_id=row.tool_call_id,
            name=row.name,
            tool_calls=json.loads(row.tool_calls_json) if row.tool_calls_json else None,
        )

    def _persist_message(self, session: Session, message: ChatMessage) -> None:
        with SessionLocal() as db:
            db.add(
                SessionMessageModel(
                    id=message.id,
                    session_id=session.session_id,
                    sequence=len(session.messages) - 1,
                    role=str(message.role),
                    content=message.content,
                    reasoning_content=message.reasoning_content,
                    tool_call_id=message.tool_call_id,
                    name=message.name,
                    tool_calls_json=json.dumps(message.tool_calls, ensure_ascii=False) if message.tool_calls is not None else None,
                )
            )
            row = db.get(SessionModel, session.session_id)
            if row is not None:
                row.updated_at = session.updated_at
                row.last_active_at = session.updated_at
                row.title = session.title
            db.commit()

    def _persist_session_meta(self, session: Session) -> None:
        with SessionLocal() as db:
            row = db.get(SessionModel, session.session_id)
            if row is None:
                raise HTTPException(status_code=404, detail="session not found")
            row.title = session.title
            row.updated_at = session.updated_at
            row.last_active_at = session.updated_at
            db.commit()

    def _persist_runtime_state(self, session: Session) -> None:
        with SessionLocal() as db:
            runtime = db.get(SessionRuntimeStateModel, session.session_id)
            if runtime is None:
                runtime = SessionRuntimeStateModel(
                    session_id=session.session_id,
                    workspace_files_json=json.dumps(DEFAULT_WORKSPACE_FILES, ensure_ascii=False),
                )
                db.add(runtime)

            runtime.workspace_files_json = json.dumps(session.workspace_files, ensure_ascii=False)
            runtime.active_turn_json = session.active_turn.model_dump_json() if session.active_turn else None
            runtime.pending_frontend_tool_json = (
                session.pending_frontend_tool.model_dump_json() if session.pending_frontend_tool else None
            )
            runtime.last_compile_feedback_json = (
                session.last_compile_feedback.model_dump_json() if session.last_compile_feedback else None
            )

            row = db.get(SessionModel, session.session_id)
            if row is not None:
                row.updated_at = session.updated_at
                row.last_active_at = session.updated_at
                row.title = session.title
            db.commit()

    def _build_title_from_content(self, content: str) -> str:
        normalized = " ".join(content.strip().split())
        if not normalized:
            return "New Project"
        if len(normalized) <= 40:
            return normalized
        return f"{normalized[:37]}..."


session_store = SessionStore()
