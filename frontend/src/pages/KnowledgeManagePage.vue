<script setup lang="ts">
import { computed } from 'vue'
import { Delete, DocumentAdd, Edit, Files, Search, UploadFilled } from '@element-plus/icons-vue'
import type { UploadFile } from 'element-plus'
import { useKnowledgeBase } from '../composables/useKnowledgeBase'

const {
  beforeUpload,
  cancelEditDocument,
  categories,
  categoryOptions,
  closeUploadDialog,
  deleteDocument,
  deletingDocumentId,
  editingDocumentCategory,
  editingDocumentId,
  editingDocumentName,
  documentSearch,
  documentsError,
  filteredDocuments,
  healthError,
  isLoadingDocuments,
  isSavingDocument,
  isUploadDialogOpen,
  isUploading,
  onUploadRemove,
  openUploadDialog,
  saveDocumentChanges,
  selectedCategoryDocumentCount,
  selectedFile,
  selectedManageCategory,
  startEditDocument,
  uploadCategory,
  uploadDialogKey,
  uploadError,
  uploadFile,
  uploadRef,
} = useKnowledgeBase()

const selectedCategoryLabel = computed(() => selectedManageCategory.value || '全部文档')
const pageDescription = computed(() =>
  selectedManageCategory.value ? `当前分类：${selectedManageCategory.value}` : '展示全部已入库文档',
)

/**
 * Adapt Element Plus upload-change events into the shared upload validator.
 */
function handleUploadChange(file: UploadFile) {
  if (file.raw) {
    void beforeUpload(file.raw)
  }
}
</script>

<template>
  <section class="manage-layout">
    <div class="table-toolbar top-search inline-tools">
      <div class="manage-toolbar-filters">
        <el-input
          v-model="documentSearch"
          clearable
          :prefix-icon="Search"
          placeholder="按文件名查询"
          style="width: 200px;"
        />
        <el-select v-model="selectedManageCategory" clearable placeholder="选择分类" class="category-select">
          <el-option v-for="category in categories" :key="category" :label="category" :value="category" />
        </el-select>
      </div>
      <div class="inline-actions">
        <el-button type="primary" :icon="DocumentAdd" @click="openUploadDialog">添加知识库</el-button>
      </div>
    </div>
    <section class="manage-grid">
      <el-card shadow="never" class="documents-card">
        <template #header>
          <div class="card-header">
            <span><el-icon><Files /></el-icon>{{ selectedCategoryLabel }}</span>
            <el-tag>{{ selectedCategoryLabel }} · {{ selectedCategoryDocumentCount }} 个文档</el-tag>
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

        <el-table v-loading="isLoadingDocuments" :data="filteredDocuments" empty-text="暂无文档">
          <el-table-column label="文件" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <template v-if="editingDocumentId === row.documentId">
                <el-input v-model="editingDocumentName" size="small" placeholder="输入文件名" />
              </template>
              <template v-else>
                <span>{{ row.source }}</span>
              </template>
            </template>
          </el-table-column>
          <el-table-column label="分类" width="100">
            <template #default="{ row }">
              <template v-if="editingDocumentId === row.documentId">
                <el-select v-model="editingDocumentCategory" size="small" placeholder="选择分类">
                  <el-option v-for="category in categories" :key="category" :label="category" :value="category" />
                </el-select>
              </template>
              <template v-else>
                <el-tag effect="light">{{ row.category || '默认' }}</el-tag>
              </template>
            </template>
          </el-table-column>
          <el-table-column prop="chunks" label="片段" width="80" />
          <el-table-column prop="parser" label="解析器" width="120" />
          <el-table-column prop="quality" label="质量" width="100" />
          <el-table-column label="操作" align="right" >
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
          <el-form-item label="知识库分类">
            <el-select
              v-model="uploadCategory"
              allow-create
              filterable
              default-first-option
              placeholder="选择或输入分类"
            >
              <el-option v-for="category in categoryOptions" :key="category" :label="category" :value="category" />
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
