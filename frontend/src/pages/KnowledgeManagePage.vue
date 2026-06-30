<script setup lang="ts">
import { computed } from 'vue'
import {
  Delete,
  Document,
  DocumentAdd,
  Edit,
  Files,
  Folder,
  FolderOpened,
  Plus,
  Search,
  UploadFilled,
} from '@element-plus/icons-vue'
import type { UploadFile } from 'element-plus'
import { useKnowledgeBase } from '../composables/useKnowledgeBase'

type SourceTreeNode = {
  path: string
  name: string
  level: number
  documentCount: number
  children: SourceTreeNode[]
  documents: Array<{
    documentId: string
    source: string
    category: string
    folderPath?: string
    chunks: number
    parser?: string | null
    quality?: string | null
    pages?: number | null
  }>
}

type FileManagerRow = {
  key: string
  type: 'folder' | 'document'
  name: string
  path: string
  level: number
  documentCount: number
  chunks?: number
  parser?: string | null
  quality?: string | null
  document?: SourceTreeNode['documents'][number]
  children: FileManagerRow[]
}

const {
  addFolder,
  beforeUpload,
  cancelEditDocument,
  cancelEditFolder,
  canCreateChildFolder,
  closeUploadDialog,
  defaultFolderPath,
  deleteDocument,
  deleteFolder,
  deletingDocumentId,
  deletingFolderPath,
  documentFolderPath,
  documentSearch,
  documentsError,
  editingDocumentFolderPath,
  editingDocumentId,
  editingDocumentName,
  editingFolderName,
  editingFolderPath,
  folderDepth,
  folderOptions,
  folderTree,
  healthError,
  isLoadingDocuments,
  isSavingDocument,
  isSavingFolder,
  isUploadDialogOpen,
  isUploading,
  newFolderName,
  onUploadRemove,
  openUploadDialog,
  saveDocumentChanges,
  saveFolderName,
  selectManageFolder,
  selectedFile,
  selectedManageFolderPath,
  startEditDocument,
  startEditFolder,
  uploadDialogKey,
  uploadError,
  uploadFile,
  uploadFolderPath,
  uploadRef,
} = useKnowledgeBase()

const selectedFolderLabel = computed(() => selectedManageFolderPath.value || defaultFolderPath)
const pageDescription = computed(() => `当前目标文件夹：${selectedFolderLabel.value}`)
const fileManagerRows = computed(() => folderTree.value.map((node) => folderNodeToRow(node)))
const filteredFileManagerRows = computed(() => filterRowsByKeyword(fileManagerRows.value, documentSearch.value.trim().toLowerCase()))
const selectedDirectDocumentCount = computed(() => countDirectDocuments(selectedManageFolderPath.value))

/**
 * Adapt Element Plus upload-change events into the shared upload validator.
 */
function handleUploadChange(file: UploadFile) {
  if (file.raw) {
    void beforeUpload(file.raw)
  }
}

/**
 * Convert folder tree nodes into nested table rows for a file-manager style table.
 */
function folderNodeToRow(node: SourceTreeNode): FileManagerRow {
  return {
    key: `folder:${node.path}`,
    type: 'folder',
    name: node.name,
    path: node.path,
    level: node.level,
    documentCount: node.documentCount,
    children: [
      ...node.children.map((child) => folderNodeToRow(child)),
      ...node.documents.map((document) => ({
        key: `document:${document.documentId}`,
        type: 'document' as const,
        name: document.source,
        path: node.path,
        level: node.level + 1,
        documentCount: 0,
        chunks: document.chunks,
        parser: document.parser,
        quality: document.quality,
        document,
        children: [],
      })),
    ],
  }
}

/**
 * Filter table rows by file/folder name while preserving matching ancestors.
 */
function filterRowsByKeyword(rows: FileManagerRow[], keyword: string): FileManagerRow[] {
  if (!keyword) return rows
  return rows
    .map((row) => {
      const children = filterRowsByKeyword(row.children, keyword)
      const matched = row.name.toLowerCase().includes(keyword) || row.path.toLowerCase().includes(keyword)
      if (!matched && !children.length) return null
      return { ...row, children }
    })
    .filter((row): row is FileManagerRow => Boolean(row))
}

/**
 * Count direct documents in the selected folder for the table header.
 */
function countDirectDocuments(folderPath: string) {
  const row = findFolderRow(fileManagerRows.value, folderPath || defaultFolderPath)
  return row?.children.filter((child) => child.type === 'document').length ?? 0
}

/**
 * Find one folder row recursively by path.
 */
function findFolderRow(rows: FileManagerRow[], folderPath: string): FileManagerRow | null {
  for (const row of rows) {
    if (row.type === 'folder' && row.path === folderPath) return row
    const child = findFolderRow(row.children, folderPath)
    if (child) return child
  }
  return null
}

/**
 * Select one folder row as the target for upload and creation actions.
 */
function selectFolderRow(row: FileManagerRow) {
  if (row.type !== 'folder') return
  selectManageFolder(row.path)
}

/**
 * Save the folder currently being renamed from an inline table input.
 */
function saveEditingFolder() {
  if (!editingFolderPath.value) return
  void saveFolderName(editingFolderPath.value)
}
</script>

<template>
  <section class="manage-layout">
    <div class="table-toolbar top-search inline-tools">
      <div class="toolbar-title">
        <strong>文件管理器</strong>
        <span>{{ pageDescription }}</span>
      </div>
      <div class="toolbar-controls">
        <div class="manage-toolbar-filters">
          <el-input
            v-model="documentSearch"
            clearable
            :prefix-icon="Search"
            placeholder="搜索文件夹或文件"
            style="width: 240px;"
          />
          <div class="folder-create-bar manager-create-bar">
            <el-input
              v-model="newFolderName"
              clearable
              size="small"
              :disabled="!canCreateChildFolder || isSavingFolder"
              :placeholder="canCreateChildFolder ? `在“${selectedFolderLabel}”下新增` : '第 3 级不能继续新增'"
              @keydown.enter.prevent="addFolder"
            />
            <el-button
              size="small"
              type="primary"
              :icon="Plus"
              title="新增子文件夹"
              aria-label="新增子文件夹"
              :disabled="!canCreateChildFolder || !newFolderName.trim()"
              :loading="isSavingFolder && !editingFolderPath"
              @click="addFolder"
            />
          </div>
        </div>
        <div class="inline-actions">
          <el-button type="primary" :icon="DocumentAdd" @click="openUploadDialog">上传文件</el-button>
        </div>
      </div>
    </div>

    <el-card shadow="never" class="documents-card file-manager-card">
      <template #header>
        <div class="card-header">
          <span><el-icon><Files /></el-icon>知识库文件</span>
          <el-tag>{{ selectedFolderLabel }} · {{ selectedDirectDocumentCount }} 个直接文件</el-tag>
        </div>
      </template>
      <el-alert v-if="uploadError" class="stack-alert" type="error" :closable="false" show-icon :title="uploadError" />
      <el-alert v-if="healthError" class="stack-alert" type="error" :closable="false" show-icon title="后端服务暂不可用" />
      <el-alert
        v-if="documentsError"
        class="stack-alert"
        type="error"
        :closable="false"
        show-icon
        :title="documentsError"
      />

      <el-table
        v-loading="isLoadingDocuments"
        :data="filteredFileManagerRows"
        row-key="key"
        empty-text="暂无文件"
        :tree-props="{ children: 'children' }"
        @row-click="selectFolderRow"
      >
        <el-table-column label="名称" min-width="280" show-overflow-tooltip>
          <template #default="{ row }">
            <div
              class="file-manager-name"
              :class="{ active: row.type === 'folder' && row.path === selectedManageFolderPath }"
            >
              <el-button
                v-if="row.type === 'folder'"
                class="file-manager-expand"
                text
                size="small"
                :icon="row.path === selectedManageFolderPath ? FolderOpened : Folder"
                @click.stop="selectManageFolder(row.path)"
              />
              <el-icon v-else class="file-manager-file-icon"><Document /></el-icon>
              <template v-if="row.type === 'folder' && editingFolderPath === row.path">
                <el-input
                  v-model="editingFolderName"
                  size="small"
                  autofocus
                  placeholder="文件夹名称"
                  @keydown.enter.prevent="saveEditingFolder"
                  @keydown.esc.prevent="cancelEditFolder"
                  @click.stop
                />
              </template>
              <template v-else-if="row.type === 'document' && editingDocumentId === row.document?.documentId">
                <el-input
                  v-model="editingDocumentName"
                  size="small"
                  placeholder="输入文件名"
                  @click.stop
                />
              </template>
              <template v-else>
                <div class="file-manager-title">
                  <strong>{{ row.name }}</strong>
                  <small>{{ row.type === 'folder' ? row.path : documentFolderPath(row.document) }}</small>
                </div>
              </template>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            <el-tag v-if="row.type === 'folder'" effect="light">文件夹</el-tag>
            <el-tag v-else type="info" effect="light">文件</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="位置" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <template v-if="row.type === 'document' && editingDocumentId === row.document?.documentId">
              <el-select v-model="editingDocumentFolderPath" size="small" filterable placeholder="选择文件夹" @click.stop>
                <el-option v-for="folderPath in folderOptions" :key="folderPath" :label="folderPath" :value="folderPath" />
              </el-select>
            </template>
            <template v-else>
              <span>{{ row.path }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="数量/片段" width="110">
          <template #default="{ row }">
            <span v-if="row.type === 'folder'">{{ row.documentCount }} 个文件</span>
            <span v-else>{{ row.chunks ?? 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="解析器" width="120">
          <template #default="{ row }">
            <span>{{ row.type === 'document' ? row.parser || '-' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="质量" width="100">
          <template #default="{ row }">
            <span>{{ row.type === 'document' ? row.quality || '-' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" align="right" width="220">
          <template #default="{ row }">
            <div class="document-row-actions">
              <template v-if="row.type === 'folder'">
                <template v-if="editingFolderPath === row.path">
                  <el-button size="small" type="primary" :loading="isSavingFolder" @click.stop="saveEditingFolder">保存</el-button>
                  <el-button size="small" @click.stop="cancelEditFolder">取消</el-button>
                </template>
                <template v-else>
                  <el-button
                    size="small"
                    text
                    :icon="Plus"
                    :disabled="folderDepth(row.path) >= 3"
                    @click.stop="selectManageFolder(row.path)"
                  >
                    选为目标
                  </el-button>
                  <el-button
                    v-if="row.path !== defaultFolderPath"
                    circle
                    text
                    size="small"
                    :icon="Edit"
                    @click.stop="startEditFolder(row.path)"
                  />
                  <el-button
                    v-if="row.path !== defaultFolderPath"
                    circle
                    text
                    type="danger"
                    size="small"
                    :icon="Delete"
                    :loading="deletingFolderPath === row.path"
                    @click.stop="deleteFolder(row.path)"
                  />
                </template>
              </template>
              <template v-else-if="row.document">
                <template v-if="editingDocumentId === row.document.documentId">
                  <el-button size="small" type="primary" :loading="isSavingDocument" @click.stop="saveDocumentChanges(row.document)">保存</el-button>
                  <el-button size="small" @click.stop="cancelEditDocument">取消</el-button>
                </template>
                <template v-else>
                  <el-button circle text size="small" :icon="Edit" @click.stop="startEditDocument(row.document)" />
                  <el-button
                    circle
                    text
                    type="danger"
                    :icon="Delete"
                    :loading="deletingDocumentId === row.document.documentId"
                    @click.stop="deleteDocument(row.document)"
                  />
                </template>
              </template>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="isUploadDialogOpen"
      title="添加知识库文档"
      width="640px"
      destroy-on-close
      @closed="closeUploadDialog"
    >
      <div class="upload-dialog-body">
        <el-upload
          :key="uploadDialogKey"
          ref="uploadRef"
          class="kb-upload"
          drag
          accept=".pdf,.txt,.md,.docx,.xlsx,.xls,.csv"
          :auto-upload="false"
          :limit="1"
          :before-upload="beforeUpload"
          :on-change="handleUploadChange"
          :on-remove="onUploadRemove"
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖拽文件到这里，或 <em>选择文件</em></div>
          <template #tip>
            <div class="el-upload__tip">支持 PDF / Word / Excel（xlsx/xls）/ CSV / TXT / MD</div>
          </template>
        </el-upload>
        <el-alert
          v-if="selectedFile"
          type="info"
          :closable="false"
          show-icon
          :title="`已选择：${selectedFile.name}`"
        />
        <el-form label-position="top">
          <el-form-item label="知识库文件夹">
            <el-select v-model="uploadFolderPath" filterable placeholder="选择文件夹">
              <el-option v-for="folderPath in folderOptions" :key="folderPath" :label="folderPath" :value="folderPath" />
            </el-select>
          </el-form-item>
        </el-form>
        <el-alert v-if="uploadError" type="error" :closable="false" show-icon :title="uploadError" />
      </div>
      <template #footer>
        <el-button @click="isUploadDialogOpen = false">取消</el-button>
        <el-button type="primary" :icon="DocumentAdd" :disabled="!selectedFile" :loading="isUploading" @click="uploadFile">
          上传
        </el-button>
      </template>
    </el-dialog>
  </section>
</template>
