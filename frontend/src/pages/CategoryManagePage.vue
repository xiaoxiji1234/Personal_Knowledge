<script setup lang="ts">
import { computed, ref } from 'vue'
import { Delete, Edit, FolderAdd, Files } from '@element-plus/icons-vue'
import { useKnowledgeBase } from '../composables/useKnowledgeBase'

const {
  addCategory,
  cancelEditCategory,
  categories,
  deleteCategory,
  deletingCategory,
  documents,
  editingCategory,
  editingCategoryName,
  isSavingCategory,
  newCategoryName,
  saveCategoryName,
  startEditCategory,
} = useKnowledgeBase()

type CategoryTableRow =
  | {
      name: string
      count: number
      isNew: false
    }
  | {
      name: string
      count: null
      isNew: true
    }

const categorySearch = ref('')
const isCreatingCategory = ref(false)

const categoryStats = computed(() =>
  categories.value.map((category) => ({
    name: category,
    count: documents.value.filter((document) => document.category === category).length,
    isNew: false as const,
  })),
)

/**
 * Filter categories by name while keeping the table search focused on classification.
 */
const filteredCategoryStats = computed(() => {
  const keyword = categorySearch.value.trim().toLowerCase()
  if (!keyword) return categoryStats.value
  return categoryStats.value.filter((item) => item.name.toLowerCase().includes(keyword))
})

/**
 * Append a temporary editable row to the bottom of the category table.
 */
function handleStartCreateCategory() {
  newCategoryName.value = ''
  isCreatingCategory.value = true
}

/**
 * Remove the temporary creation row and clear its draft value.
 */
function handleCancelCreateCategory() {
  newCategoryName.value = ''
  isCreatingCategory.value = false
}

/**
 * Persist the active rename draft for a category row.
 */
async function handleSaveCategoryName(category: string) {
  await saveCategoryName(category)
}

/**
 * Persist the newly inserted category row and collapse it after success.
 */
async function handleCreateCategory() {
  const created = await addCategory()
  if (!created) return
  isCreatingCategory.value = false
}

/**
 * Delete the selected category from the management page.
 */
async function handleDeleteCategory(category: string) {
  await deleteCategory(category)
}

/**
 * Build the table rows, always keeping the editable create row at the bottom.
 */
const categoryTableRows = computed<CategoryTableRow[]>(() => {
  const rows: CategoryTableRow[] = [...filteredCategoryStats.value]
  if (isCreatingCategory.value) {
    rows.push({ name: '__new__', count: null, isNew: true })
  }
  return rows
})
</script>

<template>
  <section class="manage-layout">
    <div class="table-toolbar top-search inline-tools">
      <div class="toolbar-title">
        <strong>分类维护</strong>
        <span>统一维护知识库分类与文档归属</span>
      </div>
      <div class="toolbar-controls">
        <div class="manage-toolbar-filters">
          <el-input v-model="categorySearch" clearable placeholder="查询分类" />
        </div>
        <div class="inline-actions">
          <el-button type="primary" :icon="FolderAdd" @click="handleStartCreateCategory">新增分类</el-button>
        </div>
      </div>
    </div>

    <section class="manage-grid">
      <el-card shadow="never" class="documents-card">
        <template #header>
          <div class="card-header">
            <span><el-icon><Files /></el-icon>分类列表</span>
            <el-tag>{{ filteredCategoryStats.length }} / {{ categories.length }} 个分类</el-tag>
          </div>
        </template>

        <el-table :data="categoryTableRows" empty-text="暂无分类">
          <el-table-column label="分类" min-width="220">
            <template #default="{ row }">
              <template v-if="row.isNew">
                <div class="category-manage-edit">
                  <el-input
                    v-model="newCategoryName"
                    size="small"
                    placeholder="输入新分类名称"
                    @keyup.enter.stop="handleCreateCategory"
                    @keyup.esc.stop="handleCancelCreateCategory"
                  />
                </div>
              </template>
              <template v-else-if="editingCategory === row.name">
                <div class="category-manage-edit">
                  <el-input
                    v-model="editingCategoryName"
                    size="small"
                    @keyup.enter.stop="handleSaveCategoryName(row.name)"
                    @keyup.esc.stop="cancelEditCategory"
                  />
                  <el-button size="small" type="primary" :loading="isSavingCategory" @click.stop="handleSaveCategoryName(row.name)">
                    保存
                  </el-button>
                </div>
              </template>
              <template v-else>
                <div class="category-manage-main">
                  <span class="category-manage-title">{{ row.name }}</span>
                </div>
              </template>
            </template>
          </el-table-column>
          <el-table-column label="文档数" width="120" align="center">
            <template #default="{ row }">
              <el-tag v-if="!row.isNew" effect="light">{{ row.count }}</el-tag>
              <el-tag v-else type="info" effect="plain">新建</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" align="right">
            <template #default="{ row }">
              <span v-if="row.isNew" class="category-manage-actions">
                <el-button size="small" type="primary" :loading="isSavingCategory" @click.stop="handleCreateCategory">
                  保存
                </el-button>
                <el-button size="small" @click.stop="handleCancelCreateCategory">取消</el-button>
              </span>
              <span v-else-if="editingCategory !== row.name" class="category-manage-actions">
                <el-button
                  circle
                  text
                  size="small"
                  :icon="Edit"
                  :disabled="row.name === '默认'"
                  @click.stop="startEditCategory(row.name)"
                />
                <el-button
                  circle
                  text
                  type="danger"
                  size="small"
                  :icon="Delete"
                  :disabled="row.name === '默认'"
                  :loading="deletingCategory === row.name"
                  @click.stop="handleDeleteCategory(row.name)"
                />
              </span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </section>
  </section>
</template>
