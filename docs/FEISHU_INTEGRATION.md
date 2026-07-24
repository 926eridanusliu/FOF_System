# Hermes 飞书通知接入说明

## 它做什么

每次 Word 报告成功生成后，系统创建一条不可丢失的通知记录，再调用现有
Hermes Feishu 网关。消息数据来自当次报告，包含：

- 管理人名称
- 产品名称
- 报告日期
- Word 下载链接

飞书失败不会使 Word 生成失败。网络错误会按指数间隔自动重试，达到上限后可从
API 手动重试。

## 需要公司提供的私密数据

以下信息不能从现有项目推断，也不应提交 GitHub：

1. Hermes Feishu 网关完整 URL。
2. 网关要求的 HTTP 方法。
3. 鉴权请求头及密钥。
4. 接收对象 ID（群、用户或机器人对应的真实标识）。
5. 网关要求的 JSON 请求体结构。
6. 用户浏览器能够访问的系统地址，用来组成下载链接。

## 配置方法

1. 将 `deployment/windows/backend.env.production.example` 复制为
   `backend/.env`。
2. 根据 `backend/config/README.md` 创建两个私密 JSON 文件。
3. 先保持 `HERMES_FEISHU_ENABLED=false` 启动系统。
4. 打开 `GET /api/notifications/config`，确认接口不会返回秘密。
5. 填完配置后改为 `true` 并重启后端。
6. 生成一份测试报告，检查
   `GET /api/reports/{report_id}/notifications`。

通知状态：

- `disabled`：功能未启用，报告生成正常。
- `pending` / `sending`：等待或正在发送。
- `sent`：网关返回成功。
- `failed`：配置或网络失败，可查看 `last_error`。

手动重试：

```text
POST /api/reports/{report_id}/notifications/{notification_id}/retry
```

## 请求体模板占位符

真实网关请求体由公司提供，代码仅替换以下占位符：

`manager_name`、`product_name`、`report_date`、`download_url`、
`recipient_id`、`report_id`、`filename`。具体写法见
`backend/config/README.md`。
