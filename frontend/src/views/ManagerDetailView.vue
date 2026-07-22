<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, apiMessage } from '../api'
import type { Manager, Product, Report, TemplateType } from '../types'
import { statusLabel, templateLabel } from '../utils/report'

const route = useRoute(); const router = useRouter(); const managerId = Number(route.params.id)
const loading = ref(true); const manager = ref<Manager>(); const products = ref<Product[]>([]); const reports = ref<Report[]>([])
const productDialog = ref(false); const reportDialog = ref(false); const saving = ref(false)
const productForm = reactive({ name: '', product_type: '', established_date: '' })
const today = new Date()
const localDate = `${today.getFullYear()}.${String(today.getMonth() + 1).padStart(2, '0')}.${String(today.getDate()).padStart(2, '0')}`
const reportForm = reactive({ title: '', product_id: undefined as number | undefined, template_type: 'private_fund' as TemplateType, investigator: '', report_date: localDate, strategy: 'cover_strategy_futures_quant_trend' })

const reportByProduct = computed(() => Object.fromEntries(products.value.map((item) => [item.id, item.name])))

async function load() {
  loading.value = true
  try { [manager.value, products.value, reports.value] = await Promise.all([api.managers.get(managerId), api.products.list(managerId), api.reports.list({ managerId })]) }
  catch (error) { ElMessage.error(apiMessage(error)) }
  finally { loading.value = false }
}

async function createProduct() {
  if (!productForm.name.trim()) return ElMessage.warning('请输入产品名称')
  saving.value = true
  try {
    await api.products.create({ manager_id: managerId, name: productForm.name.trim(), product_type: productForm.product_type || null, established_date: productForm.established_date || null })
    ElMessage.success('产品已创建'); productDialog.value = false; Object.assign(productForm, { name: '', product_type: '', established_date: '' }); await load()
  } catch (error) { ElMessage.error(apiMessage(error)) } finally { saving.value = false }
}

async function createReport() {
  if (!manager.value || !reportForm.title.trim() || !reportForm.product_id || !reportForm.investigator.trim()) return ElMessage.warning('请填写报告标题、产品和调查人')
  const product = products.value.find((item) => item.id === reportForm.product_id)!
  saving.value = true
  try {
    const report = await api.reports.create({
      title: reportForm.title.trim(), manager_id: managerId, product_id: product.id, template_type: reportForm.template_type,
      content: {
        cover_manager_name: manager.value.name, cover_product_name: product.name,
        cover_investigator: reportForm.investigator.trim(), cover_report_date: reportForm.report_date,
        [reportForm.strategy]: true, table_1_row0_col1: manager.value.name,
      },
      conclusion: null, risk_items: [],
    })
    ElMessage.success('报告草稿已创建'); reportDialog.value = false; router.push(`/reports/${report.id}`)
  } catch (error) { ElMessage.error(apiMessage(error)) } finally { saving.value = false }
}

onMounted(load)
</script>

<template>
  <section class="page" v-loading="loading">
    <div v-if="manager" class="page-heading">
      <div><span class="eyebrow">Manager Profile · #{{ manager.id }}</span><h1>{{ manager.name }}</h1><p>机构档案、产品与尽调历史集中视图。</p></div>
      <div class="heading-actions"><el-button @click="router.push('/managers')">返回名录</el-button><el-button type="primary" :disabled="!products.length" @click="reportDialog = true">新建尽调报告</el-button></div>
    </div>
    <div v-if="manager" class="detail-grid">
      <div class="stack">
        <div class="surface">
          <div class="surface-header"><h2>尽调历史</h2><span class="muted">{{ reports.length }} 份报告</span></div>
          <el-table :data="reports" @row-click="(row: Report) => router.push(`/reports/${row.id}`)">
            <el-table-column label="报告标题" min-width="260"><template #default="{ row }"><span class="text-link">{{ row.title }}</span></template></el-table-column>
            <el-table-column label="产品" min-width="180"><template #default="{ row }">{{ reportByProduct[row.product_id] || `产品 #${row.product_id}` }}</template></el-table-column>
            <el-table-column label="模板" width="190"><template #default="{ row }">{{ templateLabel[row.template_type as TemplateType] }}</template></el-table-column>
            <el-table-column label="状态" width="110"><template #default="{ row }"><span :class="['status-dot', row.status]" />{{ statusLabel[row.status as keyof typeof statusLabel] }}</template></el-table-column>
            <el-table-column label="更新日期" width="130"><template #default="{ row }">{{ new Date(row.updated_at).toLocaleDateString('zh-CN') }}</template></el-table-column>
            <template #empty><div class="empty-state"><strong>暂无尽调报告</strong>{{ products.length ? '创建第一份报告开始尽调。' : '请先创建产品。' }}</div></template>
          </el-table>
        </div>
        <div class="surface">
          <div class="surface-header"><h2>旗下产品</h2><el-button size="small" @click="productDialog = true">新增产品</el-button></div>
          <el-table :data="products">
            <el-table-column prop="name" label="产品名称" min-width="250" />
            <el-table-column prop="product_type" label="产品类型" min-width="150"><template #default="{ row }">{{ row.product_type || '—' }}</template></el-table-column>
            <el-table-column prop="established_date" label="成立日期" width="140"><template #default="{ row }">{{ row.established_date || '—' }}</template></el-table-column>
          </el-table>
        </div>
      </div>
      <aside class="stack">
        <div class="surface"><div class="surface-header"><h2>机构信息</h2></div><div class="surface-body definition-grid" style="grid-template-columns:1fr">
          <div class="definition-item"><label>统一社会信用代码</label><div class="mono">{{ manager.unified_social_credit_code || '未填写' }}</div></div>
          <div class="definition-item"><label>联系人</label><div>{{ manager.contact_name || '未填写' }}</div></div>
          <div class="definition-item"><label>联系方式</label><div>{{ manager.contact_phone || '未填写' }}</div></div>
          <div class="definition-item"><label>建档日期</label><div>{{ new Date(manager.created_at).toLocaleDateString('zh-CN') }}</div></div>
        </div></div>
        <div class="metric-card"><span>产品 / 报告</span><strong>{{ products.length }} <small style="font-size:14px;color:#8491a4">/ {{ reports.length }}</small></strong><em>当前管理人档案</em></div>
      </aside>
    </div>

    <el-dialog v-model="productDialog" title="新增产品" width="520px">
      <el-form label-position="top"><el-form-item label="产品名称" required><el-input v-model="productForm.name" /></el-form-item><el-form-item label="产品类型"><el-input v-model="productForm.product_type" /></el-form-item><el-form-item label="成立日期"><el-date-picker v-model="productForm.established_date" value-format="YYYY-MM-DD" type="date" style="width:100%" /></el-form-item></el-form>
      <template #footer><el-button @click="productDialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="createProduct">创建产品</el-button></template>
    </el-dialog>
    <el-dialog v-model="reportDialog" title="创建尽调报告草稿" width="620px">
      <el-form label-position="top"><el-form-item label="报告标题" required><el-input v-model="reportForm.title" /></el-form-item><div class="field-grid"><el-form-item label="产品" required><el-select v-model="reportForm.product_id" style="width:100%"><el-option v-for="item in products" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="模板类型"><el-select v-model="reportForm.template_type" style="width:100%"><el-option v-for="(label,key) in templateLabel" :key="key" :label="label" :value="key" /></el-select></el-form-item><el-form-item label="调查人" required><el-input v-model="reportForm.investigator" /></el-form-item><el-form-item label="报告日期"><el-input v-model="reportForm.report_date" /></el-form-item></div><el-form-item label="首选策略"><el-select v-model="reportForm.strategy" style="width:100%"><el-option label="量化 CTA" value="cover_strategy_futures_quant_trend" /><el-option label="股票量化选股" value="cover_strategy_stock_quant" /><el-option label="纯债" value="cover_strategy_bond_pure" /><el-option label="期货期权套利" value="cover_strategy_futures_options_arbitrage" /></el-select></el-form-item></el-form>
      <template #footer><el-button @click="reportDialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="createReport">创建并编辑</el-button></template>
    </el-dialog>
  </section>
</template>
