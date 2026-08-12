<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { ManifestField, TableColumnDefinition, TableDefinition, TableInputType, TemplateType } from '../types'
import { fieldIsRequired, formatTableOutput, getTableDefinitions, normalizeTableInput, tableApplies } from '../utils/report'

type TableRow = Record<string, unknown>
type DynamicTables = Record<string, TableRow[]>

const props = defineProps<{
  fields: ManifestField[]
  content: Record<string, any>
  templateType: TemplateType
  disabled?: boolean
}>()

const definitions = computed(() => getTableDefinitions(props.templateType))
const visibleDefinitions = computed(() => Object.entries(definitions.value)
  .filter(([, definition]) => tableApplies(definition, props.content))
  .sort(([a], [b]) => Number(a) - Number(b)))
const activeTable = ref('')
const tableRows = reactive<DynamicTables>({})
const currentDefinition = computed(() => definitions.value[activeTable.value])
const currentRows = computed(() => tableRows[activeTable.value] || [])
const cutoffField = computed(() => props.fields.find((item) => item.type === 'table_cutoff_date' && item.table === Number(activeTable.value)))

function metadata(): DynamicTables {
  if (!props.content.__dynamic_tables || typeof props.content.__dynamic_tables !== 'object') {
    props.content.__dynamic_tables = {}
  }
  return props.content.__dynamic_tables as DynamicTables
}

function legacyValue(table: string, row: number, col: number): unknown {
  return props.content[`table_${table}_row${row}_col${col}`] ?? ''
}

function makeLegacyRows(table: string, definition: TableDefinition): TableRow[] {
  const rows = Array.from({ length: definition.template_rows }, (_, offset) => {
    const row: TableRow = {}
    for (const column of definition.columns) {
      const actualRow = definition.start_row + offset
      const type = definition.row_input_types?.[String(actualRow)] || column.input
      row[String(column.col)] = normalizeTableInput(legacyValue(table, actualRow, column.col), type)
    }
    return row
  })
  if (definition.mode !== 'dynamic') return rows
  let used = rows.reduce((last, row, index) => Object.values(row).some((value) => value !== '' && value != null) ? index + 1 : last, 0)
  used = Math.max(1, used)
  return rows.slice(0, used)
}

function ensureTable(table: string, definition: TableDefinition) {
  if (tableRows[table]) return
  const saved = metadata()[table]
  tableRows[table] = Array.isArray(saved) && saved.length
    ? saved.map((row, offset) => Object.fromEntries(definition.columns.map((column) => {
      const type = definition.row_input_types?.[String(definition.start_row + offset)] || column.input
      return [String(column.col), normalizeTableInput(row[String(column.col)] ?? row[column.col], type)]
    })))
    : makeLegacyRows(table, definition)
  syncTable(table)
}

function syncTable(table: string) {
  const definition = definitions.value[table]
  const rows = tableRows[table]
  if (!definition || !rows) return
  metadata()[table] = rows.map((row) => ({ ...row }))
  for (let offset = 0; offset < definition.template_rows; offset += 1) {
    for (const column of definition.columns) {
      const actualRow = definition.start_row + offset
      const type = definition.row_input_types?.[String(actualRow)] || column.input
      props.content[`table_${table}_row${actualRow}_col${column.col}`] = formatTableOutput(rows[offset]?.[String(column.col)] ?? '', type)
    }
  }
}

function setCell(rowIndex: number, column: TableColumnDefinition, value: unknown) {
  currentRows.value[rowIndex][String(column.col)] = value ?? ''
  syncTable(activeTable.value)
}

function addRow() {
  const definition = currentDefinition.value
  if (!definition || definition.mode !== 'dynamic') return
  currentRows.value.push(Object.fromEntries(definition.columns.map((column) => [String(column.col), ''])))
  syncTable(activeTable.value)
}

function removeRow(index: number) {
  if (currentDefinition.value?.mode !== 'dynamic' || currentRows.value.length <= 1) return
  currentRows.value.splice(index, 1)
  syncTable(activeTable.value)
}

function actualRow(index: number): number { return (currentDefinition.value?.start_row || 0) + index }
function rowLabel(index: number): string {
  const labels = currentDefinition.value?.row_labels || {}
  return labels[String(actualRow(index))] || labels[String(index)] || `第 ${index + 1} 行`
}
function inputType(index: number, column: TableColumnDefinition): TableInputType {
  return currentDefinition.value?.row_input_types?.[String(actualRow(index))] || column.input
}
function rowOptional(index: number): boolean {
  return Boolean(currentDefinition.value?.optional_rows?.includes(actualRow(index)))
}
function cellError(value: unknown, type: TableInputType): string {
  if (value === '' || value == null) return ''
  const text = String(value).trim()
  if (type === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text)) return '请输入有效邮箱地址'
  if (type === 'phone' && !/^[+()\d\s-]{6,30}$/.test(text)) return '请输入有效电话号码'
  if (type === 'url') { try { new URL(text) } catch { return '请输入完整网址（含 http:// 或 https://）' } }
  if (type === 'year' && !/^(19|20)\d{2}$/.test(text)) return '请输入四位年份'
  if (['integer', 'number', 'percent'].includes(type) && !Number.isFinite(Number(value))) return '请输入数字'
  return ''
}

watch(visibleDefinitions, (items) => {
  for (const [table, definition] of items) ensureTable(table, definition)
  if (!items.some(([table]) => table === activeTable.value)) activeTable.value = items[0]?.[0] || ''
}, { immediate: true, deep: true })
</script>

<template>
  <div v-if="visibleDefinitions.length">
    <el-alert title="请按表头逐项填写；可增删表格没有行数上限，生成 Word 时会自动扩展。" type="info" :closable="false" show-icon style="margin-bottom:14px" />
    <el-tabs v-model="activeTable" type="card">
      <el-tab-pane v-for="([number, definition]) in visibleDefinitions" :key="number" :name="number" :label="definition.title" />
    </el-tabs>
    <template v-if="currentDefinition">
      <div class="table-introduction">
        <h3>{{ currentDefinition.title }}</h3>
        <p>{{ currentDefinition.description }}</p>
      </div>
      <el-form v-if="cutoffField" label-position="top" style="max-width:320px">
        <el-form-item :label="`${cutoffField.prompt || '数据截止日期'}${fieldIsRequired(cutoffField) ? ' *' : ''}`">
          <el-date-picker v-model="content[cutoffField.bookmark]" type="date" value-format="YYYY.MM.DD" format="YYYY.MM.DD" :disabled="disabled" style="width:100%" />
        </el-form-item>
      </el-form>
      <div v-if="currentDefinition.mode === 'dynamic'" class="table-row-toolbar">
        <span>当前 {{ currentRows.length }} 行，请按实际情况填写</span>
        <el-button size="small" type="primary" plain :disabled="disabled" @click="addRow">添加一行</el-button>
      </div>
      <div class="table-editor">
        <table>
          <thead>
            <tr>
              <th v-if="currentDefinition.mode !== 'dynamic'">项目</th>
              <th v-else>序号</th>
              <th v-for="column in currentDefinition.columns" :key="column.col">{{ column.label }} <span class="required-star">*</span></th>
              <th v-if="currentDefinition.mode === 'dynamic'" class="row-action-column">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, rowIndex) in currentRows" :key="rowIndex">
              <th>
                {{ currentDefinition.mode === 'dynamic' ? rowIndex + 1 : rowLabel(rowIndex) }}
                <span v-if="currentDefinition.mode !== 'dynamic' && !rowOptional(rowIndex)" class="required-star">*</span>
                <small v-if="rowOptional(rowIndex)" class="muted">（可选）</small>
              </th>
              <td v-for="column in currentDefinition.columns" :key="column.col">
                <el-input
                  v-if="inputType(rowIndex, column) === 'textarea'"
                  :model-value="row[String(column.col)]" type="textarea" :rows="3" :disabled="disabled"
                  @update:model-value="setCell(rowIndex, column, $event)"
                />
                <el-date-picker
                  v-else-if="inputType(rowIndex, column) === 'date'"
                  :model-value="row[String(column.col)]" type="date" value-format="YYYY.MM.DD" format="YYYY.MM.DD"
                  :disabled="disabled" style="width:100%" @update:model-value="setCell(rowIndex, column, $event)"
                />
                <el-input
                  v-else :model-value="row[String(column.col)]" :disabled="disabled"
                  :inputmode="['integer','number','percent'].includes(inputType(rowIndex, column)) ? 'decimal' : undefined"
                  @update:model-value="setCell(rowIndex, column, $event)"
                >
                  <template v-if="column.unit" #append>{{ column.unit }}</template>
                </el-input>
                <small v-if="cellError(row[String(column.col)], inputType(rowIndex, column))" class="field-error">
                  {{ cellError(row[String(column.col)], inputType(rowIndex, column)) }}
                </small>
              </td>
              <td v-if="currentDefinition.mode === 'dynamic'" class="row-action-column">
                <el-button link type="danger" :disabled="disabled || currentRows.length <= 1" @click="removeRow(rowIndex)">删除</el-button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="required-note"><span>*</span> 为必填项；标有“（如有）”或“可选”的项目可选填。</p>
    </template>
  </div>
  <el-empty v-else description="当前所选策略没有需要填写的数据表格" />
</template>
