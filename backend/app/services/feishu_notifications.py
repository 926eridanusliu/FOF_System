from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import Lock, Timer
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.database import BACKEND_DIR
from app.models.manager import Manager
from app.models.notification import NotificationStatus, ReportNotification
from app.models.product import Product
from app.models.report import DueDiligenceReport


ALLOWED_METHODS = {"POST", "PUT", "PATCH"}
PLACEHOLDERS = {
    "report_id",
    "manager_name",
    "product_name",
    "report_date",
    "download_url",
    "recipient_id",
    "filename",
}
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="feishu-notification")
_futures: dict[tuple[Engine, int], Future[None]] = {}
_timers: dict[tuple[Engine, int], Timer] = {}
_lock = Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return min(max(value, minimum), maximum)


def _resolve_config_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


@dataclass(frozen=True)
class FeishuConfig:
    enabled: bool
    gateway_url: str
    method: str
    headers_file: Path | None
    payload_template_file: Path | None
    recipient_id: str
    public_base_url: str
    timeout_seconds: int
    max_attempts: int
    retry_base_seconds: int

    @classmethod
    def from_env(cls) -> "FeishuConfig":
        return cls(
            enabled=_env_bool("HERMES_FEISHU_ENABLED"),
            gateway_url=os.getenv("HERMES_FEISHU_GATEWAY_URL", "").strip(),
            method=os.getenv("HERMES_FEISHU_METHOD", "POST").strip().upper(),
            headers_file=_resolve_config_path(os.getenv("HERMES_FEISHU_HEADERS_FILE")),
            payload_template_file=_resolve_config_path(
                os.getenv("HERMES_FEISHU_PAYLOAD_TEMPLATE_FILE")
            ),
            recipient_id=os.getenv("HERMES_FEISHU_RECIPIENT_ID", "").strip(),
            public_base_url=os.getenv("REPORT_PUBLIC_BASE_URL", "").strip().rstrip("/"),
            timeout_seconds=_env_int("HERMES_FEISHU_TIMEOUT_SECONDS", 10, 1, 60),
            max_attempts=_env_int("HERMES_FEISHU_MAX_ATTEMPTS", 3, 1, 10),
            retry_base_seconds=_env_int(
                "HERMES_FEISHU_RETRY_BASE_SECONDS", 5, 0, 60
            ),
        )

    def missing_settings(self) -> list[str]:
        missing: list[str] = []
        if not self.gateway_url:
            missing.append("HERMES_FEISHU_GATEWAY_URL")
        elif urlparse(self.gateway_url).scheme not in {"http", "https"}:
            missing.append("HERMES_FEISHU_GATEWAY_URL（必须是 http/https）")
        if self.method not in ALLOWED_METHODS:
            missing.append("HERMES_FEISHU_METHOD（仅支持 POST/PUT/PATCH）")
        if not self.payload_template_file or not self.payload_template_file.is_file():
            missing.append("HERMES_FEISHU_PAYLOAD_TEMPLATE_FILE")
        if not self.recipient_id:
            missing.append("HERMES_FEISHU_RECIPIENT_ID")
        if not self.public_base_url:
            missing.append("REPORT_PUBLIC_BASE_URL")
        return missing


def config_summary() -> dict[str, Any]:
    config = FeishuConfig.from_env()
    parsed = urlparse(config.gateway_url) if config.gateway_url else None
    missing = config.missing_settings() if config.enabled else []
    return {
        "enabled": config.enabled,
        "ready": config.enabled and not missing,
        "missing_settings": missing,
        "gateway_host": parsed.netloc if parsed and parsed.netloc else None,
        "recipient_configured": bool(config.recipient_id),
        "payload_template_configured": bool(
            config.payload_template_file and config.payload_template_file.is_file()
        ),
    }


def _read_json(path: Path, description: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{description}无法读取或不是合法 JSON：{path}") from exc


def _replace_placeholders(value: Any, values: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _replace_placeholders(item, values) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_placeholders(item, values) for item in value]
    if not isinstance(value, str):
        return value
    exact = value.removeprefix("{{").removesuffix("}}") if value.startswith("{{") else ""
    if exact in values and value == f"{{{{{exact}}}}}":
        return values[exact]
    rendered = value
    for key, replacement in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(replacement))
    if "{{" in rendered or "}}" in rendered:
        raise ValueError(f"通知模板包含未识别的占位符：{rendered}")
    return rendered


def render_gateway_request(
    notification: ReportNotification, config: FeishuConfig
) -> tuple[dict[str, str], Any, str]:
    missing = config.missing_settings()
    if missing:
        raise ValueError("飞书通知配置不完整：" + "、".join(missing))
    assert config.payload_template_file is not None
    download_url = (
        f"{config.public_base_url}/api/files/{quote(notification.filename)}"
    )
    values = {
        "report_id": notification.report_id,
        "manager_name": notification.manager_name,
        "product_name": notification.product_name,
        "report_date": notification.report_date,
        "download_url": download_url,
        "recipient_id": config.recipient_id,
        "filename": notification.filename,
    }
    template = _read_json(config.payload_template_file, "飞书消息模板")
    payload = _replace_placeholders(template, values)
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if config.headers_file:
        raw_headers = _read_json(config.headers_file, "飞书鉴权头文件")
        if not isinstance(raw_headers, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in raw_headers.items()
        ):
            raise ValueError("飞书鉴权头文件必须是字符串键值对 JSON 对象")
        headers.update(raw_headers)
    return headers, payload, download_url


def send_gateway_request(
    config: FeishuConfig, headers: dict[str, str], payload: Any
) -> httpx.Response:
    with httpx.Client(timeout=config.timeout_seconds) as client:
        return client.request(
            config.method,
            config.gateway_url,
            headers=headers,
            json=payload,
        )


def create_notification(
    db: Session,
    report: DueDiligenceReport,
    manager: Manager,
    product: Product,
    filename: str,
    generation_job_id: int | None = None,
) -> ReportNotification:
    event_key = f"generated:{filename}"
    existing = db.scalar(
        select(ReportNotification).where(ReportNotification.event_key == event_key)
    )
    if existing is not None:
        return existing
    config = FeishuConfig.from_env()
    content = report.content or {}
    notification = ReportNotification(
        report_id=report.id,
        generation_job_id=generation_job_id,
        event_key=event_key,
        status=(
            NotificationStatus.PENDING
            if config.enabled
            else NotificationStatus.DISABLED
        ),
        filename=filename,
        manager_name=manager.name,
        product_name=product.name,
        report_date=str(content.get("cover_report_date") or ""),
        recipient_id=config.recipient_id or None,
        max_attempts=config.max_attempts,
    )
    db.add(notification)
    db.flush()
    return notification


def _schedule_retry(notification_id: int, bind: Engine, delay_seconds: int) -> None:
    task_key = (bind, notification_id)
    timer = Timer(delay_seconds, enqueue_notification, args=(notification_id, bind))
    timer.daemon = True
    with _lock:
        prior = _timers.pop(task_key, None)
        if prior:
            prior.cancel()
        _timers[task_key] = timer
    timer.start()


def _run_notification(notification_id: int, bind: Engine) -> None:
    should_retry = False
    retry_delay = 0
    with Session(bind=bind) as db:
        notification = db.get(ReportNotification, notification_id)
        if notification is None or notification.status == NotificationStatus.SENT:
            return
        config = FeishuConfig.from_env()
        if not config.enabled:
            notification.status = NotificationStatus.DISABLED
            notification.last_error = None
            db.commit()
            return
        if notification.attempt_count >= notification.max_attempts:
            return
        notification.status = NotificationStatus.SENDING
        notification.attempt_count += 1
        notification.last_error = None
        db.commit()
        try:
            headers, payload, download_url = render_gateway_request(notification, config)
            response = send_gateway_request(config, headers, payload)
            notification.download_url = download_url
            notification.recipient_id = config.recipient_id
            notification.response_status = response.status_code
            notification.response_body = response.text[:2000]
            response.raise_for_status()
            notification.status = NotificationStatus.SENT
            notification.sent_at = _now()
        except ValueError as exc:
            notification.status = NotificationStatus.FAILED
            notification.last_error = str(exc)[:2000]
        except (httpx.HTTPError, OSError) as exc:
            notification.status = NotificationStatus.FAILED
            # Do not persist a request URL because some gateways put secrets in
            # query parameters. The HTTP status is stored separately.
            notification.last_error = f"飞书网关请求失败（{type(exc).__name__}）"
            should_retry = notification.attempt_count < notification.max_attempts
            retry_delay = min(
                config.retry_base_seconds * (2 ** (notification.attempt_count - 1)),
                60,
            )
        db.commit()
    if should_retry:
        _schedule_retry(notification_id, bind, retry_delay)


def enqueue_notification(notification_id: int, bind: Engine) -> None:
    task_key = (bind, notification_id)
    with _lock:
        _timers.pop(task_key, None)
        existing = _futures.get(task_key)
        if existing is not None and not existing.done():
            return
        future = _executor.submit(_run_notification, notification_id, bind)
        _futures[task_key] = future
    future.add_done_callback(lambda _: _remove_future(task_key))


def _remove_future(task_key: tuple[Engine, int]) -> None:
    with _lock:
        _futures.pop(task_key, None)


def recover_notifications(bind: Engine) -> None:
    config = FeishuConfig.from_env()
    if not config.enabled:
        return
    with Session(bind=bind) as db:
        notifications = list(
            db.scalars(
                select(ReportNotification).where(
                    ReportNotification.status.in_(
                        [
                            NotificationStatus.DISABLED,
                            NotificationStatus.PENDING,
                            NotificationStatus.SENDING,
                            NotificationStatus.FAILED,
                        ]
                    )
                )
            )
        )
        for notification in notifications:
            notification.status = NotificationStatus.PENDING
        db.commit()
        notification_ids = [
            item.id
            for item in notifications
            if item.attempt_count < item.max_attempts
        ]
    for notification_id in notification_ids:
        enqueue_notification(notification_id, bind)


def retry_notification(
    notification: ReportNotification, db: Session
) -> ReportNotification:
    config = FeishuConfig.from_env()
    if not config.enabled:
        raise ValueError("飞书通知功能尚未启用")
    notification.status = NotificationStatus.PENDING
    notification.attempt_count = 0
    notification.max_attempts = config.max_attempts
    notification.last_error = None
    notification.response_status = None
    notification.response_body = None
    notification.sent_at = None
    db.commit()
    db.refresh(notification)
    enqueue_notification(notification.id, db.get_bind())
    return notification
