"""FA 苯丙氨酸 — 数据模型"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import Base


class FaFermentationBatch(Base):
    """发酵液放罐 — 主批表（每个罐号一条记录）"""

    __tablename__ = "fa_fermentation_batches"
    __table_args__ = (
        Index("ix_fafb_date", "放罐日期"),
        {"schema": "production"},
    )

    发酵罐号: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="罐号，如 FA-EX25315"
    )
    放罐日期: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="放罐日期"
    )
    放罐体积_kl: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="主批体积(kl)，后期格式才有"
    )
    放罐含量_gL: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="主批含量(g/L)，后期格式才有"
    )
    主批自身总量_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="主批自身批总量(kg)=体积×含量，后期格式才有"
    )
    汇总总量_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="C+D 汇总总重(kg)"
    )
    电导_uscm: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="电导率(us/cm)"
    )
    调酸量_L: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="调酸量(L)"
    )
    酸化液滤速_ml10min: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="酸化液滤速(ml/10min)"
    )
    发酵液湿固: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="发酵液湿固百分比"
    )
    产量: Mapped[float | None] = mapped_column(Float, nullable=True, comment="产量(kg)")
    收率: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="收率")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )


class FaFermentationSubBatch(Base):
    """发酵液放罐 — 子批表（每个罐号的C/D子批明细）"""

    __tablename__ = "fa_fermentation_sub_batches"
    __table_args__ = (
        UniqueConstraint("父发酵罐号", "子批后缀", name="uq_fafsb_parent_suffix"),
        Index("ix_fafsb_parent", "父发酵罐号"),
        {"schema": "production"},
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: __import__("uuid").uuid4().hex
    )
    发酵批号: Mapped[str] = mapped_column(
        String(128), comment="完整批号，如 FA-EX25315C"
    )
    父发酵罐号: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("production.fa_fermentation_batches.发酵罐号"),
        comment="所属主批罐号",
    )
    子批后缀: Mapped[str] = mapped_column(String(4), comment="C 或 D")
    放罐体积_kl: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="单罐体积(kl)"
    )
    放罐含量_gL: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="单罐含量(g/L)"
    )
    批总量_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="批总量(kg)=体积×含量"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )


class FaAcidificationRecord(Base):
    """FA 酸化过滤 — 单表（31列）"""

    __tablename__ = "fa_acidification_records"
    __table_args__ = (
        Index("ix_fa_acid_date", "日期"),
        Index("ix_fa_acid_batch", "批号"),
        {"schema": "production"},
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: __import__("uuid").uuid4().hex
    )
    日期: Mapped[date | None] = mapped_column(Date, nullable=True)
    批号: Mapped[str | None] = mapped_column(String(64), nullable=True)
    发酵液体积_kl: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="发酵液体积（kl)"
    )
    发酵液含量_gL: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="发酵液含量（g/L）"
    )
    发酵液罐产_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="发酵液罐产（kg）"
    )
    用酸量: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="用酸量（95-98%浓硫酸）"
    )
    PH酸化后: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="PH（酸化后）"
    )
    酸化液体积_kl: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="酸化液体积（kl)"
    )
    理论酸化液含量_gL: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="理论酸化液含量（g/L）"
    )
    PH: Mapped[float | None] = mapped_column(Float, nullable=True, name="PH")
    膜滤液体积_KL: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="膜滤液体积（KL）"
    )
    膜滤液含量_gL: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="膜滤液含量（g/L）"
    )
    膜滤液产品量_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="膜滤液产品量（kg）"
    )
    膜滤液产品总量_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="膜滤液产品总量（kg）"
    )
    本批低单位含量_gL: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="本批低单位含量（g/L）"
    )
    本批低单位体积_KL: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="本批低单位体积（KL）"
    )
    本批低单位苯产品_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="本批低单位苯产品（kg）"
    )
    本批低单位量_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="本批低单位量（kg）"
    )
    上批套用低单位量_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="上批套用低单位量（kg）"
    )
    批收率: Mapped[str | None] = mapped_column(String(32), nullable=True)
    顶洗前体积_kl: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="顶洗前体积（kl）"
    )
    尾液含量_gL: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="尾液含量（g/L）"
    )
    渣含量_gL: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="渣含量（g/L）"
    )
    体积_罐渣膜渣_kl: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="体积（罐渣+膜渣（kl）"
    )
    渣产品量_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="渣产品量（kg）"
    )
    渣损失率: Mapped[str | None] = mapped_column(
        String(32), nullable=True, name="渣损失率（渣苯丙量/罐产）"
    )
    渣体积_发酵液体积: Mapped[str | None] = mapped_column(
        String(32), nullable=True, name="渣体积/发酵液体积"
    )
    酸化液_发酵液体积: Mapped[str | None] = mapped_column(
        String(32), nullable=True, name="酸化液/发酵液体积"
    )
    滤液体积_发酵液体积: Mapped[str | None] = mapped_column(
        String(32), nullable=True, name="滤液体积/发酵液体积"
    )
    平衡率: Mapped[str | None] = mapped_column(String(32), nullable=True)
    消泡剂使用量_L: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="消泡剂使用量（L）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FaDecolor1Record(Base):
    """FA 一次脱色过滤"""

    __tablename__ = "fa_decolor1_records"
    __table_args__ = ({"schema": "production"},)
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    日期: Mapped[date | None] = mapped_column(Date, nullable=True)
    批号: Mapped[str | None] = mapped_column(String(64), nullable=True)
    体积_kl: Mapped[float | None] = mapped_column(Float, nullable=True, name="体积(kl)")
    含量_gL: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="含量(g/L)"
    )
    电导_uscm: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="电导(us/cm)"
    )
    调前电导碳柱: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="调前电导碳柱(us/cm)"
    )
    混合含量_gL: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="混合含量(g/L)"
    )
    母液体积_kl: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="母液体积(kl)"
    )
    母液含量_gL: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="母液含量(g/L)"
    )
    电导2: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="电导(us/cm)2"
    )
    活性炭添加量_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="活性炭添加量(kg)"
    )
    碳后含量_gL: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="碳后含量(g/L)"
    )
    湿碳_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="湿重(kg）"
    )
    收率: Mapped[str | None] = mapped_column(String(32), nullable=True)
    产品量_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="产品量(kg)"
    )
    滤损失率: Mapped[str | None] = mapped_column(String(32), nullable=True)
    备注: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FaMvrRecord(Base):
    """FA MVR浓缩"""

    __tablename__ = "fa_mvr_records"
    __table_args__ = ({"schema": "production"},)
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    日期: Mapped[date | None] = mapped_column(Date, nullable=True)
    白班进料: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="白班进料/m3"
    )
    白班出料: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="白班出料/m3"
    )
    白班进料合计: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="白班进料合计/m3"
    )
    白班进料累计合计: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="白班进料累计合计/m3"
    )
    夜班进料: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="夜班进料/m3"
    )
    夜班出料: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="夜班出料/m3"
    )
    夜班进料合计: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="夜班进料合计/m3"
    )
    夜班进料累计合计: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="夜班进料累计合计/m3"
    )
    备注: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FaMotherLiquorRecord(Base):
    """FA 母液溶粉"""

    __tablename__ = "fa_mother_liquor_records"
    __table_args__ = ({"schema": "production"},)
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    日期: Mapped[date | None] = mapped_column(Date, nullable=True)
    批号: Mapped[str | None] = mapped_column(String(64), nullable=True)
    母液打料量: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="母液打料量(m3)"
    )
    溶解体积: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="溶解体积(m3)"
    )
    溶解含量: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="溶解含量(g/L)"
    )
    电导: Mapped[float | None] = mapped_column(Float, nullable=True, name="电导(ms/cm)")
    ph: Mapped[float | None] = mapped_column(Float, nullable=True, name="ph")
    备注: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FaPlateRecoveryRecord(Base):
    """FA 板框回收"""

    __tablename__ = "fa_plate_recovery_records"
    __table_args__ = ({"schema": "production"},)
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    日期: Mapped[date | None] = mapped_column(Date, nullable=True)
    白班板框进料量: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="白班板框进料量/方"
    )
    白班板框拆卸回收粉包数: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="白班板框拆卸回收粉包数"
    )
    白班分液罐投回收粉包数: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="白班分液罐投回收粉包数/包"
    )
    白班分液罐体积: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="白班分液罐体积/方"
    )
    复滤粉拆包数: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="复滤粉拆包数"
    )
    夜班板框进料量: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="夜班板框进料量/方"
    )
    夜班板框拆卸回收粉包数: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="夜班板框拆卸回收粉包数"
    )
    夜班分液罐投回收粉包数: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="夜班分液罐投回收粉包数/包"
    )
    夜班分液罐体积: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="夜班分液罐体积/方"
    )
    复滤粉拆包数夜: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="复滤粉拆包数(夜)"
    )
    白班装车体积: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="白班装车体积"
    )
    废液槽接收体积: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="废液槽接收体积"
    )
    总进料体积: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="总进料体积（m3/天）"
    )
    累计进料体积: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="累计进料体积m3"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FaDecolorCentrifugeRecord(Base):
    """FA 脱色离心 — 17列"""

    __tablename__ = "fa_decolor_centrifuge_records"
    __table_args__ = ({"schema": "production"},)
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    日期: Mapped[date | None] = mapped_column(Date, nullable=True)
    批号: Mapped[str | None] = mapped_column(String(64), nullable=True)
    体积_kl: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="体积（kl）"
    )
    含量_gL: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="含量（g/L）"
    )
    电导_uscm: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="电导（us/cm)"
    )
    掺后电导碳脱: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="掺后电导碳脱（us/cm)"
    )
    混合含量: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="混合含量(g/L）"
    )
    体积_kl2: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="体积（kl）2"
    )
    含量_gL2: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="含量（g/L）2"
    )
    电导_uscm2: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="电导（us/cm)2"
    )
    活性炭用量: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="活性炭用量（kg)"
    )
    炭后含量: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="炭后含量(g/L）"
    )
    湿重_kg: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="湿重(kg）"
    )
    含量: Mapped[float | None] = mapped_column(Float, nullable=True, name="含量")
    产品量: Mapped[float | None] = mapped_column(
        Float, nullable=True, name="产品量(kg）"
    )
    损失收率: Mapped[str | None] = mapped_column(String(32), nullable=True)
    备注: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
