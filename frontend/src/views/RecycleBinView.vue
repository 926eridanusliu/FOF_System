<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RefreshRight } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, apiMessage } from '../api'
import type { DeletionRecord } from '../types'

const records = ref<DeletionRecord[]>([])
const loading = ref(true)
const restoring = ref<number>()

async function load() {
  loading.value = true
  try { records.value = await api.deletions.list() }
  catch (error) { ElMessage.error(apiMessage(error)) }
  finally { loading.value = false }
}

async function restore(record: DeletionRecord) {
  try {
    await ElMessageBox.confirm(`恢复“${record.display_name}”后，它会重新出现在工作台。是否继续？`, '恢复删除数据', { type: 'warning' })
    restoring.value = record.id
    await api.deletions.restore(record.id)
    ElMessage.success('已恢复')
    await load()
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(apiMessage(error)) }
  finally { restoring.value = undefined }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-heading">
      <div><span class="eyebrow">Deletion Audit</span><h1>回收站与删除记录</h1><p>删除只会从工作台隐藏数据；原因和时间会留存，并可恢复。</p></div>
    </div>
    <div class="surface">
      <el-table v-loading="loading" :data="records" row-key="id">
        <el-table-column label="类型" width="100"><template #default="{ row }"><el-tag :type="row.entity_type === 'manager' ? 'primary' : 'info'">{{ row.entity_type === 'manager' ? '管理人' : '报告' }}</el-tag></template></el-table-column>
        <el-table-column prop="display_name" label="名称" min-width="240" />
        <el-table-column prop="reason" label="删除原因" min-width="260" />
        <el-table-column label="删除时间" width="190"><template #default="{ row }">{{ new Date(row.deleted_at).toLocaleString('zh-CN') }}</template></el-table-column>
        <el-table-column label="操作" width="110"><template #default="{ row }"><el-button link type="primary" :icon="RefreshRight" :loading="restoring === row.id" @click="restore(row)">恢复</el-button></template></el-table-column>
        <template #empty><div class="empty-state"><strong>回收站为空</strong>删除操作会在这里留下记录。</div></template>
      </el-table>
    </div>
  </section>
</template>
