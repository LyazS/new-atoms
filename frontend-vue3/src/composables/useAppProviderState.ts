import { fetchEventSource } from '@microsoft/fetch-event-source'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import type { CompileFeedback } from './useSandpackManualRun'
import { getApiBaseUrl } from '../lib/api'
import { cloneDefaultWorkspace } from '../lib/sandpackWorkspace'

type MessageRole = 'assistant' | 'user'
type TurnState = 'running' | 'waiting_for_frontend' | 'completed' | 'failed'

type ServerMessage = {
  id: string
  role: 'system' | 'assistant' | 'user' | 'tool'
  content: string
}

type ServerDisplayMessage = {
  id: string
  role: MessageRole
  content: string
  reasoning_content: string | null
  tool_calls: string[]
  is_in_progress: boolean
}

type CreateSessionResponse = {
  session_id: string
}

type SessionInputResponse = {
  accepted: boolean
  turn_id: string
  state: TurnState | null
}

type WorkspaceOp =
  | {
      op: 'upsert'
      path: string
      code?: string
    }
  | {
      op: 'delete'
      path: string
    }

type SessionSnapshotResponse = {
  session_id: string
  messages: ServerMessage[]
  display_messages: ServerDisplayMessage[]
  workspace: Record<string, string>
  active_turn: {
    id: string
    state: TurnState
    streaming_message_id: string | null
  } | null
  last_compile_feedback: CompileFeedback | null
  pending_frontend_tool: {
    tool_name: 'run_diagnostics'
    tool_call_id: string
    arguments: Record<string, unknown>
    created_at: string
  } | null
}

export type ChatMessage = {
  id: string
  role: MessageRole
  content: string
  reasoningContent: string | null
  toolCalls: string[]
  isInProgress: boolean
}

const API_BASE_URL = getApiBaseUrl()
const SESSION_STORAGE_KEY = 'fastapi-agent-loop-session-id'

export function useAppProviderState() {
  const messages = ref<ChatMessage[]>([])
  const workspaceFiles = ref<Record<string, string>>(cloneDefaultWorkspace())
  const draft = ref('')
  const isThinking = ref(false)
  const isHydrating = ref(false)
  const sessionId = ref<string | null>(null)
  const currentTurnId = ref<string | null>(null)
  const pendingFrontendTurnId = ref<string | null>(null)
  const runRequestKey = ref(0)
  const lastCompileFeedback = ref<CompileFeedback | null>(null)
  const eventConnectionState = ref<'connecting' | 'open' | 'closed'>('closed')

  let eventStreamController: AbortController | null = null
  let eventSourceReadyPromise: Promise<void> | null = null
  let reconnectTimer: number | null = null
  let reconnectAttempt = 0
  let activeEventStreamSessionId: string | null = null
  let shouldMaintainEventStream = false

  const connectionLabel = computed(() => {
    if (!sessionId.value) {
      return 'Ready to Start'
    }

    if (eventConnectionState.value === 'open') {
      return 'SSE Connected'
    }

    if (eventConnectionState.value === 'closed') {
      return 'Disconnected'
    }

    return 'Connecting'
  })

  const compileStatusLabel = computed(() => {
    if (isThinking.value) {
      return 'Agent Running'
    }

    if (!lastCompileFeedback.value) {
      return 'Compile Idle'
    }

    return `Compile ${lastCompileFeedback.value.status}`
  })

  function persistSessionId(nextSessionId: string | null) {
    if (!nextSessionId) {
      window.localStorage.removeItem(SESSION_STORAGE_KEY)
      return
    }

    window.localStorage.setItem(SESSION_STORAGE_KEY, nextSessionId)
  }

  function readPersistedSessionId() {
    return window.localStorage.getItem(SESSION_STORAGE_KEY)
  }

  function hydrateMessages(nextMessages: ServerDisplayMessage[]) {
    messages.value = nextMessages.map((message) => ({
      id: message.id,
      role: message.role,
      content: message.content,
      reasoningContent: message.reasoning_content,
      toolCalls: message.tool_calls,
      isInProgress: message.is_in_progress,
    }))
  }

  function pushAssistantMessage(content: string) {
    if (!content.trim()) {
      return
    }

    messages.value = [
      ...messages.value,
      {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content,
        reasoningContent: null,
        toolCalls: [],
        isInProgress: false,
      },
    ]
  }

  function ensureAssistantMessage(messageId: string) {
    const existing = messages.value.find((message) => message.id === messageId)
    if (existing) {
      return existing
    }

    const message: ChatMessage = {
      id: messageId,
      role: 'assistant',
      content: '',
      reasoningContent: null,
      toolCalls: [],
      isInProgress: true,
    }
    messages.value = [...messages.value, message]
    return message
  }

  function startAssistantMessage(messageId: string) {
    const target = ensureAssistantMessage(messageId)
    messages.value = messages.value.map((message) =>
      message.id === target.id
        ? {
            ...message,
            isInProgress: true,
          }
        : message,
    )
  }

  function appendAssistantDelta(messageId: string, delta: string) {
    const target = ensureAssistantMessage(messageId)
    messages.value = messages.value.map((message) =>
      message.id === target.id
        ? {
            ...message,
            content: `${message.content}${delta}`,
            isInProgress: true,
          }
        : message,
    )
  }

  function appendReasoningDelta(messageId: string, delta: string) {
    const target = ensureAssistantMessage(messageId)
    messages.value = messages.value.map((message) =>
      message.id === target.id
        ? {
            ...message,
            reasoningContent: `${message.reasoningContent ?? ''}${delta}`,
            isInProgress: true,
          }
        : message,
    )
  }

  function replaceAssistantToolCalls(messageId: string, toolCalls: string[]) {
    ensureAssistantMessage(messageId)
    messages.value = messages.value.map((message) =>
      message.id === messageId
        ? {
            ...message,
            toolCalls,
            isInProgress: true,
          }
        : message,
    )
  }

  function finalizeAssistantMessage(messageId: string) {
    if (!messageId) {
      return false
    }

    let found = false
    messages.value = messages.value.map((message) => {
      if (message.id !== messageId) {
        return message
      }

      found = true
      return {
        ...message,
        isInProgress: false,
      }
    })
    return found
  }

  function applyWorkspaceOps(ops: WorkspaceOp[]) {
    const nextFiles = { ...workspaceFiles.value }

    for (const op of ops) {
      if (op.op === 'upsert') {
        nextFiles[op.path] = op.code ?? ''
        continue
      }

      delete nextFiles[op.path]
    }

    workspaceFiles.value = nextFiles
  }

  function clearReconnectTimer() {
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  function disconnectEventStream() {
    shouldMaintainEventStream = false
    activeEventStreamSessionId = null
    clearReconnectTimer()
    eventStreamController?.abort()
    eventStreamController = null
    eventSourceReadyPromise = null
    eventConnectionState.value = 'closed'
  }

  async function handleSseMessage(event: { event: string; data: string }) {
    if (event.event === 'assistant.message_started') {
      const payload = JSON.parse(event.data) as { message_id: string }
      startAssistantMessage(payload.message_id)
      return
    }

    if (event.event === 'assistant.delta') {
      const payload = JSON.parse(event.data) as { message_id: string; delta: string }
      appendAssistantDelta(payload.message_id, payload.delta)
      return
    }

    if (event.event === 'assistant.reasoning_delta') {
      const payload = JSON.parse(event.data) as { message_id: string; delta: string }
      appendReasoningDelta(payload.message_id, payload.delta)
      return
    }

    if (event.event === 'assistant.message_completed') {
      const payload = JSON.parse(event.data) as { message_id: string }
      finalizeAssistantMessage(payload.message_id)
      return
    }

    if (event.event === 'assistant.tool_calls_updated') {
      const payload = JSON.parse(event.data) as { message_id: string; tool_calls: string[] }
      replaceAssistantToolCalls(payload.message_id, payload.tool_calls)
      return
    }

    if (event.event === 'workspace.patch') {
      const payload = JSON.parse(event.data) as { ops: WorkspaceOp[] }
      applyWorkspaceOps(payload.ops)
      return
    }

    if (event.event === 'frontend.tool_call') {
      const payload = JSON.parse(event.data) as { turn_id: string }
      pendingFrontendTurnId.value = payload.turn_id
      runRequestKey.value += 1
      return
    }

    if (event.event === 'turn.completed') {
      const payload = JSON.parse(event.data) as { message: string }
      isThinking.value = false
      currentTurnId.value = null
      pendingFrontendTurnId.value = null
      if (!payload.message.trim()) {
        return
      }
      pushAssistantMessage(payload.message)
      return
    }

    if (event.event === 'turn.failed') {
      const payload = JSON.parse(event.data) as { reason: string }
      isThinking.value = false
      currentTurnId.value = null
      pendingFrontendTurnId.value = null
      messages.value = messages.value.map((message) =>
        message.isInProgress ? { ...message, isInProgress: false } : message,
      )
      pushAssistantMessage(`当前任务失败：${payload.reason}`)
    }
  }

  function scheduleEventStreamReconnect(targetSessionId: string) {
    if (!shouldMaintainEventStream || sessionId.value !== targetSessionId) {
      return
    }

    clearReconnectTimer()
    const delay = Math.min(1000 * 2 ** reconnectAttempt, 8000)
    reconnectAttempt += 1
    reconnectTimer = window.setTimeout(() => {
      void connectEventStream(targetSessionId, { forceReconnect: true })
    }, delay)
  }

  async function connectEventStream(
    currentSessionId: string,
    options: {
      forceReconnect?: boolean
    } = {},
  ) {
    const { forceReconnect = false } = options

    if (
      !forceReconnect &&
      activeEventStreamSessionId === currentSessionId &&
      eventConnectionState.value === 'open'
    ) {
      return
    }

    if (
      !forceReconnect &&
      activeEventStreamSessionId === currentSessionId &&
      eventConnectionState.value === 'connecting' &&
      eventSourceReadyPromise
    ) {
      return eventSourceReadyPromise
    }

    clearReconnectTimer()
    shouldMaintainEventStream = true
    activeEventStreamSessionId = currentSessionId
    eventStreamController?.abort()
    const controller = new AbortController()
    eventStreamController = controller
    eventConnectionState.value = 'connecting'
    eventSourceReadyPromise = new Promise((resolve, reject) => {
      let isSettled = false
      const timeoutId = window.setTimeout(() => {
        eventConnectionState.value = 'closed'
        if (eventStreamController === controller) {
          eventStreamController.abort()
        }
        if (!isSettled) {
          isSettled = true
          reject(new Error('SSE connection timed out.'))
        }
      }, 5000)

      void fetchEventSource(`${API_BASE_URL}/api/sessions/${currentSessionId}/events`, {
        method: 'GET',
        signal: controller.signal,
        openWhenHidden: true,
        async onopen(response) {
          if (!response.ok) {
            window.clearTimeout(timeoutId)
            eventConnectionState.value = 'closed'
            if (!isSettled) {
              isSettled = true
              reject(new Error(`SSE connection failed with status ${response.status}.`))
            }
            throw new Error(`SSE connection failed with status ${response.status}.`)
          }

          window.clearTimeout(timeoutId)
          reconnectAttempt = 0
          eventConnectionState.value = 'open'
          if (!isSettled) {
            isSettled = true
            resolve()
          }
        },
        onmessage(message) {
          void handleSseMessage(message)
        },
        onclose() {
          window.clearTimeout(timeoutId)
          eventConnectionState.value = 'closed'
          if (eventStreamController === controller) {
            eventStreamController = null
          }
          if (!controller.signal.aborted) {
            scheduleEventStreamReconnect(currentSessionId)
          }
        },
        onerror(error) {
          window.clearTimeout(timeoutId)
          eventConnectionState.value = 'closed'
          if (eventStreamController === controller) {
            eventStreamController = null
          }
          if (!isSettled) {
            isSettled = true
            reject(error instanceof Error ? error : new Error('SSE connection failed.'))
          }
          throw error
        },
      }).catch((error) => {
        if (controller.signal.aborted) {
          return
        }

        eventConnectionState.value = 'closed'
        if (eventStreamController === controller) {
          eventStreamController = null
        }
        if (!isSettled) {
          isSettled = true
          reject(error instanceof Error ? error : new Error('SSE connection failed.'))
        }
        scheduleEventStreamReconnect(currentSessionId)
      })
    })

    return eventSourceReadyPromise
  }

  async function hydrateSession(currentSessionId: string) {
    const response = await fetch(`${API_BASE_URL}/api/sessions/${currentSessionId}`)

    if (response.status === 404) {
      disconnectEventStream()
      persistSessionId(null)
      sessionId.value = null
      return false
    }

    if (!response.ok) {
      throw new Error(`Failed to fetch session: ${response.status}`)
    }

    const payload = (await response.json()) as SessionSnapshotResponse
    sessionId.value = payload.session_id
    persistSessionId(payload.session_id)
    workspaceFiles.value = payload.workspace
    hydrateMessages(payload.display_messages)
    lastCompileFeedback.value = payload.last_compile_feedback
    currentTurnId.value = payload.active_turn?.state === 'running' ? payload.active_turn.id : null
    pendingFrontendTurnId.value =
      payload.active_turn?.state === 'waiting_for_frontend' ? payload.active_turn.id : null
    isThinking.value =
      payload.active_turn?.state === 'running' || payload.active_turn?.state === 'waiting_for_frontend'
    return true
  }

  async function createSession() {
    isHydrating.value = true
    const response = await fetch(`${API_BASE_URL}/api/sessions/create`, {
      method: 'POST',
    })

    if (!response.ok) {
      throw new Error(`Failed to create session: ${response.status}`)
    }

    const payload = (await response.json()) as CreateSessionResponse
    sessionId.value = payload.session_id
    persistSessionId(payload.session_id)
    workspaceFiles.value = cloneDefaultWorkspace()
    hydrateMessages([])
    currentTurnId.value = null
    pendingFrontendTurnId.value = null
    lastCompileFeedback.value = null
    await connectEventStream(payload.session_id)
  }

  async function handleCreateSession() {
    if (isHydrating.value || isThinking.value) {
      return
    }

    try {
      disconnectEventStream()
      persistSessionId(null)
      sessionId.value = null
      workspaceFiles.value = cloneDefaultWorkspace()
      hydrateMessages([])
      draft.value = ''
      currentTurnId.value = null
      pendingFrontendTurnId.value = null
      runRequestKey.value = 0
      lastCompileFeedback.value = null
      isThinking.value = false

      await createSession()
    } catch (error) {
      pushAssistantMessage(
        `新建会话失败：${error instanceof Error ? error.message : 'Unknown error'}`,
      )
    } finally {
      isHydrating.value = false
    }
  }

  async function restoreSession() {
    const persistedSessionId = readPersistedSessionId()
    if (!persistedSessionId) {
      return false
    }

    const restored = await hydrateSession(persistedSessionId)
    if (!restored || !sessionId.value) {
      return false
    }

    await connectEventStream(sessionId.value)
    return true
  }

  async function ensureSessionAndSseConnected() {
    if (!sessionId.value) {
      await createSession()
    }

    const currentSessionId = sessionId.value
    if (!currentSessionId) {
      throw new Error('Session was not created successfully.')
    }

    if (eventConnectionState.value === 'open') {
      return currentSessionId
    }

    if (eventConnectionState.value === 'connecting' && eventSourceReadyPromise) {
      await eventSourceReadyPromise
      return currentSessionId
    }

    await connectEventStream(currentSessionId)
    return currentSessionId
  }

  function handleWindowOnline() {
    if (!sessionId.value || eventConnectionState.value === 'open') {
      return
    }

    void connectEventStream(sessionId.value, { forceReconnect: true })
  }

  function handleVisibilityChange() {
    if (document.visibilityState !== 'visible' || !sessionId.value) {
      return
    }

    if (eventConnectionState.value !== 'open') {
      void connectEventStream(sessionId.value, { forceReconnect: true })
    }
  }

  async function handleSubmit() {
    const content = draft.value.trim()
    if (!content || isThinking.value) {
      return
    }

    try {
      isHydrating.value = true
      const currentSessionId = await ensureSessionAndSseConnected()

      messages.value = [
        ...messages.value,
        {
          id: `user-${Date.now()}`,
          role: 'user',
          content,
          reasoningContent: null,
          toolCalls: [],
          isInProgress: false,
        },
      ]
      draft.value = ''
      isThinking.value = true

      const response = await fetch(`${API_BASE_URL}/api/sessions/${currentSessionId}/inputs`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          type: 'user_message',
          content,
        }),
      })

      if (!response.ok) {
        isThinking.value = false
        pushAssistantMessage(`消息提交失败，状态码 ${response.status}。`)
        return
      }

      const payload = (await response.json()) as SessionInputResponse
      currentTurnId.value = payload.turn_id
    } catch (error) {
      isThinking.value = false
      pushAssistantMessage(
        `请求前未能建立会话或 SSE：${error instanceof Error ? error.message : 'Unknown error'}`,
      )
    } finally {
      isHydrating.value = false
    }
  }

  async function handleManualRunResult(feedback: CompileFeedback) {
    lastCompileFeedback.value = feedback

    if (!sessionId.value || !pendingFrontendTurnId.value) {
      return
    }

    try {
      isHydrating.value = true
      const currentSessionId = await ensureSessionAndSseConnected()
      const turnId = pendingFrontendTurnId.value
      if (!turnId) {
        return
      }

      const response = await fetch(`${API_BASE_URL}/api/sessions/${currentSessionId}/inputs`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          type: 'frontend_tool_result',
          turn_id: turnId,
          tool_name: 'run_diagnostics',
          ...feedback,
        }),
      })

      if (!response.ok) {
        pushAssistantMessage(`编译结果回传失败，状态码 ${response.status}。`)
        return
      }

      pendingFrontendTurnId.value = null
    } catch (error) {
      pushAssistantMessage(
        `回传编译结果前未能建立 SSE：${error instanceof Error ? error.message : 'Unknown error'}`,
      )
    } finally {
      isHydrating.value = false
    }
  }

  function handleRunnerStateChange(nextValue: boolean) {
    if (!pendingFrontendTurnId.value) {
      return
    }

    isThinking.value = nextValue || Boolean(currentTurnId.value)
  }

  onMounted(() => {
    window.addEventListener('online', handleWindowOnline)
    document.addEventListener('visibilitychange', handleVisibilityChange)
    void (async () => {
      try {
        isHydrating.value = true
        await restoreSession()
      } catch (error) {
        persistSessionId(null)
        sessionId.value = null
        pushAssistantMessage(`恢复会话失败：${error instanceof Error ? error.message : 'Unknown error'}`)
      } finally {
        isHydrating.value = false
      }
    })()
  })

  onBeforeUnmount(() => {
    window.removeEventListener('online', handleWindowOnline)
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    disconnectEventStream()
  })

  return {
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
  }
}
