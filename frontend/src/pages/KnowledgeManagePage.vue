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

type TreeItem = {
  key: string
  type: 'folder' | 'document'
  label: string
  folderPath: string
  level: number
  documentCount: number
  documentId?: string
  children: TreeItem[]
}

type SourceTreeNode = {
  path: string
  name: string
  level: number
  documentCount: number
  children: SourceTreeNode[]
  documents: Array<{ documentId: string; source: string }>
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
  filteredDocuments,
  folderDepth,
  folderOptions,
  folderTree,
  healthError,
  isFolderExpanded,
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
  selectedFolderDocumentCount,
  selectedManageFolderPath,
  startEditDocument,
  startEditFolder,
  toggleFolderExpanded,
  uploadDialogKey,
  uploadError,
  uploadFile,
  uploadFolderPath,
  uploadRef,
} = useKnowledgeBase()

const treeProps = {
  children: 'children',
  label: 'label',
}
const selectedFolderLabel = computed(() => selectedManageFolderPath.value || defaultFolderPath)
const pageDescription = computed(() => `当前文件夹：${selectedFolderLabel.value}`)
const expandedFolderKeys = computed(() =>
  folderOptions.value.filter((folderPath) => isFolderExpanded(folderPath)).map((folderPath) => folderNodeKey(folderPath)),
)
const treeData = computed(() => folderTree.value.map((node) => toTreeItem(node)))

/**
 * Adapt Element Plus upload-change events into the shared upload validator.
 */
function handleUploadChange(file: UploadFile) {
  if (file.raw) {
    void beforeUpload(file.raw)
  }
}

/**
 * Convert composable folder nodes into Element Plus tree nodes with document leaves.
 */
function toTreeItem(node: SourceTreeNode): TreeItem {
  return {
    key: folderNodeKey(node.path),
    type: 'folder',
    label: node.name,
    folderPath: node.path,
    level: node.level,
    documentCount: node.documentCount,
    children: [
      ...node.children.map((child) => toTreeItem(child)),
      ...node.documents.map((documentItem) => ({
        key: `document:${documentItem.documentId}`,
        type: 'document' as const,
        label: documentItem.source,
        folderPath: node.path,
        level: node.level + 1,
        documentCount: 0,
        documentId: documentItem.documentId,
        children: [],
      })),
    ],
  }
}

/**
 * Build a stable tree key for one folder path.
 */
function folderNodeKey(folderPath: string) {
  return `folder:${folderPath}`
}

/**
 * Select folder nodes from the tree while ignoring document leaves.
 */
function handleTreeNodeClick(data: TreeItem) {
  if (data.type !== 'folder') return
  selectManageFolder(data.folderPath)
}

/**
 * Mirror Element Plus expand events into shared tree state.
 */
function handleTreeNodeExpand(data: TreeItem) {
  if (data.type === 'folder' && !isFolderExpanded(data.folderPath)) {
    toggleFolderExpanded(data.folderPath)
  }
}

/**
 * Mirror Element Plus collapse events into shared tree state.
 */
function handleTreeNodeCollapse(data: TreeItem) {
  if (data.type === 'folder' && isFolderExpanded(data.folderPath)) {
    toggleFolderExpanded(data.folderPath)
  }
}

/**
 * Select a folder as the parent target before creating a child folder.
 */
function selectFolderForCreate(folderPath: string) {
  selectManageFolder(folderPath)
}

/**
 * Save the folder currently being renamed from an inline tree input.
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
        <strong>文档检索</strong>
        <span>{{ pageDescription }}</span>
      </div>
      <div class="toolbar-controls">
        <div class="manage-toolbar-filters">
          <el-input
            v-model="documentSearch"
            clearable
            :prefix-icon="Search"
            placeholder="按文件名查询当前文件夹"
            style="width: 240px;"
          />
        </div>
        <div class="inline-actions">
          <el-button type="primary" :icon="DocumentAdd" @click="openUploadDialog">添加知识库</el-button>
        </div>
      </div>
    </div>

    <section class="manage-folder-grid">
      <el-card shadow="never" class="folder-tree-card">
        <template #header>
          <div class="card-header">
            <span><el-icon><FolderOpened /></el-icon>文件夹</span>
            <el-tag effect="light">最多 3 级</el-tag>
          </div>
        </template>

        <div class="folder-create-bar">
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

        <el-tree
          class="folder-tree"
          :data="treeData"
          :props="treeProps"
          node-key="key"
          :default-expanded-keys="expandedFolderKeys"
          :expand-on-click-node="false"
          @node-click="handleTreeNodeClick"
          @node-expand="handleTreeNodeExpand"
          @node-collapse="handleTreeNodeCollapse"
        >
          <template #default="{ data }">
            <div
              class="folder-tree-node"
              :class="{
                active: data.type === 'folder' && data.folderPath === selectedManageFolderPath,
                document: data.type === 'document',
              }"
            >
              <template v-if="data.type === 'folder'">
                <el-icon class="folder-node-icon">
                  <FolderOpened v-if="isFolderExpanded(data.folderPath)" />
                  <Folder v-else />
                </el-icon>
                <div class="folder-node-main">
                  <template v-if="editingFolderPath === data.folderPath">
                    <el-input
                      v-model="editingFolderName"
                      size="small"
                      autofocus
                      placeholder="文件夹名称"
                      @keydown.enter.prevent="saveEditingFolder"
                      @keydown.esc.prevent="cancelEditFolder"
                    />
                  </template>
                  <template v-else>
                    <strong>{{ data.label }}</strong>
                    <small>{{ data.folderPath }}</small>
                  </template>
                </div>
                <el-tag size="small" effect="plain">{{ data.documentCount }}</el-tag>
                <div class="folder-node-actions">
                  <template v-if="editingFolderPath === data.folderPath">
                    <el-button text size="small" type="primary" :loading="isSavingFolder" @click.stop="saveEditingFolder">
                      保存
                    </el-button>
                    <el-button text size="small" @click.stop="cancelEditFolder">取消</el-button>
                  </template>
                  <template v-else>
                    <el-button
                      circle
                      text
                      size="small"
                      :icon="Plus"
                      title="设为新增父级"
                      aria-label="设为新增父级"
                      :disabled="folderDepth(data.folderPath) >= 3"
                      @click.stop="selectFolderForCreate(data.folderPath)"
                    />
                    <el-button
                      v-if="data.folderPath !== defaultFolderPath"
                      circle
                      text
                      size="small"
                      :icon="Edit"
                      @click.stop="startEditFolder(data.folderPath)"
                    />
                    <el-button
                      v-if="data.folderPath !== defaultFolderPath"
                      circle
                      text
                      type="danger"
                      size="small"
                      :icon="Delete"
                      :loading="deletingFolderPath === data.folderPath"
                      @click.stop="deleteFolder(data.folderPath)"
                    />
                  </template>
                </div>
              </template>
              <template v-else>
                <el-icon class="folder-node-icon"><Document /></el-icon>
                <span class="folder-document-name">{{ data.label }}</span>
              </template>
            </div>
          </template>
        </el-tree>
      </el-card>

      <el-card shadow="never" class="documents-card">
        <template #header>
          <div class="card-header">
            <span><el-icon><Files /></el-icon>{{ selectedFolderLabel }}</span>
            <el-tag>{{ selectedFolderDocumentCount }} 个直接文档</el-tag>
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

        <el-table v-loading="isLoadingDocuments" :data="filteredDocuments" empty-text="当前文件夹暂无文档">
          <el-table-column label="文件" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <template v-if="editingDocumentId === row.documentId">
                <el-input v-model="editingDocumentName" size="small" placeholder="输入文件名" />
              </template>
              <template v-else>
                <span>{{ row.source }}</span>
              </template>
            </template>
          </el-table-column>
          <el-table-column label="文件夹" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <template v-if="editingDocumentId === row.documentId">
                <el-select v-model="editingDocumentFolderPath" size="small" filterable placeholder="选择文件夹">
                  <el-option v-for="folderPath in folderOptions" :key="folderPath" :label="folderPath" :value="folderPath" />
                </el-select>
              </template>
              <template v-else>
                <el-tag effect="light">{{ documentFolderPath(row) }}</el-tag>
              </template>
            </template>
          </el-table-column>
          <el-table-column prop="chunks" label="片段" width="80" />
          <el-table-column prop="parser" label="解析器" width="120" />
          <el-table-column prop="quality" label="质量" width="100" />
          <el-table-column label="操作" align="right" width="150">
            <template #default="{ row }">
              <div class="document-row-actions">
                <template v-if="editingDocumentId === row.documentId">
                  <el-button size="small" type="primary" :loading="isSavingDocument" @click="saveDocumentChanges(row)">保存</el-button>
                  <el-button size="small" @click="cancelEditDocument">取消</el-button>
                </template>
                <template v-else>
                  <el-button circle text size="small" :icon="Edit" @click="startEditDocument(row)" />
                  <el-button
                    circle
                    text
                    type="danger"
                    :icon="Delete"
                    :loading="deletingDocumentId === row.documentId"
                    @click="deleteDocument(row)"
                  />
                </template>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </section>

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
