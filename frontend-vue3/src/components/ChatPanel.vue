<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'

import type { ChatMessage } from '../composables/useSessionConversationState'
import type { SelectedNodeContext } from '../lib/selection'
import { describeSelectedNode } from '../lib/selection'

const draft = defineModel<string>('draft', { required: true })

const props = defineProps<{
  isHydrating: boolean
  isThinking: boolean
  messages: ChatMessage[]
  selectedNodeContext: SelectedNodeContext | null
  selectionModeEnabled: boolean
}>()

const emit = defineEmits<{
  clearSelection: []
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

function getSelectionLabel(selection: SelectedNodeContext | null) {
  return describeSelectedNode(selection)
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
      <div
        v-if="props.selectedNodeContext || props.selectionModeEnabled"
        :class="['selection-hint', { 'is-active': Boolean(props.selectedNodeContext) }]"
      >
        <div class="selection-hint-copy">
          <p class="selection-hint-kicker">预览区点选编辑</p>
          <p v-if="props.selectedNodeContext" class="selection-hint-text">
            当前正在编辑：{{ getSelectionLabel(props.selectedNodeContext) }}
          </p>
          <p v-else class="selection-hint-text">
            在右侧预览中点击一个元素后，再描述你想调整的效果。
          </p>
        </div>
        <button
          v-if="props.selectedNodeContext"
          type="button"
          class="secondary-button selection-clear-button"
          @click="emit('clearSelection')"
        >
          清除
        </button>
      </div>
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
          {{
            props.isThinking
              ? '正在生成中，请不要关闭网页。'
              : props.selectedNodeContext
                ? '本次修改将优先作用于当前选中区域。'
                : 'Enter 发送，Shift+Enter 换行'
          }}
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
