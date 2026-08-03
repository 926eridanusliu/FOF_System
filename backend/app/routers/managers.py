from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.manager import Manager
from app.models.product import Product
from app.models.report import DueDiligenceReport
from app.schemas.deletion import DeletionRequest
from app.schemas.manager import ManagerCreate, ManagerRead, ManagerUpdate
from app.services.deletions import add_deletion, is_deleted, visible_entity


router = APIRouter(prefix="/api/managers", tags=["Managers"])


def _get_manager(manager_id: int, db: Session) -> Manager:
    manager = db.get(Manager, manager_id)
    if manager is None or is_deleted("manager", manager_id, db):
        raise HTTPException(status_code=404, detail="管理人不存在")
    return manager


def _commit(db: Session, duplicate_message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=duplicate_message) from exc


@router.post("", response_model=ManagerRead, status_code=status.HTTP_201_CREATED)
def create_manager(payload: ManagerCreate, db: Session = Depends(get_db)) -> Manager:
    manager = Manager(**payload.model_dump())
    db.add(manager)
    _commit(db, "管理人名称或统一社会信用代码已存在")
    db.refresh(manager)
    return manager


@router.get("", response_model=list[ManagerRead])
def list_managers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[Manager]:
    return list(
        db.scalars(
            select(Manager)
            .where(visible_entity("manager", Manager.id))
            .offset(skip)
            .limit(limit)
        )
    )


@router.get("/{manager_id}", response_model=ManagerRead)
def get_manager(manager_id: int, db: Session = Depends(get_db)) -> Manager:
    return _get_manager(manager_id, db)


@router.put("/{manager_id}", response_model=ManagerRead)
def update_manager(
    manager_id: int,
    payload: ManagerUpdate,
    db: Session = Depends(get_db),
) -> Manager:
    manager = _get_manager(manager_id, db)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("name", "present") is None:
        raise HTTPException(status_code=422, detail="管理人名称不能为 null")
    for field, value in changes.items():
        setattr(manager, field, value)
    _commit(db, "管理人名称或统一社会信用代码已存在")
    db.refresh(manager)
    return manager


@router.delete("/{manager_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_manager(
    manager_id: int,
    payload: DeletionRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Response:
    manager = _get_manager(manager_id, db)
    products = list(db.scalars(select(Product).where(Product.manager_id == manager_id)))
    reports = list(
        db.scalars(
            select(DueDiligenceReport).where(
                DueDiligenceReport.manager_id == manager_id,
                visible_entity("report", DueDiligenceReport.id),
            )
        )
    )
    if (products or reports) and payload is None:
        raise HTTPException(status_code=409, detail="该管理人有关联产品或报告，删除时必须填写原因")
    reason = payload.reason if payload else "删除空管理人档案"
    add_deletion(
        entity_type="manager",
        entity_id=manager.id,
        display_name=manager.name,
        reason=reason,
        snapshot={
            "name": manager.name,
            "unified_social_credit_code": manager.unified_social_credit_code,
            "product_count": len(products),
            "report_count": len(reports),
            "product_names": [product.name for product in products],
            "report_titles": [report.title for report in reports],
        },
        db=db,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
