<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Collection, DeleteFilled, Document, OfficeBuilding } from '@element-plus/icons-vue'

const route = useRoute()
const isReportWorkspace = computed(() => route.path.startsWith('/reports/'))
const isPublicFill = computed(() => route.path.startsWith('/fill/'))
</script>

<template>
  <div class="app-shell" :class="{ 'is-report-workspace': isReportWorkspace, 'is-public-fill': isPublicFill }">
    <aside v-if="!isPublicFill" class="app-sidebar">
      <router-link class="brand" to="/managers" aria-label="FOF 尽调工作台首页">
        <span class="brand-mark">F</span>
        <span><b>FOF 尽调</b><small>REPORT DESK</small></span>
      </router-link>
      <nav class="primary-nav" aria-label="主导航">
        <router-link to="/managers">
          <el-icon><OfficeBuilding /></el-icon><span>管理人</span>
        </router-link>
        <router-link to="/managers/new">
          <el-icon><Collection /></el-icon><span>新建管理人</span>
        </router-link>
        <router-link to="/recycle-bin">
          <el-icon><DeleteFilled /></el-icon><span>回收站</span>
        </router-link>
      </nav>
      <div class="sidebar-foot">
        <el-icon><Document /></el-icon>
        <span>尽调记录统一留痕</span>
      </div>
    </aside>
    <main class="app-main">
      <header v-if="!isPublicFill" class="app-topbar">
        <div>
          <span class="topbar-kicker">资产管理业务</span>
          <strong>{{ route.meta.title }}</strong>
        </div>
        <span class="environment-badge"><i /> 本地开发环境</span>
      </header>
      <router-view />
    </main>
  </div>
</template>
