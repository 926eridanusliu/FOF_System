<script setup lang="ts">
import type { ManifestField } from '../types'

defineProps<{
  fields: ManifestField[]
  content: Record<string, any>
  disabled?: boolean
}>()
</script>

<template>
  <div>
    <div v-for="field in fields" :key="field.bookmark" class="question-field">
      <label>{{ field.prompt || field.bookmark }}</label>
      <el-input
        v-model="content[field.bookmark]"
        type="textarea"
        :rows="field.type === 'cover' ? 2 : 4"
        :disabled="disabled"
        :placeholder="`填写：${field.prompt || field.bookmark}`"
      />
      <small class="mono">{{ field.bookmark }}</small>
    </div>
  </div>
</template>
