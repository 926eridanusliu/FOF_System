<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, apiMessage } from '../api'
import type { ManifestField } from '../types'
import { fieldIsRequired, imageUrl } from '../utils/report'

const props = defineProps<{ reportId?: number; publicToken?: string; fields: ManifestField[]; content: Record<string, any>; disabled?: boolean }>()
const emit = defineEmits<{ changed: [field: string, removed: boolean] }>()
const working = ref<string>()
const previews = computed(() => Object.fromEntries(props.fields.map((field) => [
  field.bookmark,
  props.publicToken && props.content[field.bookmark]
    ? `/api/public/fill/${encodeURIComponent(props.publicToken)}/images/${encodeURIComponent(field.bookmark)}`
    : props.reportId ? imageUrl(props.reportId, props.content[field.bookmark]) : undefined,
])))

async function upload(field: string, event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (!['image/png', 'image/jpeg'].includes(file.type)) { ElMessage.warning('请选择 PNG 或 JPEG 图片'); input.value = ''; return }
  working.value = field
  try {
    if (props.publicToken) await api.publicFill.uploadImage(props.publicToken, field, file)
    else if (props.reportId) await api.reports.uploadImage(props.reportId, field, file)
    else throw new Error('缺少图片上传目标')
    ElMessage.success('图片已上传并写入报告'); emit('changed', field, false)
  }
  catch (error) { ElMessage.error(apiMessage(error)) }
  finally { working.value = undefined; input.value = '' }
}

async function remove(field: string) {
  working.value = field
  try {
    if (props.publicToken) await api.publicFill.removeImage(props.publicToken, field)
    else if (props.reportId) await api.reports.removeImage(props.reportId, field)
    else throw new Error('缺少图片上传目标')
    ElMessage.success('图片已移除'); emit('changed', field, true)
  }
  catch (error) { ElMessage.error(apiMessage(error)) } finally { working.value = undefined }
}
</script>

<template>
  <div class="image-grid">
    <article v-for="field in fields" :key="field.bookmark" class="image-card">
      <h4>{{ field.prompt }}<span v-if="fieldIsRequired(field)" class="required-mark" aria-label="必填">*</span></h4>
      <div class="image-preview">
        <img v-if="previews[field.bookmark]" :src="previews[field.bookmark]" :alt="field.prompt" />
        <span v-else class="muted">尚未上传</span>
      </div>
      <div style="display:flex;gap:8px">
        <label class="el-button el-button--primary el-button--small" :class="{ 'is-disabled': disabled || working === field.bookmark }">
          {{ previews[field.bookmark] ? '替换图片' : '上传图片' }}
          <input type="file" accept="image/png,image/jpeg" hidden :disabled="disabled || Boolean(working)" @change="upload(field.bookmark, $event)" />
        </label>
        <el-button v-if="previews[field.bookmark]" size="small" :disabled="disabled" :loading="working===field.bookmark" @click="remove(field.bookmark)">移除</el-button>
      </div>
    </article>
  </div>
</template>
