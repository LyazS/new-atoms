import { ref } from 'vue'

import { ApiError, apiFetch, apiJson } from '../lib/api'
import { useAuthState } from './useAuthState'

export type SessionListItem = {
  id: string
  title: string
  created_at: string
  updated_at: string
  last_active_at: string
  preview: string | null
}

const LAST_SESSION_STORAGE_KEY = 'new-atoms-last-session-id'

export function useSessionListState() {
  const { accessToken, logout } = useAuthState()
  const sessions = ref<SessionListItem[]>([])
  const isLoading = ref(false)

  function persistLastSessionId(sessionId: string | null) {
    if (!sessionId) {
      window.localStorage.removeItem(LAST_SESSION_STORAGE_KEY)
      return
    }
    window.localStorage.setItem(LAST_SESSION_STORAGE_KEY, sessionId)
  }

  function readLastSessionId() {
    return window.localStorage.getItem(LAST_SESSION_STORAGE_KEY)
  }

  async function fetchSessions() {
    if (!accessToken.value) {
      sessions.value = []
      return []
    }

    isLoading.value = true
    try {
      const payload = await apiJson<SessionListItem[]>('/api/sessions', {}, accessToken.value)
      sessions.value = payload
      return payload
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        logout()
      }
      throw error
    } finally {
      isLoading.value = false
    }
  }

  async function createSession() {
    if (!accessToken.value) {
      throw new Error('Missing access token.')
    }

    const payload = await apiJson<{ session_id: string }>(
      '/api/sessions',
      { method: 'POST' },
      accessToken.value,
    )
    persistLastSessionId(payload.session_id)
    return payload.session_id
  }

  async function deleteSession(sessionId: string) {
    if (!accessToken.value) {
      throw new Error('Missing access token.')
    }

    const response = await apiFetch(
      `/api/sessions/${sessionId}`,
      { method: 'DELETE' },
      accessToken.value,
    )
    if (!response.ok) {
      throw new Error(`Delete failed with status ${response.status}.`)
    }

    sessions.value = sessions.value.filter((item) => item.id !== sessionId)
    if (readLastSessionId() === sessionId) {
      persistLastSessionId(null)
    }
  }

  return {
    createSession,
    deleteSession,
    fetchSessions,
    isLoading,
    persistLastSessionId,
    readLastSessionId,
    sessions,
  }
}
