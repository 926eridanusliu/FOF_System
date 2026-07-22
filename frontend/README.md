# FOF 尽调前端

Vue 3 + TypeScript + Element Plus 的尽调工作台，对接同级 `backend/` 中的
FastAPI 服务。业务字段和模板书签来自后端已经采用的第二、第三阶段数据，前端
没有另造业务样例。

## 页面

- `/managers`：管理人列表、搜索和统计；
- `/managers/new`：新建管理人；
- `/managers/:id`：管理人详情、产品和尽调历史；
- `/reports/:id`：多 Tab 报告编辑、动态策略、内嵌表格、图片上传、校验和状态流转；
- `/reports/:id/preview`：创建异步 Word 任务、显示进度，并在浏览器中预览和下载。

草稿编辑页每 30 秒检查一次未保存修改并自动保存。离开有未保存修改的页面前会
二次确认。报告提交后只读，已提交报告可归档。

报告预览不会用一个请求等待 10–30 秒：页面先取得任务编号，再轮询
`queued / running / completed / failed` 状态。任务完成后才读取 DOCX 并转换为
在线预览，因此长时间生成不会触发普通 HTTP 请求超时。

## 本地运行

先启动后端（终端一）：

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

再启动前端（终端二）：

```bash
cd frontend
npm install
npm run dev
```

打开 <http://127.0.0.1:5173>。开发服务器会把 `/api` 和 `/health` 请求代理到
`http://127.0.0.1:8000`。

## 构建与测试

```bash
npm run build
npm test
```

构建产物位于 `frontend/dist/`。如将前后端部署到不同域名，请在后端环境变量
`CORS_ORIGINS` 中用英文逗号列出允许的前端地址。
