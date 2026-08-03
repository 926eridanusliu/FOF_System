import json
from pathlib import Path
from types import SimpleNamespace
import time

import httpx
from app import storage
from app.services import feishu_notifications
from app.services.feishu_notifications import FeishuConfig, render_gateway_request
from tests.test_api_workflow import create_report_records


def test_gateway_template_uses_real_report_values(
    tmp_path: Path, monkeypatch
) -> None:
    payload_file = tmp_path / "payload.json"
    headers_file = tmp_path / "headers.json"
    payload_file.write_text(
        json.dumps(
            {
                "receiver": "{{recipient_id}}",
                "content": {
                    "manager": "{{manager_name}}",
                    "product": "{{product_name}}",
                    "date": "{{report_date}}",
                    "link": "{{download_url}}",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    headers_file.write_text(
        json.dumps({"Authorization": "Bearer test-only-token"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_FEISHU_ENABLED", "true")
    monkeypatch.setenv("HERMES_FEISHU_GATEWAY_URL", "https://gateway.example.test/send")
    monkeypatch.setenv("HERMES_FEISHU_HEADERS_FILE", str(headers_file))
    monkeypatch.setenv("HERMES_FEISHU_PAYLOAD_TEMPLATE_FILE", str(payload_file))
    monkeypatch.setenv("HERMES_FEISHU_RECIPIENT_ID", "test-recipient")
    monkeypatch.setenv("REPORT_PUBLIC_BASE_URL", "https://fof.example.test")

    notification = SimpleNamespace(
        report_id=7,
        manager_name="测试管理人",
        product_name="测试产品",
        report_date="2026-07-24",
        filename="报告 文件.docx",
    )
    headers, payload, download_url = render_gateway_request(
        notification, FeishuConfig.from_env()
    )

    assert headers["Authorization"] == "Bearer test-only-token"
    assert payload["receiver"] == "test-recipient"
    assert payload["content"]["manager"] == "测试管理人"
    assert payload["content"]["product"] == "测试产品"
    assert payload["content"]["date"] == "2026-07-24"
    assert payload["content"]["link"] == download_url
    assert download_url == "https://fof.example.test/api/files/%E6%8A%A5%E5%91%8A%20%E6%96%87%E4%BB%B6.docx"


def test_generation_succeeds_and_records_disabled_notification(
    client,
    private_fund_data,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HERMES_FEISHU_ENABLED", "false")
    monkeypatch.setattr(storage, "GENERATED_DIR", tmp_path / "generated")
    _, _, report = create_report_records(
        client,
        private_fund_data,
        "private_fund",
        "飞书通知关闭时仍可生成",
    )

    generated = client.post(f"/api/reports/{report['id']}/generate")
    assert generated.status_code == 200, generated.text

    notifications = client.get(f"/api/reports/{report['id']}/notifications")
    assert notifications.status_code == 200
    records = notifications.json()
    assert len(records) == 1
    assert records[0]["status"] == "disabled"
    assert records[0]["manager_name"] == private_fund_data["cover_manager_name"]
    assert records[0]["product_name"] == private_fund_data["cover_product_name"]
    assert records[0]["report_date"] == private_fund_data["cover_report_date"]
    assert "recipient_id" not in records[0]


def test_notification_config_endpoint_never_returns_secrets(
    client, monkeypatch
) -> None:
    monkeypatch.setenv("HERMES_FEISHU_ENABLED", "true")
    monkeypatch.setenv(
        "HERMES_FEISHU_GATEWAY_URL", "https://internal.example.test/private/path"
    )
    monkeypatch.setenv("HERMES_FEISHU_RECIPIENT_ID", "private-recipient")

    response = client.get("/api/notifications/config")
    assert response.status_code == 200
    body = response.json()
    assert body["gateway_host"] == "internal.example.test"
    assert body["recipient_configured"] is True
    serialized = json.dumps(body)
    assert "private/path" not in serialized
    assert "private-recipient" not in serialized


def test_generated_report_is_delivered_through_configured_gateway(
    client,
    private_fund_data,
    tmp_path: Path,
    monkeypatch,
) -> None:
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(
        json.dumps(
            {
                "recipient": "{{recipient_id}}",
                "text": "{{manager_name}}|{{product_name}}|{{report_date}}",
                "download": "{{download_url}}",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_FEISHU_ENABLED", "true")
    monkeypatch.setenv("HERMES_FEISHU_GATEWAY_URL", "https://gateway.example.test/send")
    monkeypatch.setenv("HERMES_FEISHU_PAYLOAD_TEMPLATE_FILE", str(payload_file))
    monkeypatch.setenv("HERMES_FEISHU_RECIPIENT_ID", "approved-test-recipient")
    monkeypatch.setenv("REPORT_PUBLIC_BASE_URL", "https://fof.example.test")
    monkeypatch.delenv("HERMES_FEISHU_HEADERS_FILE", raising=False)
    monkeypatch.setattr(storage, "GENERATED_DIR", tmp_path / "generated")
    captured: dict = {}

    def fake_send(config, headers, payload):
        captured["payload"] = payload
        request = httpx.Request(config.method, config.gateway_url)
        return httpx.Response(200, request=request, json={"ok": True})

    monkeypatch.setattr(feishu_notifications, "send_gateway_request", fake_send)
    _, _, report = create_report_records(
        client,
        private_fund_data,
        "private_fund",
        "飞书网关发送测试",
    )

    generated = client.post(f"/api/reports/{report['id']}/generate")
    assert generated.status_code == 200, generated.text

    deadline = time.monotonic() + 3
    records = []
    while time.monotonic() < deadline:
        records = client.get(
            f"/api/reports/{report['id']}/notifications"
        ).json()
        if records and records[0]["status"] == "sent":
            break
        time.sleep(0.02)

    assert records[0]["status"] == "sent", records
    payload = captured["payload"]
    assert payload["recipient"] == "approved-test-recipient"
    assert private_fund_data["cover_manager_name"] in payload["text"]
    assert private_fund_data["cover_product_name"] in payload["text"]
    assert payload["download"].startswith("https://fof.example.test/api/files/")
