<script setup lang="ts">
defineProps<{
  connectionLabel: string
}>()
</script>

<template>
  <header class="hero">
    <div>
      <p class="eyebrow">Btoms</p>
      <h1>Agent Chat + Live Sandpack Studio</h1>
      <p class="hero-copy">Btoms 前端工作台，左侧对话驱动生成，右侧即时预览代码效果。</p>
    </div>
    <div class="hero-badge">
      <span class="hero-badge-dot" />
      {{ connectionLabel }}
    </div>
  </header>
</template>
