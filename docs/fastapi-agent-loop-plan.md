# FastAPI + AsyncOpenAI Chat Completions Tool Calling 实施计划

## 概要

- 目标是把当前 `frontend-vue3` 原型接成真实闭环：用户在左侧对话，后端 Agent 通过 `tool calling` 修改虚拟文件，前端把变更同步到 Sandpack 编译，再把结果回传给后端继续修复。
- 后端固定采用 `FastAPI + AsyncOpenAI.chat.completions.create(...)`，`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL` 全部由环境文件提供。
- 后端依赖管理固定使用 `pip`，不使用 `uv`、Poetry 或其他包管理封装。
- 后端日志固定使用 `loguru`，不再以标准库 `logging` 作为应用层主日志入口。
- Agent 不允许输出 JSON 文本补丁；所有文件操作必须通过 `tools` 完成。
- 当前一次后端 Agent 运行有两种结束条件：调用 `complete_task` 表示任务完成，或调用前端工具并挂起等待前端回调。
- 第一版范围固定为 `vite-vue` 单页应用，不做多框架切换、不做依赖安装、不做真实仓库写盘。

## 后端设计
 
### 目录结构

后端代码固定放在 `backend` 目录下，建议采用现有的 `backend/app` 结构：

- `backend/app/main.py`：FastAPI 入口与路由挂载
- `backend/app/config/settings.py`：读取环境变量
- `backend/app/config/logging.py`：初始化 `loguru`、统一日志格式与 sink
- `backend/app/schemas/`：API 请求/响应、tool 参数、session/turn 类型
- `backend/app/services/openai_client.py`：统一创建 `AsyncOpenAI`
- `backend/app/services/session_store.py`：内存版 session/workspace/turn store
- `backend/app/services/agent_runner.py`：Agent 循环编排
- `backend/app/services/tool_executor.py`：执行后端工具，并把前端工具转换成待执行动作
- `backend/app/api/routes/sessions.py`：session、message、events、frontend-tool-result 接口

### 依赖与运行方式

后端 Python 项目固定采用 `pip + requirements.txt`：

建议最少依赖包括：

- `fastapi`
- `uvicorn[standard]`
- `openai`
- `pydantic`
- `pydantic-settings`
- `sse-starlette`
- `loguru`

本计划中的本地启动命令统一写为：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 环境变量

固定使用以下环境变量：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `OPENAI_TIMEOUT=60`
- `AGENT_MAX_ITERATIONS=6`
- `LOG_LEVEL=INFO`

### 日志方案

后端日志统一由 `loguru` 管理，约束如下：

- 应用代码统一 `from loguru import logger` 获取日志器，不再在业务层直接创建标准库 `logging.Logger`
- 在 `config/logging.py` 中集中完成 `logger.remove()`、控制台 sink、可选文件 sink、日志格式、日志级别配置
- FastAPI 启动时在 `backend/app/main.py` 中优先执行 `setup_logging()`，确保路由、Agent 循环、工具执行器都使用同一套日志配置
- 记录关键链路日志：session 创建、turn 开始/结束、模型请求耗时、tool call 参数摘要、前端工具挂起与恢复、异常堆栈
- 对模型返回、工具参数和 compile feedback 做必要脱敏，避免把完整代码和敏感环境变量直接打进日志
- 若需要兼容 Uvicorn/FastAPI 生态日志，可在启动阶段把标准库 logging 拦截转发到 `loguru`，但应用侧唯一日志出口仍是 `loguru`

### Session 模型

`session` 建议固定包含这些字段：

- `session_id`
- `messages`
- `workspace_files`
- `active_turn`
- `last_compile_feedback`
- `pending_frontend_tool`
- `created_at`
- `updated_at`

其中：

- `workspace_files` 是唯一真相源，保存为 `dict[path, code]`
- Sandpack 只是运行镜像，不承担持久化职责
- 同一 session 同时只允许一个 `running turn`
- 若当前 turn 因前端工具而挂起，则状态为 `waiting_for_frontend`
- 当上一个 turn 未结束时，新消息直接返回 `409`

## Agent 循环

每个用户消息创建一个 `turn`，并启动一个后台 `asyncio` 任务执行。

### 单轮循环流程

1. 组装 `messages`：system prompt、历史 user/assistant 消息、必要的 workspace 摘要、最近一次 compile feedback。
2. 调用 `await client.chat.completions.create(...)`，固定参数如下：

```python
response = await client.chat.completions.create(
    model=settings.openai_model,
    messages=messages,
    tools=tool_definitions,
    tool_choice="auto",
    parallel_tool_calls=False,
    stream=True,
)
```

3. 流式读取 chunk：
   - 把 `delta.content` 转成 `assistant.delta` SSE 推给前端
   - 累积 `delta.tool_calls`，按 `index` 拼接完整工具名和参数字符串
   - 使用 `loguru` 记录本轮 stream 开始、chunk 汇总状态与结束耗时，避免逐 chunk 打过量日志
4. 流结束后先校验工具调用约束：
   - 每轮模型响应必须调用且只能调用一个工具
   - 若模型返回 0 个工具调用，则视为无效回合
   - 若模型返回超过 1 个工具调用，则同样视为无效回合，并返回约束错误给模型
5. 通过校验后，再分两种情况处理：
   - 若收到后端工具调用，则执行工具并继续本轮循环
   - 若收到前端工具调用，则保存 `pending_frontend_tool`，发 SSE 给前端，并挂起当前 turn
   - 若没有 tool calls，则视为无效回合，并补一条系统约束“必须使用工具结束”，进入下一轮，最多重试 1 次
6. 执行工具前，先把“带 `tool_calls` 的 assistant message”写入会话历史。
7. 后端工具执行后，把结果写成 `tool` role message，再继续下一次 `chat.completions.create(...)`。
8. 若执行的是前端工具，则先把最新 `workspace.patch` 发给前端，再把 turn 状态切到 `waiting_for_frontend`，当前后端 Agent 运行先结束。
9. 前端收到 `workspace.patch` 和前端工具事件后，执行 Sandpack 相关动作，并调用 `frontend-tool-result` 接口回传结果。
10. 后端收到前端工具结果后，把结果写成 `tool` role message，恢复 turn 为 `running`，再进入下一轮模型调用。
11. 当模型调用 `complete_task(message)` 时，写入最终 assistant 消息，turn 标记为 `completed`。

### 循环约束

- 最大循环次数固定为 `6`
- 超限后 turn 标记为 `failed`
- 当前一次后端 Agent 运行有两种结束条件：
  - 调用了 `complete_task`
  - 调用了前端工具并进入 `waiting_for_frontend`
- 每轮响应必须且只能产生一个工具调用；若需要多个工具，则必须拆成多轮调用
- 前端动作完成后，不是继续原 HTTP 请求，而是由前端单独回调结果，再恢复下一轮 Agent 运行

## Tool Calling 设计

模型工具分为两类。

### 后端工具

- `list_files()`
- `read_files(paths: string[])`
- `apply_diff(path: string, diff: string)`
- `delete_files(paths: string[])`
- `complete_task(message: string)`

### 前端工具

- `run_sandpack()`

其中，`run_sandpack()` 表示“请前端基于当前 workspace 同步到 Sandpack，并执行一次编译，然后把结果回传”。它不是在后端立即完成，而是会让当前 Agent 运行先挂起。

### 工具约束

- 工具定义使用 Chat Completions 的 `tools=[{"type":"function","function":{...}}]` 形式注册
- `parallel_tool_calls` 固定为 `False`
- 每个工具参数都用 Pydantic 模型校验
- 参数校验失败时，返回结构化错误字符串给模型，不直接中断 turn
- 工具执行前后都要通过 `loguru` 打摘要日志，至少包含 `session_id`、`turn_id`、`tool_name`、耗时、执行结果
- 每轮模型响应必须调用工具，不能只输出普通文本
- 每轮模型响应只允许一个工具调用；若模型需要多个动作，必须拆成多轮
- 文件修改默认使用 `apply_diff`，不再采用整文件覆盖
- `apply_diff` 仅用于对已存在文件做精确、局部修改；若模型不确定目标内容，必须先调用 `read_files`
- `apply_diff` 的 `SEARCH` 段必须与原文件内容完全一致，包括缩进和空白
- 若一次需要多个局部修改，允许在单次 `apply_diff` 的 `diff` 参数里放多个 `SEARCH/REPLACE` block，但仍然算一次工具调用
- `delete_files` 仅允许删除当前 session workspace 中已存在的文件
- `complete_task` 是唯一合法的“任务完成”方式
- `run_sandpack` 是唯一前端工具
- system prompt 必须明确要求“不要用纯文本宣告完成，必须调用 `complete_task`；如果需要查看前端执行结果，必须调用 `run_sandpack`”
- 模型不接触真实文件系统、shell、网络、数据库

### `apply_diff` 参数格式

`apply_diff` 的定义建议参考以下结构：

```json
{
  "type": "function",
  "function": {
    "name": "apply_diff",
    "description": "Apply precise, targeted modifications to an existing file using one or more search/replace blocks. This tool is for surgical edits only; the SEARCH block must exactly match the existing content, including whitespace and indentation. Use read_files first if you are not confident in the exact content to search for.",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "The path of the file to modify, relative to the current workspace directory."
        },
        "diff": {
          "type": "string",
          "description": "A string containing one or more search/replace blocks defining the changes. The :start_line: is required and indicates the starting line number of the original content. Each block must follow this format:\n<<<<<<< SEARCH\n:start_line:[line_number]\n-------\n[exact content to find]\n=======\n[new content to replace with]\n>>>>>>> REPLACE"
        }
      },
      "required": ["path", "diff"],
      "additionalProperties": false
    },
    "strict": true
  }
}
```

`diff` 内容格式固定如下：

```text
<<<<<<< SEARCH
:start_line:[line_number]
-------
[exact content to find]
=======
[new content to replace with]
>>>>>>> REPLACE
```

如果同一文件需要多个局部修改，就在同一个 `diff` 字符串里顺序追加多个 block。

## 前端改造点

以 [frontend-vue3/src/components/AppProvider.vue](/Users/airzostorm/Documents/new-atoms/frontend-vue3/src/components/AppProvider.vue) 和 [frontend-vue3/src/composables/useSandpackManualRun.ts](/Users/airzostorm/Documents/new-atoms/frontend-vue3/src/composables/useSandpackManualRun.ts) 为主接线点。

### 会话层职责

前端需要补一层 `agent session` 控制逻辑，职责包括：

- 创建 session
- 在前端内存中保存当前 `session_id`
- 提交用户消息
- 订阅 SSE
- 渲染 assistant 增量文本
- 接收前端工具事件
- 基于当前 workspace 同步到 Sandpack
- 执行编译
- 回传 frontend tool result

第一版前端会话策略保持最简：

- `session_id` 仅保存在前端内存状态中，不写入 `localStorage`、`sessionStorage` 或 URL
- 页面刷新后直接丢失当前 session，由前端重新创建新 session
- 不做“刷新后恢复历史 session / workspace”的能力

### Sandpack 集成

- Sandpack 文件更新方式固定为使用 `useSandpack().sandpack.updateFile(...)` 和 `deleteFile(...)`
- 不直接重建整个 `SandpackProvider`
- 当前手动编译按钮可以保留，但真实循环里默认由 `run_sandpack` 工具触发自动编译

### 编译反馈标准化

[frontend-vue3/src/composables/useSandpackManualRun.ts](/Users/airzostorm/Documents/new-atoms/frontend-vue3/src/composables/useSandpackManualRun.ts) 需要扩展为统一回传：

- `result: "done" | "timeout"`
- `status: "success" | "compile_error" | "runtime_error" | "timeout"`
- `server_logs: string[]`
- `client_logs: unknown[]`
- `error_summary?: string`

## API 设计

### 1. `POST /api/sessions/create`

创建 session，返回：

- `session_id`
- 初始 messages
- 初始 workspace

### 2. `GET /api/sessions/{session_id}`

返回：

- 当前 messages
- 当前 workspace
- 当前 turn 状态

### 3. `GET /api/sessions/{session_id}/events`

SSE 事件流，事件类型固定为：

- `assistant.delta`
- `workspace.patch`
- `frontend.tool_call`
- `turn.completed`
- `turn.failed`

### 4. `POST /api/sessions/{session_id}/messages`

请求体：

```json
{ "content": "用户需求文本" }
```

响应体：

```json
{ "turn_id": "xxx", "state": "running" }
```

### 5. `POST /api/sessions/{session_id}/turns/{turn_id}/frontend-tool-result`

请求体：

```json
{
  "tool_name": "run_sandpack",
  "status": "success",
  "result": "done",
  "server_logs": [],
  "client_logs": [],
  "error_summary": null
}
```

响应体：

```json
{ "accepted": true }
```

### 关键结构

```ts
type WorkspacePatch = {
  ops: Array<
    | { op: "upsert"; path: string; code: string }
    | { op: "delete"; path: string }
  >
}

type CompileFeedback = {
  status: "success" | "compile_error" | "runtime_error" | "timeout"
  result: "done" | "timeout"
  server_logs: string[]
  client_logs: unknown[]
  error_summary?: string
}

type TurnState = "running" | "waiting_for_frontend" | "completed" | "failed"
```

## 测试计划

- 新开发环境能通过 `python -m venv .venv && pip install -r requirements.txt` 完成安装，不依赖 `uv`
- 创建 session 后，前端能把返回的 workspace 注入 Sandpack 并正常显示代码
- 前端能在内存中持有当前 `session_id` 并完成后续 `messages`、`events`、`frontend-tool-result` 调用
- 用户提交需求后，后端能通过 `chat.completions.create(..., tools=..., stream=True)` 产出 assistant 文本增量和至少一轮 tool call
- 当模型一次响应里返回多个 tool calls 时，后端能识别并拒绝该回合，返回约束错误后进入下一轮
- 当模型执行文件修改时，优先通过 `read_files` + `apply_diff` 完成局部变更，而不是整文件重写
- 当 `apply_diff` 的 `SEARCH` 内容不匹配当前文件时，后端能返回明确错误，让模型先重新读取文件
- 当前 workspace 发生改动后，前端能收到一次 `workspace.patch`
- 当模型调用 `run_sandpack` 时，后端能发出 `frontend.tool_call` 并将 turn 正确挂起
- 前端收到前端工具事件后，能基于 [frontend-vue3/src/composables/useSandpackManualRun.ts](/Users/airzostorm/Documents/new-atoms/frontend-vue3/src/composables/useSandpackManualRun.ts) 回传一次标准化 frontend tool result
- 当首次生成存在编译错误时，后端能把 compile feedback 带回下一轮模型调用并完成至少一次修复
- 当模型只输出普通文本、不调用 `complete_task` 或 `run_sandpack` 时，后端会触发一次约束重试，而不是把该文本当最终完成
- 当达到最大循环次数、前端掉线、或 compile 超时后，turn 会明确进入 `failed`，不会留下悬挂状态
- `loguru` 能输出统一格式日志，并覆盖应用启动、Agent 循环、tool call、异常这几类关键链路

## 默认假设

- `OPENAI_BASE_URL` 对应服务兼容 `AsyncOpenAI.chat.completions.create` 的 `tools`、`tool_choice`、`parallel_tool_calls` 和 `stream`
- 第一版模板固定为 `vite-vue`
- 第一版默认允许操作 `/src/App.vue`、`/src/main.js`、`/src/styles.css`，以及少量新增 `src/components/*` 文件
- 第一版不做数据库持久化；session 生命周期跟随 API 进程内存
- 第一版前端不持久化 `session_id`；刷新页面后重新创建 session
- 第一版不做视觉截图分析和浏览器 DOM 级判定，先把“代码生成 + 编译修复”闭环跑通
