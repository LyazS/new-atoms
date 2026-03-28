# Agent Sandbox Studio

一个独立的前端目录，提供：

- 左侧 Agent 聊天框
- 右侧 Sandpack 实时代码编辑和预览
- 适合后续接入真实 Agent 接口的前端壳子

## 启动

```bash
npm install
npm run dev
```

## 说明

- 聊天区当前使用本地 mock 数据，提交逻辑在 `src/App.jsx` 中。
- 右侧 Sandpack 已内置一个 React 示例页面，可直接作为代码生成预览区。
