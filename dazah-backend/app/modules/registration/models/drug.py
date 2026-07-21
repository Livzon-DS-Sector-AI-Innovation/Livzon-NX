"""Drug review progress ORM models."""

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import BaseModel


class Drug(BaseModel):
    """药品品种表"""

    __tablename__ = "drugs"
    __table_args__ = (
        CheckConstraint(
            "type IN ('仿制药', '创新药', '原料药')",
            name="ck_drugs_type",
        ),
        {"schema": "registration"},
    )

    name: Mapped[str] = mapped_column(
        String(255), comment="药品名称"
    )
    type: Mapped[str] = mapped_column(
        String(20), comment="药品类型：仿制药/创新药/原料药"
    )
    acceptance_date: Mapped[date] = mapped_column(
        Date, comment="受理日期"
    )
    current_node: Mapped[int] = mapped_column(
        Integer, default=0, comment="当前审评节点"
    )

    # 关系
    nodes: Mapped[list["DrugNode"]] = relationship(
        "DrugNode",
        back_populates="drug",
        cascade="all, delete-orphan",
    )


class DrugNode(BaseModel):
    """审评节点记录表"""

    __tablename__ = "drug_nodes"
    __table_args__ = (
        UniqueConstraint(
            "drug_id", "node_index", "is_deleted",
            name="uq_drug_nodes_drug_node",
        ),
        {"schema": "registration"},
    )

    drug_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("registration.drugs.id", ondelete="CASCADE"),
        comment="药品ID",
    )
    node_index: Mapped[int] = mapped_column(
        Integer, comment="节点序号（1-10）"
    )
    actual_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="实际完成日期"
    )

    # 关系
    drug: Mapped["Drug"] = relationship(
        "Drug",
        back_populates="nodes",
    )


class Holiday(BaseModel):
    """节假日表"""

    __tablename__ = "holidays"
    __table_args__ = (
        CheckConstraint(
            "type IN ('holiday', 'makeup')",
            name="ck_holidays_type",
        ),
        {"schema": "registration"},
    )

    year: Mapped[int] = mapped_column(
        Integer, comment="年份"
    )
    date: Mapped[date] = mapped_column(
        Date, comment="日期"
    )
    type: Mapped[str] = mapped_column(
        String(20), comment="类型：holiday(节假日)/makeup(补班日)"
    )
    description: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="描述"
    )
