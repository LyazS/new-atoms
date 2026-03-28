import { useEffect, useRef, useState } from "react";
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
  "/App.jsx": `export default function App() {
  return (
    <main style={styles.page}>
      <div style={styles.glowA} />
      <div style={styles.glowB} />
      <section style={styles.card}>
        <p style={styles.kicker}>Agent Generated Landing Page</p>
        <h1 style={styles.title}>Build bold ideas while chatting with your agent.</h1>
        <p style={styles.body}>
          Ask for layouts, components, or full-page redesigns and iterate live in the preview.
        </p>
        <div style={styles.actions}>
          <button style={styles.primary}>Launch Demo</button>
          <button style={styles.secondary}>View Prompt</button>
        </div>
      </section>
    </main>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    position: "relative",
    overflow: "hidden",
    display: "grid",
    placeItems: "center",
    background:
      "radial-gradient(circle at top, #ffd58a 0%, #f29559 28%, #8a2a20 62%, #19090b 100%)",
    color: "#fff7ed",
    fontFamily: "Arial, sans-serif",
    padding: 24
  },
  glowA: {
    position: "absolute",
    width: 280,
    height: 280,
    borderRadius: "50%",
    background: "rgba(255, 244, 185, 0.26)",
    filter: "blur(24px)",
    top: 40,
    left: 20
  },
  glowB: {
    position: "absolute",
    width: 220,
    height: 220,
    borderRadius: "50%",
    background: "rgba(255, 144, 88, 0.24)",
    filter: "blur(30px)",
    bottom: 48,
    right: 30
  },
  card: {
    position: "relative",
    zIndex: 1,
    width: "min(720px, 100%)",
    borderRadius: 32,
    padding: 36,
    background: "rgba(33, 10, 9, 0.72)",
    border: "1px solid rgba(255,255,255,0.12)",
    backdropFilter: "blur(18px)",
    boxShadow: "0 30px 90px rgba(0,0,0,0.28)"
  },
  kicker: {
    margin: 0,
    textTransform: "uppercase",
    letterSpacing: "0.18em",
    fontSize: 12,
    color: "#ffd7b0"
  },
  title: {
    marginTop: 16,
    marginBottom: 16,
    fontSize: "clamp(2.6rem, 7vw, 4.6rem)",
    lineHeight: 0.95
  },
  body: {
    margin: 0,
    maxWidth: 520,
    fontSize: 18,
    lineHeight: 1.6,
    color: "rgba(255,247,237,0.78)"
  },
  actions: {
    display: "flex",
    gap: 14,
    flexWrap: "wrap",
    marginTop: 28
  },
  primary: {
    border: 0,
    borderRadius: 999,
    padding: "14px 22px",
    fontWeight: 700,
    background: "#fff2bd",
    color: "#4d1507",
    cursor: "pointer"
  },
  secondary: {
    borderRadius: 999,
    padding: "14px 22px",
    fontWeight: 700,
    border: "1px solid rgba(255,255,255,0.18)",
    background: "transparent",
    color: "#fff7ed",
    cursor: "pointer"
  }
};`
  ,
  "/index.jsx": `import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
`
};

function App() {
  const [messages, setMessages] = useState(starterMessages);
  const [draft, setDraft] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const [activeTab, setActiveTab] = useState("code");
  const [isFileTreeOpen, setIsFileTreeOpen] = useState(true);
  const [isTerminalOpen, setIsTerminalOpen] = useState(true);
  const previewRef = useRef(null);

  useEffect(() => {
    if (activeTab !== "preview") {
      return;
    }

    const refreshPreview = () => {
      const client = previewRef.current?.getClient?.();
      if (client?.dispatch) {
        client.dispatch({ type: "refresh" });
      }

      window.dispatchEvent(new Event("resize"));
    };

    const firstFrame = window.requestAnimationFrame(refreshPreview);
    const timer = window.setTimeout(refreshPreview, 250);

    return () => {
      window.cancelAnimationFrame(firstFrame);
      window.clearTimeout(timer);
    };
  }, [activeTab]);

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
                visibleFiles: ["/App.jsx", "/index.jsx"],
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
                      ref={previewRef}
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
