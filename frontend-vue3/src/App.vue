<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import {
  SandpackProvider,
  SandpackCodeEditor,
  SandpackConsole,
  SandpackFileExplorer,
  SandpackPreview,
} from 'sandpack-vue3'

type MessageRole = 'assistant' | 'user'

type ChatMessage = {
  id: string
  role: MessageRole
  content: string
}

const starterMessages: ChatMessage[] = [
  {
    id: 'assistant-1',
    role: 'assistant',
    content:
      '我是你的前端 Agent。你可以在这里描述需求，我会在右侧 Sandpack 里逐步生成和调整代码。',
  },
  {
    id: 'user-1',
    role: 'user',
    content: '帮我做一个更有未来感的欢迎页，按钮要醒目一点。',
  },
  {
    id: 'assistant-2',
    role: 'assistant',
    content:
      '收到，我先把视觉方向切到暖色霓虹和大字标题，并保留一个明确的 CTA。右侧示例代码已经可以直接预览。',
  },
]

const sandpackFiles = {
  '/src/App.vue': `<script setup>
const actions = [
  { label: "Launch Demo", kind: "primary" },
  { label: "View Prompt", kind: "secondary" },
];
<\/script>

<template>
  <main class="page-shell">
    <div class="glow glow-a"></div>
    <div class="glow glow-b"></div>
    <section class="card">
      <p class="kicker">Agent Generated Vue Page</p>
      <h1>Build bold ideas while chatting with your agent.</h1>
      <p class="body">
        Ask for layouts, sections, or full-page redesigns and iterate live in the preview.
      </p>
      <div class="actions">
        <button
          v-for="action in actions"
          :key="action.label"
          :class="action.kind"
        >
          {{ action.label }}
        </button>
      </div>
    </section>
  </main>
</template>

<style>
:root {
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
  z-index: 1;
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
</style>
`,
  '/src/main.js': `import { createApp } from "vue";
import App from "./App.vue";
import "./styles.css";

createApp(App).mount("#app");
`,
  '/src/styles.css': `:root {
  color: #fff7ed;
  font-family: "Space Grotesk", "Noto Sans SC", sans-serif;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
}
`,
}

const messages = ref<ChatMessage[]>(starterMessages)
const draft = ref('')
const isThinking = ref(false)
const activeTab = ref<'code' | 'preview'>('code')
const isFileTreeOpen = ref(true)
const isTerminalOpen = ref(true)
watch(activeTab, async (nextTab) => {
  if (nextTab !== 'preview') {
    return
  }

  await nextTick()
  window.requestAnimationFrame(() => {
    window.dispatchEvent(new Event('resize'))
  })
})

function handleTabChange(nextTab: 'code' | 'preview') {
  activeTab.value = nextTab
}

function handleSubmit() {
  const content = draft.value.trim()
  if (!content) {
    return
  }

  messages.value = [
    ...messages.value,
    {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
    },
  ]
  draft.value = ''
  isThinking.value = true

  window.setTimeout(() => {
    messages.value = [
      ...messages.value,
      {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content:
          '我已经记录这个需求。这里现在接的是前端演示数据，你可以把提交逻辑替换成真实 Agent API，然后把返回的代码同步到右侧 Sandpack 文件。',
      },
    ]
    isThinking.value = false
  }, 900)
}
</script>

<template>
  <div class="app-shell">
    <header class="hero">
      <div>
        <p class="eyebrow">Standalone Frontend</p>
        <h1>Agent Chat + Live Sandpack Studio</h1>
        <p class="hero-copy">一个独立前端工作台，左侧对话驱动生成，右侧即时预览代码效果。</p>
      </div>
      <div class="hero-badge">
        <span class="hero-badge-dot" />
        Ready for API wiring
      </div>
    </header>

    <main class="workspace">
      <section class="panel chat-panel">
        <div class="panel-header">
          <div>
            <p class="panel-kicker">Agent Console</p>
            <h2>聊天框</h2>
          </div>
          <div class="status-pill">Mock Stream</div>
        </div>

        <div class="messages" aria-live="polite">
          <article
            v-for="message in messages"
            :key="message.id"
            :class="['message', `message-${message.role}`]"
          >
            <div class="message-role">
              {{ message.role === 'assistant' ? 'Agent' : 'You' }}
            </div>
            <p>{{ message.content }}</p>
          </article>

          <article v-show="isThinking" class="message message-assistant">
            <div class="message-role">Agent</div>
            <p>正在整理界面和代码变更建议...</p>
          </article>
        </div>

        <form class="composer" @submit.prevent="handleSubmit">
          <label class="composer-label" for="prompt">把你的页面需求发给 Agent</label>
          <textarea
            id="prompt"
            v-model="draft"
            placeholder="例如：做一个产品介绍页，使用暖色渐变背景，增加 pricing section。"
            rows="4"
          />
          <div class="composer-footer">
            <p>当前是前端演示版，适合后续接入你的多轮 Agent 接口。</p>
            <button type="submit">发送需求</button>
          </div>
        </form>
      </section>

      <section class="panel sandbox-panel">
        <div class="panel-header">
          <div>
            <p class="panel-kicker">Interactive Preview</p>
            <h2>Sandpack</h2>
          </div>
          <div class="sandbox-toolbar">
            <div class="tab-switcher" role="tablist" aria-label="Sandpack views">
              <button
                type="button"
                role="tab"
                :aria-selected="activeTab === 'code'"
                :class="['tab-button', { 'is-active': activeTab === 'code' }]"
                @click="handleTabChange('code')"
              >
                代码
              </button>
              <button
                type="button"
                role="tab"
                :aria-selected="activeTab === 'preview'"
                :class="['tab-button', { 'is-active': activeTab === 'preview' }]"
                @click="handleTabChange('preview')"
              >
                预览
              </button>
            </div>
            <div class="status-pill">Vue Template</div>
          </div>
        </div>

        <div class="sandpack-frame">
          <SandpackProvider
            template="vite-vue"
            :files="sandpackFiles"
            theme="dark"
            :options="{
              activeFile: '/src/App.vue',
              visibleFiles: ['/src/App.vue', '/src/main.js', '/src/styles.css'],
              autorun: true,
              initMode: 'immediate',
              recompileMode: 'immediate',
            }"
          >
            <div class="sandpack-tab-panel">
              <div v-show="activeTab === 'code'" class="sandpack-view is-active">
                <div class="code-workbench">
                  <div class="workbench-toolbar">
                    <button
                      type="button"
                      :class="['pane-toggle', { 'is-open': isFileTreeOpen }]"
                      @click="isFileTreeOpen = !isFileTreeOpen"
                    >
                      {{ isFileTreeOpen ? '隐藏目录树' : '显示目录树' }}
                    </button>
                    <button
                      type="button"
                      :class="['pane-toggle', { 'is-open': isTerminalOpen }]"
                      @click="isTerminalOpen = !isTerminalOpen"
                    >
                      {{ isTerminalOpen ? '隐藏终端' : '显示终端' }}
                    </button>
                  </div>

                  <div :class="['workbench-body', { 'is-tree-collapsed': !isFileTreeOpen }]">
                    <aside v-show="isFileTreeOpen" class="file-tree-panel">
                      <div class="file-tree-header">Files</div>
                      <SandpackFileExplorer :auto-hidden-files="false" />
                    </aside>

                    <div :class="['editor-column', { 'is-terminal-collapsed': !isTerminalOpen }]">
                      <div class="editor-panel">
                        <SandpackCodeEditor :show-line-numbers="true" />
                      </div>

                      <section v-show="isTerminalOpen" class="terminal-panel">
                        <div class="terminal-header">Terminal</div>
                        <SandpackConsole :reset-on-preview-restart="true" :show-syntax-error="true" />
                      </section>
                    </div>
                  </div>
                </div>
              </div>

              <div v-show="activeTab === 'preview'" class="sandpack-view is-active">
                <div class="preview-panel">
                  <SandpackPreview
                    :show-navigator="false"
                    :show-refresh-button="true"
                    :show-restart-button="false"
                    :show-open-in-code-sandbox="false"
                  />
                </div>
              </div>
            </div>
          </SandpackProvider>
        </div>
      </section>
    </main>
  </div>
</template>
