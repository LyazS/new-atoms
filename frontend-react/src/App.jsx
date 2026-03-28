import { useState } from "react";
import {
  SandpackCodeEditor,
  SandpackConsole,
  SandpackFileExplorer,
  SandpackPreview,
  SandpackProvider
} from "@codesandbox/sandpack-react";

const starterMessages = [
  {
    id: "assistant-1",
    role: "assistant",
    content:
      "我是你的前端 Agent。你可以在这里描述需求，我会在右侧 Sandpack 里逐步生成和调整代码。"
  },
  {
    id: "user-1",
    role: "user",
    content: "帮我做一个更有未来感的欢迎页，按钮要醒目一点。"
  },
  {
    id: "assistant-2",
    role: "assistant",
    content:
      "收到，我先把视觉方向切到暖色霓虹和大字标题，并保留一个明确的 CTA。右侧示例代码已经可以直接预览。"
  }
];

const sandpackFiles = {
  "/App.jsx": `const actions = [
  { label: "Launch Demo", kind: "primary" },
  { label: "View Prompt", kind: "secondary" }
];

export default function App() {
  return (
    <main className="page-shell">
      <div className="glow glow-a" />
      <div className="glow glow-b" />
      <section className="card">
        <p className="kicker">Agent Generated Vue Page</p>
        <h1>Build bold ideas while chatting with your agent.</h1>
        <p className="body">
          Ask for layouts, components, or full-page redesigns and iterate live in the preview.
        </p>
        <div className="actions">
          {actions.map((action) => (
            <button key={action.label} className={action.kind}>
              {action.label}
            </button>
          ))}
        </div>
      </section>
    </main>
  );
}
`
  ,
  "/index.jsx": `import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
`,
  "/styles.css": `:root {
  color: #fff7ed;
  font-family: "Space Grotesk", "Noto Sans SC", sans-serif;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
}

.page-shell {
  min-height: 100vh;
  position: relative;
  overflow: hidden;
  display: grid;
  place-items: center;
  padding: 24px;
  background:
    radial-gradient(circle at top, #ffd58a 0%, #f29559 28%, #8a2a20 62%, #19090b 100%);
}

.glow {
  position: absolute;
  border-radius: 999px;
  filter: blur(24px);
}

.glow-a {
  width: 280px;
  height: 280px;
  top: 40px;
  left: 20px;
  background: rgba(255, 244, 185, 0.26);
}

.glow-b {
  width: 220px;
  height: 220px;
  right: 30px;
  bottom: 48px;
  background: rgba(255, 144, 88, 0.24);
  filter: blur(30px);
}

.card {
  position: relative;
  zIndex: 1;
  width: min(720px, 100%);
  padding: 36px;
  border-radius: 32px;
  background: rgba(33, 10, 9, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(18px);
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.28);
}

.kicker {
  margin: 0;
  color: #ffd7b0;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 12px;
}

h1 {
  margin: 16px 0;
  font-size: clamp(2.6rem, 7vw, 4.6rem);
  line-height: 0.95;
}

.body {
  margin: 0;
  max-width: 520px;
  color: rgba(255, 247, 237, 0.78);
  font-size: 18px;
  line-height: 1.6;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 28px;
}

button {
  border: 0;
  border-radius: 999px;
  padding: 14px 22px;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.primary {
  background: #fff2bd;
  color: #4d1507;
}

.secondary {
  color: #fff7ed;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.18);
}
`
};

function App() {
  const [messages, setMessages] = useState(starterMessages);
  const [draft, setDraft] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const [activeTab, setActiveTab] = useState("code");
  const [isFileTreeOpen, setIsFileTreeOpen] = useState(true);
  const [isTerminalOpen, setIsTerminalOpen] = useState(true);
  const handleTabChange = (nextTab) => {
    setActiveTab(nextTab);
  };

  const handleSubmit = (event) => {
    event.preventDefault();

    const content = draft.trim();
    if (!content) {
      return;
    }

    const userMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content
    };

    setMessages((current) => [...current, userMessage]);
    setDraft("");
    setIsThinking(true);

    window.setTimeout(() => {
      setMessages((current) => [
        ...current,
        {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content:
            "我已经记录这个需求。这里现在接的是前端演示数据，你可以把提交逻辑替换成真实 Agent API，然后把返回的代码同步到右侧 Sandpack 文件。"
        }
      ]);
      setIsThinking(false);
    }, 900);
  };

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Standalone Frontend</p>
          <h1>Agent Chat + Live Sandpack Studio</h1>
          <p className="hero-copy">
            一个独立前端工作台，左侧对话驱动生成，右侧即时预览代码效果。
          </p>
        </div>
        <div className="hero-badge">
          <span className="hero-badge-dot" />
          Ready for API wiring
        </div>
      </header>

      <main className="workspace">
        <section className="panel chat-panel">
          <div className="panel-header">
            <div>
              <p className="panel-kicker">Agent Console</p>
              <h2>聊天框</h2>
            </div>
            <div className="status-pill">Mock Stream</div>
          </div>

          <div className="messages" aria-live="polite">
            {messages.map((message) => (
              <article
                key={message.id}
                className={`message message-${message.role}`}
              >
                <div className="message-role">
                  {message.role === "assistant" ? "Agent" : "You"}
                </div>
                <p>{message.content}</p>
              </article>
            ))}

            <article
              className="message message-assistant"
              hidden={!isThinking}
            >
              <div className="message-role">Agent</div>
              <p>正在整理界面和代码变更建议...</p>
            </article>
          </div>

          <form className="composer" onSubmit={handleSubmit}>
            <label className="composer-label" htmlFor="prompt">
              把你的页面需求发给 Agent
            </label>
            <textarea
              id="prompt"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="例如：做一个产品介绍页，使用暖色渐变背景，增加 pricing section。"
              rows={4}
            />
            <div className="composer-footer">
              <p>当前是前端演示版，适合后续接入你的多轮 Agent 接口。</p>
              <button type="submit">发送需求</button>
            </div>
          </form>
        </section>

        <section className="panel sandbox-panel">
          <div className="panel-header">
            <div>
              <p className="panel-kicker">Interactive Preview</p>
              <h2>Sandpack</h2>
            </div>
            <div className="sandbox-toolbar">
              <div className="tab-switcher" role="tablist" aria-label="Sandpack views">
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === "code"}
                  className={`tab-button ${activeTab === "code" ? "is-active" : ""}`}
                  onClick={() => handleTabChange("code")}
                >
                  代码
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === "preview"}
                  className={`tab-button ${activeTab === "preview" ? "is-active" : ""}`}
                  onClick={() => handleTabChange("preview")}
                >
                  预览
                </button>
              </div>
              <div className="status-pill">React Template</div>
            </div>
          </div>

          <div className="sandpack-frame">
            <SandpackProvider
              template="vite-react"
              files={sandpackFiles}
              theme="dark"
              options={{
                activeFile: "/App.jsx",
                visibleFiles: ["/App.jsx", "/index.jsx", "/styles.css"],
                autorun: true,
                initMode: "immediate",
                recompileMode: "immediate",
                showNavigator: true,
                showTabs: true
              }}
            >
              <div className="sandpack-tab-panel">
                <div
                  className="sandpack-view is-active"
                  hidden={activeTab !== "code"}
                >
                  <div className="code-workbench">
                    <div className="workbench-toolbar">
                      <button
                        type="button"
                        className={`pane-toggle ${isFileTreeOpen ? "is-open" : ""}`}
                        onClick={() => setIsFileTreeOpen((current) => !current)}
                      >
                        {isFileTreeOpen ? "隐藏目录树" : "显示目录树"}
                      </button>
                      <button
                        type="button"
                        className={`pane-toggle ${isTerminalOpen ? "is-open" : ""}`}
                        onClick={() => setIsTerminalOpen((current) => !current)}
                      >
                        {isTerminalOpen ? "隐藏终端" : "显示终端"}
                      </button>
                    </div>

                    <div
                      className={`workbench-body ${isFileTreeOpen ? "" : "is-tree-collapsed"}`}
                    >
                      <aside
                        className="file-tree-panel"
                        hidden={!isFileTreeOpen}
                      >
                        <div className="file-tree-header">Files</div>
                        <SandpackFileExplorer autoHiddenFiles={false} />
                      </aside>

                      <div
                        className={`editor-column ${isTerminalOpen ? "" : "is-terminal-collapsed"}`}
                      >
                        <div className="editor-panel">
                          <SandpackCodeEditor showLineNumbers />
                        </div>

                        <section
                          className="terminal-panel"
                          hidden={!isTerminalOpen}
                        >
                          <div className="terminal-header">Terminal</div>
                          <SandpackConsole
                            resetOnPreviewRestart
                            showSyntaxError
                            style={{ height: "100%" }}
                          />
                        </section>
                      </div>
                    </div>
                  </div>
                </div>

                <div
                  className="sandpack-view is-active"
                  hidden={activeTab !== "preview"}
                >
                  <div className="preview-panel">
                    <SandpackPreview
                      showNavigator={false}
                      showRefreshButton
                      showRestartButton={false}
                      showOpenInCodeSandbox={false}
                    />
                  </div>
                </div>
              </div>
            </SandpackProvider>
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
