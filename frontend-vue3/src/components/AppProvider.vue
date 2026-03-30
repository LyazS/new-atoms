<script setup lang="ts">
import AppHero from './AppHero.vue'
import ChatPanel from './ChatPanel.vue'
import SandpackStudio from './SandpackStudio.vue'
import { useAppProviderState } from '../composables/useAppProviderState'

const {
  compileStatusLabel,
  connectionLabel,
  draft,
  handleManualRunResult,
  handleRunnerStateChange,
  handleSubmit,
  isHydrating,
  isThinking,
  lastCompileFeedback,
  messages,
  runRequestKey,
  workspaceFiles,
} = useAppProviderState()
</script>

<template>
  <div class="app-shell">
    <AppHero :connection-label="connectionLabel" />

    <main class="workspace">
      <ChatPanel
        v-model:draft="draft"
        :is-hydrating="isHydrating"
        :is-thinking="isThinking"
        :messages="messages"
        :selected-node-context="null"
        :selection-mode-enabled="false"
        @submit="handleSubmit"
      />

      <SandpackStudio
        :compile-status-label="compileStatusLabel"
        :last-compile-feedback="lastCompileFeedback"
        :run-request-key="runRequestKey"
        :selected-node-context="null"
        :selection-mode-enabled="false"
        :workspace-files="workspaceFiles"
        @manual-run-result="handleManualRunResult"
        @node-selected="() => undefined"
        @runner-state-change="handleRunnerStateChange"
        @selection-mode-change="() => undefined"
      />
    </main>
  </div>
</template>
