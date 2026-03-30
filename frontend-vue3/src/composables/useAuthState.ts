import { computed, ref } from 'vue'

import { ApiError, apiJson } from '../lib/api'

type User = {
  id: string
  username: string
  created_at: string
}

type AuthResponse = {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

const TOKEN_STORAGE_KEY = 'new-atoms-access-token'
const USER_STORAGE_KEY = 'new-atoms-user'

const accessToken = ref<string | null>(null)
const currentUser = ref<User | null>(null)
const isReady = ref(false)
let initPromise: Promise<void> | null = null

function persistAuth(token: string | null, user: User | null) {
  if (!token || !user) {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY)
    window.localStorage.removeItem(USER_STORAGE_KEY)
    accessToken.value = null
    currentUser.value = null
    return
  }

  window.localStorage.setItem(TOKEN_STORAGE_KEY, token)
  window.localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user))
  accessToken.value = token
  currentUser.value = user
}

function restoreLocalSnapshot() {
  accessToken.value = window.localStorage.getItem(TOKEN_STORAGE_KEY)

  const rawUser = window.localStorage.getItem(USER_STORAGE_KEY)
  if (!rawUser) {
    currentUser.value = null
    return
  }

  try {
    currentUser.value = JSON.parse(rawUser) as User
  } catch {
    currentUser.value = null
  }
}

async function bootstrap() {
  restoreLocalSnapshot()
  if (!accessToken.value) {
    isReady.value = true
    return
  }

  try {
    currentUser.value = await apiJson<User>('/api/auth/me', {}, accessToken.value)
    persistAuth(accessToken.value, currentUser.value)
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      persistAuth(null, null)
    } else {
      throw error
    }
  } finally {
    isReady.value = true
  }
}

export function useAuthState() {
  async function initializeAuth() {
    if (!initPromise) {
      initPromise = bootstrap()
    }

    await initPromise
  }

  async function login(username: string, password: string) {
    const payload = await apiJson<AuthResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    persistAuth(payload.access_token, payload.user)
    return payload.user
  }

  async function register(username: string, password: string) {
    const payload = await apiJson<AuthResponse>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    persistAuth(payload.access_token, payload.user)
    return payload.user
  }

  function logout() {
    persistAuth(null, null)
  }

  return {
    accessToken,
    currentUser,
    initializeAuth,
    isAuthenticated: computed(() => Boolean(accessToken.value && currentUser.value)),
    isReady,
    login,
    logout,
    register,
  }
}
