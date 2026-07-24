<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { Check, DocumentChecked, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, apiMessage } from '../api'
import type { Manager, ManifestField, Product, Report, ValidationResult } from '../types'
import { fieldSection, getFields, statusLabel, strategyOptions, templateLabel } from '../utils/report'
import FieldGroup from '../components/FieldGroup.vue'
import StrategyEditor from '../components/StrategyEditor.vue'
import TableEditor from '../components/TableEditor.vue'
import ImageUploader from '../components/ImageUploader.vue'
import ValidationPanel from '../components/ValidationPanel.vue'
import ScorecardPanel from '../components/ScorecardPanel.vue'
import VersionHistoryPanel from '../components/VersionHistoryPanel.vue'

const route = useRoute(); const router = useRouter(); const reportId = Number(route.params.id)
const loading = ref(true); const saving = ref(false); const dirty = ref(false); const hydrating = ref(true)
const report = ref<Report>(); const manager = ref<Manager>(); const products = ref<Product[]>([])
const title = ref(''); const conclusion = ref(''); const riskItems = ref<string[]>([]); const content = reactive<Record<string, any>>({})
const activeTab = ref('basic'); const validation = ref<ValidationResult>(); const lastSavedAt = ref<Date>(); const autoSaveError = ref('')

const disabled = computed(() => report.value?.status !== 'draft')
const fields = computed(() => report.value ? getFields(report.value.template_type) : [])
const qaFields = computed(() => fields.value.filter((item) => ['qa', 'qa_attachment'].includes(item.type)))
const teamFields = computed(() => qaFields.value.filter((item) => fieldSection(item) === 1))
const strategyQaFields = computed(() => qaFields.value.filter((item) => fieldSection(item) === 2 && !item.strategy && !item.bookmark.startsWith('strat_')))
const riskFields = computed(() => qaFields.value.filter((item) => fieldSection(item) === 3))
const complianceFields = computed(() => qaFields.value.filter((item) => {
  const section = fieldSection(item)
  return (section !== undefined && section >= 4) || (section === undefined && !item.strategy && !item.bookmark.startsWith('strat_'))
}))
const tableFields = computed(() => fields.value.filter((item) => ['table_cell', 'table_cutoff_date'].includes(item.type)))
const imageFields = computed(() => fields.value.filter((item) => item.type === 'image'))
const otherCoverFields = computed(() => fields.value.filter((item) => item.type === 'cover' && !['cover_manager_name','cover_product_name','cover_investigator','cover_report_date','cover_strategy_other_text'].includes(item.bookmark)))
const investigatorMissing = computed(() => !String(content.cover_investigator || '').trim())
const reportDateMissing = computed(() => !String(content.cover_report_date || '').trim())
const strategyMissing = computed(() => !strategyOptions.some(([key]) => Boolean(content[key])))

function hydrate(data: Report) {
  hydrating.value = true; report.value = data; title.value = data.title; conclusion.value = data.conclusion || ''; riskItems.value = [...data.risk_items]
  Object.keys(content).forEach((key) => delete content[key]); Object.assign(content, structuredClone(data.content || {}))
  nextTick(() => { dirty.value = false; hydrating.value = false })
}

async function load() {
  loading.value = true
  try {
    const data = await api.reports.get(reportId); hydrate(data)
    ;[manager.value, products.value] = await Promise.all([api.managers.get(data.manager_id), api.products.list(data.manager_id)])
  } catch (error) { ElMessage.error(apiMessage(error)) }
  finally { loading.value = false }
}

watch([title, conclusion, riskItems, content], () => { if (!hydrating.value && !disabled.value) dirty.value = true }, { deep: true })

async function save(silent = false): Promise<boolean> {
  if (!report.value || disabled.value || saving.value) return !dirty.value
  if (!title.value.trim()) {
    if (!silent) ElMessage.warning('请先填写报告标题')
    return false
  }
  saving.value = true; autoSaveError.value = ''
  try {
    if (manager.value) { content.cover_manager_name = manager.value.name; content.table_1_row0_col1 = manager.value.name }
    const product = products.value.find((item) => item.id === report.value!.product_id)
    if (product) content.cover_product_name = product.name
    const updated = await api.reports.update(reportId, {
      title: title.value.trim(), content: structuredClone(content), conclusion: conclusion.value || null, risk_items: riskItems.value.filter(Boolean),
    })
    report.value = { ...updated }; dirty.value = false; lastSavedAt.value = new Date()
    if (!silent) ElMessage.success('草稿已保存')
    return true
  } catch (error) {
    autoSaveError.value = apiMessage(error); if (!silent) ElMessage.error(autoSaveError.value); return false
  } finally { saving.value = false }
}

async function runValidation() {
  if (dirty.value && !await save()) return
  try {
    validation.value = await api.reports.validate(reportId); activeTab.value = 'validation'
    validation.value.valid ? ElMessage.success('报告校验通过') : ElMessage.warning('报告仍有必填项或格式问题')
  } catch (error) { ElMessage.error(apiMessage(error)) }
}

async function submitReport() {
  if (dirty.value && !await save()) return
  await runValidation(); if (!validation.value?.valid) return
  try {
    await ElMessageBox.confirm('提交后报告将不能继续编辑，确认提交？', '提交尽调报告', { type: 'warning' })
    hydrate(await api.reports.submit(reportId)); ElMessage.success('报告已提交')
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(apiMessage(error)) }
}

async function archiveReport() {
  try { await ElMessageBox.confirm('归档后报告进入历史档案，确认归档？', '归档报告', { type: 'warning' }); hydrate(await api.reports.archive(reportId)); ElMessage.success('报告已归档') }
  catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(apiMessage(error)) }
}

async function handleVersionRestored(restored: Report) {
  hydrate(restored)
  ;[manager.value, products.value] = await Promise.all([
    api.managers.get(restored.manager_id),
    api.products.list(restored.manager_id),
  ])
  validation.value = undefined
  activeTab.value = 'history'
}

async function goPreview() { if (dirty.value && !await save()) return; router.push(`/reports/${reportId}/preview`) }

async function syncImage(field: string, removed: boolean) {
  try {
    const server = await api.reports.get(reportId)
    hydrating.value = true
    if (removed) delete content[field]; else content[field] = structuredClone(server.content[field])
    await nextTick(); hydrating.value = false; dirty.value = false; report.value = { ...server, content: structuredClone(content) }
  } catch (error) { ElMessage.error(apiMessage(error)) }
}

function addRisk() { riskItems.value.push('') }
function removeRisk(index: number) { riskItems.value.splice(index, 1) }

const timer = window.setInterval(() => { if (dirty.value && !disabled.value) save(true) }, 30_000)
const beforeUnload = (event: BeforeUnloadEvent) => { if (dirty.value) event.preventDefault() }
onMounted(() => { window.addEventListener('beforeunload', beforeUnload); load() })
onBeforeUnmount(() => { clearInterval(timer); window.removeEventListener('beforeunload', beforeUnload) })
onBeforeRouteLeave(async () => {
  if (!dirty.value) return true
  try { await ElMessageBox.confirm('当前有尚未保存的修改，确定离开？', '未保存修改', { type: 'warning' }); return true } catch { return false }
})
</script>

<template>
  <section class="page-wide" v-loading="loading">
    <div v-if="report" class="page-heading" style="margin-bottom:16px">
      <div>
        <span class="eyebrow">Due Diligence Report · #{{ report.id }}</span>
        <h1>{{ report.title }}</h1>
        <p>{{ manager?.name }} · {{ templateLabel[report.template_type] }}</p>
      </div>
      <div class="heading-actions">
        <el-tag :type="report.status === 'draft' ? 'warning' : report.status === 'submitted' ? 'primary' : 'info'" effect="plain">{{ statusLabel[report.status] }}</el-tag>
        <el-button :icon="View" @click="goPreview">生成预览</el-button>
      </div>
    </div>

    <div v-if="report" class="surface editor-shell">
      <div class="report-toolbar">
        <span class="save-state">
          <span v-if="saving" class="saving">● 正在保存</span>
          <span v-else-if="dirty">● 有未保存修改</span>
          <span v-else-if="lastSavedAt">✓ 已保存 {{ lastSavedAt.toLocaleTimeString('zh-CN', { hour:'2-digit', minute:'2-digit' }) }}</span>
          <span v-else>每 30 秒自动保存</span>
        </span>
        <el-tag v-if="autoSaveError" type="danger" effect="plain">自动保存失败：{{ autoSaveError }}</el-tag>
        <span class="toolbar-spacer" />
        <el-button :icon="DocumentChecked" @click="runValidation">校验报告</el-button>
        <el-button v-if="report.status === 'draft'" :icon="Check" :loading="saving" @click="save(false)">保存草稿</el-button>
        <el-button v-if="report.status === 'draft'" type="primary" @click="submitReport">提交报告</el-button>
        <el-button v-if="report.status === 'submitted'" type="primary" @click="archiveReport">归档报告</el-button>
      </div>

      <el-tabs v-model="activeTab" class="editor-tabs">
        <el-tab-pane name="basic" label="基本信息">
          <section class="field-section">
            <h2 class="field-section-heading">报告与封面信息</h2>
            <el-form label-position="top">
              <div class="field-grid">
                <el-form-item class="span-2" label="报告标题" required :error="!title.trim() ? '报告标题不能为空' : ''"><el-input v-model="title" :disabled="disabled" maxlength="255" show-word-limit /></el-form-item>
                <el-form-item label="管理人名称"><el-input :model-value="manager?.name" disabled /></el-form-item>
                <el-form-item label="产品名称"><el-input :model-value="String(content.cover_product_name || '')" disabled /></el-form-item>
                <el-form-item label="调查人" required :error="investigatorMissing ? '调查人不能为空' : ''"><el-input v-model="content.cover_investigator" :disabled="disabled" /></el-form-item>
                <el-form-item label="报告日期" required :error="reportDateMissing ? '报告日期不能为空' : ''"><el-date-picker v-model="content.cover_report_date" type="date" value-format="YYYY.MM.DD" format="YYYY.MM.DD" :disabled="disabled" style="width:100%" /></el-form-item>
              </div>
            </el-form>
            <FieldGroup v-if="otherCoverFields.length" :fields="otherCoverFields" :content="content" :disabled="disabled" />
            <h2 class="field-section-heading" style="margin-top:22px">结论与风险项</h2>
            <div class="question-field"><label>尽调结论</label><el-input v-model="conclusion" type="textarea" :rows="5" :disabled="disabled" placeholder="填写综合尽调结论" /></div>
            <div class="question-field"><label>风险项</label><div v-for="(item,index) in riskItems" :key="index" style="display:flex;gap:8px;margin-bottom:8px"><el-input v-model="riskItems[index]" :disabled="disabled" :placeholder="`风险项 ${index+1}`" /><el-button :disabled="disabled" @click="removeRisk(index)">移除</el-button></div><el-button :disabled="disabled" @click="addRisk">添加风险项</el-button></div>
          </section>
        </el-tab-pane>
        <el-tab-pane name="team" label="团队与组织"><section class="field-section"><h2 class="field-section-heading">管理人及团队尽调</h2><FieldGroup :fields="teamFields" :content="content" :disabled="disabled" /><h2 v-if="imageFields.some((item: ManifestField) => fieldSection(item) === 1)" class="field-section-heading">组织与股权图片</h2><ImageUploader :report-id="reportId" :fields="imageFields.filter((item: ManifestField) => fieldSection(item) === 1)" :content="content" :disabled="disabled" @changed="syncImage" /></section></el-tab-pane>
        <el-tab-pane name="strategy" label="策略"><section class="field-section"><h2 class="field-section-heading">策略选择与动态分支</h2><el-alert v-if="strategyMissing" title="请至少选择一种投资策略" type="error" :closable="false" show-icon style="margin-bottom:14px" /><StrategyEditor :fields="fields" :content="content" :disabled="disabled" /><h2 class="field-section-heading" style="margin-top:22px">产品与策略通用问题</h2><FieldGroup :fields="strategyQaFields" :content="content" :disabled="disabled" /><ImageUploader :report-id="reportId" :fields="imageFields.filter((item: ManifestField) => fieldSection(item) === 2)" :content="content" :disabled="disabled" @changed="syncImage" /></section></el-tab-pane>
        <el-tab-pane name="risk" label="风控"><section class="field-section"><h2 class="field-section-heading">风险管理</h2><FieldGroup :fields="riskFields" :content="content" :disabled="disabled" /></section></el-tab-pane>
        <el-tab-pane name="compliance" label="合规与附件"><section class="field-section"><h2 class="field-section-heading">合规、信用与结论</h2><FieldGroup :fields="complianceFields" :content="content" :disabled="disabled" /><h2 v-if="imageFields.some((item: ManifestField) => (fieldSection(item) || 0) >= 4)" class="field-section-heading">信用截图</h2><ImageUploader :report-id="reportId" :fields="imageFields.filter((item: ManifestField) => (fieldSection(item) || 0) >= 4)" :content="content" :disabled="disabled" @changed="syncImage" /></section></el-tab-pane>
        <el-tab-pane name="tables" label="数据表格"><section><h2 class="field-section-heading">模板表格内嵌编辑</h2><TableEditor :fields="tableFields" :content="content" :disabled="disabled" /></section></el-tab-pane>
        <el-tab-pane name="scorecard" label="准入评分卡"><ScorecardPanel :report-id="reportId" :disabled="disabled" /></el-tab-pane>
        <el-tab-pane name="history" label="版本历史">
          <VersionHistoryPanel
            :report-id="reportId"
            :refresh-key="report.submitted_at || ''"
            :has-unsaved-changes="dirty"
            @restored="handleVersionRestored"
          />
        </el-tab-pane>
        <el-tab-pane name="validation" label="校验"><section class="field-section"><h2 class="field-section-heading">提交前校验</h2><ValidationPanel :result="validation" /></section></el-tab-pane>
      </el-tabs>
    </div>
  </section>
</template>
