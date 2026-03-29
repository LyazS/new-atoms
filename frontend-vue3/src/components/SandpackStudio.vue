<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import {
  SandpackCodeEditor,
  SandpackConsole,
  SandpackFileExplorer,
  SandpackPreview,
  SandpackProvider,
} from 'sandpack-vue3'

import type { CompileFeedback } from '../composables/useSandpackManualRun'
import ManualRunBridge from './ManualRunBridge.vue'

const props = defineProps<{
  lastCompileFeedback: CompileFeedback | null
  runRequestKey: number
  workspaceFiles: Record<string, string>
}>()

const emit = defineEmits<{
  manualRunResult: [feedback: CompileFeedback]
  runnerStateChange: [value: boolean]
}>()

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
</script>

<template>
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
            @click="activeTab = 'code'"
          >
            代码
          </button>
          <button
            type="button"
            role="tab"
            :aria-selected="activeTab === 'preview'"
            :class="['tab-button', { 'is-active': activeTab === 'preview' }]"
            @click="activeTab = 'preview'"
          >
            预览
          </button>
        </div>
        <div class="status-pill">{{ props.lastCompileFeedback?.status ?? 'blank' }}</div>
      </div>
    </div>

    <div class="sandpack-frame">
      <SandpackProvider
        template="vite-vue"
        :files="workspaceFiles"
        theme="dark"
        :options="{
          activeFile: '/src/App.vue',
          visibleFiles: ['/src/App.vue', '/src/main.js', '/src/styles.css'],
          autorun: true,
          autoReload: true,
          initMode: 'immediate',
        }"
      >
        <div class="sandpack-tab-panel">
          <div v-show="activeTab === 'code'" class="sandpack-view is-active">
            <div class="code-workbench">
              <div class="workbench-toolbar">
                <ManualRunBridge
                  :workspace-files="workspaceFiles"
                  :run-request-key="runRequestKey"
                  @manual-run-result="emit('manualRunResult', $event)"
                  @running-change="emit('runnerStateChange', $event)"
                />
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
</template>
