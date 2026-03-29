<script setup lang="ts">
import AppHero from './AppHero.vue'
import ChatPanel from './ChatPanel.vue'
import SandpackStudio from './SandpackStudio.vue'
import { useAppProviderState } from '../composables/useAppProviderState'

const {
  compileStatusLabel,
  connectionLabel,
  draft,
  handleCreateSession,
  handleManualRunResult,
  handleRunnerStateChange,
  handleSubmit,
  isHydrating,
  isThinking,
  lastCompileFeedback,
  messages,
  runRequestKey,
  sessionId,
  workspaceFiles,
} = useAppProviderState()
</script>

<template>
  <div class="app-shell">
    <AppHero :connection-label="connectionLabel" />

    <main class="workspace">
      <ChatPanel
        v-model:draft="draft"
        :compile-status-label="compileStatusLabel"
        :is-hydrating="isHydrating"
        :is-thinking="isThinking"
        :messages="messages"
        :session-id="sessionId"
        @create-session="handleCreateSession"
        @submit="handleSubmit"
      />

      <SandpackStudio
        :last-compile-feedback="lastCompileFeedback"
        :run-request-key="runRequestKey"
        :workspace-files="workspaceFiles"
        @manual-run-result="handleManualRunResult"
        @runner-state-change="handleRunnerStateChange"
      />
    </main>
  </div>
</template>
