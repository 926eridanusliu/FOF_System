<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Download, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import DOMPurify from 'dompurify'
import * as mammoth from 'mammoth/mammoth.browser'
import { ApiError, api, apiMessage } from '../api'
import type { GenerateResult, GenerationJob, Manager, Product, Report, ValidationResult } from '../types'
import { statusLabel, templateLabel } from '../utils/report'

const route = useRoute()
const router = useRouter()
const reportId = Number(route.params.id)
const loading = ref(true)
const generating = ref(false)
const report = ref<Report>()
const manager = ref<Manager>()
const product = ref<Product>()
const generated = ref<GenerateResult>()
const generationJob = ref<GenerationJob>()
const previewHtml = ref('')
const validation = ref<ValidationResult>()
const conversionWarnings = ref<string[]>([])
let disposed = false

const productName = computed(() => product.value?.name || String(report.value?.content.cover_product_name || '—'))
const jobStatusText = computed(() => ({
  queued: '等待生成资源',
  running: '正在填充模板并校验',
  completed: '生成完成',
  failed: '生成失败',
}[generationJob.value?.status || 'queued']))

const wait = (milliseconds: number) => new Promise((resolve) => window.setTimeout(resolve, milliseconds))

async function waitForJob(initial: GenerationJob): Promise<GenerationJob> {
  let current = initial
  generationJob.value = current
  const deadline = Date.now() + 5 * 60_000
  while (['queued', 'running'].includes(current.status) && !disposed) {
    if (Date.now() >= deadline) throw new Error('生成任务等待超过 5 分钟，请稍后点击“重新生成”查询或重试')
    await wait(800)
    if (disposed) return current
    current = await api.reports.getGenerationJob(reportId, current.id)
    generationJob.value = current
  }
  return current
}

async function load() {
  if (!Number.isInteger(reportId) || reportId <= 0) {
    router.replace('/managers')
    return
  }
  loading.value = true
  try {
    const reportData = await api.reports.get(reportId)
    report.value = reportData
    const [managerData, products] = await Promise.all([
      api.managers.get(reportData.manager_id),
      api.products.list(reportData.manager_id),
    ])
    manager.value = managerData
    product.value = products.find((item) => item.id === reportData.product_id)
    await generatePreview()
  } catch (error) {
    ElMessage.error(apiMessage(error))
  } finally {
    loading.value = false
  }
}

async function generatePreview() {
  generating.value = true
  validation.value = undefined
  generated.value = undefined
  generationJob.value = undefined
  previewHtml.value = ''
  conversionWarnings.value = []
  try {
    const completed = await waitForJob(await api.reports.createGenerationJob(reportId))
    if (disposed) return
    if (completed.status === 'failed') throw new Error(completed.error || '报告生成失败')
    if (completed.status !== 'completed' || !completed.filename || !completed.download_url || !completed.validation) {
      throw new Error('生成任务未返回完整的文件信息')
    }
    generated.value = {
      filename: completed.filename,
      download_url: completed.download_url,
      validation: completed.validation,
    }
    const response = await fetch(generated.value.download_url)
    if (!response.ok) throw new Error(`读取生成文件失败（${response.status}）`)
    const result = await mammoth.convertToHtml({ arrayBuffer: await response.arrayBuffer() })
    previewHtml.value = DOMPurify.sanitize(result.value, {
      ADD_ATTR: ['colspan', 'rowspan'],
    })
    conversionWarnings.value = result.messages.map((item) => item.message)
  } catch (error) {
    if (error instanceof ApiError && error.status === 422) {
      validation.value = error.detail as ValidationResult
      ElMessage.warning('报告尚未通过校验，暂时不能生成 Word 预览')
    } else {
      ElMessage.error(apiMessage(error))
    }
  } finally {
    generating.value = false
  }
}

onMounted(load)
onBeforeUnmount(() => { disposed = true })
</script>

<template>
  <section class="page-wide" v-loading="loading">
    <div class="page-heading">
      <div>
        <span class="eyebrow">Generated Document Preview · #{{ reportId }}</span>
        <h1>{{ report?.title || '报告预览' }}</h1>
        <p>预览由当前 Word 模板实时生成；排版以下载后的 Word 文件为准。</p>
      </div>
      <div class="heading-actions">
        <el-button :icon="ArrowLeft" @click="router.push(`/reports/${reportId}`)">返回编辑</el-button>
        <el-button :icon="Refresh" :loading="generating" @click="generatePreview">重新生成</el-button>
        <el-button
          v-if="generated"
          type="primary"
          tag="a"
          :icon="Download"
          :href="generated.download_url"
          :download="generated.filename"
        >下载 Word</el-button>
      </div>
    </div>

    <div v-if="report" class="preview-layout">
      <aside class="surface preview-summary">
        <div class="surface-header"><h2>报告信息</h2></div>
        <div class="surface-body definition-list">
          <div><label>管理人</label><span>{{ manager?.name || '—' }}</span></div>
          <div><label>产品</label><span>{{ productName }}</span></div>
          <div><label>模板</label><span>{{ templateLabel[report.template_type] }}</span></div>
          <div><label>状态</label><span>{{ statusLabel[report.status] }}</span></div>
          <div v-if="generated"><label>生成文件</label><span class="mono break-word">{{ generated.filename }}</span></div>
          <div v-if="generationJob"><label>生成任务</label><span>#{{ generationJob.id }} · {{ jobStatusText }}</span></div>
        </div>
        <template v-if="generated">
          <div class="surface-header"><h2>模板匹配结果</h2></div>
          <div class="surface-body mini-metrics">
            <div><strong>{{ generated.validation.matched }}</strong><span>已匹配</span></div>
            <div><strong>{{ generated.validation.missing }}</strong><span>缺失</span></div>
            <div><strong>{{ generated.validation.format_issues }}</strong><span>格式问题</span></div>
            <div><strong>{{ generated.validation.table_issues }}</strong><span>表格问题</span></div>
          </div>
        </template>
      </aside>

      <main>
        <div v-if="generating" class="surface preview-message generation-progress">
          <div>
            <h2>{{ jobStatusText }}</h2>
            <p>{{ generationJob?.status === 'queued' ? '任务已经进入队列，页面无需持续占用生成请求。' : '正在生成 DOCX、检查书签并准备浏览器预览。' }}</p>
            <el-progress
              :percentage="generationJob?.status === 'running' ? 72 : 24"
              :indeterminate="generationJob?.status === 'running'"
              :duration="2"
              :stroke-width="8"
              :show-text="false"
            />
            <small v-if="generationJob" class="mono">TASK #{{ generationJob.id }} · {{ generationJob.template_type }}</small>
          </div>
        </div>
        <div v-else-if="validation" class="surface preview-message validation-block">
          <h2>报告暂不能生成</h2>
          <p>请返回编辑页补全以下必填内容：</p>
          <ul class="validation-list">
            <li v-for="item in validation.errors" :key="`${item.field}-${item.message}`" class="error">
              <strong>{{ item.field }}</strong>：{{ item.message }}
            </li>
          </ul>
          <el-button type="primary" style="margin-top:16px" @click="router.push(`/reports/${reportId}`)">返回报告编辑</el-button>
        </div>
        <article v-else-if="previewHtml" class="preview-paper" v-html="previewHtml" />
        <div v-else class="surface preview-message">尚未生成预览。</div>
        <el-alert
          v-if="conversionWarnings.length"
          style="margin-top:14px"
          type="warning"
          :closable="false"
          title="浏览器预览对部分 Word 样式进行了简化；请下载 Word 查看最终版式。"
        />
      </main>
    </div>
  </section>
</template>
