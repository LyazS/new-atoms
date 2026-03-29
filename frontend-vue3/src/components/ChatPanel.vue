<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'

import type { ChatMessage } from '../composables/useAppProviderState'

const draft = defineModel<string>('draft', { required: true })

const props = defineProps<{
  compileStatusLabel: string
  isHydrating: boolean
  isThinking: boolean
  messages: ChatMessage[]
  sessionId: string | null
}>()

const emit = defineEmits<{
  createSession: []
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
    <div class="panel-header">
      <div>
        <p class="panel-kicker">Agent Console</p>
        <h2>聊天框</h2>
      </div>
      <div class="status-pill">{{ props.compileStatusLabel }}</div>
    </div>

    <div ref="messagesContainer" class="messages" aria-live="polite">
      <article
        v-for="message in props.messages"
        :key="message.id"
        :class="['message', `message-${message.role}`]"
      >
        <div class="message-role">
          {{ message.role === 'assistant' ? 'Agent' : 'You' }}
        </div>

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

        <div
          v-if="message.role === 'assistant' && message.toolCalls.length"
          class="tool-call-list"
        >
          <div
            v-for="toolCall in message.toolCalls"
            :key="toolCall"
            class="tool-call-pill"
          >
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
        <div class="message-role">Agent</div>
        <div class="message-content" v-html="renderMessageContent('正在整理代码修改和编译动作...')"></div>
      </article>
    </div>

    <form class="composer" @submit.prevent="emit('submit')">
      <label class="composer-label" for="prompt">把你的页面需求发给 Agent</label>
      <textarea
        id="prompt"
        v-model="draft"
        placeholder="例如：做一个产品介绍页，使用暖色渐变背景，增加 pricing section。"
        rows="4"
        :disabled="props.isHydrating || props.isThinking"
      />
      <div class="composer-footer">
        <p>
          {{ props.sessionId ? `Session ${props.sessionId.slice(0, 8)} 已连接。` : '发送第一条消息后创建 session。' }}
        </p>
        <div class="composer-actions">
          <button
            type="button"
            class="secondary-button"
            :disabled="props.isHydrating || props.isThinking"
            @click="emit('createSession')"
          >
            新建会话
          </button>
          <button type="submit" :disabled="props.isHydrating || props.isThinking">发送需求</button>
        </div>
      </div>
    </form>
  </section>
</template>
