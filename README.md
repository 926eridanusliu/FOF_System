# FOF Due Diligence Report System

FOF 尽调报告 Web 系统。前端使用 Vue 3 + Element Plus，后端使用 FastAPI、
SQLAlchemy 和 Pydantic，并通过既有 Word 书签模板生成附件 1-1/附件 1-2 报告。

## Project structure

```text
backend/   FastAPI API、数据库模型、异步生成队列、DOCX 引擎与测试
frontend/  Vue 3 管理人、产品、外部资料收集、报告编辑及 Word 在线预览界面
deployment/ Windows/Nginx 启动、构建、健康检查和备份模板
docs/      用户、管理员、飞书接入、部署、演示和交接文档
```

## Local development

后端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

前端（另开终端）：

```bash
cd frontend
npm ci
npm run dev
```

打开 <http://127.0.0.1:5173>。Swagger 文档位于
<http://127.0.0.1:8000/docs>。

系统支持为产品配置策略、一份报告关联多只产品、预览后导入 JSON，以及生成
限定报告、带有效期并可撤销的管理人填写链接。生产环境必须在
`backend/.env` 设置对方能够访问的 `PUBLIC_FRONTEND_URL`。
公司方可在每条填写链接上单独开启或关闭管理方的修改权限。

更完整的配置、接口与运行说明见 `backend/README.md` 和 `frontend/README.md`。

每次提交和 Pull Request 都会通过 `.github/workflows/ci.yml` 自动执行后端测试、
前端测试和前端生产构建。

## Production handoff

- [Windows 内网部署手册](docs/DEPLOYMENT_WINDOWS.md)
- [Hermes 飞书通知接入](docs/FEISHU_INTEGRATION.md)
- [用户手册](docs/USER_MANUAL.md)
- [管理员手册](docs/ADMIN_MANUAL.md)
- [最终演示脚本](docs/DEMO_SCRIPT.md)
- [项目交接清单](docs/HANDOVER.md)

生产环境的服务器地址、访问控制、数据库选型、备份策略及 Hermes 私密信息必须由
公司负责人确认，不能写入公开仓库。
