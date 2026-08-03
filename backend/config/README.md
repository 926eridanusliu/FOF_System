# Hermes 飞书私密配置目录

此目录只保存说明，不保存生产密钥。

部署人员需要根据公司现有 Hermes Feishu 网关的真实接口文档，在本目录创建：

- `hermes_feishu_headers.json`：鉴权请求头；没有额外请求头时可写 `{}`。
- `hermes_feishu_payload.json`：网关要求的完整 JSON 请求体模板。

这两个真实文件已被 `.gitignore` 排除，不会上传 GitHub。

请求体模板可在任意字符串位置使用：

- `{{manager_name}}`
- `{{product_name}}`
- `{{report_date}}`
- `{{download_url}}`
- `{{recipient_id}}`
- `{{report_id}}`
- `{{filename}}`

系统按 JSON 结构替换占位符，不会把鉴权信息返回给前端。由于当前代码库没有
Hermes 网关的真实请求格式，本项目没有虚构一个可发送的示例请求体。
