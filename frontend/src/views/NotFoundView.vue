<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <section class="page">
    <div class="surface empty-state not-found">
      <span class="eyebrow">404 · Not Found</span>
      <h1>这个页面不存在</h1>
      <p>链接可能已失效，或地址输入有误。</p>
      <el-button type="primary" @click="router.push('/managers')">返回管理人列表</el-button>
    </div>
  </section>
</template>
