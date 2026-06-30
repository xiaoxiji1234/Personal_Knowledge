<script setup lang="ts">
import { Lock, User } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth'

const router = useRouter()
const formRef = ref<FormInstance>()
const { isAuthLoading, register } = useAuth()
const form = reactive({
  displayName: '',
  username: '',
  password: '',
  confirmPassword: '',
  rememberMe: true,
})
const rules: FormRules<typeof form> = {
  displayName: [
    { required: true, message: '请输入昵称', trigger: 'blur' },
    { min: 2, message: '昵称至少需要 2 个字符', trigger: 'blur' },
  ],
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, message: '用户名至少需要 3 个字符', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少需要 6 个字符', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== form.password) {
          callback(new Error('两次输入的密码不一致'))
          return
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
}

/**
 * Submit the register form and log the new user in immediately.
 */
async function submitRegister() {
  const isValid = await formRef.value?.validate().catch(() => false)
  if (!isValid) return

  try {
    await register({
      displayName: form.displayName,
      username: form.username,
      password: form.password,
      rememberMe: form.rememberMe,
    })
    ElMessage.success('注册成功，已自动登录')
    await router.push({ name: 'qa' })
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '注册失败')
  }
}
</script>

<template>
  <section class="auth-shell">
    <div class="auth-panel">
      <div class="auth-hero">
        <p class="auth-kicker">Create Account</p>
        <h1>新建你的知识库账号</h1>
        <p>
          注册后就可以进入知识库工作台，继续上传资料、整理分类，并把问答记录沉淀成自己的知识资产。
        </p>
      </div>

      <el-card shadow="never" class="auth-card">
        <template #header>
          <div class="card-header">
            <span>注册账号</span>
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
          <el-form-item label="昵称" prop="displayName">
            <el-input
              v-model="form.displayName"
              placeholder="输入昵称"
              :prefix-icon="User"
              @keydown.enter="submitRegister"
            />
          </el-form-item>
          <el-form-item label="用户名" prop="username">
            <el-input v-model="form.username" placeholder="输入用户名" :prefix-icon="User" @keydown.enter="submitRegister" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              show-password
              placeholder="输入密码"
              :prefix-icon="Lock"
              @keydown.enter="submitRegister"
            />
          </el-form-item>
          <el-form-item label="确认密码" prop="confirmPassword">
            <el-input
              v-model="form.confirmPassword"
              type="password"
              show-password
              placeholder="再次输入密码"
              :prefix-icon="Lock"
              @keydown.enter="submitRegister"
            />
          </el-form-item>
          <div class="auth-remember">
            <el-checkbox v-model="form.rememberMe">记住我</el-checkbox>
            <small>{{ form.rememberMe ? '7 天内免登录' : '仅保留当前短会话' }}</small>
          </div>
          <el-button type="primary" :loading="isAuthLoading" class="full-button" @click="submitRegister">注册并登录</el-button>
          <el-button text class="full-button" @click="router.push({ name: 'login' })">已有账号？去登录</el-button>
        </el-form>
      </el-card>
    </div>
  </section>
</template>
