<script setup lang="ts">
import { useSandpackManualRun } from '../composables/useSandpackManualRun'

const { handleManualRun, isRunning } = useSandpackManualRun()
</script>

<template>
  <button type="button" class="pane-toggle manual-run-button" :disabled="isRunning" @click="handleManualRun">
    {{ isRunning ? '编译中...' : '手动编译' }}
  </button>
</template>
