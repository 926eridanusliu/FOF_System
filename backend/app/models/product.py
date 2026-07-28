from __future__ import annotations

from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.manager import Manager
    from app.models.report import DueDiligenceReport, ReportProduct


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("manager_id", "name", name="uq_product_manager_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    manager_id: Mapped[int] = mapped_column(
        ForeignKey("managers.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    product_type: Mapped[str | None] = mapped_column(String(100))
    established_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    manager: Mapped[Manager] = relationship(back_populates="products")
    reports: Mapped[list[DueDiligenceReport]] = relationship(
        back_populates="product", passive_deletes=True
    )
    strategy_records: Mapped[list[ProductStrategy]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductStrategy.strategy_key",
    )
    report_links: Mapped[list[ReportProduct]] = relationship(
        back_populates="product", passive_deletes=True
    )

    @property
    def strategy_keys(self) -> list[str]:
        return [record.strategy_key for record in self.strategy_records]


class ProductStrategy(Base):
    __tablename__ = "product_strategies"

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    strategy_key: Mapped[str] = mapped_column(String(80), primary_key=True)

    product: Mapped[Product] = relationship(back_populates="strategy_records")
