"""Quality inspection ORM model."""

from datetime import date

from sqlalchemy import Date, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.quality.models.finished_product_inspection import (
    FinishedProductInspection as FinishedProductInspection,
)
from app.modules.quality.models.lab_instrument import LabInstrument as LabInstrument
from app.modules.quality.models.lab_item import LabItem as LabItem
from app.modules.quality.models.liquid_material_inspection import (
    LiquidMaterialInspection as LiquidMaterialInspection,
)
from app.modules.quality.models.solid_material_inspection import (
    SolidMaterialInspection as SolidMaterialInspection,
)
from app.shared.base_model import BaseModel


class InspectionRecord(BaseModel):
    """质量检验记录."""

    __tablename__ = "inspection_records"
    __table_args__ = {"schema": "quality"}

    inspection_no: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, comment="检验编号"
    )
    product_name: Mapped[str | None] = mapped_column(String(200), comment="产品名称")
    batch_no: Mapped[str | None] = mapped_column(String(100), comment="批号")
    inspection_type: Mapped[str | None] = mapped_column(
        String(50), comment="检验类型：来料检验/中间体检验/成品检验/留样检验"
    )
    inspection_item: Mapped[str | None] = mapped_column(String(500), comment="检验项目")
    specification: Mapped[str | None] = mapped_column(Text, comment="标准规定")
    test_result: Mapped[str | None] = mapped_column(Text, comment="检验结果")
    conclusion: Mapped[str | None] = mapped_column(
        String(20), comment="检验结论：合格/不合格"
    )
    inspector: Mapped[str | None] = mapped_column(String(100), comment="检验人")
    inspection_date: Mapped[date | None] = mapped_column(Date, comment="检验日期")
    department: Mapped[str | None] = mapped_column(String(100), comment="检验部门")
    remark: Mapped[str | None] = mapped_column(Text, comment="备注")


# The current platform imported all inspection resources from this module;
# the migrated implementation split them into dedicated model files. Re-export
# the split classes here so existing Agent/service imports remain valid without
# defining duplicate tables.
