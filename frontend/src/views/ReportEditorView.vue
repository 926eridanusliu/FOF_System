<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { Check, Delete, DocumentChecked, Link, Upload, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, apiMessage } from '../api'
import type { JsonImportResult, Manager, ManifestField, Product, Report, ReportInvitation, ValidationResult } from '../types'
import { cloneReportContent, fieldSection, getFields, statusLabel, strategyOptions, templateLabel } from '../utils/report'
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
const jsonInput = ref<HTMLInputElement>(); const jsonFile = ref<File>(); const jsonPreview = ref<JsonImportResult>(); const jsonDialog = ref(false); const importing = ref(false)
const invitationDialog = ref(false); const invitations = ref<ReportInvitation[]>([]); const invitationDays = ref(7); const createdFillUrl = ref('')

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
  data.auto_strategy_keys.forEach((key) => { content[key] = true })
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
    const selectedProducts = products.value.filter((item) => report.value!.product_ids.includes(item.id))
    if (selectedProducts.length) content.cover_product_name = selectedProducts.map((item) => item.name).join('、')
    report.value.auto_strategy_keys.forEach((key) => { content[key] = true })
    const updated = await api.reports.update(reportId, {
      title: title.value.trim(), content: cloneReportContent(content), conclusion: conclusion.value || null, risk_items: riskItems.value.filter(Boolean),
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

async function deleteReport() {
  if (!report.value) return
  try {
    const { value } = await ElMessageBox.prompt(
      `删除后报告将从工作台隐藏，但报告数据、版本状态和删除原因会保留在回收站。请输入删除原因。`,
      `删除报告：${report.value.title}`,
      { confirmButtonText: '确认删除', cancelButtonText: '取消', inputPlaceholder: '例如：重复报告或测试数据', inputValidator: (text) => text.trim().length >= 2 || '请填写至少2个字的删除原因', type: 'warning' },
    )
    const managerId = report.value.manager_id
    await api.reports.remove(reportId, value.trim())
    dirty.value = false
    ElMessage.success('报告已移入回收站')
    router.push(`/managers/${managerId}`)
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(apiMessage(error)) }
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

async function chooseJson(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  jsonFile.value = file; importing.value = true
  try {
    jsonPreview.value = await api.reports.importJson(reportId, file, false)
    jsonDialog.value = true
  } catch (error) { ElMessage.error(apiMessage(error)) }
  finally { importing.value = false; (event.target as HTMLInputElement).value = '' }
}

async function applyJson() {
  if (!jsonFile.value) return
  importing.value = true
  try {
    await api.reports.importJson(reportId, jsonFile.value, true)
    hydrate(await api.reports.get(reportId)); jsonDialog.value = false
    ElMessage.success('JSON 数据已导入，请检查后再提交')
  } catch (error) { ElMessage.error(apiMessage(error)) }
  finally { importing.value = false }
}

async function openInvitations() {
  try { invitations.value = await api.reports.listInvitations(reportId); invitationDialog.value = true }
  catch (error) { ElMessage.error(apiMessage(error)) }
}

async function createInvitation() {
  try {
    const created = await api.reports.createInvitation(reportId, invitationDays.value)
    createdFillUrl.value = created.fill_url || ''
    invitations.value = await api.reports.listInvitations(reportId)
    ElMessage.success('安全填写链接已生成，请复制并妥善发送')
  } catch (error) { ElMessage.error(apiMessage(error)) }
}

async function copyFillUrl() {
  try { await navigator.clipboard.writeText(createdFillUrl.value); ElMessage.success('链接已复制') }
  catch { ElMessage.warning('复制失败，请手动选择链接复制') }
}

async function revokeInvitation(id: number) {
  try {
    await ElMessageBox.confirm('撤销后该链接将立即失效，是否继续？', '撤销填写链接', { type: 'warning' })
    await api.reports.revokeInvitation(reportId, id); invitations.value = await api.reports.listInvitations(reportId)
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(apiMessage(error)) }
}

async function syncImage(field: string, removed: boolean) {
  try {
    const server = await api.reports.get(reportId)
    hydrating.value = true
    if (removed) delete content[field]; else content[field] = structuredClone(server.content[field])
    await nextTick(); hydrating.value = false; dirty.value = false; report.value = { ...server, content: cloneReportContent(content) }
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
        <input ref="jsonInput" type="file" accept=".json,application/json" hidden @change="chooseJson" />
        <el-button v-if="report.status === 'draft'" :icon="Upload" :loading="importing" @click="jsonInput?.click()">导入 JSON</el-button>
        <el-button v-if="report.status === 'draft'" :icon="Link" @click="openInvitations">管理填写链接</el-button>
        <el-button :icon="DocumentChecked" @click="runValidation">校验报告</el-button>
        <el-button v-if="report.status === 'draft'" :icon="Check" :loading="saving" @click="save(false)">保存草稿</el-button>
        <el-button v-if="report.status === 'draft'" type="primary" @click="submitReport">提交报告</el-button>
        <el-button v-if="report.status === 'submitted'" type="primary" @click="archiveReport">归档报告</el-button>
        <el-button type="danger" plain :icon="Delete" @click="deleteReport">删除报告</el-button>
      </div>

      <el-tabs v-model="activeTab" class="editor-tabs">
        <el-tab-pane name="basic" label="基本信息">
          <section class="field-section">
            <h2 class="field-section-heading">报告与封面信息</h2>
            <el-form label-position="top">
              <div class="field-grid">
                <el-form-item class="span-2" label="报告标题" required :error="!title.trim() ? '报告标题不能为空' : ''"><el-input v-model="title" :disabled="disabled" maxlength="255" show-word-limit /></el-form-item>
                <el-form-item label="管理人名称"><el-input :model-value="manager?.name" disabled /></el-form-item>
                <el-form-item label="关联产品"><el-input :model-value="String(content.cover_product_name || '')" disabled /></el-form-item>
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
        <el-tab-pane name="strategy" label="策略"><section class="field-section"><h2 class="field-section-heading">策略选择与动态分支</h2><el-alert v-if="strategyMissing" title="请至少选择一种投资策略" type="error" :closable="false" show-icon style="margin-bottom:14px" /><el-alert v-if="report.auto_strategy_keys.length" title="标有“产品自动”的策略来自关联产品；你仍可手动补充其他策略。" type="info" :closable="false" style="margin-bottom:14px" /><StrategyEditor :fields="fields" :content="content" :disabled="disabled" :auto-strategy-keys="report.auto_strategy_keys" /><h2 class="field-section-heading" style="margin-top:22px">产品与策略通用问题</h2><FieldGroup :fields="strategyQaFields" :content="content" :disabled="disabled" /><ImageUploader :report-id="reportId" :fields="imageFields.filter((item: ManifestField) => fieldSection(item) === 2)" :content="content" :disabled="disabled" @changed="syncImage" /></section></el-tab-pane>
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

    <el-dialog v-model="jsonDialog" title="JSON 导入预览" width="680px">
      <div v-if="jsonPreview" class="stack">
        <el-alert title="导入不会自动提交报告；应用后请逐项检查。" type="warning" :closable="false" show-icon />
        <div class="definition-grid">
          <div class="definition-item"><label>识别格式</label><div>{{ jsonPreview.source_format }}</div></div>
          <div class="definition-item"><label>识别字段</label><div>{{ jsonPreview.recognized_count }}</div></div>
          <div class="definition-item"><label>冲突字段</label><div>{{ jsonPreview.conflicts.length }}</div></div>
          <div class="definition-item"><label>忽略字段</label><div>{{ jsonPreview.ignored_fields.length }}</div></div>
        </div>
        <el-table v-if="jsonPreview.conflicts.length" :data="jsonPreview.conflicts" max-height="260">
          <el-table-column prop="field" label="冲突字段" min-width="210" />
          <el-table-column label="现有值"><template #default="{ row }">{{ String(row.current) }}</template></el-table-column>
          <el-table-column label="导入值"><template #default="{ row }">{{ String(row.incoming) }}</template></el-table-column>
        </el-table>
        <p v-if="jsonPreview.ignored_fields.length" class="muted">忽略的模板外字段：{{ jsonPreview.ignored_fields.slice(0, 8).join('、') }}</p>
      </div>
      <template #footer><el-button @click="jsonDialog=false">取消</el-button><el-button type="primary" :loading="importing" @click="applyJson">应用导入数据</el-button></template>
    </el-dialog>

    <el-dialog v-model="invitationDialog" title="管理人安全填写链接" width="720px">
      <el-alert title="链接只允许访问这一份草稿；到期、撤销或管理人提交后将不能继续修改。" type="info" :closable="false" show-icon />
      <div style="display:flex;gap:10px;align-items:center;margin:18px 0">
        <span>有效天数</span><el-input-number v-model="invitationDays" :min="1" :max="30" />
        <el-button type="primary" @click="createInvitation">生成新链接</el-button>
      </div>
      <el-input v-if="createdFillUrl" v-model="createdFillUrl" readonly><template #append><el-button @click="copyFillUrl">复制</el-button></template></el-input>
      <el-table :data="invitations" style="margin-top:16px">
        <el-table-column label="创建时间" min-width="170"><template #default="{ row }">{{ new Date(row.created_at).toLocaleString('zh-CN') }}</template></el-table-column>
        <el-table-column label="到期时间" min-width="170"><template #default="{ row }">{{ new Date(row.expires_at).toLocaleString('zh-CN') }}</template></el-table-column>
        <el-table-column label="状态" width="110"><template #default="{ row }">{{ row.revoked_at ? '已撤销' : row.submitted_at ? '已提交' : '填写中' }}</template></el-table-column>
        <el-table-column label="操作" width="90"><template #default="{ row }"><el-button v-if="!row.revoked_at" link type="danger" @click="revokeInvitation(row.id)">撤销</el-button></template></el-table-column>
      </el-table>
    </el-dialog>
  </section>
</template>
