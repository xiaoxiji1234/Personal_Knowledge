<script setup lang="ts">
import { ChatLineRound, Finished, Link, Position, Search } from '@element-plus/icons-vue'
import { useKnowledgeBase } from '../composables/useKnowledgeBase'

const {
  answer,
  askQuestion,
  canAsk,
  categoryOptions,
  confidencePercent,
  confidenceTone,
  isAnswerStreaming,
  isQuerying,
  latencyLabel,
  latencyTone,
  queryCategory,
  queryError,
  queryModeLabel,
  question,
  renderedAnswer,
  scoreLabel,
  useOnlineFallback,
} = useKnowledgeBase()
</script>

<template>
  <section class="qa-layout">
    <el-card shadow="never" class="query-card">
      <template #header>
        <div class="card-header">
          <span><el-icon><ChatLineRound /></el-icon>提问</span>
        </div>
      </template>

      <div class="query-toolbar">
        <el-select v-model="queryCategory" clearable placeholder="全部分类" class="category-select">
          <el-option v-for="category in categoryOptions" :key="category" :label="category" :value="category" />
        </el-select>
        <el-switch v-model="useOnlineFallback" active-text="低置信度时联网查证" />
      </div>
      <el-input
        v-model="question"
        type="textarea"
        :rows="2"
        resize="none"
        placeholder="输入你想问知识库的问题"
        @keydown.enter.exact.prevent="askQuestion"
      />
      <div class="query-actions">
        <div v-if="answer" class="query-summary">
          <div class="query-summary-item">
            <span class="query-summary-label">置信度</span>
            <span class="query-summary-value" :class="confidenceTone">{{ confidencePercent }}%</span>
          </div>
          <div class="query-summary-item">
            <span class="query-summary-label">检索模式</span>
            <span class="query-summary-value query-summary-mode" :class="{ 'is-search': answer.usedSearch }">
              {{ queryModeLabel }}
            </span>
          </div>
          <div class="query-summary-item">
            <span class="query-summary-label">耗时</span>
            <span class="query-summary-value" :class="latencyTone">{{ latencyLabel }}</span>
          </div>
        </div>
        <div class="query-submit">
          <el-button type="primary" :icon="Position" :disabled="!canAsk" :loading="isQuerying" @click="askQuestion">
            发送问题
          </el-button>
        </div>
      </div>
      <el-alert v-if="queryError" class="stack-alert" type="error" :closable="false" show-icon :title="queryError" />
    </el-card>

    <section class="results">
      <el-card v-if="answer" shadow="never" class="answer-card">
        <template #header>
          <div class="card-header">
            <span><el-icon><Finished /></el-icon>回答</span>
            <el-tag v-if="isQuerying" type="primary" effect="light" round>流式输出中</el-tag>
          </div>
        </template>
        <div class="answer-stream-shell" :class="{ streaming: isAnswerStreaming }">
          <div class="markdown-body" v-html="renderedAnswer"></div>
          <span v-if="isAnswerStreaming" class="answer-caret" aria-hidden="true"></span>
        </div>
      </el-card>
      <el-empty v-else class="answer-empty" description="输入问题后，这里会显示精炼回答、引用来源和本地命中。" />

      <section v-if="answer" class="evidence-grid">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span><el-icon><Search /></el-icon>本地命中</span>
            </div>
          </template>
          <el-empty v-if="!answer.localResults.length" description="没有本地命中" />
          <div v-else class="result-list">
            <el-card v-for="item in answer.localResults" :key="item.chunk_id" shadow="never" class="result-item">
              <div class="result-meta">
                <el-text truncated>{{ item.source }}</el-text>
                <el-tag type="success" effect="light">{{ scoreLabel(item.score) }}</el-tag>
              </div>
              <p>{{ item.content }}</p>
            </el-card>
          </div>
        </el-card>

        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span><el-icon><Link /></el-icon>引用来源</span>
            </div>
          </template>
          <el-empty v-if="!answer.citations.length" description="暂无引用" />
          <div v-else class="citation-list">
            <a
              v-for="(citation, index) in answer.citations"
              :key="`${citation.title}-${index}`"
              class="citation"
              :href="citation.url || undefined"
              target="_blank"
              rel="noreferrer"
            >
              <el-tag size="small">{{ citation.source }}</el-tag>
              <strong>{{ citation.title }}</strong>
              <small v-if="citation.chunk_id">{{ citation.chunk_id }}</small>
              <small v-if="citation.fetched_at">{{ citation.fetched_at }}</small>
            </a>
          </div>
        </el-card>
      </section>
    </section>
  </section>
</template>
