<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'

import type { ChatMessage } from '../composables/useAppProviderState'

const draft = defineModel<string>('draft', { required: true })

const props = defineProps<{
  isHydrating: boolean
  isThinking: boolean
  messages: ChatMessage[]
}>()

const emit = defineEmits<{
  submit: []
}>()

const markdown = new MarkdownIt({
  breaks: true,
  linkify: true,
})

const messagesContainer = ref<HTMLDivElement | null>(null)

function hasInProgressAssistant(messages: ChatMessage[]) {
  return messages.some((message) => message.role === 'assistant' && message.isInProgress)
}

function renderMessageContent(content: string) {
  return markdown.render(content)
}

function handleComposerKeydown(event: KeyboardEvent) {
  if (event.isComposing || props.isHydrating || props.isThinking) {
    return
  }

  if (event.key !== 'Enter' || event.shiftKey) {
    return
  }

  event.preventDefault()
  emit('submit')
}

async function scrollMessagesToBottom() {
  await nextTick()
  const container = messagesContainer.value
  if (!container) {
    return
  }
  container.scrollTop = container.scrollHeight
}

watch(
  () => [props.messages, props.isThinking],
  () => {
    void scrollMessagesToBottom()
  },
  { deep: true, flush: 'post' },
)
</script>

<template>
  <section class="panel chat-panel">
    <div ref="messagesContainer" class="messages" aria-live="polite">
      <article
        v-for="message in props.messages"
        :key="message.id"
        :class="['message', `message-${message.role}`]"
      >
        <div v-if="message.role !== 'assistant'" class="message-role">YOU</div>

        <details
          v-if="message.role === 'assistant' && message.reasoningContent"
          class="reasoning-panel"
          open
        >
          <summary>Reasoning</summary>
          <pre>{{ message.reasoningContent }}</pre>
        </details>

        <div
          v-if="message.content"
          class="message-content"
          v-html="renderMessageContent(message.content)"
        ></div>

        <div v-if="message.role === 'assistant' && message.toolCalls.length" class="tool-call-list">
          <div v-for="toolCall in message.toolCalls" :key="toolCall" class="tool-call-pill">
            <span class="tool-call-label">Tool</span>
            <span class="tool-call-name">{{ toolCall }}</span>
          </div>
        </div>

        <div v-if="message.role === 'assistant' && message.isInProgress" class="message-status">
          正在继续生成...
        </div>
      </article>

      <article
        v-show="props.isThinking && !hasInProgressAssistant(props.messages)"
        class="message message-assistant"
      >
        <div
          class="message-content"
          v-html="renderMessageContent('正在整理代码修改和编译动作...')"
        ></div>
      </article>
    </div>

    <form class="composer" @submit.prevent="emit('submit')">
      <textarea
        v-if="!props.isThinking"
        id="prompt"
        v-model="draft"
        placeholder="例如：做一个产品介绍页，使用暖色渐变背景，增加 pricing section。"
        rows="4"
        :disabled="props.isHydrating"
        @keydown="handleComposerKeydown"
      />
      <div class="composer-footer">
        <p class="composer-hint">
          {{ props.isThinking ? '正在生成中，请不要关闭网页。' : 'Enter 发送，Shift+Enter 换行' }}
        </p>
        <button
          type="submit"
          class="composer-submit"
          :disabled="props.isHydrating || props.isThinking"
        >
          {{ props.isThinking ? '生成中' : '发送需求' }}
        </button>
      </div>
    </form>
  </section>
</template>
