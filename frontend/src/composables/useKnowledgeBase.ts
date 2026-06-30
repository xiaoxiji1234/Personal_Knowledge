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
  folderPath?: string
  chunks: number
  parser?: string | null
  quality?: string | null
  pages?: number | null
}

type FolderResponse = {
  items: string[]
  count: number
  detail?: string
}

type FolderTreeNode = {
  path: string
  name: string
  level: number
  documentCount: number
  children: FolderTreeNode[]
  documents: KnowledgeDocument[]
}

const apiBase = '/api'
const defaultFolderPath = '默认'
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
const selectedFile = ref<File | null>(null)
const uploadFolderPath = ref(defaultFolderPath)
const uploadError = ref('')
const isUploading = ref(false)
const documents = ref<KnowledgeDocument[]>([])
const folders = ref<string[]>([defaultFolderPath])
const documentsError = ref('')
const isLoadingDocuments = ref(false)
const deletingDocumentId = ref<string | null>(null)
const editingDocumentId = ref<string | null>(null)
const editingDocumentName = ref('')
const editingDocumentFolderPath = ref(defaultFolderPath)
const isSavingDocument = ref(false)
const selectedManageFolderPath = ref(defaultFolderPath)
const documentSearch = ref('')
const newFolderName = ref('')
const editingFolderPath = ref('')
const editingFolderName = ref('')
const isSavingFolder = ref(false)
const deletingFolderPath = ref('')
const expandedFolderPaths = ref<Set<string>>(new Set([defaultFolderPath]))
const question = ref('')
const queryFolderPath = ref('')
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
const folderOptions = computed(() =>
  Array.from(
    new Set(
      [
        defaultFolderPath,
        ...folders.value,
        uploadFolderPath.value,
        editingDocumentFolderPath.value,
        ...documents.value.map((item) => documentFolderPath(item)),
      ].filter(Boolean),
    ),
  ),
)
const filteredDocuments = computed(() => {
  const keyword = documentSearch.value.trim().toLowerCase()
  return documents.value.filter((item) => {
    const itemFolder = documentFolderPath(item)
    const matchedFolder = selectedManageFolderPath.value ? itemFolder === selectedManageFolderPath.value : true
    const matchedName = keyword ? item.source.toLowerCase().includes(keyword) : true
    return matchedFolder && matchedName
  })
})
const selectedFolderDocumentCount = computed(() => filteredDocuments.value.length)
const selectedFolderDepth = computed(() => folderDepth(selectedManageFolderPath.value))
const canCreateChildFolder = computed(() => selectedFolderDepth.value < 3)
const folderTree = computed(() => buildFolderTree(folderOptions.value, documents.value))

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
    canCreateChildFolder,
    confidencePercent,
    confidenceTone,
    defaultFolderPath,
    deletingDocumentId,
    deletingFolderPath,
    editingDocumentFolderPath,
    editingDocumentId,
    editingDocumentName,
    editingFolderName,
    editingFolderPath,
    documentSearch,
    documents,
    documentsError,
    filteredDocuments,
    folderOptions,
    folderTree,
    folders,
    health,
    healthError,
    isLoadingDocuments,
    isAnswerStreaming,
    isQuerying,
    isSavingFolder,
    isSavingDocument,
    isUploadDialogOpen,
    isUploading,
    latencyTone,
    latencyLabel,
    newFolderName,
    queryFolderPath,
    queryError,
    queryModeLabel,
    question,
    renderedAnswer,
    selectedFolderDocumentCount,
    selectedFile,
    selectedManageFolderPath,
    uploadFolderPath,
    uploadDialogKey,
    uploadError,
    uploadRef,
    useOnlineFallback,
    addFolder,
    askQuestion,
    beforeUpload,
    cancelEditDocument,
    cancelEditFolder,
    closeUploadDialog,
    deleteDocument,
    deleteFolder,
    documentFolderPath,
    folderDepth,
    isFolderExpanded,
    loadKnowledgeBase,
    onUploadRemove,
    openUploadDialog,
    renderMarkdown,
    saveDocumentChanges,
    saveFolderName,
    scoreLabel,
    selectManageFolder,
    startEditDocument,
    startEditFolder,
    toggleFolderExpanded,
    uploadFile,
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
 * Refresh documents and folders together to keep page state aligned.
 */
async function loadKnowledgeBase() {
  await Promise.all([loadDocuments(), loadFolders()])
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
 * Load folder options used by upload, query, and document management flows.
 */
async function loadFolders() {
  try {
    const response = await apiFetch(`${apiBase}/folders`)
    const payload: FolderResponse = await response.json()
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`)
    folders.value = normalizeFolderList(payload.items)
    syncFolderSelections()
  } catch {
    folders.value = [defaultFolderPath]
    syncFolderSelections()
  }
}

/**
 * Parse JSON API responses and surface backend error messages consistently.
 */
async function readApiPayload(response: Response): Promise<Record<string, unknown>> {
  const payload = await response.json()
  if (!response.ok) throw new Error(String(payload.detail || `HTTP ${response.status}`))
  return payload
}

/**
 * Open the upload dialog and prefill its folder from the current management context.
 */
function openUploadDialog() {
  uploadFolderPath.value = selectedManageFolderPath.value || uploadFolderPath.value || defaultFolderPath
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
 * Create a folder below the selected folder, with root-level behavior for the default folder.
 */
async function addFolder(): Promise<string | null> {
  const name = newFolderName.value.trim()
  if (!name) return null
  if (!canCreateChildFolder.value) {
    ElMessage.warning('最多只能创建 3 级文件夹')
    return null
  }
  isSavingFolder.value = true
  try {
    const response = await apiFetch(`${apiBase}/folders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ name, parentPath: selectedManageFolderPath.value || defaultFolderPath }),
    })
    const payload = await readApiPayload(response)
    const folderPath = String(payload.folderPath || payload.name || name)
    newFolderName.value = ''
    selectedManageFolderPath.value = folderPath
    expandFolderAncestors(folderPath)
    ElMessage.success(`已添加文件夹 ${folderPath}`)
    await loadKnowledgeBase()
    return folderPath
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '文件夹添加失败')
    return null
  } finally {
    isSavingFolder.value = false
  }
}

/**
 * Enter folder rename mode with the leaf name prefilled.
 */
function startEditFolder(folderPath: string) {
  if (folderPath === defaultFolderPath) return
  editingFolderPath.value = folderPath
  editingFolderName.value = folderLeafName(folderPath)
}

/**
 * Exit folder rename mode without committing changes.
 */
function cancelEditFolder() {
  editingFolderPath.value = ''
  editingFolderName.value = ''
}

/**
 * Persist a folder rename and update local selected paths that point into the renamed subtree.
 */
async function saveFolderName(folderPath: string): Promise<string | null> {
  const name = editingFolderName.value.trim()
  if (!name || name === folderLeafName(folderPath)) {
    cancelEditFolder()
    return null
  }
  isSavingFolder.value = true
  try {
    const response = await apiFetch(`${apiBase}/folders/${encodeFolderPath(folderPath)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ name }),
    })
    const payload = await readApiPayload(response)
    const nextPath = String(payload.folderPath || payload.name || name)
    updateFolderReferences(folderPath, nextPath)
    expandFolderAncestors(nextPath)
    cancelEditFolder()
    ElMessage.success(`已重命名为 ${nextPath}`)
    await loadKnowledgeBase()
    return nextPath
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '文件夹重命名失败')
    return null
  } finally {
    isSavingFolder.value = false
  }
}

/**
 * Delete a folder after confirmation and move all nested documents to the default folder.
 */
async function deleteFolder(folderPath: string): Promise<boolean> {
  if (folderPath === defaultFolderPath) {
    ElMessage.warning('默认文件夹不能删除')
    return false
  }
  try {
    await ElMessageBox.confirm(
      `删除文件夹“${folderPath}”？该文件夹及子文件夹内的文档会保留，并移动到“默认”。`,
      '删除文件夹',
      {
        confirmButtonText: '删除文件夹',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return false
  }

  deletingFolderPath.value = folderPath
  try {
    const response = await apiFetch(`${apiBase}/folders/${encodeFolderPath(folderPath)}`, {
      method: 'DELETE',
    })
    await readApiPayload(response)
    resetDeletedFolderReferences(folderPath)
    ElMessage.success(`已删除文件夹 ${folderPath}，文档已移到默认`)
    await refreshHealth()
    await loadKnowledgeBase()
    return true
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : '文件夹删除失败')
    return false
  } finally {
    deletingFolderPath.value = ''
  }
}

/**
 * Select the active folder in the document management page and reveal its tree ancestors.
 */
function selectManageFolder(folderPath: string) {
  selectedManageFolderPath.value = folderPath || defaultFolderPath
  expandFolderAncestors(selectedManageFolderPath.value)
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
 * Upload the selected document into the selected folder and refresh lists.
 */
async function uploadFile() {
  if (!selectedFile.value) return
  isUploading.value = true
  uploadError.value = ''
  try {
    const folderPath = normalizeFolderPath(uploadFolderPath.value)
    await ensureFolderPathExists(folderPath)
    const form = new FormData()
    form.append('file', selectedFile.value)
    form.append('category', folderPath)
    form.append('folderPath', folderPath)
    const response = await apiFetch(`${apiBase}/upload`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: form,
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`)
    selectedManageFolderPath.value = folderPath
    expandFolderAncestors(folderPath)
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
 * Create any missing folders in one user-entered path before uploading a file there.
 */
async function ensureFolderPathExists(folderPath: string) {
  if (!folderPath || folderPath === defaultFolderPath || folders.value.includes(folderPath)) {
    return
  }
  const segments = folderPath.split('/')
  let currentPath = ''
  for (const segment of segments) {
    currentPath = currentPath ? `${currentPath}/${segment}` : segment
    if (folders.value.includes(currentPath)) {
      continue
    }
    const parentPath = currentPath.includes('/') ? currentPath.slice(0, currentPath.lastIndexOf('/')) : null
    const response = await apiFetch(`${apiBase}/folders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ name: segment, parentPath }),
    })
    await readApiPayload(response)
    folders.value = normalizeFolderList([...folders.value, currentPath])
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
 * Enter document row edit mode with the current name and folder prefilled.
 */
function startEditDocument(document: KnowledgeDocument) {
  editingDocumentId.value = document.documentId
  editingDocumentName.value = document.source
  editingDocumentFolderPath.value = documentFolderPath(document)
}

/**
 * Exit document row edit mode without persisting draft changes.
 */
function cancelEditDocument() {
  editingDocumentId.value = null
  editingDocumentName.value = ''
  editingDocumentFolderPath.value = defaultFolderPath
}

/**
 * Persist one document row's edited display name and folder path.
 */
async function saveDocumentChanges(document: KnowledgeDocument) {
  const source = editingDocumentName.value.trim()
  const folderPath = normalizeFolderPath(editingDocumentFolderPath.value)
  if (!source) {
    ElMessage.error('文件名不能为空')
    return
  }
  if (source === document.source && folderPath === documentFolderPath(document)) {
    cancelEditDocument()
    return
  }

  isSavingDocument.value = true
  documentsError.value = ''
  try {
    const response = await apiFetch(`${apiBase}/documents/${document.documentId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ source, category: folderPath, folderPath }),
    })
    await readApiPayload(response)
    if (!folders.value.includes(folderPath)) {
      folders.value = normalizeFolderList([...folders.value, folderPath])
    }
    selectedManageFolderPath.value = folderPath
    uploadFolderPath.value = folderPath
    expandFolderAncestors(folderPath)
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
  const folderPath = queryFolderPath.value ? normalizeFolderPath(queryFolderPath.value) : null
  const payload = {
    query: question.value.trim(),
    category: folderPath,
    folderPath,
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

/**
 * Read a document's folder path while keeping backward compatibility with category.
 */
function documentFolderPath(document: KnowledgeDocument) {
  return normalizeFolderPath(document.folderPath || document.category)
}

/**
 * Return folder depth; default folder behaves like the virtual root.
 */
function folderDepth(folderPath: string) {
  const normalized = normalizeFolderPath(folderPath)
  if (normalized === defaultFolderPath) return 0
  return normalized.split('/').length
}

/**
 * Toggle one tree node's expanded state.
 */
function toggleFolderExpanded(folderPath: string) {
  const next = new Set(expandedFolderPaths.value)
  if (next.has(folderPath)) {
    next.delete(folderPath)
  } else {
    next.add(folderPath)
  }
  expandedFolderPaths.value = next
}

/**
 * Return whether one tree node should show its nested content.
 */
function isFolderExpanded(folderPath: string) {
  return expandedFolderPaths.value.has(folderPath)
}

/**
 * Build a nested folder tree from persisted folders plus document metadata.
 */
function buildFolderTree(folderPaths: string[], sourceDocuments: KnowledgeDocument[]): FolderTreeNode[] {
  const nodeMap = new Map<string, FolderTreeNode>()
  const rootNodes: FolderTreeNode[] = []
  const ensureNode = (path: string): FolderTreeNode => {
    const normalized = normalizeFolderPath(path)
    const existing = nodeMap.get(normalized)
    if (existing) return existing
    const node: FolderTreeNode = {
      path: normalized,
      name: folderLeafName(normalized),
      level: folderDepth(normalized),
      documentCount: 0,
      children: [],
      documents: [],
    }
    nodeMap.set(normalized, node)
    const parentPath = parentFolderPath(normalized)
    if (parentPath) {
      ensureNode(parentPath).children.push(node)
    } else {
      rootNodes.push(node)
    }
    return node
  }

  ensureNode(defaultFolderPath)
  for (const path of folderPaths) {
    ensurePathWithAncestors(path, ensureNode)
  }
  for (const document of sourceDocuments) {
    ensurePathWithAncestors(documentFolderPath(document), ensureNode).documents.push(document)
  }
  for (const node of nodeMap.values()) {
    node.children.sort((left, right) => left.name.localeCompare(right.name, 'zh-Hans-CN'))
    node.documents.sort((left, right) => left.source.localeCompare(right.source, 'zh-Hans-CN'))
    node.documentCount = countNodeDocuments(node)
  }
  return rootNodes.sort((left, right) => {
    if (left.path === defaultFolderPath) return -1
    if (right.path === defaultFolderPath) return 1
    return left.name.localeCompare(right.name, 'zh-Hans-CN')
  })
}

/**
 * Normalize one folder path for frontend state without silently creating empty levels.
 */
function normalizeFolderPath(path: string | null | undefined) {
  const parts = String(path || defaultFolderPath)
    .split('/')
    .map((part) => part.trim())
    .filter(Boolean)
  if (!parts.length) return defaultFolderPath
  return parts.slice(0, 3).join('/')
}

/**
 * Normalize and sort a folder list while ensuring the default folder is first.
 */
function normalizeFolderList(items: string[] | undefined) {
  const normalized = Array.from(new Set([defaultFolderPath, ...(items ?? []).map((item) => normalizeFolderPath(item))]))
  return [defaultFolderPath, ...normalized.filter((item) => item !== defaultFolderPath).sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'))]
}

/**
 * Keep selected upload/query folders valid after a folder list refresh.
 */
function syncFolderSelections() {
  if (!folders.value.includes(selectedManageFolderPath.value)) {
    selectedManageFolderPath.value = defaultFolderPath
  }
  if (!folders.value.includes(uploadFolderPath.value)) {
    uploadFolderPath.value = selectedManageFolderPath.value || defaultFolderPath
  }
  if (queryFolderPath.value && !folders.value.includes(queryFolderPath.value)) {
    queryFolderPath.value = ''
  }
  expandFolderAncestors(selectedManageFolderPath.value)
}

/**
 * Return the display leaf segment for one folder path.
 */
function folderLeafName(folderPath: string) {
  const normalized = normalizeFolderPath(folderPath)
  if (normalized === defaultFolderPath) return defaultFolderPath
  const parts = normalized.split('/')
  return parts[parts.length - 1] || normalized
}

/**
 * Return the parent folder path, mapping root-level folders under the default folder.
 */
function parentFolderPath(folderPath: string) {
  const normalized = normalizeFolderPath(folderPath)
  if (normalized === defaultFolderPath || !normalized.includes('/')) return null
  return normalized.slice(0, normalized.lastIndexOf('/'))
}

/**
 * Ensure every ancestor node exists before returning the leaf node.
 */
function ensurePathWithAncestors(path: string, ensureNode: (folderPath: string) => FolderTreeNode) {
  const normalized = normalizeFolderPath(path)
  if (normalized === defaultFolderPath) return ensureNode(defaultFolderPath)
  const parts = normalized.split('/')
  let cursor = ''
  for (const part of parts) {
    cursor = cursor ? `${cursor}/${part}` : part
    ensureNode(cursor)
  }
  return ensureNode(normalized)
}

/**
 * Count direct and nested documents so parent folders show useful totals.
 */
function countNodeDocuments(node: FolderTreeNode): number {
  return node.documents.length + node.children.reduce((total, child) => total + countNodeDocuments(child), 0)
}

/**
 * Expand the selected folder and all parents so the active item is visible.
 */
function expandFolderAncestors(folderPath: string) {
  const next = new Set(expandedFolderPaths.value)
  next.add(defaultFolderPath)
  const normalized = normalizeFolderPath(folderPath)
  if (normalized !== defaultFolderPath) {
    const parts = normalized.split('/')
    let cursor = ''
    for (const part of parts) {
      cursor = cursor ? `${cursor}/${part}` : part
      next.add(cursor)
    }
  }
  expandedFolderPaths.value = next
}

/**
 * Update selected paths after a folder prefix has been renamed.
 */
function updateFolderReferences(oldPath: string, nextPath: string) {
  selectedManageFolderPath.value = replaceFolderPrefix(selectedManageFolderPath.value, oldPath, nextPath)
  uploadFolderPath.value = replaceFolderPrefix(uploadFolderPath.value, oldPath, nextPath)
  queryFolderPath.value = queryFolderPath.value ? replaceFolderPrefix(queryFolderPath.value, oldPath, nextPath) : ''
}

/**
 * Move selected paths out of a deleted subtree and back to safe defaults.
 */
function resetDeletedFolderReferences(deletedPath: string) {
  if (isSameOrChildFolder(selectedManageFolderPath.value, deletedPath)) {
    selectedManageFolderPath.value = defaultFolderPath
  }
  if (isSameOrChildFolder(uploadFolderPath.value, deletedPath)) {
    uploadFolderPath.value = defaultFolderPath
  }
  if (queryFolderPath.value && isSameOrChildFolder(queryFolderPath.value, deletedPath)) {
    queryFolderPath.value = ''
  }
  expandedFolderPaths.value = new Set(
    Array.from(expandedFolderPaths.value).filter((path) => !isSameOrChildFolder(path, deletedPath)),
  )
}

/**
 * Replace a folder prefix while preserving child suffixes.
 */
function replaceFolderPrefix(path: string, oldPath: string, nextPath: string) {
  if (path === oldPath) return nextPath
  if (path.startsWith(`${oldPath}/`)) return `${nextPath}/${path.slice(oldPath.length + 1)}`
  return path
}

/**
 * Return whether one path is equal to or nested under another folder path.
 */
function isSameOrChildFolder(path: string, parentPath: string) {
  return path === parentPath || path.startsWith(`${parentPath}/`)
}

/**
 * Encode path segments for FastAPI path parameters while preserving hierarchy separators.
 */
function encodeFolderPath(folderPath: string) {
  return normalizeFolderPath(folderPath).split('/').map(encodeURIComponent).join('/')
}
