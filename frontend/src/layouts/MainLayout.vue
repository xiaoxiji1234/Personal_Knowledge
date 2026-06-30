<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChatLineRound, Expand, Files, Fold, FolderAdd } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAuth } from '../composables/useAuth'

const route = useRoute()
const router = useRouter()
const isSidebarCollapsed = ref(false)
const { currentUserName, logout } = useAuth()

const sidebarWidth = computed(() => (isSidebarCollapsed.value ? '76px' : '232px'))
const pageTitle = computed(() => String(route.meta.title ?? '个人知识库'))
const activeMenu = computed(() => String(route.name ?? 'qa'))

/**
 * Toggle the left navigation width for a more focused workspace.
 */
function toggleSidebar() {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
}

/**
 * Navigate from the sidebar menu into the selected routed page.
 */
function handleSelect(key: string) {
  void router.push({ name: key })
}

/**
 * Log out the current local user and send them back to the login page.
 */
async function handleLogout() {
  await logout()
  ElMessage.success('已退出登录')
  await router.push({ name: 'login' })
}
</script>

<template>
  <el-container class="app-shell">
    <el-aside class="sidebar" :width="sidebarWidth" :class="{ collapsed: isSidebarCollapsed }">
      <div class="brand" :class="{ collapsed: isSidebarCollapsed }">
        <h1>小库-知识库</h1>
        <el-button
          class="collapse-button"
          circle
          text
          :icon="isSidebarCollapsed ? Expand : Fold"
          @click="toggleSidebar"
        />
      </div>
      <el-menu :default-active="activeMenu" :collapse="isSidebarCollapsed" class="side-menu" @select="handleSelect">
        <el-menu-item index="qa">
          <el-icon><ChatLineRound /></el-icon>
          <span>问答</span>
        </el-menu-item>
        <el-menu-item index="manage">
          <el-icon><Files /></el-icon>
          <span>知识库管理</span>
        </el-menu-item>
        <el-menu-item index="category-manage">
          <el-icon><FolderAdd /></el-icon>
          <span>分类管理</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-main class="main-panel">
      <header class="page-header">
        <div>
          <h2 class="page-title">{{ pageTitle }}</h2>
        </div>
        <div class="page-actions">
          <el-tag effect="light" round>{{ currentUserName }}</el-tag>
          <el-button text @click="handleLogout">退出登录</el-button>
        </div>
      </header>
      <router-view />
    </el-main>
  </el-container>
</template>
