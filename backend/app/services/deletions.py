from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models.deletion import DeletionRecord


def is_deleted(entity_type: str, entity_id: int, db: Session) -> bool:
    return db.scalar(
        select(DeletionRecord.id)
        .where(
            DeletionRecord.entity_type == entity_type,
            DeletionRecord.entity_id == entity_id,
        )
        .limit(1)
    ) is not None


def visible_entity(entity_type: str, entity_id_column):
    return ~exists().where(
        DeletionRecord.entity_type == entity_type,
        DeletionRecord.entity_id == entity_id_column,
    )


def add_deletion(
    *,
    entity_type: str,
    entity_id: int,
    display_name: str,
    reason: str,
    snapshot: dict,
    db: Session,
) -> DeletionRecord:
    record = DeletionRecord(
        entity_type=entity_type,
        entity_id=entity_id,
        display_name=display_name,
        reason=reason.strip(),
        snapshot=snapshot,
    )
    db.add(record)
    return record
