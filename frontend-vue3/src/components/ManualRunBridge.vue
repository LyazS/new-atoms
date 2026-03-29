<script setup lang="ts">
import { watch } from 'vue'
import { useSandpack } from 'sandpack-vue3'

import { useSandpackManualRun } from '../composables/useSandpackManualRun'
import type { CompileFeedback } from '../composables/useSandpackManualRun'

const props = defineProps<{
  workspaceFiles: Record<string, string>
  runRequestKey: number
}>()

const emit = defineEmits<{
  manualRunResult: [feedback: CompileFeedback]
  runningChange: [value: boolean]
}>()

const { sandpack } = useSandpack()
const { handleManualRun, isRunning } = useSandpackManualRun()

let knownPaths = new Set<string>()
let lastRunRequestKey = 0

function syncWorkspace(nextFiles: Record<string, string>) {
  const nextPaths = new Set(Object.keys(nextFiles))

  for (const [path, code] of Object.entries(nextFiles)) {
    sandpack.updateFile(path, code)
  }

  for (const path of knownPaths) {
    if (!nextPaths.has(path)) {
      sandpack.deleteFile(path)
    }
  }

  knownPaths = nextPaths
}

async function runAndEmit() {
  const feedback = await handleManualRun()
  if (!feedback) {
    return
  }

  emit('manualRunResult', feedback)
}

watch(
  () => props.workspaceFiles,
  (nextFiles) => {
    syncWorkspace(nextFiles)
  },
  {
    deep: true,
    immediate: true,
  },
)

watch(
  () => props.runRequestKey,
  async (nextValue) => {
    if (nextValue <= lastRunRequestKey) {
      return
    }

    lastRunRequestKey = nextValue
    await runAndEmit()
  },
)

watch(
  isRunning,
  (value) => {
    emit('runningChange', value)
  },
  {
    immediate: true,
  },
)
</script>

<template>
  <button type="button" class="pane-toggle manual-run-button" :disabled="isRunning" @click="runAndEmit">
    {{ isRunning ? '编译中...' : '手动编译' }}
  </button>
</template>
