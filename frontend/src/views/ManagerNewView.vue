<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { api, apiMessage } from '../api'

const router = useRouter()
const formRef = ref<FormInstance>()
const submitting = ref(false)
const form = reactive({ name: '', unified_social_credit_code: '', contact_name: '', contact_phone: '' })
const rules: FormRules = {
  name: [{ required: true, message: '请输入管理人名称', trigger: 'blur' }],
  unified_social_credit_code: [{ pattern: /^[0-9A-Z]{18}$/, message: '统一社会信用代码应为 18 位大写字母或数字', trigger: 'blur' }],
}

async function submit() {
  if (!await formRef.value?.validate().catch(() => false)) return
  submitting.value = true
  try {
    const manager = await api.managers.create({
      name: form.name.trim(),
      unified_social_credit_code: form.unified_social_credit_code || null,
      contact_name: form.contact_name || null,
      contact_phone: form.contact_phone || null,
    })
    ElMessage.success('管理人已创建')
    router.replace(`/managers/${manager.id}`)
  } catch (error) { ElMessage.error(apiMessage(error)) }
  finally { submitting.value = false }
}
</script>

<template>
  <section class="page">
    <div class="page-heading">
      <div><span class="eyebrow">New Manager</span><h1>新建管理人</h1><p>建立机构基础档案，后续可关联产品和尽调报告。</p></div>
      <el-button @click="router.back()">返回</el-button>
    </div>
    <div class="surface" style="max-width: 820px">
      <div class="surface-header"><h2>机构基础信息</h2><span class="muted">标记 * 的字段为必填</span></div>
      <div class="surface-body">
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
          <div class="field-grid">
            <el-form-item class="span-2" label="管理人名称" prop="name"><el-input v-model="form.name" maxlength="255" show-word-limit placeholder="请输入工商登记全称" /></el-form-item>
            <el-form-item label="统一社会信用代码" prop="unified_social_credit_code"><el-input v-model="form.unified_social_credit_code" maxlength="18" placeholder="18 位代码（可稍后补充）" /></el-form-item>
            <el-form-item label="联系人" prop="contact_name"><el-input v-model="form.contact_name" maxlength="100" placeholder="尽调对接人" /></el-form-item>
            <el-form-item label="联系方式" prop="contact_phone"><el-input v-model="form.contact_phone" maxlength="100" placeholder="电话或邮箱" /></el-form-item>
          </div>
          <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:18px"><el-button @click="router.back()">取消</el-button><el-button type="primary" :loading="submitting" @click="submit">保存并进入详情</el-button></div>
        </el-form>
      </div>
    </div>
  </section>
</template>
