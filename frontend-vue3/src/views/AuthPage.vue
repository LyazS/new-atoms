<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthState } from '../composables/useAuthState'

const router = useRouter()
const { login, register } = useAuthState()

const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const isSubmitting = ref(false)
const errorMessage = ref('')

const title = computed(() => (mode.value === 'login' ? '登录继续管理项目' : '创建账号开始管理项目'))
const submitLabel = computed(() => (mode.value === 'login' ? '登录' : '注册并进入'))

async function handleSubmit() {
  if (isSubmitting.value) {
    return
  }

  errorMessage.value = ''
  isSubmitting.value = true

  try {
    if (mode.value === 'login') {
      await login(username.value, password.value)
    } else {
      await register(username.value, password.value)
    }
    await router.push('/sessions')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '提交失败，请稍后再试。'
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-card">
      <div class="auth-copy">
        <p class="eyebrow">User Access</p>
        <h1>{{ title }}</h1>
        <p>
          先完成注册或登录，再进入你的会话管理页。登录后每个用户都只能访问自己的项目和会话。
        </p>
      </div>

      <div class="auth-switcher" role="tablist" aria-label="Authentication mode">
        <button
          type="button"
          class="auth-switcher-button"
          :class="{ 'is-active': mode === 'login' }"
          @click="mode = 'login'"
        >
          登录
        </button>
        <button
          type="button"
          class="auth-switcher-button"
          :class="{ 'is-active': mode === 'register' }"
          @click="mode = 'register'"
        >
          注册
        </button>
      </div>

      <form class="auth-form" @submit.prevent="handleSubmit">
        <label>
          用户名
          <input v-model.trim="username" type="text" minlength="3" maxlength="64" required />
        </label>
        <label>
          密码
          <input v-model="password" type="password" minlength="6" maxlength="128" required />
        </label>
        <p v-if="errorMessage" class="auth-error">{{ errorMessage }}</p>
        <button type="submit" class="primary-button" :disabled="isSubmitting">
          {{ submitLabel }}
        </button>
      </form>
    </section>
  </main>
</template>
