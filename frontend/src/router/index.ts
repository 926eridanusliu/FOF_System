import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/managers' },
    { path: '/managers', name: 'managers', component: () => import('../views/ManagersView.vue'), meta: { title: '管理人' } },
    { path: '/managers/new', name: 'manager-new', component: () => import('../views/ManagerNewView.vue'), meta: { title: '新建管理人' } },
    { path: '/managers/:id', name: 'manager-detail', component: () => import('../views/ManagerDetailView.vue'), meta: { title: '管理人详情' } },
    { path: '/reports/:id', name: 'report-edit', component: () => import('../views/ReportEditorView.vue'), meta: { title: '报告编辑' } },
    { path: '/reports/:id/preview', name: 'report-preview', component: () => import('../views/ReportPreviewView.vue'), meta: { title: '报告预览' } },
    { path: '/:pathMatch(.*)*', component: () => import('../views/NotFoundView.vue'), meta: { title: '页面不存在' } },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title || '工作台')} · FOF 尽调`
})

export default router
