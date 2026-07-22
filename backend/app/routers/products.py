from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.manager import Manager
from app.models.product import Product
from app.models.report import DueDiligenceReport
from app.schemas.product import ProductCreate, ProductRead, ProductUpdate


router = APIRouter(prefix="/api/products", tags=["Products"])


def _get_product(product_id: int, db: Session) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="产品不存在")
    return product


def _ensure_manager(manager_id: int, db: Session) -> None:
    if db.get(Manager, manager_id) is None:
        raise HTTPException(status_code=404, detail="管理人不存在")


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="该管理人下已存在同名产品") from exc


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)) -> Product:
    _ensure_manager(payload.manager_id, db)
    product = Product(**payload.model_dump())
    db.add(product)
    _commit(db)
    db.refresh(product)
    return product


@router.get("", response_model=list[ProductRead])
def list_products(
    manager_id: int | None = Query(default=None, gt=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[Product]:
    statement = select(Product)
    if manager_id is not None:
        statement = statement.where(Product.manager_id == manager_id)
    return list(db.scalars(statement.offset(skip).limit(limit)))


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, db: Session = Depends(get_db)) -> Product:
    return _get_product(product_id, db)


@router.put("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
) -> Product:
    product = _get_product(product_id, db)
    changes = payload.model_dump(exclude_unset=True)
    for field in ("manager_id", "name"):
        if field in changes and changes[field] is None:
            raise HTTPException(status_code=422, detail=f"{field} 不能为 null")
    if "manager_id" in changes:
        _ensure_manager(changes["manager_id"], db)
    for field, value in changes.items():
        setattr(product, field, value)
    _commit(db)
    db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, db: Session = Depends(get_db)) -> Response:
    product = _get_product(product_id, db)
    has_reports = db.scalar(
        select(DueDiligenceReport.id)
        .where(DueDiligenceReport.product_id == product_id)
        .limit(1)
    )
    if has_reports:
        raise HTTPException(status_code=409, detail="产品仍有关联报告，不能删除")
    db.delete(product)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
