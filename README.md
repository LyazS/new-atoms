# Btoms

Btoms 是一个前后端分离的会话式工作台：

- `backend/` 提供 FastAPI 接口、会话管理、鉴权和 agent 运行能力
- `frontend-vue3/` 提供 Vue 3 前端界面，用于会话管理、对话交互和 Sandpack 预览

## 项目结构

```text
.
├── backend/
├── docs/
└── frontend-vue3/
```

## 本地启动

### 1. 启动后端

后端依赖位于 `backend/requirements.txt`，示例：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
```

默认服务地址通常为 `http://127.0.0.1:8000`。

### 2. 启动前端

```bash
cd frontend-vue3
npm install
npm run dev
```

前端开发环境默认由 Vite 提供。

## 环境变量

可以参考 `backend/.env.example` 配置后端环境变量，例如：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `AUTH_SECRET_KEY`
- `DATABASE_URL`

## 说明

- 当前仓库前端品牌名已统一为 `Btoms`
- `docs/` 下保留了项目设计和实现说明
