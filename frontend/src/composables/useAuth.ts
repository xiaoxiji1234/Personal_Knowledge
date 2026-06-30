import { computed, ref } from 'vue'

type AuthUser = {
  username: string
  displayName: string
}

type AuthResponse = {
  token: string
  user: AuthUser
  expiresAt: string
}

const apiBase = '/api'
const authTokenKey = 'knowledge-agent-auth-token'
const authExpiresAtKey = 'knowledge-agent-auth-expires-at'
const authUser = ref<AuthUser | null>(null)
const authToken = ref(readStoredToken())
const authExpiresAt = ref(readStoredExpiresAt())
const authReady = ref(false)
const isAuthLoading = ref(false)

/**
 * Provide shared authentication state and actions for login-protected pages.
 */
export function useAuth() {
  return {
    authReady,
    authExpiresAt,
    authToken,
    authUser,
    clearAuthSession,
    currentUserName,
    handleUnauthorized,
    isAuthenticated,
    isAuthLoading,
    ensureAuthReady,
    fetchCurrentUser,
    getAuthHeaders,
    login,
    logout,
    register,
  }
}

const isAuthenticated = computed(() => !!authToken.value && !!authUser.value)
const currentUserName = computed(() => authUser.value?.displayName || authUser.value?.username || '')

/**
 * Ensure the current user profile has been loaded before route checks run.
 */
async function ensureAuthReady() {
  if (authReady.value) return
  if (!authToken.value) {
    authReady.value = true
    return
  }
  await fetchCurrentUser()
  authReady.value = true
}

/**
 * Register a new local account and store the returned login session.
 */
async function register(payload: { username: string; password: string; displayName: string; rememberMe: boolean }) {
  isAuthLoading.value = true
  try {
    const response = await fetch(`${apiBase}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const result = await response.json()
    if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`)
    applyAuthSession(result)
    authReady.value = true
  } finally {
    isAuthLoading.value = false
  }
}

/**
 * Log in with local credentials and persist the returned bearer token.
 */
async function login(payload: { username: string; password: string; rememberMe: boolean }) {
  isAuthLoading.value = true
  try {
    const response = await fetch(`${apiBase}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const result = await response.json()
    if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`)
    applyAuthSession(result)
    authReady.value = true
  } finally {
    isAuthLoading.value = false
  }
}

/**
 * Load the signed-in user profile from the backend using the stored bearer token.
 */
async function fetchCurrentUser() {
  if (isTokenExpired()) {
    clearAuthSession()
    return null
  }
  if (!authToken.value) {
    authUser.value = null
    return null
  }
  isAuthLoading.value = true
  try {
    const response = await fetch(`${apiBase}/auth/me`, {
      headers: {
        Authorization: `Bearer ${authToken.value}`,
      },
    })
    const result = await response.json()
    if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`)
    authUser.value = result.user ?? null
    authReady.value = true
    return authUser.value
  } catch {
    handleUnauthorized()
    return null
  } finally {
    isAuthLoading.value = false
  }
}

/**
 * Revoke the current session token and clear local auth state.
 */
async function logout() {
  try {
    if (authToken.value) {
      await fetch(`${apiBase}/auth/logout`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken.value}`,
        },
      })
    }
  } finally {
    clearAuthSession()
    authReady.value = true
  }
}

/**
 * Persist the new auth session into shared reactive state and localStorage.
 */
function applyAuthSession(result: AuthResponse) {
  authToken.value = result.token
  authUser.value = result.user
  authExpiresAt.value = result.expiresAt
  if (result.token) {
    localStorage.setItem(authTokenKey, result.token)
  }
  if (result.expiresAt) {
    localStorage.setItem(authExpiresAtKey, result.expiresAt)
  }
}

/**
 * Remove any cached auth session from both memory and localStorage.
 */
function clearAuthSession() {
  authToken.value = ''
  authExpiresAt.value = ''
  authUser.value = null
  localStorage.removeItem(authTokenKey)
  localStorage.removeItem(authExpiresAtKey)
}

/**
 * Clear the invalid session and redirect the user back to the login page.
 */
function handleUnauthorized() {
  clearAuthSession()
  authReady.value = true
  if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
    window.location.replace('/login')
  }
}

/**
 * Read the last bearer token from localStorage on initial module load.
 */
function readStoredToken() {
  if (typeof window === 'undefined') return ''
  return localStorage.getItem(authTokenKey) || ''
}

/**
 * Read the stored session expiration timestamp from localStorage.
 */
function readStoredExpiresAt() {
  if (typeof window === 'undefined') return ''
  return localStorage.getItem(authExpiresAtKey) || ''
}

/**
 * Build the Authorization header used by protected API requests.
 */
function getAuthHeaders() {
  const headers: Record<string, string> = {}
  if (authToken.value) {
    headers.Authorization = `Bearer ${authToken.value}`
  }
  return headers
}

/**
 * Check whether the stored session has already passed its expiration time.
 */
function isTokenExpired() {
  if (!authExpiresAt.value) return false
  const expiresAt = new Date(authExpiresAt.value)
  if (Number.isNaN(expiresAt.getTime())) return false
  return expiresAt.getTime() <= Date.now()
}
