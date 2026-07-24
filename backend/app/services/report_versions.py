from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import storage
from app.models.manager import Manager
from app.models.product import Product
from app.models.report import DueDiligenceReport, ReportStatus, ReportTemplateType
from app.models.report_version import ReportVersion
from app.models.scorecard import ReportScorecard
from app.schemas.report_version import (
    ReportVersionComparison,
    ReportVersionSummary,
    VersionDiffItem,
)
from app.services.report_validator import MANIFEST_FILES


REPORT_LABELS = {
    "title": "报告标题",
    "manager_name": "管理人",
    "product_name": "产品",
    "template_type": "报告模板",
    "conclusion": "尽调结论",
    "risk_items": "风险项",
}
SCORECARD_LABELS = {
    "quantitative_score": "评分卡／定量得分",
    "qualitative_score": "评分卡／定性得分",
    "compliance_deduction": "评分卡／合规扣分",
    "total_score": "评分卡／总分",
    "admitted": "评分卡／准入结论",
    "calculation_inputs": "评分卡／计算输入",
    "metrics": "评分卡／定量指标",
}


def _json_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_version_path(path: Path) -> str:
    return str(path.resolve().relative_to(storage.VERSION_STORAGE_DIR.resolve()))


def _resolve_version_file(relative_path: str, expected_hash: str) -> Path:
    root = storage.VERSION_STORAGE_DIR.resolve()
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError("历史版本附件不存在，无法完整回滚")
    if _file_hash(target) != expected_hash:
        raise ValueError("历史版本附件校验失败，文件可能已被修改")
    return target


def _scorecard_payload(scorecard: ReportScorecard | None) -> dict[str, Any] | None:
    if scorecard is None:
        return None
    return {
        "nav_original_filename": scorecard.nav_original_filename,
        "nav_sheet_name": scorecard.nav_sheet_name,
        "nav_columns": deepcopy(scorecard.nav_columns or []),
        "detected_columns": deepcopy(scorecard.detected_columns or {}),
        "nav_preview": deepcopy(scorecard.nav_preview or []),
        "calculation_inputs": deepcopy(scorecard.calculation_inputs or {}),
        "metrics": deepcopy(scorecard.metrics or {}),
        "score_rows": deepcopy(scorecard.score_rows or []),
        "quantitative_score": scorecard.quantitative_score,
        "qualitative_score": scorecard.qualitative_score,
        "compliance_deduction": scorecard.compliance_deduction,
        "total_score": scorecard.total_score,
        "admitted": scorecard.admitted,
        "calculated_at": (
            scorecard.calculated_at.isoformat() if scorecard.calculated_at else None
        ),
    }


def _next_version_number(report_id: int, db: Session) -> int:
    latest = db.scalar(
        select(func.max(ReportVersion.version_number)).where(
            ReportVersion.report_id == report_id
        )
    )
    return int(latest or 0) + 1


def create_report_version(
    report: DueDiligenceReport,
    manager: Manager,
    product: Product,
    scorecard: ReportScorecard | None,
    submitted_at: datetime,
    db: Session,
) -> tuple[ReportVersion, Path]:
    version_number = _next_version_number(report.id, db)
    version_root = storage.VERSION_STORAGE_DIR / f"report-{report.id}"
    storage_key = uuid4().hex[:12]
    final_dir = version_root / f"version-{version_number}-{storage_key}"
    temporary_dir = version_root / f".version-{version_number}-{storage_key}.tmp"
    temporary_dir.mkdir(parents=True, exist_ok=False)

    report_snapshot = {
        "title": report.title,
        "manager_id": report.manager_id,
        "manager_name": manager.name,
        "product_id": report.product_id,
        "product_name": product.name,
        "template_type": report.template_type.value,
        "content": deepcopy(report.content or {}),
        "conclusion": report.conclusion,
        "risk_items": deepcopy(report.risk_items or []),
        "generated_filename": report.generated_filename,
    }
    scorecard_data = _scorecard_payload(scorecard)
    file_manifest: dict[str, Any] = {"images": {}}

    try:
        for field, value in (report.content or {}).items():
            if not isinstance(value, dict) or not value.get("path"):
                continue
            source = Path(str(value["path"])).expanduser().resolve()
            upload_root = storage.UPLOAD_DIR.resolve()
            if not source.is_relative_to(upload_root) or not source.is_file():
                continue
            image_dir = temporary_dir / "images"
            image_dir.mkdir(exist_ok=True)
            target = image_dir / f"{field}{source.suffix.lower()}"
            shutil.copy2(source, target)
            final_target = final_dir / "images" / target.name
            file_manifest["images"][field] = {
                "path": _relative_version_path(final_target),
                "sha256": _file_hash(target),
                "original_filename": value.get("original_filename") or source.name,
            }

        if scorecard and scorecard.nav_stored_filename:
            source = (
                storage.NAV_UPLOAD_DIR
                / f"report-{report.id}"
                / Path(scorecard.nav_stored_filename).name
            ).resolve()
            nav_root = storage.NAV_UPLOAD_DIR.resolve()
            if source.is_relative_to(nav_root) and source.is_file():
                nav_dir = temporary_dir / "nav"
                nav_dir.mkdir(exist_ok=True)
                target = nav_dir / source.name
                shutil.copy2(source, target)
                final_target = final_dir / "nav" / target.name
                file_manifest["nav"] = {
                    "path": _relative_version_path(final_target),
                    "sha256": _file_hash(target),
                    "original_filename": scorecard.nav_original_filename or source.name,
                }

        final_dir.parent.mkdir(parents=True, exist_ok=True)
        temporary_dir.rename(final_dir)
    except Exception:
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir)
        raise

    hash_payload = {
        "report": report_snapshot,
        "scorecard": scorecard_data,
        "files": file_manifest,
    }
    version = ReportVersion(
        report_id=report.id,
        version_number=version_number,
        report_snapshot=report_snapshot,
        scorecard_snapshot=scorecard_data,
        file_manifest=file_manifest,
        snapshot_hash=_json_hash(hash_payload),
        submitted_at=submitted_at,
    )
    return version, final_dir


def remove_uncommitted_version_files(path: Path) -> None:
    root = storage.VERSION_STORAGE_DIR.resolve()
    target = path.resolve()
    if target.is_relative_to(root) and target.is_dir():
        shutil.rmtree(target)


def verify_version(version: ReportVersion) -> None:
    actual = _json_hash(
        {
            "report": version.report_snapshot,
            "scorecard": version.scorecard_snapshot,
            "files": version.file_manifest,
        }
    )
    if actual != version.snapshot_hash:
        raise ValueError("历史版本快照校验失败，数据可能已被修改")


def version_summary(version: ReportVersion) -> ReportVersionSummary:
    report = version.report_snapshot or {}
    scorecard = version.scorecard_snapshot or {}
    return ReportVersionSummary(
        id=version.id,
        report_id=version.report_id,
        version_number=version.version_number,
        title=str(report.get("title") or ""),
        template_type=ReportTemplateType(report["template_type"]),
        total_score=scorecard.get("total_score"),
        submitted_at=version.submitted_at,
        created_at=version.created_at,
        snapshot_hash=version.snapshot_hash,
    )


def _manifest_labels(template_type: str) -> dict[str, str]:
    payload = json.loads(
        MANIFEST_FILES[ReportTemplateType(template_type)].read_text(encoding="utf-8")
    )
    return {
        item["bookmark"]: item.get("prompt") or item["bookmark"]
        for item in payload["bookmarks"]
    }


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict) and ("original_filename" in value or "path" in value):
        return value.get("original_filename") or Path(str(value.get("path", ""))).name
    return value


def _comparison_payload(version: ReportVersion) -> dict[str, Any]:
    report = deepcopy(version.report_snapshot or {})
    content = {
        key: _normalize_value(value)
        for key, value in (report.get("content") or {}).items()
    }
    scorecard = version.scorecard_snapshot or {}
    return {
        "title": report.get("title"),
        "manager_name": report.get("manager_name"),
        "product_name": report.get("product_name"),
        "template_type": report.get("template_type"),
        "content": content,
        "conclusion": report.get("conclusion"),
        "risk_items": report.get("risk_items") or [],
        "scorecard": {
            key: deepcopy(scorecard.get(key))
            for key in (
                "calculation_inputs",
                "metrics",
                "quantitative_score",
                "qualitative_score",
                "compliance_deduction",
                "total_score",
                "admitted",
            )
            if scorecard.get(key) not in (None, {}, [])
        },
    }


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        flattened: dict[str, Any] = {}
        for key in sorted(value):
            path = f"{prefix}.{key}" if prefix else key
            flattened.update(_flatten(value[key], path))
        return flattened
    return {prefix: value}


def _field_label(path: str, labels: dict[str, str]) -> str:
    if path.startswith("content."):
        bookmark = path.split(".", 1)[1]
        return labels.get(bookmark, bookmark)
    if path.startswith("scorecard."):
        parts = path.split(".")
        root = parts[1]
        base = SCORECARD_LABELS.get(root, root)
        return base if len(parts) == 2 else f"{base}／{'／'.join(parts[2:])}"
    return REPORT_LABELS.get(path, path)


def compare_versions(
    report_id: int,
    before: ReportVersion,
    after: ReportVersion,
) -> ReportVersionComparison:
    verify_version(before)
    verify_version(after)
    before_flat = _flatten(_comparison_payload(before))
    after_flat = _flatten(_comparison_payload(after))
    template_type = str(
        (after.report_snapshot or {}).get("template_type")
        or (before.report_snapshot or {}).get("template_type")
    )
    labels = _manifest_labels(template_type)
    changes: list[VersionDiffItem] = []
    for path in sorted(set(before_flat) | set(after_flat)):
        old_value = before_flat.get(path)
        new_value = after_flat.get(path)
        if old_value == new_value:
            continue
        if path not in before_flat:
            change_type = "added"
        elif path not in after_flat:
            change_type = "removed"
        else:
            change_type = "changed"
        changes.append(
            VersionDiffItem(
                field_path=path,
                label=_field_label(path, labels),
                change_type=change_type,
                before=old_value,
                after=new_value,
            )
        )
    return ReportVersionComparison(
        report_id=report_id,
        from_version=before.version_number,
        to_version=after.version_number,
        change_count=len(changes),
        changes=changes,
    )


def restore_report_version(
    report: DueDiligenceReport,
    version: ReportVersion,
    scorecard: ReportScorecard | None,
    db: Session,
) -> list[Path]:
    verify_version(version)
    snapshot = deepcopy(version.report_snapshot or {})
    file_manifest = version.file_manifest or {}
    content = deepcopy(snapshot.get("content") or {})
    created_files: list[Path] = []

    try:
        for field, metadata in (file_manifest.get("images") or {}).items():
            source = _resolve_version_file(metadata["path"], metadata["sha256"])
            report_dir = storage.UPLOAD_DIR / f"report-{report.id}"
            report_dir.mkdir(parents=True, exist_ok=True)
            target = (
                report_dir
                / f"{field}-restored-v{version.version_number}-{uuid4().hex[:8]}{source.suffix.lower()}"
            )
            shutil.copy2(source, target)
            created_files.append(target)
            content[field] = {
                "path": str(target.resolve()),
                "original_filename": metadata.get("original_filename") or source.name,
            }

        scorecard_data = deepcopy(version.scorecard_snapshot)
        nav_stored_filename: str | None = None
        nav_metadata = file_manifest.get("nav")
        if scorecard_data is not None and nav_metadata:
            source = _resolve_version_file(nav_metadata["path"], nav_metadata["sha256"])
            report_dir = storage.NAV_UPLOAD_DIR / f"report-{report.id}"
            report_dir.mkdir(parents=True, exist_ok=True)
            nav_stored_filename = (
                f"nav-restored-v{version.version_number}-{uuid4().hex[:8]}{source.suffix.lower()}"
            )
            target = report_dir / nav_stored_filename
            shutil.copy2(source, target)
            created_files.append(target)

        report.title = str(snapshot["title"])
        report.manager_id = int(snapshot["manager_id"])
        report.product_id = int(snapshot["product_id"])
        report.template_type = ReportTemplateType(snapshot["template_type"])
        report.content = content
        report.conclusion = snapshot.get("conclusion")
        report.risk_items = list(snapshot.get("risk_items") or [])
        report.generated_filename = None
        report.status = ReportStatus.DRAFT
        report.submitted_at = None
        report.archived_at = None

        if scorecard_data is None:
            if scorecard is not None:
                db.delete(scorecard)
        else:
            if scorecard is None:
                scorecard = ReportScorecard(report_id=report.id)
                db.add(scorecard)
            scorecard.nav_original_filename = scorecard_data.get("nav_original_filename")
            scorecard.nav_stored_filename = nav_stored_filename
            scorecard.nav_sheet_name = scorecard_data.get("nav_sheet_name")
            scorecard.nav_columns = scorecard_data.get("nav_columns") or []
            scorecard.detected_columns = scorecard_data.get("detected_columns") or {}
            scorecard.nav_preview = scorecard_data.get("nav_preview") or []
            scorecard.calculation_inputs = scorecard_data.get("calculation_inputs") or {}
            scorecard.metrics = scorecard_data.get("metrics") or {}
            scorecard.score_rows = scorecard_data.get("score_rows") or []
            scorecard.quantitative_score = scorecard_data.get("quantitative_score")
            scorecard.qualitative_score = scorecard_data.get("qualitative_score")
            scorecard.compliance_deduction = scorecard_data.get("compliance_deduction")
            scorecard.total_score = scorecard_data.get("total_score")
            scorecard.admitted = scorecard_data.get("admitted")
            calculated_at = scorecard_data.get("calculated_at")
            scorecard.calculated_at = (
                datetime.fromisoformat(calculated_at) if calculated_at else None
            )
        return created_files
    except Exception:
        for path in created_files:
            path.unlink(missing_ok=True)
        raise
