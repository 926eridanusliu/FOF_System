from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.manager import Manager
from app.models.product import Product
from app.models.report import DueDiligenceReport
from app.schemas.manager import ManagerCreate, ManagerRead, ManagerUpdate


router = APIRouter(prefix="/api/managers", tags=["Managers"])


def _get_manager(manager_id: int, db: Session) -> Manager:
    manager = db.get(Manager, manager_id)
    if manager is None:
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
    return list(db.scalars(select(Manager).offset(skip).limit(limit)))


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
def delete_manager(manager_id: int, db: Session = Depends(get_db)) -> Response:
    manager = _get_manager(manager_id, db)
    has_products = db.scalar(select(Product.id).where(Product.manager_id == manager_id).limit(1))
    has_reports = db.scalar(
        select(DueDiligenceReport.id)
        .where(DueDiligenceReport.manager_id == manager_id)
        .limit(1)
    )
    if has_products or has_reports:
        raise HTTPException(status_code=409, detail="管理人仍有关联产品或报告，不能删除")
    db.delete(manager)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
