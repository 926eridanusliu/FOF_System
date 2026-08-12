# FOF System - Start Here

本运行包已包含构建好的前端页面。启动后，前端页面和后端 API 共用地址：
`http://127.0.0.1:8000`。

## macOS / Linux

```bash
chmod +x start-macos-linux.sh
./start-macos-linux.sh
```

## Windows PowerShell

```powershell
powershell -ExecutionPolicy Bypass -File .\start-windows.ps1
```

首次启动会自动创建独立 Python 环境并安装后端依赖，需要电脑已安装 Python 3.12
且首次能访问 Python 包源。业务数据保存在 `data/` 目录。

公司内网正式部署请另外按 `docs/DEPLOYMENT_WINDOWS.md` 配置固定服务、HTTPS、
SSO/VPN 访问控制和备份。
