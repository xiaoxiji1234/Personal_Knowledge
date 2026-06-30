<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowDown,
  ChatLineRound,
  Expand,
  Files,
  Fold,
  HomeFilled,
  SwitchButton,
  UserFilled,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAuth } from '../composables/useAuth'

const route = useRoute()
const router = useRouter()
const isSidebarCollapsed = ref(false)
const { currentUserName, logout } = useAuth()

const sidebarWidth = computed(() => (isSidebarCollapsed.value ? '64px' : '220px'))
const pageTitle = computed(() => String(route.meta.title ?? '个人知识库'))
const activeMenu = computed(() => String(route.name ?? 'qa'))

const menuItems = [
  { key: 'qa', label: '知识库问答', icon: ChatLineRound },
  { key: 'manage', label: '知识库管理', icon: Files },
]

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
    <el-aside class="admin-sidebar" :width="sidebarWidth" :class="{ collapsed: isSidebarCollapsed }">
      <div class="admin-brand" :class="{ collapsed: isSidebarCollapsed }">
        <div class="brand-mark">K</div>
        <div class="brand-copy">
          <strong>小库知识库</strong>
          <span>Knowledge Admin</span>
        </div>
      </div>

      <el-menu
        :default-active="activeMenu"
        :collapse="isSidebarCollapsed"
        class="admin-menu"
        @select="handleSelect"
      >
        <el-menu-item v-for="item in menuItems" :key="item.key" :index="item.key">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.label }}</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container class="admin-body">
      <el-header class="admin-topbar" height="52px">
        <div class="topbar-left">
          <el-button
            class="sidebar-toggle"
            text
            :icon="isSidebarCollapsed ? Expand : Fold"
            @click="toggleSidebar"
          />
          <el-breadcrumb separator="/">
            <el-breadcrumb-item>
              <el-icon><HomeFilled /></el-icon>
            </el-breadcrumb-item>
            <el-breadcrumb-item>{{ pageTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>

        <div class="topbar-right">
          <el-dropdown trigger="click" @command="handleLogout">
            <button class="user-menu" type="button">
              <el-icon><UserFilled /></el-icon>
              <span>{{ currentUserName }}</span>
              <el-icon><ArrowDown /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout" :icon="SwitchButton">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="admin-main">
        <header class="page-header">
          <div>
            <p class="page-kicker">Workspace</p>
            <h2 class="page-title">{{ pageTitle }}</h2>
          </div>
        </header>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>
