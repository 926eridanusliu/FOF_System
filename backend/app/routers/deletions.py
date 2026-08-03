from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.deletion import DeletionRecord
from app.models.manager import Manager
from app.models.report import DueDiligenceReport
from app.schemas.deletion import DeletionRecordRead


router = APIRouter(prefix="/api/deletions", tags=["Deletion audit"])


@router.get("", response_model=list[DeletionRecordRead])
def list_deletions(
    entity_type: str | None = Query(default=None, pattern="^(manager|report)$"),
    db: Session = Depends(get_db),
) -> list[DeletionRecord]:
    statement = select(DeletionRecord).order_by(DeletionRecord.id.desc())
    if entity_type:
        statement = statement.where(DeletionRecord.entity_type == entity_type)
    return list(db.scalars(statement))


@router.post("/{record_id}/restore", response_model=DeletionRecordRead)
def restore_deletion(record_id: int, db: Session = Depends(get_db)) -> DeletionRecord:
    record = db.get(DeletionRecord, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="删除记录不存在")
    entity = (
        db.get(Manager, record.entity_id)
        if record.entity_type == "manager"
        else db.get(DueDiligenceReport, record.entity_id)
    )
    if entity is None:
        raise HTTPException(status_code=409, detail="原始数据已经被物理清除，无法恢复")
    restored = DeletionRecord(
        id=record.id,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        display_name=record.display_name,
        reason=record.reason,
        snapshot=record.snapshot,
        deleted_at=record.deleted_at,
    )
    db.delete(record)
    db.commit()
    return restored
