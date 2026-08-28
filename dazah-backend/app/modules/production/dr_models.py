"""DR 多拉菌素 — 发酵/萃取 ORM 模型（批次→罐→萃取→滤液 四级嵌套）"""

from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import BaseModel


class DrFermentationBatch(BaseModel):
    """DR 发酵批次主表"""

    __tablename__ = "dr_fermentation_batches"
    __table_args__ = (
        Index("ix_drfb_batch_no", "batch_no"),
        Index("ix_drfb_workshop", "workshop"),
        {"schema": "production"},
    )

    batch_no: Mapped[str] = mapped_column(String(128), nullable=False, comment="批号")
    workshop: Mapped[str] = mapped_column(
        String(32), nullable=False, default="201-3", comment="车间"
    )
    tank_date: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="接罐日期"
    )

    # ── 杂质检测结果 ──
    impurity_6: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质6"
    )
    impurity_1: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质1"
    )
    impurity_2: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质2"
    )
    impurity_7: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质7"
    )
    impurity_3: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质3"
    )
    impurity_4: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质4"
    )
    impurity_5: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质5"
    )
    rrt_068: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="RRT0.68"
    )
    unknown_max_single: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="未知最大单杂"
    )
    total_impurities: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="总杂"
    )
    purity: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="纯度(%)"
    )

    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class DrFermentationTank(BaseModel):
    """DR 发酵罐 — 每批可接多个罐"""

    __tablename__ = "dr_fermentation_tanks"
    __table_args__ = (
        Index("ix_drft_batch_id", "fermentation_batch_id"),
        Index("ix_drft_tank_no", "tank_no"),
        {"schema": "production"},
    )

    fermentation_batch_id: Mapped[str] = mapped_column(
        String(36), nullable=False, comment="关联发酵批次ID"
    )
    tank_no: Mapped[str] = mapped_column(String(64), nullable=False, comment="罐号")
    handover_unit: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="交接单位(mg/l)"
    )
    handover_volume: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="交接体积(m³)"
    )
    fermentation_product_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="产品量(kg)"
    )
    actual_product_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="实际产品量"
    )
    handover_product_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="交接产品量"
    )
    bacteria_residue_plates: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="菌渣盘数"
    )

    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class DrExtraction(BaseModel):
    """DR 萃取批次 — 每罐可对应多个萃取批次"""

    __tablename__ = "dr_extractions"
    __table_args__ = (
        Index("ix_dre_tank_id", "fermentation_tank_id"),
        Index("ix_dre_batch_no", "extraction_batch_no"),
        {"schema": "production"},
    )

    fermentation_tank_id: Mapped[str] = mapped_column(
        String(36), nullable=False, comment="关联发酵罐ID"
    )
    feeding_time: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="投料时间"
    )
    extraction_batch_no: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="萃取批号"
    )
    feeding_plates: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="投料盘数"
    )
    extraction_product_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="产品量(萃取)"
    )
    total_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="合计"
    )
    fermentation_liquid_yield: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="萃取液对应发酵液收率(%)"
    )
    single_batch_yield: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="单批萃取收率(%)"
    )

    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


class DrFiltrate(BaseModel):
    """DR 滤液罐 — 每萃取批次可对应多个滤液罐"""

    __tablename__ = "dr_filtrates"
    __table_args__ = (
        Index("ix_drf_extraction_id", "extraction_id"),
        {"schema": "production"},
    )

    extraction_id: Mapped[str] = mapped_column(
        String(36), nullable=False, comment="关联萃取批次ID"
    )
    tank_no: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="滤液罐号"
    )
    volume: Mapped[float | None] = mapped_column(Float, nullable=True, comment="体积")
    potency: Mapped[float | None] = mapped_column(Float, nullable=True, comment="效价")
    product_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="产品量"
    )
    dilute_wash_volume: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="稀释洗涤体积"
    )
    dilute_wash_potency: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="稀释洗涤效价"
    )
    dilute_wash_product_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="稀释洗涤产品量"
    )

    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


# ── DR 层析及一次结晶 ──────────────────────────────────────


class DrChromatographyCrystal(BaseModel):
    """DR 层析及一次结晶岗位台账（扁平表）"""

    __tablename__ = "dr_chromatography_crystal"
    __table_args__ = (
        Index("ix_drcc_batch_no", "chromatography_batch_no"),
        Index("ix_drcc_fl_batch", "fl_batch_no"),
        {"schema": "production"},
    )

    row_no: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="飞书行号(用于还原表格原始顺序)"
    )

    fl_batch_no: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="发酵液批号"
    )
    production_date: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="生产日期"
    )
    chromatography_batch_no: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="层析生产批号"
    )
    column_no: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="柱号"
    )
    extraction_batch_no: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="萃取批号"
    )

    volume_kl: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="体积(KL)"
    )
    potency_mg_l: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="效价(mg/L)"
    )
    product_qty_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="产品量(kg)"
    )
    total_product_qty_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="累计产品量(kg)"
    )

    column_load_vol_kl: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="上柱液体积(KL)"
    )
    column_load_potency_mg_l: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="上柱液效价(mg/L)"
    )
    column_load_product_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="上柱液产品量(kg)"
    )
    column_load_total_product_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="上柱液累计产品量(kg)"
    )

    elution_volume: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="合格洗脱液体积"
    )
    elution_unit: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="合格洗脱液单位"
    )
    elution_product_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="合格洗脱液产品量(kg)"
    )

    chromatography_yield: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="层析收率"
    )

    wet_powder_batch_no: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="一次湿粉生产批号"
    )
    wet_powder_weight_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="一次湿粉重量(kg)"
    )
    wet_powder_content: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="一次湿粉含量"
    )
    wet_powder_dry_loss: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="一次湿粉干燥失重"
    )
    wet_powder_pure_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="一次湿粉折纯(kg)"
    )

    crystallization_yield: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="结晶收率"
    )

    mother_liquor_volume: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="母液体积"
    )
    mother_liquor_content: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="母液含量"
    )
    mother_liquor_product_qty: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="母液产品量"
    )

    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


# ── DR 一次精制 ──────────────────────────────────────


class DrFirstRefinement(BaseModel):
    """DR 一次精制岗位台账（扁平表）"""

    __tablename__ = "dr_first_refinement"
    __table_args__ = (
        Index("ix_drfr_refine_batch", "refinement_batch_no"),
        Index("ix_drfr_fl_batch", "fl_batch_no"),
        {"schema": "production"},
    )

    row_no: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="飞书行号(用于还原表格原始顺序)"
    )

    fl_batch_no: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="发酵液批号"
    )
    production_date: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="生产日期"
    )
    refinement_batch_no: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="生产批号"
    )

    # ── 一次湿粉投料 ──
    feed_weight_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="投料重量(kg)"
    )
    feed_content: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="投料含量"
    )
    feed_dry_loss: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="投料干燥失重"
    )
    feed_pure_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="投料折纯(kg)"
    )

    # ── 母液 ──
    mother_liquor_volume: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="母液体积"
    )
    mother_liquor_unit: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="母液单位"
    )
    mother_liquor_product_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="母液产品量(kg)"
    )

    # ── 一次湿粉成品方法杂质 ──
    impurity_6: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质6 RRT=0.51"
    )
    impurity_1: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质1 RRT=0.59"
    )
    impurity_2: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质2 RRT=0.69"
    )
    impurity_7: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质7 RRT=0.72"
    )
    impurity_3: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质3 RRT=0.88"
    )
    impurity_4: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质4 RRT=1.38"
    )
    impurity_5: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质5 RRT=1.56"
    )
    rrt_068: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="RRT=0.68"
    )
    unknown_max_single: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="未知最大单杂"
    )
    total_impurities: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="总杂"
    )
    purity: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="纯度(%)"
    )

    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


# ── DR 二次精制 ──────────────────────────────────────


class DrSecondRefinement(BaseModel):
    """DR 二次精制岗位台账（扁平表）"""

    __tablename__ = "dr_second_refinement"
    __table_args__ = (
        Index("ix_drsr_refine_batch", "refinement_batch_no"),
        Index("ix_drsr_fl_batch", "fl_batch_no"),
        {"schema": "production"},
    )

    row_no: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="飞书行号(用于还原表格原始顺序)"
    )

    fl_batch_no: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="发酵液批号"
    )
    production_date: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="生产日期"
    )
    refinement_batch_no: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="生产批号"
    )

    # ── 一次湿粉投料 ──
    feed_batch_no: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="投料批次"
    )
    feed_weight_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="投料重量(kg)"
    )
    feed_pure_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="投料折纯(kg)"
    )

    # ── 二次湿粉 ──
    product_weight_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="二次湿粉重量(kg)"
    )
    product_content: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="二次湿粉含量"
    )
    product_dry_loss: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="二次湿粉干燥失重"
    )
    product_pure_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="二次湿粉折纯(kg)"
    )
    batch_yield: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="批收率"
    )

    # ── 复离粉 ──
    recovery_powder_weight_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="复离粉重量(kg)"
    )
    recovery_powder_pure_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="复离粉折纯(kg)"
    )

    # ── 母液 ──
    mother_liquor_unit: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="母液单位"
    )
    mother_liquor_volume: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="母液体积"
    )
    mother_liquor_product_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="母液产品量(kg)"
    )

    # ── 二次湿粉成品方法杂质 ──
    impurity_6: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质6"
    )
    impurity_1: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质1"
    )
    impurity_2: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质2"
    )
    impurity_7: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质7"
    )
    impurity_3: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质3"
    )
    impurity_4: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质4"
    )
    impurity_5: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质5"
    )
    rrt_068: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="RRT=0.68"
    )
    unknown_max_single: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="未知最大单杂"
    )
    total_impurities: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="总杂"
    )
    purity: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="纯度(%)"
    )

    remarks: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")


# ── DR 三次精制 ──────────────────────────────────────


class DrThirdRefinement(BaseModel):
    """DR 三次精制岗位台账（扁平表）"""

    __tablename__ = "dr_third_refinement"
    __table_args__ = (
        Index("ix_drtr_refine_batch", "refinement_batch_no"),
        Index("ix_drtr_fl_batch", "fl_batch_no"),
        {"schema": "production"},
    )

    row_no: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="飞书行号(用于还原表格原始顺序)"
    )

    fl_batch_no: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="发酵液批号"
    )
    production_date: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="生产日期"
    )
    refinement_batch_no: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="生产批号"
    )

    # ── 二次精制投料 ──
    feed_batch_no: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="投入批次"
    )
    feed_weight_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="投料重量(kg)"
    )
    feed_pure_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="投料折纯(kg)"
    )

    # ── 三次湿粉 ──
    activated_carbon: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="活性炭加量"
    )
    product_weight_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="三次湿粉重量(kg)"
    )
    product_pure_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="三次湿粉折纯(kg)"
    )
    yield_rate: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="收率"
    )

    # ── 母液 ──
    mother_liquor_volume: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="母液体积"
    )
    mother_liquor_unit: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="母液单位"
    )
    mother_liquor_product_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="母液产品量(kg)"
    )

    # ── 三次湿粉成品方法杂质 ──
    impurity_6: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质6"
    )
    impurity_1: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质1"
    )
    impurity_2: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质2"
    )
    impurity_7: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质7"
    )
    impurity_3: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质3"
    )
    impurity_4: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质4"
    )
    impurity_5: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质5"
    )
    rrt_068: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="RRT=0.68"
    )
    rrt_083: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="RRT=0.83"
    )
    unknown_max_single: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="未知最大单杂"
    )
    total_impurities: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="总杂"
    )
    purity: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="纯度(%)"
    )


# ── DR 四次精制 ──────────────────────────────────────


class DrFourthRefinement(BaseModel):
    """DR 四次精制岗位台账（扁平表）"""

    __tablename__ = "dr_fourth_refinement"
    __table_args__ = (
        Index("ix_drfr4_refine_batch", "refinement_batch_no"),
        Index("ix_drfr4_fl_batch", "fl_batch_no"),
        {"schema": "production"},
    )

    row_no: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="飞书行号(用于还原表格原始顺序)"
    )

    fl_batch_no: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="发酵液批号"
    )
    production_date: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="生产日期"
    )
    refinement_batch_no: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="生产批号"
    )

    # ── 三次精制投料 ──
    feed_batch_no: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="投入批次"
    )
    feed_weight_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="投料重量(kg)"
    )
    feed_pure_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="投料折纯(kg)"
    )

    # ── 四次湿粉 ──
    product_weight_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="四次湿粉重量(kg)"
    )
    product_content: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="四次湿粉含量"
    )
    product_dry_loss: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="四次湿粉干燥失重"
    )
    product_pure_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="四次湿粉折纯(kg)"
    )

    # ── 四次干粉 ──
    dry_weight_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="四次干粉重量(kg)"
    )
    yield_rate: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="收率"
    )

    # ── 四次干粉成品方法杂质 ──
    impurity_6: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质6"
    )
    impurity_1: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质1"
    )
    impurity_2: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质2"
    )
    impurity_7: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质7"
    )
    impurity_3: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质3"
    )
    impurity_4: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质4"
    )
    impurity_5: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="杂质5"
    )
    rrt_083: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="RRT=0.83"
    )
    rrt_055: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="RRT=0.55"
    )
    rrt_068: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="RRT=0.68"
    )
    unknown_max_single: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="未知最大单杂"
    )
    total_impurities: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="总杂"
    )
    purity: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="纯度(%)"
    )
