import { onBeforeUnmount, ref, watch } from 'vue'
import { useSandpack, useSandpackConsole } from 'sandpack-vue3'

export type ManualRunResult = 'done' | 'timeout'
export type CompileStatus = 'success' | 'compile_error' | 'runtime_error' | 'timeout'

export type CompileFeedback = {
  result: ManualRunResult
  status: CompileStatus
  server_logs: string[]
  client_logs: unknown[]
  error_summary?: string
}

type ServerBufferEntry =
  | {
      type: 'stdout'
      data: string
    }
  | {
      type: 'done'
      compilatonError?: boolean
    }
  | {
      type: 'timeout'
    }

type ClientBufferEntry =
  | {
      type: 'logs'
      data: unknown[]
    }
  | {
      type: 'status'
      status: ReturnType<typeof useSandpack>['sandpack']['status']
    }

function stripAnsi(value: string) {
  return value.replace(/\u001B\[[0-9;]*[A-Za-z]/g, '')
}

function normalizeServerStdout(value: string) {
  return stripAnsi(value)
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line && !line.includes('"clearScreenDown" is not yet implemented'))
    .join('\n')
}

function toJsonSafeValue<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

export function useSandpackManualRun() {
  const { sandpack, listen } = useSandpack()
  const { logs } = useSandpackConsole({
    showSyntaxError: true,
    resetOnPreviewRestart: true,
  })

  const isRunning = ref(false)
  const serverBuffer = ref<ServerBufferEntry[]>([])
  const clientBuffer = ref<ClientBufferEntry[]>([])
  let resolveManualRun: ((result: ManualRunResult) => void) | null = null

  function resetBuffers() {
    serverBuffer.value = []
    clientBuffer.value = []
  }

  function getLatestServerCompletionSignal() {
    for (let index = serverBuffer.value.length - 1; index >= 0; index -= 1) {
      const entry = serverBuffer.value[index]

      if (!entry) {
        continue
      }

      if (entry.type === 'done' || entry.type === 'timeout') {
        return entry
      }
    }

    return null
  }

  function getLatestClientCompletionSignal() {
    for (let index = clientBuffer.value.length - 1; index >= 0; index -= 1) {
      const entry = clientBuffer.value[index]

      if (!entry || entry.type !== 'status') {
        continue
      }

      if (entry.status === 'done' || entry.status === 'timeout') {
        return entry
      }
    }

    return null
  }

  function flushManualRunSignal() {
    if (!resolveManualRun) {
      return
    }

    const latestServerSignal = getLatestServerCompletionSignal()

    if (latestServerSignal?.type === 'done') {
      const resolve = resolveManualRun
      resolveManualRun = null
      resolve('done')
      return
    }

    if (latestServerSignal?.type === 'timeout') {
      const resolve = resolveManualRun
      resolveManualRun = null
      resolve('timeout')
      return
    }

    const latestClientSignal = getLatestClientCompletionSignal()

    if (!latestClientSignal) {
      return
    }

    const resolve = resolveManualRun
    resolveManualRun = null
    resolve(latestClientSignal.status === 'done' ? 'done' : 'timeout')
  }

  function getBufferedServerOutput() {
    return serverBuffer.value
      .filter((entry) => entry.type === 'stdout')
      .map((entry) => entry.data)
  }

  function getBufferedClientOutput() {
    return clientBuffer.value
      .filter((entry) => entry.type === 'logs')
      .map((entry) => entry.data)
  }

  function detectCompileFeedback(result: ManualRunResult): CompileFeedback {
    const serverLogs = getBufferedServerOutput()
    const clientLogs = toJsonSafeValue(getBufferedClientOutput())

    if (result === 'timeout') {
      return {
        result,
        status: 'timeout',
        server_logs: serverLogs,
        client_logs: clientLogs,
        error_summary: 'Sandpack compile timed out.',
      }
    }

    const hasCompileError = serverBuffer.value.some(
      (entry) => entry.type === 'done' && Boolean(entry.compilatonError),
    )
    if (hasCompileError) {
      return {
        result,
        status: 'compile_error',
        server_logs: serverLogs,
        client_logs: clientLogs,
        error_summary: serverLogs.at(-1) ?? 'Compilation failed.',
      }
    }

    const hasRuntimeError = clientLogs.some((entry) => {
      if (!Array.isArray(entry)) {
        return false
      }

      return entry.some(
        (item) =>
          typeof item === 'object' &&
          item !== null &&
          'method' in item &&
          item.method === 'error',
      )
    })

    if (hasRuntimeError) {
      return {
        result,
        status: 'runtime_error',
        server_logs: serverLogs,
        client_logs: clientLogs,
        error_summary: 'Preview emitted runtime errors.',
      }
    }

    return {
      result,
      status: 'success',
      server_logs: serverLogs,
      client_logs: clientLogs,
    }
  }

  function printManualRunDebugOutput(result: ManualRunResult) {
    console.group('[Sandpack][manual-run]')
    console.log('result', result)
    console.log('server', getBufferedServerOutput())
    console.log('client', toJsonSafeValue(getBufferedClientOutput()))
    console.groupEnd()
  }

  watch(
    logs,
    (nextLogs, prevLogs) => {
      if (nextLogs.length === prevLogs.length) {
        return
      }

      clientBuffer.value.push({
        type: 'logs',
        data: toJsonSafeValue(nextLogs),
      })
    },
    {
      deep: true,
    },
  )

  watch(
    () => sandpack.status,
    (status) => {
      clientBuffer.value.push({
        type: 'status',
        status,
      })

      flushManualRunSignal()
    },
    {
      immediate: true,
    },
  )

  const unsubscribe = listen((message) => {
    if (message.type === 'stdout' && message.payload.data?.trim()) {
      const normalizedData = normalizeServerStdout(message.payload.data)

      if (!normalizedData) {
        return
      }

      serverBuffer.value.push({
        type: 'stdout',
        data: normalizedData,
      })
      return
    }

    if (message.type === 'done') {
      serverBuffer.value.push({
        type: 'done',
        compilatonError: message.compilatonError,
      })
      flushManualRunSignal()
    }
  })

  onBeforeUnmount(() => {
    unsubscribe?.()
  })

  function waitForRunCompletion() {
    return new Promise<ManualRunResult>((resolve) => {
      resolveManualRun = resolve
      flushManualRunSignal()
    })
  }

  async function handleManualRun() {
    if (isRunning.value) {
      return null
    }

    isRunning.value = true

    try {
      resetBuffers()
      const completion = waitForRunCompletion()
      await sandpack.runSandpack()
      const result = await completion

      printManualRunDebugOutput(result)

      return detectCompileFeedback(result)
    } finally {
      isRunning.value = false
    }
  }

  return {
    handleManualRun,
    isRunning,
  }
}
