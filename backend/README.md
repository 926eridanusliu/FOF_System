# FOF Due Diligence Report Backend

基于 FastAPI、SQLAlchemy 和 Pydantic 的 FOF 尽调报告后端。系统提供管理人、
产品、尽调报告 CRUD，支持报告校验、提交、归档，以及按既有附件 1-1/1-2
模板生成并下载 DOCX。报告生成完成后可通过可配置的 Hermes Feishu 网关发送通知。

Word 模板、书签清单、生成器和校验器均复用桌面“任务”目录第二、三阶段的
既有成果；测试夹具也直接复制自第三阶段最小数据，没有创建业务样例数据。

## Project structure

```text
backend/
├── app/
│   ├── main.py
│   ├── database.py
│   ├── models/                 # SQLAlchemy 表模型
│   ├── schemas/                # Pydantic 请求/响应模型
│   ├── routers/                # API 路由
│   ├── services/               # 业务校验与 Word 生成
│   └── templates/              # 两类官方模板及书签清单
├── docx_engine/                # 第三阶段书签填充引擎
├── validator/                  # 第三阶段 DOCX 校验器
├── generated_reports/
├── uploaded_images/            # API 上传图片（运行时自动创建）
├── uploaded_nav/               # API 上传净值文件（运行时自动创建）
├── report_versions/            # 历史版本的不可变图片/净值副本
├── config/                     # Hermes 私密配置说明（真实配置不入 Git）
├── tests/
├── requirements.txt
├── pytest.ini
├── .env.example
└── README.md
```

## Setup

Run these commands from the `backend/` directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate the environment with `.venv\Scripts\activate` instead.

如需自定义数据库或跨域配置：

```bash
cp .env.example .env
```

后端会自动读取 `backend/.env`。相对 SQLite 路径始终以 `backend/` 为基准，
不会因终端当前目录不同而创建到其他位置。`.env` 已被 Git 忽略。

## Database configuration

本地开发无需配置。应用默认使用 SQLite，并在首次启动时创建
`backend/fof_reports.db`。SQLite 外键检查已开启。

Production deployments should set `FOF_DATA_DIR` to a persistent directory outside
the source checkout. The SQLite database, generated reports, uploaded images/NAV
files, and version attachments then stay intact across code updates. To use another
database, export `DATABASE_URL` before starting the service. For
example:

```bash
export DATABASE_URL="postgresql+psycopg://username:password@localhost:5432/fof_reports"
```

切换 PostgreSQL 时还需要安装对应的 SQLAlchemy 驱动。

## Run

```bash
uvicorn app.main:app --reload
```

Available URLs:

- Service: <http://127.0.0.1:8000>
- Health check: <http://127.0.0.1:8000/health>
- Swagger documentation: <http://127.0.0.1:8000/docs>
- OpenAPI schema: <http://127.0.0.1:8000/openapi.json>

Vue 开发服务器默认允许从 `http://127.0.0.1:5173` 或
`http://localhost:5173` 跨域访问。部署到其他地址时，在 `.env` 或启动环境中设置：

```bash
export CORS_ORIGINS="https://your-frontend.example.com"
```

依赖版本已在 `requirements.txt` 中固定；升级依赖时需要重新执行完整测试，避免
不同机器安装到不兼容的 FastAPI、Starlette 或 SQLAlchemy 版本。

Expected health response:

```json
{
  "status": "ok",
  "service": "fof-report-backend"
}
```

## Test

```bash
pytest
```

测试覆盖健康检查、三类对象创建与查询、两类模板生成、文件下载、报告校验、
`draft → submitted → archived` 状态流转、不可变版本快照、字段对比、附件回滚及
关联数据删除保护，以及多产品策略并集、JSON 导入和外部填写令牌。

## API

### 管理人

| Method | Path | Description |
|---|---|---|
| POST | `/api/managers` | 创建管理人 |
| GET | `/api/managers` | 分页查询管理人 |
| GET | `/api/managers/{id}` | 查询管理人详情 |
| PUT | `/api/managers/{id}` | 更新管理人 |
| DELETE | `/api/managers/{id}` | 将管理人及关联档案移入回收站 |

### 产品

| Method | Path | Description |
|---|---|---|
| POST | `/api/products` | 创建产品 |
| GET | `/api/products` | 分页查询产品，可按管理人筛选 |
| GET | `/api/products/{id}` | 查询产品详情 |
| PUT | `/api/products/{id}` | 更新产品 |
| DELETE | `/api/products/{id}` | 删除无关联报告的产品 |

### 尽调报告

| Method | Path | Description |
|---|---|---|
| POST | `/api/reports` | 创建草稿 |
| GET | `/api/reports` | 分页查询，可按状态、管理人、产品筛选 |
| GET | `/api/reports/{id}` | 查询报告详情 |
| PUT | `/api/reports/{id}` | 编辑草稿 |
| DELETE | `/api/reports/{id}` | 将报告移入回收站 |
| POST | `/api/reports/{id}/validate` | 校验关联关系和模板内容 |
| POST | `/api/reports/{id}/submit` | 提交校验通过的草稿 |
| POST | `/api/reports/{id}/archive` | 归档已提交报告 |
| POST | `/api/reports/{id}/generate` | 生成 DOCX 并返回下载地址 |
| POST | `/api/reports/{id}/generation-jobs` | 创建异步 DOCX 生成任务，立即返回任务状态 |
| GET | `/api/reports/{id}/generation-jobs/{job_id}` | 查询生成任务进度与下载地址 |
| POST | `/api/reports/{id}/images/{field}` | 上传 PNG/JPEG 并写入图片书签 |
| DELETE | `/api/reports/{id}/images/{field}` | 删除草稿中的已上传图片 |
| POST | `/api/reports/{id}/import-json` | 预览或应用 JSON 导入 |
| POST | `/api/reports/{id}/invitations` | 生成带有效期的管理人填写链接 |
| GET | `/api/reports/{id}/invitations` | 查询填写链接状态 |
| DELETE | `/api/reports/{id}/invitations/{invitation_id}` | 撤销填写链接 |
| GET | `/api/reports/{id}/scorecard` | 查询净值文件、评分输入及计算结果 |
| POST | `/api/reports/{id}/scorecard/nav` | 上传并识别 `.xlsx/.csv` 净值文件 |
| POST | `/api/reports/{id}/scorecard/calculate` | 计算并保存定量、定性和合规扣分 |
| DELETE | `/api/reports/{id}/scorecard/nav` | 删除净值文件及已有评分结果 |
| GET | `/api/reports/{id}/versions` | 按版本号倒序查询提交快照 |
| GET | `/api/reports/{id}/versions/{version}` | 查询一个不可变版本 |
| GET | `/api/reports/{id}/versions/compare` | 对比两个版本的字段变化 |
| POST | `/api/reports/{id}/versions/{version}/restore` | 将历史版本复制回当前草稿 |
| GET | `/api/reports/{id}/notifications` | 查询飞书通知发送记录 |
| POST | `/api/reports/{id}/notifications/{notification_id}/retry` | 手动重试通知 |
| GET | `/api/notifications/config` | 查询非敏感的飞书配置完整度 |
| GET | `/api/files/{filename}` | 下载生成的 DOCX |
| GET | `/api/files/images/{report_id}/{filename}` | 预览或下载已上传图片 |

### 受控删除与回收站

管理人和报告的删除采用可恢复的逻辑删除，不会物理清除原始数据库记录。删除请求需
提交 `{"reason": "删除原因"}`；有关联数据的管理人、正式报告和已有历史版本的
报告不填写原因时会被拒绝。删除后：

- 工作台、详情接口及外部填写链接不再显示或访问该数据；
- 删除类型、名称、原因、时间和摘要写入 `deletion_records`；
- `GET /api/deletions` 可查看删除记录；
- `POST /api/deletions/{record_id}/restore` 可恢复。

历史报告、评分数据和版本文件不会因为逻辑删除而被清除。

公开填写接口仅凭随机令牌访问指定报告，不提供管理人、产品或其他报告列表：

- `GET/PUT /api/public/fill/{token}`：读取及自动保存；
- `POST /api/public/fill/{token}/submit`：提交并锁定链接；
- `POST/DELETE/GET /api/public/fill/{token}/images/{field}`：管理该报告图片。

数据库只保存令牌的 SHA-256 摘要，原始链接只在创建时返回一次。链接最长30天，
可由内部人员提前撤销。生产环境还必须使用 HTTPS，并由公司决定内部工作台的登录、
VPN或Nginx访问控制；邀请令牌不能替代内部人员身份认证。

报告的 `template_type` 可选：

- `private_fund`：附件 1-1 私募基金模板；
- `licensed_institution`：附件 1-2 持牌金融机构模板。

报告的 `content` 是书签字段 JSON。可直接参考：

- `tests/fixtures/private_fund_minimal.json`
- `tests/fixtures/licensed_institution_minimal.json`

`content` 至少需要提供两类第三阶段最小数据共同包含的身份字段，并至少选择
一种 `cover_strategy_*` 投资策略。完整字段以 `app/templates/` 下对应 manifest
为准。Swagger 会展示所有请求与响应格式。

### Upload report images

图片上传接口不使用 Base64，也不要求前端提交服务器路径。请求体就是图片二进制：

```bash
curl -X POST \
  "http://127.0.0.1:8000/api/reports/1/images/image_org_structure" \
  -H "Content-Type: image/png" \
  -H "X-Filename: org-structure.png" \
  --data-binary "@org-structure.png"
```

后端会验证：

- 报告必须仍是草稿；
- 字段必须是当前模板 manifest 中声明的图片书签；
- 文件真实格式必须是 PNG 或 JPEG；
- 单张图片不得超过 10 MB；
- 保存文件名和目录由后端生成，防止路径穿越。

附件 1-1 当前支持的图片字段：

```text
image_org_structure
image_performance_comparison
image_equity_structure
qa_section5_credit_screenshot_1
qa_section5_credit_screenshot_2
qa_section5_credit_screenshot_3
```

## State rules

```text
draft --submit--> submitted --archive--> archived
```

- 只有草稿可以编辑和删除；
- 只有校验通过的草稿可以提交；
- 每次提交会创建新的不可变历史版本；
- 只有已提交报告可以归档；
- 已提交或归档报告仍可生成和下载 Word，但不能改写报告内容。
- 回滚会将选中版本复制为新的当前草稿；原快照不会改变，重新提交时会生成下一版本。

## Asynchronous generation

前端预览使用异步任务接口，不会让浏览器请求持续等待 Word 生成。任务状态持久化在
数据库的 `report_generation_jobs` 表中，依次为：

```text
queued → running → completed
                 ↘ failed
```

创建任务时会冻结当前 `template_type` 和书签内容快照，因此附件 1-1 与附件 1-2
不会在生成途中互相混用。服务重启后会自动恢复未完成任务。默认每个服务实例同时
处理两个任务，可通过 `REPORT_GENERATION_WORKERS` 调整。原同步 `/generate` 接口
保留，供兼容已有调用方使用。

## Admission scorecard

报告编辑页“准入评分卡”支持上传 `.xlsx` 或 `.csv` 净值文件。文件至少需要：

```text
日期        累计净值
2024-01-01  1.0000
2024-01-08  1.0032
```

系统会识别常用中文/英文列名，也允许前端重新指定日期列、产品净值列和可选基准
净值列。旧版 `.xls` 需要先另存为 `.xlsx`。解析失败时接口会返回具体的行号和原因，
不会把无法识别的内容当作零值。

计算口径：

- 年化收益按实际起止日期，以 `365.25` 天复利年化；
- 波动率使用周期收益率样本标准差，并依据净值日期间隔年化；
- 夏普比率为 `(年化收益率 - 年化无风险利率) / 年化波动率`；
- 最大回撤使用期间净值高水位计算；
- 卡玛比率为 `年化收益率 / 最大回撤绝对值`；
- 月度胜率使用各自然月末最后一个净值计算；
- 近1年、近3/5年以及不足1年/3年的折扣规则，均来自
  `副本开源证券私募产品准入打分卡-评分调整版.xlsx`。

无风险利率由评分表单明确填写，默认显示 `0%`，可以修改；有明确基准时需要选择
基准净值列，否则按评分卡中的无基准策略规则判定相对收益。定性项目使用结构化
表单，不从自由文本中猜测人数、年限或评级。

评分完成后，同步和异步报告生成都会将评分结果快照作为附录写入 Word 末尾。
未计算评分卡的历史报告仍可按原流程生成，不会出现空白附录。

## Report version history

每次调用 `/submit` 时，报告状态变化和历史快照写入同一个数据库事务。快照包括：

- 报告标题、关联管理人/产品、模板类型、全部书签字段、结论和风险项；
- 当时已经计算的评分卡输入、指标、逐项评分和总分；
- 已上传图片及原始净值文件的独立副本；
- 用于检查快照是否被改写的 SHA-256 哈希。

历史版本没有更新或删除接口，数据库模型也会拒绝 ORM 更新/删除。已经产生历史
版本的报告即使回滚为草稿，也不能删除。

版本对比示例：

```text
GET /api/reports/1/versions/compare?from_version=1&to_version=2
```

响应逐项给出字段路径、中文字段名称、变化类型以及前后值。回滚接口会先校验快照
和附件哈希，再把选中版本复制到当前报告并将状态设为 `draft`。图片和净值文件会
从历史副本复制到新的草稿存储位置，因此之后的编辑不会改写旧版本文件。

## Hermes Feishu notification

同步和异步报告成功生成后都会写入 `report_notifications` 通知发件箱。飞书网关
故障不影响 Word 生成和下载；网络失败会有限重试，服务重启会恢复未完成任务。
系统不会把鉴权请求头、完整网关地址或网关响应体返回给前端。

网关协议和私密信息不能从业务模板推断，因此默认
`HERMES_FEISHU_ENABLED=false`。完整接入步骤见
`../docs/FEISHU_INTEGRATION.md`。
