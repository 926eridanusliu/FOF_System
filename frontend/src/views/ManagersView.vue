<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api, apiMessage } from '../api'
import type { Manager } from '../types'

const router = useRouter()
const managers = ref<Manager[]>([])
const loading = ref(true)
const keyword = ref('')

const filtered = computed(() => {
  const needle = keyword.value.trim().toLowerCase()
  if (!needle) return managers.value
  return managers.value.filter((item) => [item.name, item.unified_social_credit_code, item.contact_name]
    .some((value) => value?.toLowerCase().includes(needle)))
})

const withContact = computed(() => managers.value.filter((item) => item.contact_name || item.contact_phone).length)

async function load() {
  loading.value = true
  try { managers.value = await api.managers.list() }
  catch (error) { ElMessage.error(apiMessage(error)) }
  finally { loading.value = false }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="page-heading">
      <div><span class="eyebrow">Manager Registry</span><h1>管理人名录</h1><p>统一查看机构档案、产品及历次尽调记录。</p></div>
      <el-button type="primary" :icon="Plus" @click="router.push('/managers/new')">新建管理人</el-button>
    </div>

    <div class="metric-grid">
      <div class="metric-card"><span>管理人总数</span><strong>{{ managers.length }}</strong><em>机构档案</em></div>
      <div class="metric-card"><span>已留联系人</span><strong>{{ withContact }}</strong><em>可直接联络</em></div>
      <div class="metric-card"><span>待补充联系信息</span><strong>{{ managers.length - withContact }}</strong><em>资料完整度提醒</em></div>
    </div>

    <div class="surface">
      <div class="filter-bar">
        <el-input v-model="keyword" :prefix-icon="Search" clearable placeholder="搜索名称、信用代码或联系人" style="width: 340px" />
        <span class="spacer" />
        <span class="muted">共 {{ filtered.length }} 条</span>
      </div>
      <el-table v-loading="loading" :data="filtered" row-key="id" @row-click="(row: Manager) => router.push(`/managers/${row.id}`)">
        <el-table-column label="管理人名称" min-width="260">
          <template #default="{ row }"><span class="text-link">{{ row.name }}</span></template>
        </el-table-column>
        <el-table-column prop="unified_social_credit_code" label="统一社会信用代码" min-width="190">
          <template #default="{ row }"><span class="mono">{{ row.unified_social_credit_code || '—' }}</span></template>
        </el-table-column>
        <el-table-column prop="contact_name" label="联系人" width="130"><template #default="{ row }">{{ row.contact_name || '—' }}</template></el-table-column>
        <el-table-column prop="contact_phone" label="联系方式" width="170"><template #default="{ row }">{{ row.contact_phone || '—' }}</template></el-table-column>
        <el-table-column label="最近更新" width="150"><template #default="{ row }">{{ new Date(row.updated_at).toLocaleDateString('zh-CN') }}</template></el-table-column>
        <template #empty><div class="empty-state"><strong>暂无管理人</strong>从新建管理人开始建立尽调档案。</div></template>
      </el-table>
    </div>
  </section>
</template>
