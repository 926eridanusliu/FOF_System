from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
import os
from threading import Lock
from types import SimpleNamespace
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.models.generation_job import GenerationJobStatus, ReportGenerationJob
from app.models.report import DueDiligenceReport
from app.models.manager import Manager
from app.models.product import Product
from app.services.document_generator import generate_document
from app.services.feishu_notifications import create_notification, enqueue_notification


WORKER_COUNT = max(1, int(os.getenv("REPORT_GENERATION_WORKERS", "2")))
_executor = ThreadPoolExecutor(max_workers=WORKER_COUNT, thread_name_prefix="report-generator")
_futures: dict[int, Future[None]] = {}
_lock = Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _run_generation_job(job_id: int, bind: Engine) -> None:
    with Session(bind=bind) as db:
        job = db.get(ReportGenerationJob, job_id)
        if job is None or job.status == GenerationJobStatus.COMPLETED:
            return
        job.status = GenerationJobStatus.RUNNING
        job.started_at = _now()
        job.finished_at = None
        job.error = None
        db.commit()

        try:
            snapshot_content = dict(job.content_snapshot or {})
            scorecard_snapshot = snapshot_content.pop("__scorecard__", None)
            snapshot = SimpleNamespace(
                id=job.report_id,
                template_type=job.template_type,
                content=snapshot_content,
            )
            generated = generate_document(  # type: ignore[arg-type]
                snapshot,
                scorecard_snapshot=scorecard_snapshot,
            )
        except Exception as exc:  # Worker boundary: persist any generator failure for polling clients.
            db.rollback()
            failed = db.get(ReportGenerationJob, job_id)
            if failed is not None:
                failed.status = GenerationJobStatus.FAILED
                failed.error = f"报告生成失败：{exc}"[:2000]
                failed.finished_at = _now()
                db.commit()
            return

        completed = db.get(ReportGenerationJob, job_id)
        report = db.get(DueDiligenceReport, job.report_id)
        notification_id: int | None = None
        if completed is None:
            return
        completed.status = GenerationJobStatus.COMPLETED
        completed.filename = generated.filename
        completed.validation = generated.validation
        completed.finished_at = _now()
        if report is not None:
            report.generated_filename = generated.filename
            manager = db.get(Manager, report.manager_id)
            product = db.get(Product, report.product_id)
            if manager is not None and product is not None:
                notification = create_notification(
                    db,
                    report,
                    manager,
                    product,
                    generated.filename,
                    generation_job_id=job.id,
                )
                notification_id = notification.id
        db.commit()
        if notification_id is not None:
            enqueue_notification(notification_id, bind)


def enqueue_generation(job_id: int, bind: Engine) -> None:
    with _lock:
        existing = _futures.get(job_id)
        if existing is not None and not existing.done():
            return
        future = _executor.submit(_run_generation_job, job_id, bind)
        _futures[job_id] = future
    future.add_done_callback(lambda _: _remove_future(job_id))


def _remove_future(job_id: int) -> None:
    with _lock:
        _futures.pop(job_id, None)


def recover_generation_jobs(bind: Engine) -> None:
    with Session(bind=bind) as db:
        jobs = list(
            db.scalars(
                select(ReportGenerationJob).where(
                    ReportGenerationJob.status.in_(
                        [GenerationJobStatus.QUEUED, GenerationJobStatus.RUNNING]
                    )
                )
            )
        )
        for job in jobs:
            job.status = GenerationJobStatus.QUEUED
            job.started_at = None
            job.error = None
        db.commit()
        job_ids = [job.id for job in jobs]
    for job_id in job_ids:
        enqueue_generation(job_id, bind)


def active_job_count() -> int:
    with _lock:
        return sum(not future.done() for future in _futures.values())
