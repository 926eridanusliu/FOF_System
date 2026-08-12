<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Delete, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, apiMessage } from '../api'
import type {
  QualitativeScoreInputs,
  ReportScorecard,
  ScorecardCalculationInput,
} from '../types'

const props = defineProps<{ reportId: number; disabled: boolean }>()
const loading = ref(true)
const uploading = ref(false)
const calculating = ref(false)
const savingScores = ref(false)
const generatingExcel = ref(false)
const scorecard = ref<ReportScorecard>()
const settings = reactive({
  date_column: '',
  nav_column: '',
  benchmark_column: '',
  benchmark_mode: 'absolute' as 'absolute' | 'benchmark',
  risk_free_rate_percent: 0,
})
const qualitative = reactive<Partial<QualitativeScoreInputs>>({})
const manualScores = reactive<Record<string, number | null>>({})

const hasResult = computed(() => scorecard.value?.total_score !== null && scorecard.value?.total_score !== undefined)
const scoreTagType = computed(() => scorecard.value?.admitted ? 'success' : 'danger')
const manualSummary = computed(() => {
  const value = (key: string) => Number(manualScores[key] ?? 0)
  const quantitative = Math.max(value('one_year_return'), value('relative_return'))
    + value('long_term_return') + value('monthly_win_rate') + value('max_drawdown')
    + value('sharpe_ratio') + value('calmar_ratio')
  const qualitativeScore = value('managed_products') + value('investment_manager')
    + value('research_team') + value('team_stability') + value('allocation_value')
    + value('risk_control') + value('coinvestment')
  const deduction = value('compliance_deduction')
  return { quantitative, qualitative: qualitativeScore, deduction, total: quantitative + qualitativeScore - deduction }
})

function hydrate(data: ReportScorecard) {
  scorecard.value = data
  const saved = data.calculation_inputs
  settings.date_column = saved.date_column || data.detected_columns.date || ''
  settings.nav_column = saved.nav_column || data.detected_columns.nav || ''
  settings.benchmark_column = saved.benchmark_column || data.detected_columns.benchmark || ''
  settings.benchmark_mode = saved.benchmark_mode || 'absolute'
  settings.risk_free_rate_percent = saved.risk_free_rate_percent ?? 0
  Object.keys(qualitative).forEach((key) => delete (qualitative as Record<string, unknown>)[key])
  if (saved.qualitative) Object.assign(qualitative, saved.qualitative)
  Object.keys(manualScores).forEach((key) => delete manualScores[key])
  for (const item of data.template_items) manualScores[item.key] = data.manual_scores[item.key] ?? null
}

async function load() {
  loading.value = true
  try { hydrate(await api.reports.getScorecard(props.reportId)) }
  catch (error) { ElMessage.error(apiMessage(error)) }
  finally { loading.value = false }
}

async function chooseFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!/\.(xlsx|csv)$/i.test(file.name)) {
    ElMessage.warning('仅支持 .xlsx 或 .csv 净值文件')
    return
  }
  uploading.value = true
  try {
    hydrate(await api.reports.uploadNav(props.reportId, file))
    ElMessage.success('净值文件已上传并完成列识别')
  } catch (error) { ElMessage.error(apiMessage(error)) }
  finally { uploading.value = false }
}

async function removeNav() {
  try {
    await ElMessageBox.confirm('删除后已计算的评分结果也会清空，确认继续？', '删除净值文件', { type: 'warning' })
    await api.reports.removeNav(props.reportId)
    hydrate(await api.reports.getScorecard(props.reportId))
    ElMessage.success('净值文件和评分结果已删除')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(apiMessage(error))
  }
}

const requiredNumbers: Array<[keyof QualitativeScoreInputs, string]> = [
  ['managed_scale_100m', '管理规模'],
  ['active_product_count', '存续产品数量'],
  ['company_headcount', '公司总人数'],
  ['manager_same_strategy_years', '投资经理同策略业绩年限'],
  ['manager_industry_years', '投资经理投研从业年限'],
  ['research_headcount', '投研团队人数'],
  ['core_research_experience_years', '核心投研经验年限'],
  ['core_departures_1y', '近1年核心投研离职人数'],
  ['core_departures_3y', '近3年核心投研离职人数'],
  ['current_strategy_scale_100m', '当前策略管理规模'],
  ['theoretical_capacity_100m', '策略理论容量'],
  ['risk_team_headcount', '风控团队人数'],
  ['risk_team_experience_years', '风控团队相关经验'],
  ['manager_coinvest_percent', '管理人跟投比例'],
  ['manager_coinvest_lock_years', '管理人跟投锁定期'],
  ['regulatory_events_3y', '近3年监管处罚/自律处分次数'],
  ['negative_or_litigation_events_3y', '近3年重大负面/涉诉次数'],
]
const requiredChoices: Array<[keyof QualitativeScoreInputs, string]> = [
  ['strategy_scale_group', '策略规模分类'],
  ['manager_philosophy_level', '投资理念成熟度'],
  ['manager_profile_stable', '投资经理履历/风格是否稳定'],
  ['research_background_match', '投研团队专业背景是否匹配'],
  ['research_live_track_record', '投研团队是否有实盘验证'],
  ['incentive_level', '激励机制'],
  ['differentiation_level', '策略差异化'],
  ['risk_system_level', '风控制度建设'],
  ['core_personal_coinvest', '核心投研是否个人跟投'],
]

async function calculate() {
  if (!scorecard.value?.nav_original_filename) {
    ElMessage.warning('请先上传净值文件')
    return
  }
  if (!settings.date_column || !settings.nav_column) {
    ElMessage.warning('请选择日期列和产品净值列')
    return
  }
  if (settings.benchmark_mode === 'benchmark' && !settings.benchmark_column) {
    ElMessage.warning('相对收益模式必须选择基准净值列')
    return
  }
  for (const [key, label] of requiredNumbers) {
    const value = qualitative[key]
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      ElMessage.warning(`请填写：${label}`)
      return
    }
  }
  for (const [key, label] of requiredChoices) {
    if (qualitative[key] === undefined || qualitative[key] === null) {
      ElMessage.warning(`请选择：${label}`)
      return
    }
  }
  calculating.value = true
  try {
    const body: ScorecardCalculationInput = {
      date_column: settings.date_column,
      nav_column: settings.nav_column,
      benchmark_column: settings.benchmark_mode === 'benchmark' ? settings.benchmark_column : null,
      benchmark_mode: settings.benchmark_mode,
      risk_free_rate_percent: settings.risk_free_rate_percent,
      qualitative: qualitative as QualitativeScoreInputs,
    }
    hydrate(await api.reports.calculateScorecard(props.reportId, body))
    ElMessage.success('自动测算完成，结果已带入人工评分表；可复核调整后生成 Excel')
  } catch (error) { ElMessage.error(apiMessage(error)) }
  finally { calculating.value = false }
}

function validatedScores(): Record<string, number> | null {
  const output: Record<string, number> = {}
  for (const item of scorecard.value?.template_items || []) {
    const value = manualScores[item.key]
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      ElMessage.warning(`请填写：${item.indicator}`)
      return null
    }
    if (value < 0 || (item.maximum !== null && value > item.maximum)) {
      ElMessage.warning(item.maximum === null ? `${item.indicator}不能小于0` : `${item.indicator}应在0至${item.maximum}分之间`)
      return null
    }
    output[item.key] = value
  }
  return output
}

async function saveManualScores(showMessage = true): Promise<boolean> {
  const scores = validatedScores()
  if (!scores) return false
  savingScores.value = true
  try {
    hydrate(await api.reports.saveManualScorecard(props.reportId, scores))
    if (showMessage) ElMessage.success('人工评分已保存')
    return true
  } catch (error) {
    ElMessage.error(apiMessage(error))
    return false
  } finally { savingScores.value = false }
}

async function generateExcel() {
  if (!props.disabled && !(await saveManualScores(false))) return
  if (props.disabled && !hasResult.value) {
    ElMessage.warning('该历史报告尚未保存评分结果')
    return
  }
  generatingExcel.value = true
  try {
    const result = await api.reports.generateScorecardExcel(props.reportId)
    const link = document.createElement('a')
    link.href = result.download_url
    link.download = result.filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    ElMessage.success('已生成并下载独立的准入打分卡 Excel')
  } catch (error) { ElMessage.error(apiMessage(error)) }
  finally { generatingExcel.value = false }
}

onMounted(load)
</script>

<template>
  <section v-loading="loading" class="scorecard-panel">
    <div class="scorecard-section">
      <div class="scorecard-heading">
        <div><h2>1. 净值自动测算（可选）</h2><p>支持 .xlsx/.csv；测算结果仅作为建议分数，员工仍可在下方复核调整。</p></div>
        <div class="scorecard-actions">
          <label v-if="!disabled" class="file-button" :class="{ loading: uploading }">
            <input type="file" accept=".xlsx,.csv" :disabled="uploading" @change="chooseFile" />
            <el-icon><UploadFilled /></el-icon>{{ uploading ? '正在解析…' : '选择净值文件' }}
          </label>
          <el-button v-if="scorecard?.nav_original_filename && !disabled" :icon="Delete" @click="removeNav">删除</el-button>
        </div>
      </div>
      <el-alert
        v-if="scorecard?.nav_original_filename"
        type="success"
        :closable="false"
        :title="`已上传：${scorecard.nav_original_filename} · 工作表：${scorecard.nav_sheet_name || 'CSV'}`"
      />
      <el-alert v-else type="info" :closable="false" title="尚未上传净值文件，不能计算定量指标。" />

      <el-form v-if="scorecard?.nav_original_filename" label-position="top" class="scorecard-form">
        <div class="field-grid">
          <el-form-item label="日期列" required>
            <el-select v-model="settings.date_column" :disabled="disabled" style="width:100%">
              <el-option v-for="column in scorecard.nav_columns" :key="column" :label="column" :value="column" />
            </el-select>
          </el-form-item>
          <el-form-item label="产品净值列" required>
            <el-select v-model="settings.nav_column" :disabled="disabled" style="width:100%">
              <el-option v-for="column in scorecard.nav_columns" :key="column" :label="column" :value="column" />
            </el-select>
          </el-form-item>
          <el-form-item label="相对收益模式">
            <el-select v-model="settings.benchmark_mode" :disabled="disabled" style="width:100%">
              <el-option label="无明确基准，按绝对收益正负" value="absolute" />
              <el-option label="有明确基准，计算超额收益" value="benchmark" />
            </el-select>
          </el-form-item>
          <el-form-item label="基准净值列" :required="settings.benchmark_mode === 'benchmark'">
            <el-select v-model="settings.benchmark_column" clearable :disabled="disabled || settings.benchmark_mode !== 'benchmark'" style="width:100%">
              <el-option v-for="column in scorecard.nav_columns" :key="column" :label="column" :value="column" />
            </el-select>
          </el-form-item>
          <el-form-item label="年化无风险利率（%）" required>
            <el-input-number v-model="settings.risk_free_rate_percent" :disabled="disabled" :min="-100" :max="100" :step="0.1" :precision="2" style="width:100%" />
            <small>远澜历史申请单的“收益率÷波动率”结果对应 0%；如制度口径变化请在此修改。</small>
          </el-form-item>
        </div>
      </el-form>
    </div>

    <div class="scorecard-section">
      <div class="scorecard-heading"><div><h2>2. 自动评分所需信息（可选）</h2><p>如使用自动测算，请填写；也可以跳过本区，直接在第3部分人工打分。</p></div></div>
      <el-form label-position="top" class="scorecard-form">
        <h3>管理规模与团队</h3>
        <div class="field-grid field-grid-3">
          <el-form-item label="策略规模分类" required><el-select v-model="qualitative.strategy_scale_group" :disabled="disabled" style="width:100%"><el-option label="债券策略" value="bond" /><el-option label="CTA / T0" value="cta_t0" /><el-option label="其他策略" value="other" /></el-select></el-form-item>
          <el-form-item label="管理规模（亿元）" required><el-input-number v-model="qualitative.managed_scale_100m" :disabled="disabled" :min="0" style="width:100%" /></el-form-item>
          <el-form-item label="存续产品数量" required><el-input-number v-model="qualitative.active_product_count" :disabled="disabled" :min="0" :precision="0" style="width:100%" /></el-form-item>
          <el-form-item label="公司总人数" required><el-input-number v-model="qualitative.company_headcount" :disabled="disabled" :min="0" :precision="0" style="width:100%" /></el-form-item>
          <el-form-item label="投研团队人数" required><el-input-number v-model="qualitative.research_headcount" :disabled="disabled" :min="0" :precision="0" style="width:100%" /></el-form-item>
          <el-form-item label="核心投研经验（年）" required><el-input-number v-model="qualitative.core_research_experience_years" :disabled="disabled" :min="0" style="width:100%" /></el-form-item>
          <el-form-item label="专业背景与策略匹配" required><el-select v-model="qualitative.research_background_match" :disabled="disabled" style="width:100%"><el-option label="是" :value="true" /><el-option label="否" :value="false" /></el-select></el-form-item>
          <el-form-item label="具有实盘验证" required><el-select v-model="qualitative.research_live_track_record" :disabled="disabled" style="width:100%"><el-option label="是" :value="true" /><el-option label="否" :value="false" /></el-select></el-form-item>
        </div>

        <h3>投资经理与稳定性</h3>
        <div class="field-grid field-grid-3">
          <el-form-item label="同策略可追溯业绩（年）" required><el-input-number v-model="qualitative.manager_same_strategy_years" :disabled="disabled" :min="0" style="width:100%" /></el-form-item>
          <el-form-item label="投研从业年限" required><el-input-number v-model="qualitative.manager_industry_years" :disabled="disabled" :min="0" style="width:100%" /></el-form-item>
          <el-form-item label="投资理念成熟度" required><el-select v-model="qualitative.manager_philosophy_level" :disabled="disabled" style="width:100%"><el-option label="体系完善、逻辑闭环" value="complete" /><el-option label="理念成熟" value="mature" /><el-option label="理念清晰" value="clear" /><el-option label="较弱或不清晰" value="weak" /></el-select></el-form-item>
          <el-form-item label="履历稳定且风格无大幅漂移" required><el-select v-model="qualitative.manager_profile_stable" :disabled="disabled" style="width:100%"><el-option label="是" :value="true" /><el-option label="否" :value="false" /></el-select></el-form-item>
          <el-form-item label="近1年核心投研离职人数" required><el-input-number v-model="qualitative.core_departures_1y" :disabled="disabled" :min="0" :precision="0" style="width:100%" /></el-form-item>
          <el-form-item label="近3年核心投研离职人数" required><el-input-number v-model="qualitative.core_departures_3y" :disabled="disabled" :min="0" :precision="0" style="width:100%" /></el-form-item>
          <el-form-item label="激励机制" required><el-select v-model="qualitative.incentive_level" :disabled="disabled" style="width:100%"><el-option label="长期激励（股权/期权/业绩报酬）" value="long_term" /><el-option label="明确业绩激励" value="clear" /><el-option label="基本激励" value="basic" /><el-option label="无激励机制" value="none" /></el-select></el-form-item>
        </div>

        <h3>配置价值与风控</h3>
        <div class="field-grid field-grid-3">
          <el-form-item label="当前策略规模（亿元）" required><el-input-number v-model="qualitative.current_strategy_scale_100m" :disabled="disabled" :min="0" style="width:100%" /></el-form-item>
          <el-form-item label="策略理论容量（亿元）" required><el-input-number v-model="qualitative.theoretical_capacity_100m" :disabled="disabled" :min="0.01" style="width:100%" /></el-form-item>
          <el-form-item label="与池内策略差异化" required><el-select v-model="qualitative.differentiation_level" :disabled="disabled" style="width:100%"><el-option label="显著差异化" value="significant" /><el-option label="部分重叠但可分散" value="partial" /><el-option label="高度同质化" value="none" /></el-select></el-form-item>
          <el-form-item label="风控制度建设" required><el-select v-model="qualitative.risk_system_level" :disabled="disabled" style="width:100%"><el-option label="完备制度+负责人+全套流程" value="complete" /><el-option label="较完备制度+专职人员" value="substantial" /><el-option label="基本制度和岗位" value="basic" /><el-option label="无成文制度/专职人员" value="none" /></el-select></el-form-item>
          <el-form-item label="风控团队人数" required><el-input-number v-model="qualitative.risk_team_headcount" :disabled="disabled" :min="0" :precision="0" style="width:100%" /></el-form-item>
          <el-form-item label="风控团队相关经验（年）" required><el-input-number v-model="qualitative.risk_team_experience_years" :disabled="disabled" :min="0" style="width:100%" /></el-form-item>
        </div>

        <h3>跟投与合规扣分</h3>
        <div class="field-grid field-grid-3">
          <el-form-item label="管理人自有资金跟投（%）" required><el-input-number v-model="qualitative.manager_coinvest_percent" :disabled="disabled" :min="0" :step="0.5" style="width:100%" /></el-form-item>
          <el-form-item label="管理人跟投锁定期（年）" required><el-input-number v-model="qualitative.manager_coinvest_lock_years" :disabled="disabled" :min="0" :step="0.5" style="width:100%" /></el-form-item>
          <el-form-item label="核心投研个人跟投" required><el-select v-model="qualitative.core_personal_coinvest" :disabled="disabled" style="width:100%"><el-option label="是" :value="true" /><el-option label="否" :value="false" /></el-select></el-form-item>
          <el-form-item label="近3年监管处罚/自律处分次数" required><el-input-number v-model="qualitative.regulatory_events_3y" :disabled="disabled" :min="0" :precision="0" style="width:100%" /></el-form-item>
          <el-form-item label="近3年重大负面/涉诉次数" required><el-input-number v-model="qualitative.negative_or_litigation_events_3y" :disabled="disabled" :min="0" :precision="0" style="width:100%" /></el-form-item>
        </div>
      </el-form>
      <el-button v-if="!disabled" type="primary" size="large" :loading="calculating" @click="calculate">计算并保存评分卡</el-button>
    </div>

    <div class="scorecard-section">
      <div class="scorecard-heading">
        <div><h2>3. 员工复核并录入实际得分</h2><p>逐项对应正式 Excel 模板“实际得分”列，所有项目必须填写。</p></div>
        <div class="scorecard-actions">
          <el-button v-if="!disabled" :loading="savingScores" @click="saveManualScores(true)">保存评分</el-button>
          <el-button type="primary" :loading="generatingExcel" :disabled="disabled && !hasResult" @click="generateExcel">生成并下载 Excel</el-button>
        </div>
      </div>
      <el-table :data="scorecard?.template_items || []" border stripe class="manual-score-table">
        <el-table-column prop="category" label="一级维度" min-width="170" />
        <el-table-column prop="indicator" label="二级指标" min-width="210">
          <template #default="{ row }"><span class="required-score">*</span> {{ row.indicator }}<small v-if="row.take_higher">（与近1年收益率取高）</small></template>
        </el-table-column>
        <el-table-column label="满分" width="100" align="center"><template #default="{ row }">{{ row.maximum === null ? '扣分' : row.maximum }}</template></el-table-column>
        <el-table-column label="实际得分" width="210" align="center">
          <template #default="{ row }"><el-input-number v-model="manualScores[row.key]" :disabled="disabled" :min="0" :max="row.maximum ?? 999" :step="0.5" :precision="2" controls-position="right" /></template>
        </el-table-column>
      </el-table>
      <div class="manual-score-summary">
        <span>定量 {{ manualSummary.quantitative.toFixed(2) }}/62</span>
        <span>定性 {{ manualSummary.qualitative.toFixed(2) }}/38</span>
        <span>扣分 -{{ manualSummary.deduction.toFixed(2) }}</span>
        <strong>预计总分 {{ manualSummary.total.toFixed(2) }}/100</strong>
      </div>
      <p class="scorecard-footnote">评分卡单独生成 Excel，不写入附件1-1或附件1-2的 Word 文档。</p>
    </div>

    <div v-if="hasResult" class="scorecard-section">
      <div class="scorecard-result">
        <div><span>定量</span><strong>{{ scorecard?.quantitative_score }}<small>/62</small></strong></div>
        <div><span>定性</span><strong>{{ scorecard?.qualitative_score }}<small>/38</small></strong></div>
        <div><span>合规扣分</span><strong>-{{ scorecard?.compliance_deduction }}</strong></div>
        <div class="total"><span>总分</span><strong>{{ scorecard?.total_score }}<small>/100</small></strong></div>
        <el-tag :type="scoreTagType" size="large" effect="dark">{{ scorecard?.admitted ? '达到入池标准' : '未达到入池标准' }}</el-tag>
      </div>
      <el-table :data="scorecard?.score_rows" border stripe>
        <el-table-column prop="category" label="一级维度" width="110" />
        <el-table-column prop="indicator" label="二级指标" min-width="170" />
        <el-table-column prop="value" label="指标值" min-width="180" />
        <el-table-column label="得分" width="90" align="center">
          <template #default="{ row }">{{ row.score }}<template v-if="row.maximum !== '扣分'">/{{ row.maximum }}</template></template>
        </el-table-column>
        <el-table-column prop="basis" label="评分依据" min-width="280" />
      </el-table>
      <p class="scorecard-footnote">此处展示已保存结果；Excel 与附件1-1、附件1-2分别下载。</p>
    </div>
  </section>
</template>
