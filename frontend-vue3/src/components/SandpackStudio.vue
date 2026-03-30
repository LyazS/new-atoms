<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from 'vue'
import {
  SandpackCodeEditor,
  SandpackConsole,
  SandpackFileExplorer,
  SandpackPreview,
  SandpackProvider,
} from 'sandpack-vue3'

import type { CompileFeedback } from '../composables/useSandpackManualRun'
import { buildPreviewWorkspaceFiles } from '../lib/selection'
import type { SelectedNodeContext } from '../lib/selection'
import SandpackCompileBridge from './SandpackCompileBridge.vue'

const props = defineProps<{
  compileStatusLabel: string
  lastCompileFeedback: CompileFeedback | null
  runRequestKey: number
  selectedNodeContext: SelectedNodeContext | null
  selectionModeEnabled: boolean
  workspaceFiles: Record<string, string>
}>()

const emit = defineEmits<{
  manualRunResult: [feedback: CompileFeedback]
  nodeSelected: [selection: SelectedNodeContext]
  runnerStateChange: [value: boolean]
  selectionModeChange: [value: boolean]
}>()

const activeTab = ref<'code' | 'preview'>('preview')
const isFileTreeOpen = ref(true)
const isTerminalOpen = ref(false)
const previewPanelRef = useTemplateRef<HTMLDivElement>('previewPanel')

const PREVIEW_SELECTION_MESSAGE_SOURCE = 'btoms-preview-selection'

let previewIframe: HTMLIFrameElement | null = null
let previewMutationObserver: MutationObserver | null = null
let previewLoadCleanup: (() => void) | null = null

const previewWorkspaceFiles = computed(() =>
  buildPreviewWorkspaceFiles(props.workspaceFiles, props.selectionModeEnabled),
)

function postSelectionModeToPreview() {
  if (!previewIframe?.contentWindow) {
    return
  }

  previewIframe.contentWindow.postMessage(
    {
      source: PREVIEW_SELECTION_MESSAGE_SOURCE,
      type: 'selection-mode',
      enabled: props.selectionModeEnabled,
    },
    '*',
  )
}

function cleanupPreviewIframe() {
  previewLoadCleanup?.()
  previewLoadCleanup = null
  previewIframe = null
}

function bindPreviewIframe(nextIframe: HTMLIFrameElement | null) {
  if (previewIframe === nextIframe) {
    return
  }

  cleanupPreviewIframe()
  previewIframe = nextIframe

  if (!previewIframe) {
    return
  }

  const handleLoad = () => {
    window.setTimeout(() => {
      postSelectionModeToPreview()
    }, 120)
  }

  previewIframe.addEventListener('load', handleLoad)
  previewLoadCleanup = () => {
    previewIframe?.removeEventListener('load', handleLoad)
  }

  handleLoad()
}

function scanPreviewIframe() {
  const nextIframe = previewPanelRef.value?.querySelector('iframe') ?? null
  bindPreviewIframe(nextIframe)
}

function handleWindowMessage(event: MessageEvent) {
  const data = event.data
  if (!data || data.source !== PREVIEW_SELECTION_MESSAGE_SOURCE || data.type !== 'node-selected') {
    return
  }

  emit('nodeSelected', data.payload as SelectedNodeContext)
}

watch(activeTab, async (nextTab) => {
  if (nextTab !== 'preview') {
    return
  }

  await nextTick()
  window.requestAnimationFrame(() => {
    window.dispatchEvent(new Event('resize'))
  })
})

watch(
  () => props.selectionModeEnabled,
  () => {
    postSelectionModeToPreview()
  },
)

watch(
  previewWorkspaceFiles,
  () => {
    window.setTimeout(() => {
      scanPreviewIframe()
      postSelectionModeToPreview()
    }, 120)
  },
  { deep: true },
)

onMounted(() => {
  window.addEventListener('message', handleWindowMessage)
  previewMutationObserver = new MutationObserver(() => {
    scanPreviewIframe()
  })
  if (previewPanelRef.value) {
    previewMutationObserver.observe(previewPanelRef.value, { childList: true, subtree: true })
  }
  scanPreviewIframe()
})

onBeforeUnmount(() => {
  window.removeEventListener('message', handleWindowMessage)
  previewMutationObserver?.disconnect()
  previewMutationObserver = null
  cleanupPreviewIframe()
})
</script>

<template>
  <section class="panel sandbox-panel">
    <div class="panel-header sandbox-panel-header">
      <div class="sandbox-toolbar">
        <div class="status-pill sandbox-status-pill">{{ props.compileStatusLabel }}</div>
        <button
          type="button"
          :class="['secondary-button', 'selection-mode-button', { 'is-active': props.selectionModeEnabled }]"
          @click="emit('selectionModeChange', !props.selectionModeEnabled)"
        >
          {{ props.selectionModeEnabled ? '点选编辑已开启' : '点选编辑已关闭' }}
        </button>
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
      </div>
    </div>

    <div class="sandpack-frame">
      <SandpackProvider
        :custom-setup="{
          entry: '/index.html',
          environment: 'node',
          dependencies: {
            vue: '^3.3.2',
          },
          devDependencies: {
            '@vitejs/plugin-vue': '^4.2.3',
            'esbuild-wasm': '^0.17.19',
            vite: '4.2.2',
          },
        }"
        :files="previewWorkspaceFiles"
        theme="dark"
        :options="{
          activeFile: '/src/App.vue',
          visibleFiles: [
            '/src/App.vue',
            '/src/main.js',
            '/src/styles.css',
            '/package.json',
            '/index.html',
            '/vite.config.ts',
          ],
          autorun: true,
          autoReload: true,
          initMode: 'immediate',
        }"
      >
        <SandpackCompileBridge
          :workspace-files="previewWorkspaceFiles"
          :run-request-key="runRequestKey"
          @manual-run-result="emit('manualRunResult', $event)"
          @running-change="emit('runnerStateChange', $event)"
        />
        <div class="sandpack-tab-panel">
          <div v-show="activeTab === 'code'" class="sandpack-view is-active">
            <div class="code-workbench">
              <div :class="['workbench-body', { 'is-tree-collapsed': !isFileTreeOpen }]">
                <aside :class="['file-tree-panel', { 'is-collapsed': !isFileTreeOpen }]">
                  <div class="file-tree-header">
                    <span v-show="isFileTreeOpen">Files</span>
                    <button
                      type="button"
                      class="file-tree-icon-button"
                      :aria-label="isFileTreeOpen ? '隐藏目录树' : '显示目录树'"
                      :title="isFileTreeOpen ? '隐藏目录树' : '显示目录树'"
                      @click="isFileTreeOpen = !isFileTreeOpen"
                    >
                      <svg
                        viewBox="0 0 16 16"
                        aria-hidden="true"
                        :class="['file-tree-icon', { 'is-collapsed': !isFileTreeOpen }]"
                      >
                        <path
                          d="M10.5 3.5 6 8l4.5 4.5"
                          fill="none"
                          stroke="currentColor"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                          stroke-width="1.6"
                        />
                      </svg>
                    </button>
                  </div>
                  <SandpackFileExplorer v-show="isFileTreeOpen" :auto-hidden-files="false" />
                </aside>

                <div :class="['editor-column', { 'is-terminal-collapsed': !isTerminalOpen }]">
                  <div class="editor-panel">
                    <SandpackCodeEditor :show-line-numbers="true" />
                  </div>

                  <section :class="['terminal-panel', { 'is-collapsed': !isTerminalOpen }]">
                    <div class="terminal-header">
                      <span>Terminal</span>
                      <button
                        type="button"
                        class="terminal-icon-button"
                        :aria-label="isTerminalOpen ? '隐藏终端' : '显示终端'"
                        :title="isTerminalOpen ? '隐藏终端' : '显示终端'"
                        @click="isTerminalOpen = !isTerminalOpen"
                      >
                        <svg
                          viewBox="0 0 16 16"
                          aria-hidden="true"
                          :class="['terminal-icon', { 'is-collapsed': !isTerminalOpen }]"
                        >
                          <path
                            d="M3.5 5.5 8 10l4.5-4.5"
                            fill="none"
                            stroke="currentColor"
                            stroke-linecap="round"
                            stroke-linejoin="round"
                            stroke-width="1.6"
                          />
                        </svg>
                      </button>
                    </div>
                    <SandpackConsole
                      v-show="isTerminalOpen"
                      :reset-on-preview-restart="true"
                      :show-syntax-error="true"
                    />
                  </section>
                </div>
              </div>
            </div>
          </div>

          <div v-show="activeTab === 'preview'" class="sandpack-view is-active">
            <div ref="previewPanel" class="preview-panel">
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
