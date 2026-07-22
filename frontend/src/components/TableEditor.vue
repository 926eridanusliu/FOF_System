<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ManifestField } from '../types'

const props = defineProps<{ fields: ManifestField[]; content: Record<string, any>; disabled?: boolean }>()
const tableNumbers = computed(() => [...new Set(props.fields.map((item) => item.table).filter((value): value is number => value !== undefined))].sort((a,b) => a-b))
const activeTable = ref(String(tableNumbers.value[0] ?? ''))
const currentTable = computed(() => Number(activeTable.value || tableNumbers.value[0]))
const currentFields = computed(() => props.fields.filter((item) => item.type === 'table_cell' && item.table === currentTable.value))
const cutoffField = computed(() => props.fields.find((item) => item.type === 'table_cutoff_date' && item.table === currentTable.value))
const rows = computed(() => Math.max(-1, ...currentFields.value.map((item) => item.row ?? -1)) + 1)
const cols = computed(() => Math.max(-1, ...currentFields.value.map((item) => item.col ?? -1)) + 1)
const fieldAt = (row: number, col: number) => currentFields.value.find((item) => item.row === row && item.col === col)
</script>

<template>
  <div>
    <el-tabs v-model="activeTable" type="card">
      <el-tab-pane v-for="number in tableNumbers" :key="number" :name="String(number)" :label="`表 ${number}`" />
    </el-tabs>
    <el-form v-if="cutoffField" label-position="top" style="max-width:320px">
      <el-form-item :label="cutoffField.prompt || '数据截止日期'">
        <el-date-picker v-model="content[cutoffField.bookmark]" type="date" value-format="YYYY.MM.DD" format="YYYY.MM.DD" :disabled="disabled" style="width:100%" />
      </el-form-item>
    </el-form>
    <div class="table-editor">
      <table>
        <thead><tr><th>行 / 列</th><th v-for="col in cols" :key="col">列 {{ col }}</th></tr></thead>
        <tbody>
          <tr v-for="row in rows" :key="row"><th>行 {{ row }}</th>
            <td v-for="col in cols" :key="col">
              <template v-if="fieldAt(row - 1, col - 1)">
                <el-input v-model="content[fieldAt(row - 1, col - 1)!.bookmark]" type="textarea" :rows="2" :disabled="disabled" :placeholder="fieldAt(row - 1, col - 1)!.bookmark" />
              </template>
              <span v-else class="muted">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="muted" style="font-size:11px">表格结构来自 Word 官方模板；空白单元格表示该位置没有可填写书签。</p>
  </div>
</template>
