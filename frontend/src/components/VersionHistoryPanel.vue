<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, apiMessage } from '../api'
import type {
  Report,
  ReportVersionComparison,
  ReportVersionSummary,
  VersionChangeType,
} from '../types'

const props = defineProps<{
  reportId: number
  refreshKey: string
  hasUnsavedChanges: boolean
}>()
const emit = defineEmits<{ restored: [report: Report] }>()

const loading = ref(false)
const comparing = ref(false)
const restoring = ref<number>()
const versions = ref<ReportVersionSummary[]>([])
const comparison = ref<ReportVersionComparison>()
const fromVersion = ref<number>()
const toVersion = ref<number>()

const canCompare = computed(
  () => Boolean(fromVersion.value && toVersion.value && fromVersion.value !== toVersion.value),
)

function formatDate(value: string) {
  return new Date(value).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (value === true) return '是'
  if (value === false) return '否'
  if (typeof value === 'string') return value
  if (typeof value === 'number') return String(value)
  return JSON.stringify(value, null, 2)
}

function changeLabel(type: VersionChangeType) {
  return { added: '新增', removed: '删除', changed: '修改' }[type]
}

function changeTag(type: VersionChangeType) {
  return { added: 'success', removed: 'danger', changed: 'warning' }[type] as
    'success' | 'danger' | 'warning'
}

async function loadVersions() {
  loading.value = true
  try {
    versions.value = await api.reports.listVersions(props.reportId)
    if (versions.value.length >= 2) {
      const available = new Set(versions.value.map((item) => item.version_number))
      if (!fromVersion.value || !available.has(fromVersion.value)) {
        fromVersion.value = versions.value[1].version_number
      }
      if (!toVersion.value || !available.has(toVersion.value)) {
        toVersion.value = versions.value[0].version_number
      }
    } else if (versions.value.length === 1) {
      fromVersion.value = versions.value[0].version_number
      toVersion.value = undefined
    }
    comparison.value = undefined
  } catch (error) {
    ElMessage.error(apiMessage(error))
  } finally {
    loading.value = false
  }
}

async function compareSelected() {
  if (!canCompare.value || !fromVersion.value || !toVersion.value) {
    ElMessage.warning('请选择两个不同版本')
    return
  }
  comparing.value = true
  try {
    comparison.value = await api.reports.compareVersions(
      props.reportId,
      fromVersion.value,
      toVersion.value,
    )
  } catch (error) {
    ElMessage.error(apiMessage(error))
  } finally {
    comparing.value = false
  }
}

async function restoreVersion(version: ReportVersionSummary) {
  const unsaved = props.hasUnsavedChanges
    ? '当前页面还有未保存修改，这些修改也会被覆盖。'
    : ''
  try {
    await ElMessageBox.confirm(
      `系统会把版本 V${version.version_number} 的内容复制为新的当前草稿。${unsaved}历史快照本身不会改变，确认继续？`,
      `回滚到版本 V${version.version_number}`,
      {
        type: 'warning',
        confirmButtonText: '确认回滚',
        cancelButtonText: '取消',
      },
    )
    restoring.value = version.version_number
    const restored = await api.reports.restoreVersion(
      props.reportId,
      version.version_number,
    )
    emit('restored', restored)
    await loadVersions()
    ElMessage.success(`已回滚到版本 V${version.version_number}，报告现为可编辑草稿`)
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(apiMessage(error))
  } finally {
    restoring.value = undefined
  }
}

watch(() => props.refreshKey, loadVersions)
onMounted(loadVersions)
</script>

<template>
  <div class="version-panel" v-loading="loading">
    <section class="version-intro">
      <div>
        <h2>报告历史版本</h2>
        <p>每次提交都会冻结表单、评分卡、图片和净值源文件。历史快照只能查看、比较或复制回草稿，不能被修改或删除。</p>
      </div>
      <el-tag type="info" effect="plain">{{ versions.length }} 个不可变快照</el-tag>
    </section>

    <el-empty
      v-if="!loading && versions.length === 0"
      description="尚无历史版本；首次提交报告后将自动生成 V1"
    />

    <template v-else>
      <section class="version-list">
        <article v-for="version in versions" :key="version.id" class="version-card">
          <div class="version-number">V{{ version.version_number }}</div>
          <div class="version-meta">
            <strong>{{ version.title }}</strong>
            <span>提交于 {{ formatDate(version.submitted_at) }}</span>
            <code title="快照完整性校验哈希">{{ version.snapshot_hash.slice(0, 12) }}</code>
          </div>
          <div class="version-score">
            <span>准入评分</span>
            <strong>{{ version.total_score ?? '—' }}</strong>
          </div>
          <el-button
            type="primary"
            plain
            :loading="restoring === version.version_number"
            @click="restoreVersion(version)"
          >
            回滚到此版本
          </el-button>
        </article>
      </section>

      <section class="version-compare">
        <div class="version-compare-heading">
          <div>
            <h3>版本对比</h3>
            <p>选择两个提交版本，查看表单字段及评分结果发生了哪些变化。</p>
          </div>
          <div class="version-selectors">
            <el-select v-model="fromVersion" placeholder="较早版本">
              <el-option
                v-for="version in versions"
                :key="version.id"
                :label="`V${version.version_number} · ${formatDate(version.submitted_at)}`"
                :value="version.version_number"
              />
            </el-select>
            <span>→</span>
            <el-select v-model="toVersion" placeholder="较新版本">
              <el-option
                v-for="version in versions"
                :key="version.id"
                :label="`V${version.version_number} · ${formatDate(version.submitted_at)}`"
                :value="version.version_number"
              />
            </el-select>
            <el-button
              type="primary"
              :disabled="!canCompare"
              :loading="comparing"
              @click="compareSelected"
            >
              开始对比
            </el-button>
          </div>
        </div>

        <div v-if="comparison" class="version-diff">
          <el-alert
            v-if="comparison.change_count === 0"
            title="两个版本内容完全一致"
            type="success"
            :closable="false"
            show-icon
          />
          <template v-else>
            <p class="version-diff-summary">
              V{{ comparison.from_version }} → V{{ comparison.to_version }}，共
              <strong>{{ comparison.change_count }}</strong> 项变化
            </p>
            <el-table :data="comparison.changes" border>
              <el-table-column label="变化" width="82">
                <template #default="{ row }">
                  <el-tag :type="changeTag(row.change_type)" effect="plain">
                    {{ changeLabel(row.change_type) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="label" label="字段" min-width="220">
                <template #default="{ row }">
                  <strong>{{ row.label }}</strong>
                  <small class="version-field-path">{{ row.field_path }}</small>
                </template>
              </el-table-column>
              <el-table-column label="原版本" min-width="260">
                <template #default="{ row }">
                  <pre class="version-value before">{{ formatValue(row.before) }}</pre>
                </template>
              </el-table-column>
              <el-table-column label="新版本" min-width="260">
                <template #default="{ row }">
                  <pre class="version-value after">{{ formatValue(row.after) }}</pre>
                </template>
              </el-table-column>
            </el-table>
          </template>
        </div>
      </section>
    </template>
  </div>
</template>
