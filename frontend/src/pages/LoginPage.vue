<script setup lang="ts">
import { Lock, User } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth'

const router = useRouter()
const formRef = ref<FormInstance>()
const { isAuthLoading, login } = useAuth()
const form = reactive({
  username: '',
  password: '',
  rememberMe: true,
})
const rules: FormRules<typeof form> = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, message: '用户名至少需要 3 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少需要 6 个字符', trigger: 'blur' },
  ],
}

/**
 * Submit the login form, then send authenticated users back to the QA page.
 */
async function submitLogin() {
  const isValid = await formRef.value?.validate().catch(() => false)
  if (!isValid) return

  try {
    await login({
      username: form.username,
      password: form.password,
      rememberMe: form.rememberMe,
    })
    ElMessage.success('登录成功')
    await router.push({ name: 'qa' })
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '登录失败')
  }
}
</script>

<template>
  <section class="auth-shell">
    <div class="auth-panel">
      <div class="auth-hero">
        <p class="auth-kicker">Knowledge Workspace</p>
        <h1>登录你的知识库工作台</h1>
        <p>
          继续管理文档、分类与问答记录。登录后我们会保留你的本地会话，方便你直接回到上一次的工作流。
        </p>
      </div>

      <el-card shadow="never" class="auth-card">
        <template #header>
          <div class="card-header">
            <span>账号登录</span>
          </div>
        </template>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          class="auth-form"
          status-icon
          :show-message="true"
          :inline-message="false"
        >
          <el-form-item label="用户名" prop="username">
            <el-input v-model="form.username" placeholder="输入用户名" :prefix-icon="User" @keydown.enter="submitLogin" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              show-password
              placeholder="输入密码"
              :prefix-icon="Lock"
              @keydown.enter="submitLogin"
            />
          </el-form-item>
          <div class="auth-remember">
            <el-checkbox v-model="form.rememberMe">记住我</el-checkbox>
            <small>{{ form.rememberMe ? '7 天内免登录' : '仅保留当前短会话' }}</small>
          </div>
          <el-button type="primary" :loading="isAuthLoading" class="full-button" @click="submitLogin">登录</el-button>
          <el-button text class="full-button" @click="router.push({ name: 'register' })">没有账号？去注册</el-button>
        </el-form>
      </el-card>
    </div>
  </section>
</template>
