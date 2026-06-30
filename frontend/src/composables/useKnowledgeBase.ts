import { computed, onMounted, ref } from 'vue'
import MarkdownIt from 'markdown-it'
import { ElMessage, ElMessageBox, type UploadInstance } from 'element-plus'
import { useAuth } from './useAuth'

type Citation = {
  source: 'local' | 'web' | 'search' | string
  title: string
  url?: string | null
  chunk_id?: string | null
  fetched_at?: string | null
}

type LocalResult = {
  chunk_id: string
  score: number
  content: string
  source: string
  meta: Record<string, unknown>
}

type QueryResponse = {
  text: string
  citations: Citation[]
  confidence: number
  usedSearch: boolean
  latencyMs: number
  localResults: LocalResult[]
}

type QueryStreamMeta = {
  citations: Citation[]
  confidence: number
  usedSearch: boolean
  localResults: LocalResult[]
}

type QueryStreamDone = {
  latencyMs: number
}

type QueryStreamEvent = {
  event: string
  data: Record<string, unknown>
}

type KnowledgeDocument = {
  documentId: string
  source: string
  category: string
  chunks: number
  parser?: string | null
  quality?: string | null
  pages?: number | null
}

type CategoryResponse = {
  items: string[]
  count: number
  detail?: string
}

const apiBase = '/api'
const defaultCategory = '默认'
const { getAuthHeaders, handleUnauthorized } = useAuth()
const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

const health = ref<{ ok: boolean; chunks: number } | null>(null)
const healthError = ref('')
const uploadRef = ref<UploadInstance>()
const uploadDialogKey = ref(0)
const isUploadDialogOpen = ref(false)
const isCategoryDialogOpen = ref(false)
const selectedFile = ref<File | null>(null)
const uploadCategory = ref(defaultCategory)
const uploadError = ref('')
const isUploading = ref(false)
const documents = ref<KnowledgeDocument[]>([])
const categories = ref<string[]>([defaultCategory])
const documentsError = ref('')
const isLoadingDocuments = ref(false)
const deletingDocumentId = ref<string | null>(null)
const editingDocumentId = ref<string | null>(null)
const editingDocumentName = ref('')
const editingDocumentCategory = ref(defaultCategory)
const isSavingDocument = ref(false)
const selectedManageCategory = ref('')
const documentSearch = ref('')
const newCategoryName = ref('')
const editingCategory = ref('')
const editingCategoryName = ref('')
const isSavingCategory = ref(false)
const deletingCategory = ref('')
const question = ref('')
const queryCategory = ref('')
const useOnlineFallback = ref(true)
const answer = ref<QueryResponse | null>(null)
const queryError = ref('')
const isQuerying = ref(false)
const displayedAnswerText = ref('')
const pendingAnswerText = ref('')
const isAnswerStreaming = ref(false)

const confidencePercent = computed(() => Math.round((answer.value?.confidence ?? 0) * 100))
const queryModeLabel = computed(() => (answer.value?.usedSearch ? '联网查证' : '本地知识库'))
const confidenceTone = computed(() => {
  if (confidencePercent.value >= 80) return 'is-good'
  if (confidencePercent.value >= 60) return 'is-warn'
  return 'is-bad'
})
const latencyLabel = computed(() => {
  if (!answer.value) return ''
  if (isQuerying.value && answer.value.latencyMs <= 0) return '生成中'
  return `${answer.value.latencyMs}ms`
})
const latencyTone = computed(() => {
  if (isQuerying.value && (answer.value?.latencyMs ?? 0) <= 0) return 'is-pending'
  const latency = answer.value?.latencyMs ?? 0
  if (latency <= 800) return 'is-good'
  if (latency <= 2000) return 'is-warn'
  return 'is-bad'
})
const canAsk = computed(() => question.value.trim().length > 0 && !isQuerying.value)
const renderedAnswer = computed(() => renderMarkdown(displayedAnswerText.value || (answer.value?.text ?? '')))
const categoryOptions = computed(() => Array.from(new Set([defaultCategory, ...categories.value, uploadCategory.value].filter(Boolean))))
const filteredDocuments = computed(() => {
  const keyword = documentSearch.value.trim().toLowerCase()
  return documents.value.filter((item) => {
    const matchedCategory = selectedManageCategory.value ? item.category === selectedManageCategory.value : true
    const matchedName = keyword ? item.source.toLowerCase().includes(keyword) : true
    return matchedCategory && matchedName
  })
})
const selectedCategoryDocumentCount = computed(() => filteredDocuments.value.length)

let hasMounted = false
let answerTypingTimer: ReturnType<typeof setInterval> | null = null

/**
 * Provide shared knowledge-base state and actions for routed pages.
 */
export function useKnowledgeBase() {
  onMounted(() => {
    if (hasMounted) return
    hasMounted = true
    void refreshHealth()
    void loadKnowledgeBase()
  })

  return {
    answer,
    canAsk,
    categories,
    categoryOptions,
    confidencePercent,
    confidenceTone,
    deletingCategory,
    deletingDocumentId,
    editingDocumentCategory,
    editingDocumentId,
    editingDocumentName,
    documentSearch,
    documents,
    documentsError,
    editingCategory,
    editingCategoryName,
    filteredDocuments,
    health,
    healthError,
    isCategoryDialogOpen,
    isLoadingDocuments,
    isAnswerStreaming,
    isQuerying,
    isSavingCategory,
    isSavingDocument,
    isUploadDialogOpen,
    isUploading,
    latencyTone,
    latencyLabel,
    newCategoryName,
    queryCategory,
    queryError,
    queryModeLabel,
    question,
    renderedAnswer,
    selectedCategoryDocumentCount,
    selectedFile,
    selectedManageCategory,
    uploadCategory,
    uploadDialogKey,
    uploadError,
    uploadRef,
    useOnlineFallback,
    addCategory,
    askQuestion,
    beforeUpload,
    cancelEditCategory,
    closeCategoryDialog,
    closeUploadDialog,
    deleteCategory,
    deleteDocument,
    loadKnowledgeBase,
    onUploadRemove,
    openCategoryDialog,
    openUploadDialog,
    renderMarkdown,
    saveDocumentChanges,
    saveCategoryName,
    scoreLabel,
    selectManageCategory,
    startEditDocument,
    startEditCategory,
    uploadFile,
    cancelEditDocument,
  }
}

/**
 * Refresh backend health for graceful UI degradation.
 */
async function refreshHealth() {
  healthError.value = ''
  try {
    const response = await apiFetch(`${apiBase}/health`)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    health.value = await response.json()
  } catch (error) {
    health.value = null
    healthError.value = error instanceof Error ? error.message : '服务不可用'
  }
}

/**
 * Refresh documents and categories together to keep page state aligned.
 */
async function loadKnowledgeBase() {
  await Promise.all([loadDocuments(), loadCategories()])
}

/**
 * Load knowledge-base documents for management and filtering.
 */
async function loadDocuments() {
  documentsError.value = ''
  isLoadingDocuments.value = true
  try {
    const response = await apiFetch(`${apiBase}/documents`)
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`)
    documents.value = payload.items ?? []
  } catch (error) {
    documentsError.value = error instanceof Error ? error.message : '文档列表加载失败'
  } finally {
    isLoadingDocuments.value = false
  }
}

/**
 * Load category options used by upload and query flows.
 */
async function loadCategories() {
  try {
    const response = await apiFetch(`${apiBase}/categories`)
    const payload: CategoryResponse = await response.json()
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`)
    categories.value = payload.items?.length ? payload.items : ['默认']
    if (selectedManageCategory.value && !categories.value.includes(selectedManageCategory.value)) {
      selectedManageCategory.value = ''
    }
    if (!categories.value.includes(uploadCategory.value)) {
      uploadCategory.value = '默认'
    }
    if (queryCategory.value && !categories.value.includes(queryCategory.value)) {
      queryCategory.value = ''
    }
  } catch {
    categories.value = ['默认']
  }
}

/**
 * Parse JSON API responses and surface backend error messages consistently.
 */
async function readApiPayload(response: Response): Promise<Record<string, unknown>> {
  const payload = await response.json()
  if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`)
  return payload
}

/**
 * Open the category-management dialog with a clean draft value.
 */
function openCategoryDialog() {
  newCategoryName.value = ''
  isCategoryDialogOpen.value = true
}

/**
 * Close the category-management dialog and clear temporary input.
 */
function closeCategoryDialog() {
  newCategoryName.value = ''
  isCategoryDialogOpen.value = false
}

/**
 * Open the upload dialog and prefill its category from current context.
 */
function openUploadDialog() {
  uploadCategory.value = selectedManageCategory.value || uploadCategory.value || '默认'
  uploadError.value = ''
  isUploadDialogOpen.value = true
}

/**
 * Reset upload dialog state so stale files are not reused accidentally.
 */
function resetUploadDialog() {
  selectedFile.value = null
  uploadError.value = ''
  uploadRef.value?.clearFiles()
  uploadDialogKey.value += 1
}

/**
 * Close the upload dialog and discard any temporary file selection.
 */
function closeUploadDialog() {
  resetUploadDialog()
  isUploadDialogOpen.value = false
}

/**
 * Create a new category and refresh dependent lists.
 */
async function addCategory(): Promise<string | null> {
  const name = newCategoryName.value.trim()
  if (!name) return null
  isSavingCategory.value = true
  try {
    const response = await apiFetch(`${apiBase}/categories`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ name }),
    })
    await readApiPayload(response)
    newCategoryName.value = ''
    uploadCategory.value = name
    ElMessage.success(`已添加分类 ${name}`)
    isCategoryDialogOpen.value = false
    await loadKnowledgeBase()
    return name
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '分类添加失败')
    return null
  } finally {
    isSavingCategory.value = false
  }
}

/**
 * Enter category rename mode with the current name prefilled.
 */
function startEditCategory(category: string) {
  editingCategory.value = category
  editingCategoryName.value = category
}

/**
 * Exit category rename mode without committing changes.
 */
function cancelEditCategory() {
  editingCategory.value = ''
  editingCategoryName.value = ''
}

/**
 * Persist a category rename and update related page filters.
 */
async function saveCategoryName(category: string): Promise<string | null> {
  const name = editingCategoryName.value.trim()
  if (!name || name === category) {
    cancelEditCategory()
    return null
  }
  isSavingCategory.value = true
  try {
    const response = await apiFetch(`${apiBase}/categories/${encodeURIComponent(category)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ name }),
    })
    await readApiPayload(response)
    if (selectedManageCategory.value === category) selectedManageCategory.value = name
    if (uploadCategory.value === category) uploadCategory.value = name
    if (queryCategory.value === category) queryCategory.value = name
    cancelEditCategory()
    ElMessage.success(`已重命名为 ${name}`)
    await loadKnowledgeBase()
    return name
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '分类重命名失败')
    return null
  } finally {
    isSavingCategory.value = false
  }
}

/**
 * Delete a category after user confirmation and keep documents reassigned safely.
 */
async function deleteCategory(category: string): Promise<boolean> {
  try {
    await ElMessageBox.confirm(`删除分类“${category}”？该分类下文档会保留并移到“默认”。`, '删除分类', {
      confirmButtonText: '删除分类',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return false
  }

  deletingCategory.value = category
  try {
    const response = await apiFetch(`${apiBase}/categories/${encodeURIComponent(category)}`, {
      method: 'DELETE',
    })
    await readApiPayload(response)
    if (selectedManageCategory.value === category) selectedManageCategory.value = '默认'
    if (uploadCategory.value === category) uploadCategory.value = '默认'
    if (queryCategory.value === category) queryCategory.value = ''
    ElMessage.success(`已删除分类 ${category}`)
    await loadKnowledgeBase()
    return true
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '分类删除失败')
    return false
  } finally {
    deletingCategory.value = ''
  }
}

/**
 * Toggle the active category filter in the document management page.
 */
function selectManageCategory(category: string) {
  selectedManageCategory.value = selectedManageCategory.value === category ? '' : category
}

/**
 * Capture the file selected by Element Plus and prevent auto upload.
 */
function beforeUpload(file: File) {
  selectedFile.value = file
  uploadError.value = ''
  return false
}

/**
 * Clear upload selection state when the user removes the pending file.
 */
function onUploadRemove() {
  selectedFile.value = null
  uploadError.value = ''
}

/**
 * Upload the selected document into the knowledge base and refresh lists.
 */
async function uploadFile() {
  if (!selectedFile.value) return
  isUploading.value = true
  uploadError.value = ''
  try {
    const form = new FormData()
    form.append('file', selectedFile.value)
    form.append('category', uploadCategory.value || '默认')
    const response = await apiFetch(`${apiBase}/upload`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: form,
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`)
    ElMessage.success('上传成功')
    isUploadDialogOpen.value = false
    resetUploadDialog()
    await refreshHealth()
    await loadKnowledgeBase()
  } catch (error) {
    uploadError.value = error instanceof Error ? error.message : '上传失败'
  } finally {
    isUploading.value = false
  }
}

/**
 * Delete one document and clear answer state when its citation is still visible.
 */
async function deleteDocument(document: KnowledgeDocument) {
  try {
    await ElMessageBox.confirm(`删除知识库文档“${document.source}”？此操作会移除它的所有向量片段。`, '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }

  deletingDocumentId.value = document.documentId
  documentsError.value = ''
  try {
    const response = await apiFetch(`${apiBase}/documents/${document.documentId}`, {
      method: 'DELETE',
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`)
    if (answer.value?.citations.some((citation) => citation.title === document.source)) {
      answer.value = null
    }
    ElMessage.success(`已删除 ${document.source}`)
    await refreshHealth()
    await loadKnowledgeBase()
  } catch (error) {
    documentsError.value = error instanceof Error ? error.message : '删除失败'
  } finally {
    deletingDocumentId.value = null
  }
}

/**
 * Enter document row edit mode with the current name and category prefilled.
 */
function startEditDocument(document: KnowledgeDocument) {
  editingDocumentId.value = document.documentId
  editingDocumentName.value = document.source
  editingDocumentCategory.value = document.category || defaultCategory
}

/**
 * Exit document row edit mode without persisting draft changes.
 */
function cancelEditDocument() {
  editingDocumentId.value = null
  editingDocumentName.value = ''
  editingDocumentCategory.value = defaultCategory
}

/**
 * Persist one document row's edited display name and category.
 */
async function saveDocumentChanges(document: KnowledgeDocument) {
  const source = editingDocumentName.value.trim()
  const category = (editingDocumentCategory.value || defaultCategory).trim() || defaultCategory
  if (!source) {
    ElMessage.error('文件名不能为空')
    return
  }
  if (source === document.source && category === (document.category || defaultCategory)) {
    cancelEditDocument()
    return
  }

  isSavingDocument.value = true
  documentsError.value = ''
  try {
    const response = await apiFetch(`${apiBase}/documents/${document.documentId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ source, category }),
    })
    await readApiPayload(response)
    if (!categories.value.includes(category)) {
      categories.value = Array.from(new Set([...categories.value, category]))
    }
    if (selectedManageCategory.value && !categories.value.includes(selectedManageCategory.value)) {
      selectedManageCategory.value = ''
    }
    if (uploadCategory.value === document.category) {
      uploadCategory.value = category
    }
    cancelEditDocument()
    ElMessage.success('文档已更新')
    await loadKnowledgeBase()
  } catch (error) {
    documentsError.value = error instanceof Error ? error.message : '文档更新失败'
  } finally {
    isSavingDocument.value = false
  }
}

/**
 * Send the current question to the backend and store the returned answer data.
 */
async function askQuestion() {
  if (!canAsk.value) return
  isQuerying.value = true
  isAnswerStreaming.value = true
  queryError.value = ''
  resetAnswerStreamState()
  answer.value = createEmptyQueryResponse()
  const payload = {
    query: question.value.trim(),
    category: queryCategory.value || null,
    useOnlineFallback: useOnlineFallback.value,
    userId: 'web',
  }
  try {
    const response = await apiFetch(`${apiBase}/query/stream`, {
      method: 'POST',
      headers: {
        'Accept': 'text/event-stream',
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      },
      body: JSON.stringify(payload),
    })
    if (!response.ok) {
      const errorPayload = await response.json()
      throw new Error(errorPayload.detail || `HTTP ${response.status}`)
    }
    if (!response.body) {
      await requestQuestionOnce(payload)
      return
    }
    await consumeQueryStream(response)
    await waitForAnswerTyping()
  } catch (error) {
    if (!displayedAnswerText.value) {
      answer.value = null
    }
    queryError.value = error instanceof Error ? error.message : '查询失败'
  } finally {
    isAnswerStreaming.value = false
    await waitForAnswerTyping()
    isQuerying.value = false
  }
}

/**
 * Create a blank query response draft so stream metadata can fill fields incrementally.
 */
function createEmptyQueryResponse(): QueryResponse {
  return {
    text: '',
    citations: [],
    confidence: 0,
    usedSearch: false,
    latencyMs: 0,
    localResults: [],
  }
}

/**
 * Reset the answer streaming buffers before a new query starts.
 */
function resetAnswerStreamState() {
  displayedAnswerText.value = ''
  pendingAnswerText.value = ''
  stopAnswerTyping()
}

/**
 * Start the typewriter timer that reveals streamed answer text in small chunks.
 */
function startAnswerTyping() {
  if (answerTypingTimer) return
  answerTypingTimer = setInterval(() => {
    if (!pendingAnswerText.value) {
      if (!isAnswerStreaming.value) stopAnswerTyping()
      return
    }
    const chunkSize = pendingAnswerText.value.length > 24 ? 4 : 2
    const nextText = pendingAnswerText.value.slice(0, chunkSize)
    pendingAnswerText.value = pendingAnswerText.value.slice(chunkSize)
    displayedAnswerText.value += nextText
    if (answer.value) {
      answer.value.text = displayedAnswerText.value
    }
    if (!pendingAnswerText.value && !isAnswerStreaming.value) {
      stopAnswerTyping()
    }
  }, 18)
}

/**
 * Stop the active typewriter timer once no queued text remains.
 */
function stopAnswerTyping() {
  if (!answerTypingTimer) return
  clearInterval(answerTypingTimer)
  answerTypingTimer = null
}

/**
 * Wait until all queued answer text has been revealed on screen.
 */
async function waitForAnswerTyping() {
  while (pendingAnswerText.value || isAnswerStreaming.value) {
    await new Promise((resolve) => setTimeout(resolve, 20))
  }
}

/**
 * Fallback to the original non-streaming endpoint when streaming is unavailable.
 */
async function requestQuestionOnce(payload: Record<string, unknown>) {
  const response = await apiFetch(`${apiBase}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(payload),
  })
  const result = await response.json()
  if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`)
  answer.value = result
  displayedAnswerText.value = result.text ?? ''
}

/**
 * Read the SSE response stream and route each event into local answer state.
 */
async function consumeQueryStream(response: Response) {
  const reader = response.body?.getReader()
  if (!reader) throw new Error('当前环境不支持流式响应')
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      applyQueryStreamEvent(frame)
    }
  }

  buffer += decoder.decode()
  if (buffer.trim()) {
    applyQueryStreamEvent(buffer)
  }
}

/**
 * Parse one SSE frame and apply its metadata, text delta, or completion state.
 */
function applyQueryStreamEvent(frame: string) {
  const parsed = parseQueryStreamEvent(frame)
  if (!parsed) return
  if (parsed.event === 'meta') {
    applyQueryStreamMeta(parsed.data as QueryStreamMeta)
    return
  }
  if (parsed.event === 'delta') {
    appendAnswerDelta(String(parsed.data.text ?? ''))
    return
  }
  if (parsed.event === 'done') {
    finalizeStreamAnswer(parsed.data as QueryStreamDone)
    return
  }
  if (parsed.event === 'error') {
    throw new Error(String(parsed.data.detail ?? '查询失败'))
  }
}

/**
 * Decode one SSE event block into its event name and JSON payload.
 */
function parseQueryStreamEvent(frame: string): QueryStreamEvent | null {
  const lines = frame.split('\n').map((line) => line.trim()).filter(Boolean)
  let event = 'message'
  const dataLines: string[] = []
  for (const line of lines) {
    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
  }
  if (!dataLines.length) return null
  return {
    event,
    data: JSON.parse(dataLines.join('\n')) as Record<string, unknown>,
  }
}

/**
 * Apply metadata delivered before the first answer text delta arrives.
 */
function applyQueryStreamMeta(meta: QueryStreamMeta) {
  answer.value = {
    ...(answer.value ?? createEmptyQueryResponse()),
    citations: meta.citations ?? [],
    confidence: meta.confidence ?? 0,
    usedSearch: !!meta.usedSearch,
    localResults: meta.localResults ?? [],
  }
}

/**
 * Queue one streamed answer delta so the typewriter can reveal it gradually.
 */
function appendAnswerDelta(text: string) {
  if (!text) return
  pendingAnswerText.value += text
  startAnswerTyping()
}

/**
 * Store final latency metadata once the backend finishes streaming.
 */
function finalizeStreamAnswer(done: QueryStreamDone) {
  if (answer.value) {
    answer.value.latencyMs = done.latencyMs ?? 0
  }
  isAnswerStreaming.value = false
}

/**
 * Send one protected request with the current bearer token and handle expired sessions.
 */
async function apiFetch(input: RequestInfo | URL, init?: RequestInit) {
  const response = await fetch(input, {
    ...init,
    headers: {
      ...getAuthHeaders(),
      ...(init?.headers ?? {}),
    },
  })
  if (response.status === 401) {
    handleUnauthorized()
  }
  return response
}

/**
 * Convert retrieval scores into rounded percentages for badges.
 */
function scoreLabel(score: number) {
  return `${Math.round(score * 100)}%`
}

/**
 * Render markdown safely for answer display.
 */
function renderMarkdown(content: string) {
  return markdown.render(content)
}
