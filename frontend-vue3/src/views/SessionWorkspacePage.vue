<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ChatPanel from '../components/ChatPanel.vue'
import SandpackStudio from '../components/SandpackStudio.vue'
import { useAuthState } from '../composables/useAuthState'
import { useSessionConversationState } from '../composables/useSessionConversationState'

const route = useRoute()
const router = useRouter()
const { logout, isAuthenticated } = useAuthState()
const {
  compileStatusLabel,
  disconnectEventStream,
  draft,
  handleManualRunResult,
  handleRunnerStateChange,
  handleSubmit,
  isHydrating,
  isThinking,
  lastCompileFeedback,
  loadSession,
  messages,
  runRequestKey,
  sessionTitle,
  workspaceFiles,
} = useSessionConversationState()

const sessionId = computed(() => String(route.params.sessionId ?? ''))

async function hydrateSession() {
  if (!sessionId.value) {
    await router.replace('/sessions')
    return
  }

  const ok = await loadSession(sessionId.value)
  if (!ok && !isAuthenticated.value) {
    await router.replace('/auth')
  }
}

async function handleLogout() {
  disconnectEventStream()
  logout()
  await router.push('/auth')
}

watch(sessionId, () => {
  void hydrateSession()
}, { immediate: true })

watch(isAuthenticated, (value) => {
  if (!value) {
    disconnectEventStream()
    void router.replace('/auth')
  }
})
</script>

<template>
  <div class="app-shell">
    <header class="hero">
      <div class="hero-main">
        <p class="eyebrow">Session Workspace</p>
        <p class="hero-copy">{{ sessionTitle }}</p>
      </div>
      <div class="hero-actions page-hero-actions">
        <button type="button" class="secondary-button" @click="router.push('/sessions')">返回会话管理</button>
        <button type="button" class="secondary-button" @click="handleLogout">退出登录</button>
      </div>
    </header>

    <main class="workspace">
      <ChatPanel
        v-model:draft="draft"
        :is-hydrating="isHydrating"
        :is-thinking="isThinking"
        :messages="messages"
        @submit="handleSubmit"
      />

      <SandpackStudio
        :compile-status-label="compileStatusLabel"
        :last-compile-feedback="lastCompileFeedback"
        :run-request-key="runRequestKey"
        :workspace-files="workspaceFiles"
        @manual-run-result="handleManualRunResult"
        @runner-state-change="handleRunnerStateChange"
      />
    </main>
  </div>
</template>
