from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import timezone, datetime
from typing import Any

from fastapi import HTTPException

from app.schemas.session import (
    ChatMessage,
    CompileFeedback,
    PendingFrontendTool,
    Session,
    SessionEvent,
    SessionEventName,
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

    def create_session(self) -> Session:
        session = Session(
            messages=[],
            workspace_files=dict(DEFAULT_WORKSPACE_FILES),
        )
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="session not found")
        return session

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

    def set_active_turn(self, session: Session, turn: Turn | None) -> None:
        session.active_turn = turn
        session.updated_at = datetime.now(timezone.utc)

    def set_turn_streaming_message_id(self, session: Session, message_id: str | None) -> None:
        if session.active_turn:
            session.active_turn.streaming_message_id = message_id
            session.active_turn.updated_at = datetime.now(timezone.utc)
        session.updated_at = datetime.now(timezone.utc)

    def set_turn_streaming_tool_calls(self, session: Session, tool_calls: list[str]) -> None:
        if session.active_turn:
            session.active_turn.streaming_tool_calls = tool_calls
            session.active_turn.updated_at = datetime.now(timezone.utc)
        session.updated_at = datetime.now(timezone.utc)

    def set_pending_frontend_tool(self, session: Session, pending: PendingFrontendTool | None) -> None:
        session.pending_frontend_tool = pending
        session.updated_at = datetime.now(timezone.utc)

    def set_compile_feedback(self, session: Session, feedback: CompileFeedback | None) -> None:
        session.last_compile_feedback = feedback
        session.updated_at = datetime.now(timezone.utc)

    def apply_workspace_patch(self, session: Session, patch: WorkspacePatch) -> None:
        for op in patch.ops:
            if op.op == WorkspacePatchOpName.UPSERT:
                session.workspace_files[op.path] = op.code or ""
            else:
                session.workspace_files.pop(op.path, None)
        session.updated_at = datetime.now(timezone.utc)


session_store = SessionStore()
