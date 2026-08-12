# Windows 内网部署手册

## 上线前必须由负责人决定

- 内网服务器名称/IP、访问端口和是否启用 HTTPS。
- 首期使用 SQLite 还是 PostgreSQL。
- Windows 服务托管工具（公司已有 NSSM、WinSW 或任务计划策略）。
- Nginx 安装位置、TLS 证书和防火墙规则。
- 数据库及运行文件的备份目录、保留周期和恢复责任人。
- Hermes Feishu 网关的私密配置。
- 管理方是否通过内网、VPN 或公司反向代理访问填写页面。

这些值没有写死在代码中。

## 服务器准备

安装 Git、Python 3.12、Node.js LTS 和 Nginx。使用专门的低权限服务账号，
不要使用个人账号长期运行。把仓库放到公司批准的应用目录，以下用
`C:\FOF-System` 举例；实际路径由管理员决定。

```powershell
cd C:\FOF-System\backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item ..\deployment\windows\backend.env.production.example .env
```

如果负责人选择 PostgreSQL，将安装命令中的文件改为
`requirements-postgres.txt`，并在 `.env` 填写公司提供的完整
`postgresql+psycopg://...` 连接地址。数据库密码不得写入 Git。

编辑 `.env`，将 `__DATA_DIR_FORWARD_SLASH__` 替换为独立于代码仓库的持久目录，
例如 `D:/FOF-System-Data`。数据库、生成报告、上传图片、净值文件和历史版本都会
写入该目录，代码更新不会覆盖业务数据。真实 `.env`、鉴权头、消息模板和数据库
都已被 Git 排除。

将 `PUBLIC_FRONTEND_URL` 设为管理方实际可访问的系统地址，例如
`https://fof.internal.example`。否则生成的填写链接会指向本机地址。

## 内网访问与权限边界

- 公司管理端（除 `/fill/` 及 `/api/public/` 以外的页面和接口）必须放在公司
  SSO、VPN 或 Nginx IP 白名单之后；具体账号和网段由公司管理员配置。
- 管理方只获得带随机令牌的单份报告填写链接，不能浏览管理人、产品、
  回收站或其他报告。
- 公司方可在“管理填写链接”窗口中随时选择“允许修改”或“禁止修改”，
  也可彻底撤销链接。撤销后不能恢复。
- 如果公司尚无 SSO，上线前至少应限制管理端只能从公司网段访问；不要将
  FastAPI 8000 端口直接暴露给管理方。

## 初始化与验证

后端首次启动会自动创建缺失的数据表，包括通知发件箱：

```powershell
powershell -ExecutionPolicy Bypass -File `
  C:\FOF-System\deployment\windows\run-backend.ps1 `
  -AppRoot C:\FOF-System
```

另开 PowerShell 构建前端：

```powershell
powershell -ExecutionPolicy Bypass -File `
  C:\FOF-System\deployment\windows\build-frontend.ps1 `
  -AppRoot C:\FOF-System
```

复制 `deployment/windows/nginx.conf.example`，替换四个占位符：

- `__LISTEN_PORT__`
- `__SERVER_NAME__`
- `__APP_ROOT_FORWARD_SLASH__`（例如 `C:/FOF-System`）

用 `nginx -t` 校验后再重载 Nginx。健康检查：

```powershell
powershell -ExecutionPolicy Bypass -File `
  C:\FOF-System\deployment\windows\health-check.ps1 `
  -BaseUrl http://实际服务器地址
```

## 为什么 Uvicorn 只开一个进程

当前 Word 生成和飞书发送是数据库留痕的进程内后台队列。一个 Uvicorn 进程可以
可靠恢复未完成任务；直接开多个进程可能重复拾取同一任务。以后若需要横向扩容，
先把任务执行迁移到公司批准的外部队列，再增加进程数。

## SQLite 备份

备份脚本通过 SQLite 在线备份 API 创建一致副本，并校验副本；同时复制生成报告、
上传图片和历史版本：

```powershell
powershell -ExecutionPolicy Bypass -File `
  C:\FOF-System\deployment\windows\backup-sqlite.ps1 `
  -AppRoot C:\FOF-System `
  -DataRoot D:\FOF-System-Data `
  -BackupRoot D:\FOF-Backups
```

由管理员把它加入任务计划，并决定保留周期。必须定期在隔离环境做恢复演练。
PostgreSQL 上线时改用公司的 `pg_dump`、恢复及凭据管理规范，不运行 SQLite 脚本。

## 更新与回滚

上线前备份数据库和运行目录；在测试环境执行后端测试、前端测试和构建。更新时先
停止后端服务，拉取已批准版本，安装依赖、构建前端并启动。若健康检查或核心流程
失败，停止服务、恢复上一代码版本和备份数据，再记录故障。
