<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthState } from '../composables/useAuthState'
import { useSessionListState } from '../composables/useSessionListState'

const router = useRouter()
const { currentUser, logout } = useAuthState()
const { createSession, deleteSession, fetchSessions, isLoading, persistLastSessionId, sessions } =
  useSessionListState()

const isCreating = ref(false)
const errorMessage = ref('')

async function loadSessions() {
  errorMessage.value = ''
  try {
    await fetchSessions()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '加载会话失败。'
  }
}

async function handleCreateSession() {
  isCreating.value = true
  errorMessage.value = ''
  try {
    const sessionId = await createSession()
    await router.push(`/sessions/${sessionId}`)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '创建项目失败。'
  } finally {
    isCreating.value = false
  }
}

async function handleDeleteSession(sessionId: string) {
  try {
    await deleteSession(sessionId)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '删除会话失败。'
  }
}

async function handleLogout() {
  logout()
  await router.push('/auth')
}

async function handleOpenSession(sessionId: string) {
  persistLastSessionId(sessionId)
  await router.push(`/sessions/${sessionId}`)
}

onMounted(() => {
  void loadSessions()
})
</script>

<template>
  <main class="sessions-page">
    <header class="page-hero">
      <div>
        <p class="eyebrow">Btoms Workspace</p>
        <h1>会话管理</h1>
        <p class="hero-copy">
          {{ currentUser?.username }}，你可以从这里进入 Btoms 的项目列表，创建新项目，或者回到任意历史会话继续工作。
        </p>
      </div>

      <div class="page-hero-actions">
        <button type="button" class="secondary-button" @click="handleLogout">退出登录</button>
        <button type="button" class="primary-button" :disabled="isCreating" @click="handleCreateSession">
          创建新项目
        </button>
      </div>
    </header>

    <section class="session-list-shell">
      <p v-if="errorMessage" class="panel-error">{{ errorMessage }}</p>

      <div v-if="isLoading" class="session-empty-state">正在加载你的会话列表...</div>
      <div v-else-if="!sessions.length" class="session-empty-state">
        现在还没有任何项目，点击右上角“创建新项目”开始第一条会话。
      </div>

      <ul v-else class="session-list">
        <li v-for="session in sessions" :key="session.id" class="session-list-item">
          <button type="button" class="session-card" @click="handleOpenSession(session.id)">
            <div>
              <p class="session-card-kicker">Project</p>
              <h2>{{ session.title }}</h2>
              <p class="session-card-preview">{{ session.preview ?? '还没有消息，适合从这里开启新的项目说明。' }}</p>
            </div>
            <div class="session-card-meta">
              <span>更新于 {{ new Date(session.updated_at).toLocaleString() }}</span>
            </div>
          </button>
          <button type="button" class="session-delete-button" @click="handleDeleteSession(session.id)">
            删除
          </button>
        </li>
      </ul>
    </section>
  </main>
</template>
