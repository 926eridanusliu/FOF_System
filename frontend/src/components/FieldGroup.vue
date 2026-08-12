<script setup lang="ts">
import type { ManifestField } from '../types'
import { fieldIsRequired } from '../utils/report'

defineProps<{
  fields: ManifestField[]
  content: Record<string, any>
  disabled?: boolean
}>()
</script>

<template>
  <div>
    <div v-for="field in fields" :key="field.bookmark" class="question-field">
      <label>{{ field.prompt || field.bookmark }}<span v-if="fieldIsRequired(field)" class="required-mark" aria-label="必填">*</span></label>
      <el-input
        v-model="content[field.bookmark]"
        type="textarea"
        :rows="field.type === 'cover' ? 2 : 4"
        :disabled="disabled"
      />
    </div>
  </div>
</template>
