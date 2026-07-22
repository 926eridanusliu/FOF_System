<script setup lang="ts">
import type { ValidationResult } from '../types'
defineProps<{ result?: ValidationResult }>()
</script>

<template>
  <el-alert v-if="!result" title="尚未执行校验" description="保存草稿后点击“校验报告”，检查提交前必填项和图片。" type="info" :closable="false" show-icon />
  <template v-else>
    <el-alert :title="result.valid ? '校验通过' : `发现 ${result.errors.length} 项错误`" :type="result.valid ? 'success' : 'error'" :closable="false" show-icon style="margin-bottom:12px" />
    <ul class="validation-list">
      <li v-for="item in result.errors" :key="`e-${item.field}-${item.message}`" class="error"><b>{{ item.field }}</b> · {{ item.message }}</li>
      <li v-for="item in result.warnings" :key="`w-${item.field}-${item.message}`" class="warning"><b>{{ item.field }}</b> · {{ item.message }}</li>
    </ul>
  </template>
</template>
