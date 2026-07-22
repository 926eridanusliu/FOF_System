<script setup lang="ts">
import { computed } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { ManifestField } from '../types'
import { branchLabels, strategyOptions } from '../utils/report'
import FieldGroup from './FieldGroup.vue'

const props = defineProps<{ fields: ManifestField[]; content: Record<string, any>; disabled?: boolean }>()
const branchFields = (branch: string) => props.fields.filter((item) => item.strategy === branch || item.bookmark.startsWith(`strat_${branch}_`))
const activeBranches = computed<Set<string>>(() => new Set(strategyOptions.filter(([key,,branch]) => branch && Boolean(props.content[key])).map(([, , branch]) => branch)))

async function toggle(key: string, branch: string, value: boolean) {
  if (!value && branch) {
    const anotherActive = strategyOptions.some(([otherKey,,otherBranch]) => otherKey !== key && otherBranch === branch && Boolean(props.content[otherKey]))
    const hasBranchData = branchFields(branch).some((item) => props.content[item.bookmark] !== undefined && props.content[item.bookmark] !== '')
    if (!anotherActive && hasBranchData) {
      try { await ElMessageBox.confirm('关闭该策略分支会清除已填写的专属字段，是否继续？', '策略分支确认', { type: 'warning' }) }
      catch { return }
      branchFields(branch).forEach((item) => delete props.content[item.bookmark])
    }
  }
  props.content[key] = value
}
</script>

<template>
  <div class="strategy-groups">
    <div class="strategy-card is-active">
      <h3>投资策略选择</h3>
      <el-space wrap :size="18">
        <el-checkbox
          v-for="[key, label, branch] in strategyOptions"
          :key="key"
          :model-value="Boolean(content[key])"
          :disabled="disabled"
          @change="(value: string | number | boolean) => toggle(key, branch, Boolean(value))"
        >{{ label }}</el-checkbox>
      </el-space>
      <el-input v-model="content.cover_strategy_other_text" :disabled="disabled" placeholder="其他策略说明" style="margin-top:14px" />
    </div>

    <div v-for="branch in ['quant','cta','bond','option']" :key="branch" class="strategy-card" :class="{ 'is-active': activeBranches.has(branch) }">
      <h3>{{ branchLabels[branch as keyof typeof branchLabels] }}</h3>
      <template v-if="activeBranches.has(branch)">
        <div class="strategy-branch"><FieldGroup :fields="branchFields(branch)" :content="content" :disabled="disabled" /></div>
      </template>
      <p v-else class="muted" style="margin:0;font-size:12px">选择对应策略后显示专属尽调问题。</p>
    </div>
  </div>
</template>
