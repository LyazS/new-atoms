import { fetchEventSource } from '@microsoft/fetch-event-source'
import { computed, onBeforeUnmount, ref } from 'vue'

import type { CompileFeedback } from './useSandpackManualRun'
import { ApiError, apiJson, getApiBaseUrl } from '../lib/api'
import { cloneDefaultWorkspace } from '../lib/sandpackWorkspace'
import { useAuthState } from './useAuthState'
import { useSessionListState } from './useSessionListState'

type MessageRole = 'assistant' | 'user'
type TurnState = 'running' | 'waiting_for_frontend' | 'completed' | 'failed'
type PublishStatus = 'idle' | 'queued' | 'building' | 'success' | 'failed'

type ServerDisplayMessage = {
  id: string
  role: MessageRole
  content: string
  reasoning_content: string | null
  tool_calls: string[]
  is_in_progress: boolean
}

type SessionInputResponse = {
  accepted: boolean
  turn_id: string
  state: TurnState | null
}

type PublishStateResponse = {
  session_id: string
  status: PublishStatus
  job_id: string | null
  current_version: string | null
  public_url: string | null
  started_at: string | null
  finished_at: string | null
  error_message: string | null
  logs: string
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
  title: string
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

export function useSessionConversationState() {
  const { accessToken, logout } = useAuthState()
  const { persistLastSessionId } = useSessionListState()

  const currentSessionId = ref<string | null>(null)
  const sessionTitle = ref('Project Workspace')
  const messages = ref<ChatMessage[]>([])
  const workspaceFiles = ref<Record<string, string>>(cloneDefaultWorkspace())
  const draft = ref('')
  const isThinking = ref(false)
  const isHydrating = ref(false)
  const runRequestKey = ref(0)
  const lastCompileFeedback = ref<CompileFeedback | null>(null)
  const eventConnectionState = ref<'connecting' | 'open' | 'closed'>('closed')
  const currentTurnId = ref<string | null>(null)
  const pendingFrontendTurnId = ref<string | null>(null)
  const publishStatus = ref<PublishStatus>('idle')
  const publishJobId = ref<string | null>(null)
  const publishUrl = ref<string | null>(null)
  const publishVersion = ref<string | null>(null)
  const publishError = ref<string | null>(null)
  const publishLogs = ref('')
  const publishStartedAt = ref<string | null>(null)
  const publishFinishedAt = ref<string | null>(null)

  let eventStreamController: AbortController | null = null
  let eventSourceReadyPromise: Promise<void> | null = null
  let reconnectTimer: number | null = null
  let reconnectAttempt = 0
  let activeEventStreamSessionId: string | null = null
  let shouldMaintainEventStream = false

  const connectionLabel = computed(() => {
    if (!currentSessionId.value) {
      return 'No Session'
    }
    if (eventConnectionState.value === 'open') {
      return 'SSE Connected'
    }
    if (eventConnectionState.value === 'connecting') {
      return 'Connecting'
    }
    return 'Disconnected'
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

  const isPublishing = computed(
    () => publishStatus.value === 'queued' || publishStatus.value === 'building',
  )

  const publishStatusLabel = computed(() => {
    if (publishStatus.value === 'idle') {
      return '尚未发布'
    }
    if (publishStatus.value === 'queued') {
      return '发布排队中'
    }
    if (publishStatus.value === 'building') {
      return '正在构建'
    }
    if (publishStatus.value === 'success') {
      return '发布成功'
    }
    return '发布失败'
  })

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
    ensureAssistantMessage(messageId)
    messages.value = messages.value.map((message) =>
      message.id === messageId ? { ...message, isInProgress: true } : message,
    )
  }

  function resetAssistantMessage(messageId: string) {
    ensureAssistantMessage(messageId)
    messages.value = messages.value.map((message) =>
      message.id === messageId
        ? {
            ...message,
            content: '',
            reasoningContent: null,
            toolCalls: [],
            isInProgress: false,
          }
        : message,
    )
  }

  function appendAssistantDelta(messageId: string, delta: string) {
    ensureAssistantMessage(messageId)
    messages.value = messages.value.map((message) =>
      message.id === messageId
        ? { ...message, content: `${message.content}${delta}`, isInProgress: true }
        : message,
    )
  }

  function appendReasoningDelta(messageId: string, delta: string) {
    ensureAssistantMessage(messageId)
    messages.value = messages.value.map((message) =>
      message.id === messageId
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
      message.id === messageId ? { ...message, toolCalls, isInProgress: true } : message,
    )
  }

  function finalizeAssistantMessage(messageId: string) {
    messages.value = messages.value.map((message) =>
      message.id === messageId ? { ...message, isInProgress: false } : message,
    )
  }

  function applyWorkspaceOps(ops: WorkspaceOp[]) {
    const nextFiles = { ...workspaceFiles.value }
    for (const op of ops) {
      if (op.op === 'upsert') {
        nextFiles[op.path] = op.code ?? ''
      } else {
        delete nextFiles[op.path]
      }
    }
    workspaceFiles.value = nextFiles
  }

  function applyPublishState(payload: PublishStateResponse) {
    publishStatus.value = payload.status
    publishJobId.value = payload.job_id
    publishUrl.value = payload.public_url
    publishVersion.value = payload.current_version
    publishError.value = payload.error_message
    publishLogs.value = payload.logs
    publishStartedAt.value = payload.started_at
    publishFinishedAt.value = payload.finished_at
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

    if (event.event === 'assistant.message_reset') {
      const payload = JSON.parse(event.data) as { message_id: string }
      resetAssistantMessage(payload.message_id)
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
      if (payload.message.trim()) {
        pushAssistantMessage(payload.message)
      }
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
      return
    }

    if (event.event === 'publish.status_changed') {
      const payload = JSON.parse(event.data) as PublishStateResponse
      applyPublishState({
        ...payload,
        logs: publishLogs.value,
      })
      return
    }

    if (event.event === 'publish.log') {
      const payload = JSON.parse(event.data) as { chunk: string }
      publishLogs.value = `${publishLogs.value}${payload.chunk}`
      return
    }

    if (event.event === 'publish.completed' || event.event === 'publish.failed') {
      const payload = JSON.parse(event.data) as PublishStateResponse
      applyPublishState({
        ...payload,
        logs: payload.logs ?? publishLogs.value,
      })
    }
  }

  function scheduleEventStreamReconnect(targetSessionId: string) {
    if (!shouldMaintainEventStream || currentSessionId.value !== targetSessionId) {
      return
    }

    clearReconnectTimer()
    const delay = Math.min(1000 * 2 ** reconnectAttempt, 8000)
    reconnectAttempt += 1
    reconnectTimer = window.setTimeout(() => {
      void connectEventStream(targetSessionId, { forceReconnect: true })
    }, delay)
  }

  async function connectEventStream(sessionId: string, options: { forceReconnect?: boolean } = {}) {
    const { forceReconnect = false } = options
    const token = accessToken.value
    if (!token) {
      throw new Error('Missing access token.')
    }

    if (!forceReconnect && activeEventStreamSessionId === sessionId && eventConnectionState.value === 'open') {
      return
    }

    clearReconnectTimer()
    shouldMaintainEventStream = true
    activeEventStreamSessionId = sessionId
    eventStreamController?.abort()
    const controller = new AbortController()
    eventStreamController = controller
    eventConnectionState.value = 'connecting'

    eventSourceReadyPromise = new Promise((resolve, reject) => {
      let settled = false
      const timeoutId = window.setTimeout(() => {
        eventConnectionState.value = 'closed'
        controller.abort()
        if (!settled) {
          settled = true
          reject(new Error('SSE connection timed out.'))
        }
      }, 5000)

      void fetchEventSource(`${getApiBaseUrl()}/api/sessions/${sessionId}/events`, {
        method: 'GET',
        signal: controller.signal,
        openWhenHidden: true,
        headers: {
          Authorization: `Bearer ${token}`,
        },
        async onopen(response) {
          if (response.status === 401) {
            logout()
            throw new Error('Unauthorized')
          }
          if (!response.ok) {
            window.clearTimeout(timeoutId)
            eventConnectionState.value = 'closed'
            if (!settled) {
              settled = true
              reject(new Error(`SSE connection failed with status ${response.status}.`))
            }
            throw new Error(`SSE connection failed with status ${response.status}.`)
          }

          window.clearTimeout(timeoutId)
          reconnectAttempt = 0
          eventConnectionState.value = 'open'
          if (!settled) {
            settled = true
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
            scheduleEventStreamReconnect(sessionId)
          }
        },
        onerror(error) {
          window.clearTimeout(timeoutId)
          eventConnectionState.value = 'closed'
          if (!settled) {
            settled = true
            reject(error instanceof Error ? error : new Error('SSE connection failed.'))
          }
          throw error
        },
      }).catch((error) => {
        if (controller.signal.aborted) {
          return
        }
        eventConnectionState.value = 'closed'
        if (error instanceof Error && error.message === 'Unauthorized') {
          return
        }
        if (!settled) {
          settled = true
          reject(error instanceof Error ? error : new Error('SSE connection failed.'))
        }
        scheduleEventStreamReconnect(sessionId)
      })
    })

    return eventSourceReadyPromise
  }

  async function loadSession(sessionId: string) {
    const token = accessToken.value
    if (!token) {
      logout()
      return false
    }

    isHydrating.value = true
    try {
      const payload = await apiJson<SessionSnapshotResponse>(`/api/sessions/${sessionId}`, {}, token)
      currentSessionId.value = payload.session_id
      sessionTitle.value = payload.title
      persistLastSessionId(payload.session_id)
      workspaceFiles.value = payload.workspace
      hydrateMessages(payload.display_messages)
      lastCompileFeedback.value = payload.last_compile_feedback
      currentTurnId.value = payload.active_turn?.state === 'running' ? payload.active_turn.id : null
      pendingFrontendTurnId.value =
        payload.active_turn?.state === 'waiting_for_frontend' ? payload.active_turn.id : null
      isThinking.value =
        payload.active_turn?.state === 'running' || payload.active_turn?.state === 'waiting_for_frontend'
      await connectEventStream(payload.session_id)
      await loadPublishState(payload.session_id)
      return true
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        logout()
        return false
      }
      throw error
    } finally {
      isHydrating.value = false
    }
  }

  async function handleSubmit() {
    const content = draft.value.trim()
    if (!content || isThinking.value || !currentSessionId.value || !accessToken.value) {
      return
    }

    try {
      isHydrating.value = true
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

      const payload = await apiJson<SessionInputResponse>(
        `/api/sessions/${currentSessionId.value}/inputs`,
        {
          method: 'POST',
          body: JSON.stringify({
            type: 'user_message',
            content,
          }),
        },
        accessToken.value,
      )
      currentTurnId.value = payload.turn_id
    } catch (error) {
      isThinking.value = false
      if (error instanceof ApiError && error.status === 401) {
        logout()
        return
      }
      pushAssistantMessage(
        `消息提交失败：${error instanceof Error ? error.message : 'Unknown error'}`,
      )
    } finally {
      isHydrating.value = false
    }
  }

  async function handleManualRunResult(feedback: CompileFeedback) {
    lastCompileFeedback.value = feedback
    if (!currentSessionId.value || !pendingFrontendTurnId.value || !accessToken.value) {
      return
    }

    try {
      isHydrating.value = true
      await apiJson<SessionInputResponse>(
        `/api/sessions/${currentSessionId.value}/inputs`,
        {
          method: 'POST',
          body: JSON.stringify({
            type: 'frontend_tool_result',
            turn_id: pendingFrontendTurnId.value,
            tool_name: 'run_diagnostics',
            ...feedback,
          }),
        },
        accessToken.value,
      )
      pendingFrontendTurnId.value = null
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        logout()
        return
      }
      pushAssistantMessage(
        `回传编译结果失败：${error instanceof Error ? error.message : 'Unknown error'}`,
      )
    } finally {
      isHydrating.value = false
    }
  }

  async function loadPublishState(sessionId = currentSessionId.value) {
    if (!sessionId || !accessToken.value) {
      return
    }

    try {
      const payload = await apiJson<PublishStateResponse>(
        `/api/sessions/${sessionId}/publish`,
        {},
        accessToken.value,
      )
      applyPublishState(payload)
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        logout()
        return
      }
      publishError.value = error instanceof Error ? error.message : 'Failed to load publish state'
    }
  }

  async function triggerPublish() {
    if (!currentSessionId.value || !accessToken.value || isPublishing.value) {
      return
    }

    try {
      publishError.value = null
      publishLogs.value = ''
      await apiJson<{ job_id: string; status: PublishStatus }>(
        `/api/sessions/${currentSessionId.value}/publish`,
        { method: 'POST' },
        accessToken.value,
      )
      await loadPublishState(currentSessionId.value)
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        logout()
        return
      }
      publishError.value = error instanceof Error ? error.message : 'Failed to start publish'
    }
  }

  function handleRunnerStateChange(nextValue: boolean) {
    if (!pendingFrontendTurnId.value) {
      return
    }
    isThinking.value = nextValue || Boolean(currentTurnId.value)
  }

  onBeforeUnmount(() => {
    disconnectEventStream()
  })

  return {
    compileStatusLabel,
    connectionLabel,
    currentSessionId,
    disconnectEventStream,
    draft,
    handleManualRunResult,
    handleRunnerStateChange,
    handleSubmit,
    isHydrating,
    isThinking,
    isPublishing,
    lastCompileFeedback,
    loadSession,
    loadPublishState,
    messages,
    publishError,
    publishFinishedAt,
    publishJobId,
    publishLogs,
    publishStartedAt,
    publishStatus,
    publishStatusLabel,
    publishUrl,
    publishVersion,
    runRequestKey,
    sessionTitle,
    triggerPublish,
    workspaceFiles,
  }
}
