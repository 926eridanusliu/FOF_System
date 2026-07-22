# FOF Due Diligence Report System

FOF 尽调报告 Web 系统。前端使用 Vue 3 + Element Plus，后端使用 FastAPI、
SQLAlchemy 和 Pydantic，并通过既有 Word 书签模板生成附件 1-1/附件 1-2 报告。

## Project structure

```text
backend/   FastAPI API、数据库模型、异步生成队列、DOCX 引擎与测试
frontend/  Vue 3 管理人、产品、报告编辑及 Word 在线预览界面
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
npm install
npm run dev
```

打开 <http://127.0.0.1:5173>。Swagger 文档位于
<http://127.0.0.1:8000/docs>。

更完整的配置、接口与运行说明见 `backend/README.md` 和 `frontend/README.md`。
