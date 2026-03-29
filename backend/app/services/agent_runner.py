from __future__ import annotations

import asyncio
import json
import time
from typing import Any, cast
from uuid import uuid4

from loguru import logger
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

from app.config.settings import settings
from app.schemas.session import ChatMessage, CompileFeedback, MessageRole, Session, SessionEventName, TurnState
from app.services.openai_client import openai_client
from app.services.session_store import SessionStore, session_store
from app.services.tool_executor import ToolExecutionKind, ToolExecutor, get_tool_definitions, tool_executor


SYSTEM_PROMPT = """你是一个智能前端编码助手，可以帮助用户完成任务或进行对话。

## 环境说明

你工作在一个虚拟的 Vite + Vue 工作区中。你不能访问 shell、网络或真实文件系统，你只能通过系统提供的工具查看和修改当前虚拟工作区。

### 技术栈强约束
- 这个工作区只能编写和修改 Vue 项目代码，默认使用 Vue 3 + Vite
- 你输出的前端实现必须遵循 Vue 生态，优先使用 `.vue` 单文件组件、Vue 组合式 API、`vite.config.*`、`src/main.*` 等 Vue 项目结构
- 禁止生成或改造成 React、Next.js、Angular、Svelte、Solid、jQuery 或其他非 Vue 技术栈项目
- 如果用户要求你创建或修改一个非 Vue 项目，你必须保持在 Vue 方案内完成；若需求本身与 Vue 技术栈冲突，应明确说明当前环境只支持 Vue 实现，并提供 Vue 等价方案
- 不要假设可以安装或切换到其他框架，也不要输出与当前 Vue 工作区不兼容的脚手架结构

### 当前工作目录与查询方式
- 你的当前工作目录是虚拟工作区根目录，可视为 `/`
- 所有查询和修改都只能基于这个虚拟工作区进行
- 不要使用真实机器路径，也不要假设可以访问工作区之外的内容
- 查看根目录时，优先调用 `list_files(path=".", recursive=false)`
- 查看目录结构时，先调用 `list_files`
- 读取具体文件内容时，调用 `read_file`
- 在没有真实上下文前，不要猜测文件内容或文件位置
- 路径必须严格按照工具约定和工具返回结果使用；如果工作区中出现 `.`、`src/App.vue`、`/src/App.vue` 等不同写法，优先以工具返回结果和当前上下文中的已知工作区路径为准

### 可用工具
- `list_files(path, recursive)`: 查看目录内容
- `read_file(files)`: 读取一个或多个文件内容，返回 `<file><path>...</path><content>...</content></file>` 结构；`content` 中每行以 `1|`、`2|` 这种格式标注行号，后面才是代码内容
- `apply_diff(path, diff)`: 对已存在文件执行精确的 SEARCH/REPLACE 修改
- `write_to_file(path, content)`: 将完整内容写入文件；适合创建新文件，或明确需要整文件覆盖的场景
- `delete_files(paths)`: 删除已有文件
- `run_diagnostics()`: 请求前端同步当前工作区，运行一次诊断，并返回编译或运行反馈
- `complete_task(message)`: 在任务完成或纯对话场景下，向用户返回最终回复；如果完成的是页面或交互效果，要提醒用户在右侧预览区域查看结果，且不要提及 localhost、本地端口或任何 URL

## 核心规则（必须严格遵守）

### 1. 先判断用户意图
你必须先判断，用户是在：
- 闲聊、问候、咨询、解释概念、讨论方案
- 还是要求你执行具体的代码任务、排查问题、修改文件、修复编译错误

### 2. 闲聊 / 对话场景
如果用户只是聊天、问候、咨询、解释概念，或者不需要你实际修改工作区：
- 直接调用 `complete_task(message)`
- 不要调用其他工具

### 3. 任务执行场景
如果用户要求你执行具体操作（查看、分析、修改、删除、修复、调试等），才调用相应工具。

### 4. 单工具调用规则
- 每一轮 assistant 回复必须且只能包含一次工具调用
- 严禁在一条消息中调用多个工具
- 如果任务需要多个步骤，必须逐步迭代完成
- 不要只输出纯文本来表示任务完成，完成时必须调用 `complete_task(message)`

### 5. 基于真实上下文行动
- 不要假设文件内容、目录结构或编译结果
- 信息不足时，必须先调用工具收集真实上下文
- 当你不能完全确定文件精确内容时，优先调用 `read_file`
- 修改文件前，应确保你已经拿到了足够准确的当前内容

### 6. 文件修改规则
- `apply_diff` 只能修改已经存在的文件
- `apply_diff` 中的 SEARCH 片段必须与当前文件内容完全一致
- 如果修改失败，先重新读取文件，再基于最新内容重试
- 优先使用 `apply_diff` 修改已有文件；`write_to_file` 更适合创建新文件，或在你明确要整文件重写时使用
- 使用 `write_to_file` 时，必须提供文件的完整内容，不能只写局部片段或省略未改动部分

### 7. 编译与收尾
- 当任务涉及前端改动、修复报错、集成组件或调整代码逻辑时，在合适的时候调用 `run_diagnostics()`
- 只有在任务真正完成、或可以明确向用户交付结果时，才调用 `complete_task(message)`
- 如果任务产出包含页面或界面效果，`complete_task(message)` 中应引导用户去右侧预览区域查看，不要写 `http://localhost:5173/` 这类本地地址，也不要输出任何 URL

## 工作方式
每次行动前，先评估：
1. 你已经掌握了哪些信息
2. 还缺少哪些完成任务所需的信息
3. 下一步最合适的单个工具是什么

始终基于工具返回的真实结果继续推进，不要凭空补全环境信息。
"""


def build_display_tool_calls(tool_calls: list[dict[str, Any]]) -> list[str]:
    display_tool_calls: list[str] = []
    for tool_call in tool_calls:
        function = tool_call.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if isinstance(name, str) and name:
            display_tool_calls.append(name)
    return display_tool_calls


def wrap_user_task(content: str) -> str:
    return f"<task>\n{content}\n</task>"


class AgentRunner:
    def __init__(
        self,
        *,
        session_store: SessionStore,
        openai_client: AsyncOpenAI,
        tool_executor: ToolExecutor,
    ) -> None:
        self.session_store = session_store
        self.openai_client = openai_client
        self.tool_executor = tool_executor
        self.settings = settings

    async def start_turn(self, session: Session) -> None:
        asyncio.create_task(self._run_turn(session.session_id))

    async def _run_turn(self, session_id: str) -> None:
        session = self.session_store.get_session(session_id)
        turn = session.active_turn
        if not turn:
            return

        try:
            for iteration in range(self.settings.agent_max_iterations):
                lock = self.session_store.get_lock(session_id)
                async with lock:
                    session = self.session_store.get_session(session_id)
                    turn = session.active_turn
                    if not turn or turn.state != TurnState.RUNNING:
                        return

                logger.info("agent iteration start session_id={} turn_id={} iteration={}", session_id, turn.id, iteration + 1)
                response = await self._stream_completion(session)

                lock = self.session_store.get_lock(session_id)
                async with lock:
                    session = self.session_store.get_session(session_id)
                    turn = session.active_turn
                    if not turn or turn.state != TurnState.RUNNING:
                        return

                    tool_calls = response["tool_calls"]
                    assistant_text = response["assistant_text"]
                    reasoning_text = response["reasoning_text"]

                    if len(tool_calls) != 1:
                        if turn.retries_for_missing_tool >= 1:
                            await self._fail_turn(session, "模型连续两次违反了单工具调用约束。")
                            return

                        turn.retries_for_missing_tool += 1
                        self.session_store.append_message(
                            session,
                            ChatMessage(
                                role=MessageRole.SYSTEM,
                                content=(
                                    "约束提醒：你的下一次回复必须且只能包含一次工具调用。"
                                    "不要只输出纯文本。"
                                ),
                            ),
                        )
                        continue

                    tool_call = tool_calls[0]
                    self.session_store.append_message(
                        session,
                        ChatMessage(
                            id=response["message_id"],
                            role=MessageRole.ASSISTANT,
                            content=assistant_text or "",
                            reasoning_content=reasoning_text or None,
                            tool_calls=[tool_call],
                        ),
                    )

                    execution = self.tool_executor.execute(
                        session=session,
                        turn_id=turn.id,
                        tool_name=tool_call["function"]["name"],
                        tool_call_id=tool_call["id"],
                        raw_arguments=tool_call["function"]["arguments"],
                    )

                    if execution.workspace_patch:
                        await self.session_store.publish_event(
                            session.session_id,
                            SessionEventName.WORKSPACE_PATCH,
                            execution.workspace_patch.model_dump(mode="json"),
                        )

                    if execution.kind == ToolExecutionKind.BACKEND:
                        self.session_store.append_message(
                            session,
                            ChatMessage(
                                role=MessageRole.TOOL,
                                name=tool_call["function"]["name"],
                                tool_call_id=tool_call["id"],
                                content=execution.tool_message or "",
                            ),
                        )
                        continue

                    if execution.kind == ToolExecutionKind.FRONTEND:
                        pending_frontend_tool = execution.pending_frontend_tool
                        if pending_frontend_tool is None:
                            await self._fail_turn(session, "前端工具执行后没有生成待处理的工具状态。")
                            return

                        self.session_store.set_pending_frontend_tool(session, pending_frontend_tool)
                        turn.state = TurnState.WAITING_FOR_FRONTEND
                        await self.session_store.publish_event(
                            session.session_id,
                            SessionEventName.FRONTEND_TOOL_CALL,
                            {
                                "turn_id": turn.id,
                                "tool_name": pending_frontend_tool.tool_name,
                                "tool_call_id": pending_frontend_tool.tool_call_id,
                                "arguments": pending_frontend_tool.arguments,
                                "replayed": False,
                            },
                        )
                        return

                    if execution.kind == ToolExecutionKind.COMPLETE:
                        self.session_store.append_message(
                            session,
                            ChatMessage(role=MessageRole.ASSISTANT, content=execution.completion_message or ""),
                        )
                        turn.state = TurnState.COMPLETED
                        self.session_store.set_active_turn(session, None)
                        await self.session_store.publish_event(
                            session.session_id,
                            SessionEventName.TURN_COMPLETED,
                            {
                                "turn_id": turn.id,
                                "message": execution.completion_message or "",
                            },
                        )
                        return

            async with self.session_store.get_lock(session_id):
                session = self.session_store.get_session(session_id)
                await self._fail_turn(session, "Agent 超过了最大迭代次数。")
        except Exception as exc:
            logger.exception("agent loop failed session_id={} error={}", session_id, exc)
            async with self.session_store.get_lock(session_id):
                session = self.session_store.get_session(session_id)
                await self._fail_turn(session, "Agent 执行循环发生异常。")

    async def resume_after_frontend_result(
        self,
        *,
        session: Session,
        feedback: CompileFeedback,
    ) -> None:
        turn = session.active_turn
        pending = session.pending_frontend_tool
        if not turn or not pending:
            return

        self.session_store.set_compile_feedback(session, feedback)
        self.session_store.append_message(
            session,
            ChatMessage(
                role=MessageRole.TOOL,
                name=pending.tool_name,
                tool_call_id=pending.tool_call_id,
                content=feedback.model_dump_json(),
            ),
        )
        turn.state = TurnState.RUNNING
        self.session_store.set_pending_frontend_tool(session, None)
        await self.start_turn(session)

    async def _stream_completion(self, session: Session) -> dict[str, Any]:
        started_at = time.perf_counter()
        turn_id = session.active_turn.id if session.active_turn else ""
        message_id = str(uuid4())
        async with self.session_store.get_lock(session.session_id):
            locked_session = self.session_store.get_session(session.session_id)
            self.session_store.set_turn_streaming_message_id(locked_session, message_id)
            self.session_store.set_turn_streaming_tool_calls(locked_session, [])

        await self.session_store.publish_event(
            session.session_id,
            SessionEventName.ASSISTANT_MESSAGE_STARTED,
            {
                "turn_id": turn_id,
                "message_id": message_id,
            },
        )
        messages = self._build_openai_messages(session)
        tools = cast(list[ChatCompletionToolParam], get_tool_definitions())
        stream = await self.openai_client.chat.completions.create(
            model=self.settings.openai_model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            parallel_tool_calls=False,
            stream=True,
        )

        assistant_chunks: list[str] = []
        reasoning_chunks: list[str] = []
        tool_calls: dict[int, dict[str, Any]] = {}

        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if not choice:
                continue

            delta = choice.delta
            if delta.content:
                assistant_chunks.append(delta.content)
                await self.session_store.publish_event(
                    session.session_id,
                    SessionEventName.ASSISTANT_DELTA,
                    {
                        "turn_id": turn_id,
                        "message_id": message_id,
                        "delta": delta.content,
                    },
                )

            reasoning_delta = getattr(delta, "reasoning_content", None)
            if reasoning_delta:
                reasoning_chunks.append(reasoning_delta)
                await self.session_store.publish_event(
                    session.session_id,
                    SessionEventName.ASSISTANT_REASONING_DELTA,
                    {
                        "turn_id": turn_id,
                        "message_id": message_id,
                        "delta": reasoning_delta,
                    },
                )

            if not delta.tool_calls:
                continue

            for tool_delta in delta.tool_calls:
                index = tool_delta.index
                current = tool_calls.setdefault(
                    index,
                    {
                        "id": tool_delta.id or f"tool-{index}",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    },
                )
                if tool_delta.id:
                    current["id"] = tool_delta.id
                if tool_delta.function and tool_delta.function.name:
                    current["function"]["name"] += tool_delta.function.name
                if tool_delta.function and tool_delta.function.arguments:
                    current["function"]["arguments"] += tool_delta.function.arguments

            display_tool_calls = build_display_tool_calls([tool_calls[index] for index in sorted(tool_calls)])
            if display_tool_calls:
                async with self.session_store.get_lock(session.session_id):
                    locked_session = self.session_store.get_session(session.session_id)
                    self.session_store.set_turn_streaming_tool_calls(locked_session, display_tool_calls)
                await self.session_store.publish_event(
                    session.session_id,
                    SessionEventName.ASSISTANT_TOOL_CALLS_UPDATED,
                    {
                        "turn_id": turn_id,
                        "message_id": message_id,
                        "tool_calls": display_tool_calls,
                    },
                )

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info(
            "openai stream finished session_id={} elapsed_ms={} tool_calls={} reasoning_chars={}",
            session.session_id,
            elapsed_ms,
            len(tool_calls),
            len("".join(reasoning_chunks)),
        )
        await self.session_store.publish_event(
            session.session_id,
            SessionEventName.ASSISTANT_MESSAGE_COMPLETED,
            {
                "turn_id": turn_id,
                "message_id": message_id,
            },
        )
        async with self.session_store.get_lock(session.session_id):
            locked_session = self.session_store.get_session(session.session_id)
            self.session_store.set_turn_streaming_message_id(locked_session, None)
            self.session_store.set_turn_streaming_tool_calls(locked_session, [])
        return {
            "message_id": message_id,
            "assistant_text": "".join(assistant_chunks).strip(),
            "reasoning_text": "".join(reasoning_chunks).strip(),
            "tool_calls": [tool_calls[index] for index in sorted(tool_calls)],
        }

    def _build_openai_messages(self, session: Session) -> list[ChatCompletionMessageParam]:
        messages: list[ChatCompletionMessageParam] = [
            cast(ChatCompletionMessageParam, {"role": MessageRole.SYSTEM, "content": SYSTEM_PROMPT})
        ]

        for message in session.messages:
            content = wrap_user_task(message.content) if message.role == MessageRole.USER else message.content
            payload: dict[str, Any] = {"role": message.role, "content": content}
            if message.role == MessageRole.ASSISTANT and message.tool_calls:
                payload["tool_calls"] = message.tool_calls
            if message.role == MessageRole.TOOL:
                payload["tool_call_id"] = message.tool_call_id
                payload["name"] = message.name
            messages.append(cast(ChatCompletionMessageParam, payload))
        return messages

    async def _fail_turn(self, session: Session, reason: str) -> None:
        turn = session.active_turn
        if not turn:
            return
        turn.state = TurnState.FAILED
        self.session_store.set_active_turn(session, None)
        self.session_store.set_pending_frontend_tool(session, None)
        await self.session_store.publish_event(
            session.session_id,
            SessionEventName.TURN_FAILED,
            {"turn_id": turn.id, "reason": reason},
        )


agent_runner = AgentRunner(
    session_store=session_store,
    openai_client=openai_client,
    tool_executor=tool_executor,
)
