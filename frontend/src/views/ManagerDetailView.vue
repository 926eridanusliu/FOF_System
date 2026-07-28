<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, apiMessage } from '../api'
import type { Manager, Product, Report, TemplateType } from '../types'
import { statusLabel, strategyOptions, templateLabel } from '../utils/report'

const route = useRoute(); const router = useRouter(); const managerId = Number(route.params.id)
const loading = ref(true); const manager = ref<Manager>(); const products = ref<Product[]>([]); const reports = ref<Report[]>([])
const productDialog = ref(false); const reportDialog = ref(false); const saving = ref(false)
const productForm = reactive({ id: undefined as number | undefined, name: '', product_type: '', established_date: '', strategy_keys: [] as string[] })
const today = new Date()
const localDate = `${today.getFullYear()}.${String(today.getMonth() + 1).padStart(2, '0')}.${String(today.getDate()).padStart(2, '0')}`
const reportForm = reactive({ title: '', product_ids: [] as number[], template_type: 'private_fund' as TemplateType, investigator: '', report_date: localDate, manual_strategy_keys: [] as string[] })

const reportByProduct = computed(() => Object.fromEntries(products.value.map((item) => [item.id, item.name])))
const selectedReportProducts = computed(() => products.value.filter((item) => reportForm.product_ids.includes(item.id)))
const autoReportStrategies = computed(() => [...new Set(selectedReportProducts.value.flatMap((item) => item.strategy_keys))])
const strategyLabel = Object.fromEntries(strategyOptions.map(([key, label]) => [key, label]))

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
    const payload = { manager_id: managerId, name: productForm.name.trim(), product_type: productForm.product_type || null, established_date: productForm.established_date || null, strategy_keys: productForm.strategy_keys }
    if (productForm.id) await api.products.update(productForm.id, payload)
    else await api.products.create(payload)
    ElMessage.success(productForm.id ? '产品已更新' : '产品已创建'); productDialog.value = false
    Object.assign(productForm, { id: undefined, name: '', product_type: '', established_date: '', strategy_keys: [] }); await load()
  } catch (error) { ElMessage.error(apiMessage(error)) } finally { saving.value = false }
}

function openProduct(item?: Product) {
  Object.assign(productForm, item
    ? { id: item.id, name: item.name, product_type: item.product_type || '', established_date: item.established_date || '', strategy_keys: [...item.strategy_keys] }
    : { id: undefined, name: '', product_type: '', established_date: '', strategy_keys: [] })
  productDialog.value = true
}

async function createReport() {
  if (!manager.value || !reportForm.title.trim() || !reportForm.product_ids.length || !reportForm.investigator.trim()) return ElMessage.warning('请填写报告标题、产品和调查人')
  const selectedStrategies = [...new Set([...autoReportStrategies.value, ...reportForm.manual_strategy_keys])]
  if (!selectedStrategies.length) return ElMessage.warning('请为产品配置策略，或手动补充至少一种策略')
  const selectedProducts = selectedReportProducts.value
  saving.value = true
  try {
    const report = await api.reports.create({
      title: reportForm.title.trim(), manager_id: managerId, product_id: selectedProducts[0].id, product_ids: reportForm.product_ids, template_type: reportForm.template_type,
      content: {
        cover_manager_name: manager.value.name, cover_product_name: selectedProducts.map((item) => item.name).join('、'),
        cover_investigator: reportForm.investigator.trim(), cover_report_date: reportForm.report_date,
        ...Object.fromEntries(selectedStrategies.map((key) => [key, true])), table_1_row0_col1: manager.value.name,
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
            <el-table-column label="产品" min-width="180"><template #default="{ row }">{{ (row.product_ids || [row.product_id]).map((id: number) => reportByProduct[id] || `产品 #${id}`).join('、') }}</template></el-table-column>
            <el-table-column label="模板" width="190"><template #default="{ row }">{{ templateLabel[row.template_type as TemplateType] }}</template></el-table-column>
            <el-table-column label="状态" width="110"><template #default="{ row }"><span :class="['status-dot', row.status]" />{{ statusLabel[row.status as keyof typeof statusLabel] }}</template></el-table-column>
            <el-table-column label="更新日期" width="130"><template #default="{ row }">{{ new Date(row.updated_at).toLocaleDateString('zh-CN') }}</template></el-table-column>
            <template #empty><div class="empty-state"><strong>暂无尽调报告</strong>{{ products.length ? '创建第一份报告开始尽调。' : '请先创建产品。' }}</div></template>
          </el-table>
        </div>
        <div class="surface">
          <div class="surface-header"><h2>旗下产品</h2><el-button size="small" @click="openProduct()">新增产品</el-button></div>
          <el-table :data="products">
            <el-table-column prop="name" label="产品名称" min-width="250" />
            <el-table-column prop="product_type" label="产品类型" min-width="150"><template #default="{ row }">{{ row.product_type || '—' }}</template></el-table-column>
            <el-table-column label="产品策略" min-width="260"><template #default="{ row }"><el-space wrap><el-tag v-for="key in row.strategy_keys" :key="key" size="small" effect="plain">{{ strategyLabel[key] }}</el-tag><span v-if="!row.strategy_keys.length" class="muted">未配置</span></el-space></template></el-table-column>
            <el-table-column prop="established_date" label="成立日期" width="140"><template #default="{ row }">{{ row.established_date || '—' }}</template></el-table-column>
            <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="primary" @click.stop="openProduct(row)">编辑</el-button></template></el-table-column>
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

    <el-dialog v-model="productDialog" :title="productForm.id ? '编辑产品' : '新增产品'" width="620px">
      <el-form label-position="top"><el-form-item label="产品名称" required><el-input v-model="productForm.name" /></el-form-item><el-form-item label="产品类型"><el-input v-model="productForm.product_type" /></el-form-item><el-form-item label="成立日期"><el-date-picker v-model="productForm.established_date" value-format="YYYY-MM-DD" type="date" style="width:100%" /></el-form-item><el-form-item label="产品策略" required><el-checkbox-group v-model="productForm.strategy_keys"><el-space wrap><el-checkbox v-for="[key,label] in strategyOptions" :key="key" :value="key">{{ label }}</el-checkbox></el-space></el-checkbox-group></el-form-item></el-form>
      <template #footer><el-button @click="productDialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="createProduct">{{ productForm.id ? '保存' : '创建产品' }}</el-button></template>
    </el-dialog>
    <el-dialog v-model="reportDialog" title="创建尽调报告草稿" width="620px">
      <el-form label-position="top"><el-form-item label="报告标题" required><el-input v-model="reportForm.title" /></el-form-item><div class="field-grid"><el-form-item label="关联产品（可多选）" required><el-select v-model="reportForm.product_ids" multiple style="width:100%"><el-option v-for="item in products" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="模板类型"><el-select v-model="reportForm.template_type" style="width:100%"><el-option v-for="(label,key) in templateLabel" :key="key" :label="label" :value="key" /></el-select></el-form-item><el-form-item label="调查人" required><el-input v-model="reportForm.investigator" /></el-form-item><el-form-item label="报告日期"><el-input v-model="reportForm.report_date" /></el-form-item></div><el-form-item label="产品自动带入策略"><el-space wrap><el-tag v-for="key in autoReportStrategies" :key="key">{{ strategyLabel[key] }}</el-tag><span v-if="!autoReportStrategies.length" class="muted">所选产品尚未配置策略</span></el-space></el-form-item><el-form-item label="手动补充策略"><el-checkbox-group v-model="reportForm.manual_strategy_keys"><el-space wrap><el-checkbox v-for="[key,label] in strategyOptions" :key="key" :value="key" :disabled="autoReportStrategies.includes(key)">{{ label }}</el-checkbox></el-space></el-checkbox-group></el-form-item></el-form>
      <template #footer><el-button @click="reportDialog=false">取消</el-button><el-button type="primary" :loading="saving" @click="createReport">创建并编辑</el-button></template>
    </el-dialog>
  </section>
</template>
