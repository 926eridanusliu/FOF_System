<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Check, DocumentChecked } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, apiMessage } from '../api'
import type { ManifestField, PublicReport } from '../types'
import { cloneReportContent, fieldSection, getFields, strategyOptions, templateLabel } from '../utils/report'
import FieldGroup from '../components/FieldGroup.vue'
import ImageUploader from '../components/ImageUploader.vue'
import StrategyEditor from '../components/StrategyEditor.vue'
import TableEditor from '../components/TableEditor.vue'

const route = useRoute()
const token = String(route.params.token)
const loading = ref(true); const saving = ref(false); const dirty = ref(false); const hydrating = ref(true)
const report = ref<PublicReport>(); const content = reactive<Record<string, any>>({})
const conclusion = ref(''); const riskItems = ref<string[]>([]); const activeTab = ref('basic')
const lastSavedAt = ref<Date>(); const saveError = ref('')

const disabled = computed(() => report.value ? !report.value.can_edit : true)
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
const strategyMissing = computed(() => !content.cover_strategy_other_text && !strategyOptions.some(([key]) => Boolean(content[key])))

function hydrate(data: PublicReport) {
  hydrating.value = true; report.value = data; conclusion.value = data.conclusion || ''; riskItems.value = [...data.risk_items]
  Object.keys(content).forEach((key) => delete content[key]); Object.assign(content, structuredClone(data.content || {}))
  data.auto_strategy_keys.forEach((key) => { content[key] = true })
  nextTick(() => { dirty.value = false; hydrating.value = false })
}

async function load() {
  loading.value = true
  try { hydrate(await api.publicFill.get(token)) }
  catch (error) { saveError.value = apiMessage(error); ElMessage.error(saveError.value) }
  finally { loading.value = false }
}

watch([content, conclusion, riskItems], () => {
  if (!hydrating.value && !disabled.value) dirty.value = true
}, { deep: true })

async function save(silent = false): Promise<boolean> {
  if (!report.value || disabled.value || saving.value) return !dirty.value
  saving.value = true; saveError.value = ''
  try {
    report.value.auto_strategy_keys.forEach((key) => { content[key] = true })
    hydrate(await api.publicFill.update(token, {
      content: cloneReportContent(content),
      conclusion: conclusion.value || null,
      risk_items: riskItems.value.filter(Boolean),
    }))
    lastSavedAt.value = new Date()
    if (!silent) ElMessage.success('资料已保存')
    return true
  } catch (error) {
    saveError.value = apiMessage(error)
    if (!silent) ElMessage.error(saveError.value)
    return false
  } finally { saving.value = false }
}

async function submit() {
  if (dirty.value && !await save()) return
  if (strategyMissing.value) { activeTab.value = 'strategy'; return ElMessage.warning('请至少选择一种投资策略') }
  try {
    const validation = await api.publicFill.validate(token)
    if (!validation.valid) {
      if (validation.errors.some((item) => item.field.includes('__dynamic_tables') || item.field.includes('table_'))) activeTab.value = 'tables'
      await ElMessageBox.alert(
        validation.errors.slice(0, 8).map((item, index) => `${index + 1}. ${item.message}`).join('\n') + (validation.errors.length > 8 ? `\n……另有 ${validation.errors.length - 8} 项` : ''),
        `尚有 ${validation.errors.length} 项必填内容未完成`,
        { type: 'error', confirmButtonText: '返回填写' },
      )
      return
    }
    await ElMessageBox.confirm('提交后该填写链接将锁定，不能继续修改。确认提交给尽调团队？', '提交资料', { type: 'warning' })
    hydrate(await api.publicFill.submit(token)); ElMessage.success('资料已提交，感谢配合')
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(apiMessage(error)) }
}

async function syncImage(field: string, removed: boolean) {
  try {
    const latest = await api.publicFill.get(token)
    if (removed) delete content[field]; else content[field] = structuredClone(latest.content[field])
    report.value = latest; dirty.value = false
  } catch (error) { ElMessage.error(apiMessage(error)) }
}

function addRisk() { riskItems.value.push('') }
function removeRisk(index: number) { riskItems.value.splice(index, 1) }

const timer = window.setInterval(() => { if (dirty.value && !disabled.value) save(true) }, 30_000)
const beforeUnload = (event: BeforeUnloadEvent) => { if (dirty.value) event.preventDefault() }
onMounted(() => { window.addEventListener('beforeunload', beforeUnload); load() })
onBeforeUnmount(() => { clearInterval(timer); window.removeEventListener('beforeunload', beforeUnload) })
</script>

<template>
  <main class="public-fill-page" v-loading="loading">
    <header class="public-fill-header">
      <div class="brand"><span class="brand-mark">F</span><span><b>FOF 尽调资料填写</b><small>SECURE QUESTIONNAIRE</small></span></div>
      <el-tag v-if="report" :type="disabled ? 'info' : 'warning'" effect="plain">{{ disabled ? '公司方已禁止修改' : '允许填写' }}</el-tag>
    </header>

    <section v-if="report" class="page-wide">
      <div class="page-heading">
        <div><span class="eyebrow">Due Diligence Questionnaire</span><h1>{{ report.title }}</h1><p>{{ report.manager_name }} · {{ report.product_names.join('、') }} · {{ templateLabel[report.template_type] }}</p></div>
      </div>
      <el-alert v-if="disabled" title="当前修改权限已关闭。如需补充或更正，请联系公司尽调人员重新开放修改权限。" type="info" :closable="false" show-icon style="margin-bottom:16px" />
      <el-alert v-else :title="`链接有效期至 ${new Date(report.expires_at).toLocaleString('zh-CN')}；系统每 30 秒自动保存。`" type="info" :closable="false" show-icon style="margin-bottom:16px" />

      <div class="surface editor-shell">
        <div class="report-toolbar">
          <span class="save-state"><span v-if="saving">● 正在保存</span><span v-else-if="dirty">● 有未保存修改</span><span v-else-if="lastSavedAt">✓ 已保存 {{ lastSavedAt.toLocaleTimeString('zh-CN', { hour:'2-digit', minute:'2-digit' }) }}</span><span v-else>请按栏目填写资料</span></span>
          <el-tag v-if="saveError" type="danger" effect="plain">{{ saveError }}</el-tag>
          <span class="toolbar-spacer" />
          <el-button v-if="!disabled" :icon="DocumentChecked" :loading="saving" @click="save(false)">保存</el-button>
          <el-button v-if="!disabled" type="primary" :icon="Check" @click="submit">提交资料</el-button>
        </div>

        <el-tabs v-model="activeTab" class="editor-tabs">
          <el-tab-pane name="basic" label="基本信息"><section class="field-section"><h2 class="field-section-heading">报告与封面信息</h2><el-form label-position="top"><div class="field-grid"><el-form-item label="管理人名称 *"><el-input :model-value="report.manager_name" disabled /></el-form-item><el-form-item label="关联产品 *"><el-input :model-value="report.product_names.join('、')" disabled /></el-form-item><el-form-item label="填报联系人 / 调查人 *"><el-input v-model="content.cover_investigator" :disabled="disabled" /></el-form-item><el-form-item label="报告日期 *"><el-date-picker v-model="content.cover_report_date" type="date" value-format="YYYY.MM.DD" format="YYYY.MM.DD" :disabled="disabled" style="width:100%" /></el-form-item></div></el-form><FieldGroup v-if="otherCoverFields.length" :fields="otherCoverFields" :content="content" :disabled="disabled" /><h2 class="field-section-heading" style="margin-top:22px">补充说明</h2><div class="question-field"><label>尽调结论或补充说明</label><el-input v-model="conclusion" type="textarea" :rows="5" :disabled="disabled" /></div><div class="question-field"><label>主动披露风险项</label><div v-for="(item,index) in riskItems" :key="index" style="display:flex;gap:8px;margin-bottom:8px"><el-input v-model="riskItems[index]" :disabled="disabled" /><el-button :disabled="disabled" @click="removeRisk(index)">移除</el-button></div><el-button :disabled="disabled" @click="addRisk">添加风险项</el-button></div></section></el-tab-pane>
          <el-tab-pane name="team" label="团队与组织"><section class="field-section"><FieldGroup :fields="teamFields" :content="content" :disabled="disabled" /><ImageUploader :public-token="token" :fields="imageFields.filter((item: ManifestField) => fieldSection(item) === 1)" :content="content" :disabled="disabled" @changed="syncImage" /></section></el-tab-pane>
          <el-tab-pane name="strategy" label="策略"><section class="field-section"><el-alert v-if="strategyMissing" title="请至少选择一种投资策略" type="error" :closable="false" show-icon style="margin-bottom:14px" /><StrategyEditor :fields="fields" :content="content" :disabled="disabled" :auto-strategy-keys="report.auto_strategy_keys" /><h2 class="field-section-heading" style="margin-top:22px">产品与策略通用问题</h2><FieldGroup :fields="strategyQaFields" :content="content" :disabled="disabled" /><ImageUploader :public-token="token" :fields="imageFields.filter((item: ManifestField) => fieldSection(item) === 2)" :content="content" :disabled="disabled" @changed="syncImage" /></section></el-tab-pane>
          <el-tab-pane name="risk" label="风控"><section class="field-section"><FieldGroup :fields="riskFields" :content="content" :disabled="disabled" /></section></el-tab-pane>
          <el-tab-pane name="compliance" label="合规与附件"><section class="field-section"><FieldGroup :fields="complianceFields" :content="content" :disabled="disabled" /><ImageUploader :public-token="token" :fields="imageFields.filter((item: ManifestField) => (fieldSection(item) || 0) >= 4)" :content="content" :disabled="disabled" @changed="syncImage" /></section></el-tab-pane>
          <el-tab-pane name="tables" label="数据表格"><section class="field-section"><TableEditor :fields="tableFields" :content="content" :template-type="report.template_type" :disabled="disabled" /></section></el-tab-pane>
        </el-tabs>
      </div>
      <p class="required-note"><span>*</span> 为必填项；标有“（如有）”的项目可选填。</p>
    </section>
    <el-result v-else-if="!loading" icon="error" title="无法打开填写链接" :sub-title="saveError" />
  </main>
</template>
