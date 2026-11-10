"""应急预案 AI 资料汇总：危化品档案与 MSDS 原文、厂区建筑、车间库存、向导选项。

生成与审核时提供给模型的事实依据全部来自本模块数据：理化数值只能取自
MSDS 原文，人员只能取自用户在向导/工作台确认的组织机构。
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.modules.safety.models import (
    CampusBuilding,
    ChemicalInventory,
    ChemicalMsdsAttachment,
    EmergencyPlanContent,
    HazardousChemical,
)
from app.modules.safety.schemas.emergency_plan_ai import (
    EmergencyPlanAiOptions,
    EmergencyPlanDocument,
    EmergencyPlanGenerateRequest,
    OptionBuilding,
    OptionChemical,
    OptionValue,
    PlanOrganization,
    WorkshopOrganization,
)
from app.modules.safety.service.emergency_plan_template import (
    ACCIDENT_TYPE_LABELS,
    DEFAULT_COMPANY,
    LEVEL_LABELS,
    default_organization,
    default_workshop_organization,
)
from app.modules.safety.service.hazchem import read_msds_object
from app.modules.safety.service.msds_extract import CATEGORY_LABELS, extract_msds_text

logger = logging.getLogger(__name__)

MSDS_CHARS_PER_SUBSTANCE = 6000
_MSDS_TEXT_EXTS = {".pdf", ".doc", ".docx"}
_OPTION_LIMIT = 500


@dataclass
class SubstanceContext:
    name: str
    cas_no: str = ""
    category: str = ""
    hazard_statements: str = ""
    storage_requirements: str = ""
    remark: str = ""
    msds_text: str = ""
    inventories: list[str] = field(default_factory=list)


@dataclass
class PlanGenerationContext:
    substances: list[SubstanceContext]
    building_name: str = ""
    building_category: str = ""

    @property
    def substance_names(self) -> list[str]:
        return [item.name for item in self.substances]

    @property
    def msds_text(self) -> str:
        return "\n".join(item.msds_text for item in self.substances if item.msds_text)

    def facts_text(self) -> str:
        """给模型的事实资料（危化品档案 + 库存 + MSDS 原文）。"""
        parts: list[str] = []
        if self.building_name:
            parts.append(
                f"【事故场所】{self.building_name}（{self.building_category}）"
            )
        for item in self.substances:
            lines = [f"【物质】{item.name}"]
            if item.cas_no:
                lines.append(f"CAS 号：{item.cas_no}")
            if item.category:
                lines.append(f"危险性类别：{item.category}")
            if item.hazard_statements:
                lines.append(f"危险性概述：{item.hazard_statements}")
            if item.storage_requirements:
                lines.append(f"储存要求：{item.storage_requirements}")
            if item.inventories:
                lines.append("车间库存：" + "；".join(item.inventories))
            if item.msds_text:
                lines.append("MSDS 原文（数值只能取自此处）：\n" + item.msds_text)
            else:
                lines.append("MSDS 原文：未提供（理化数值不得自行编写）")
            parts.append("\n".join(lines))
        return "\n\n".join(parts) if parts else "（未关联危化品档案）"


async def _read_msds_text(storage_key: str, file_name: str) -> str:
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in _MSDS_TEXT_EXTS:
        return ""
    try:
        found = await asyncio.to_thread(read_msds_object, storage_key)
    except Exception:  # noqa: BLE001 — 存储层异常类型不一，MSDS 缺失时降级为无原文
        logger.warning("读取 MSDS 附件失败: key=%s", storage_key, exc_info=True)
        return ""
    if found is None:
        return ""
    content, _ = found
    text = await asyncio.to_thread(
        lambda: extract_msds_text(file_name=file_name, content=content)
    )
    return text[:MSDS_CHARS_PER_SUBSTANCE]


async def _load_chemicals(
    db: AsyncSession, params_ids: list[UUID], names: list[str]
) -> list[HazardousChemical]:
    conditions: list[ColumnElement[bool]] = [HazardousChemical.is_deleted.is_(False)]
    if params_ids and names:
        conditions.append(
            HazardousChemical.id.in_(params_ids) | HazardousChemical.name.in_(names)
        )
    elif params_ids:
        conditions.append(HazardousChemical.id.in_(params_ids))
    elif names:
        conditions.append(HazardousChemical.name.in_(names))
    else:
        return []
    rows = await db.execute(select(HazardousChemical).where(*conditions))
    return list(rows.scalars().all())


async def build_generation_context(
    db: AsyncSession,
    *,
    substances: list[tuple[UUID | None, str]],
    location: str,
) -> PlanGenerationContext:
    ids = [item_id for item_id, _ in substances if item_id]
    names = [name for _, name in substances if name]
    chemicals = await _load_chemicals(db, ids, names)
    by_id = {chemical.id: chemical for chemical in chemicals}
    by_name = {chemical.name: chemical for chemical in chemicals}

    attachments: dict[UUID, list[ChemicalMsdsAttachment]] = {}
    inventories: dict[UUID, list[str]] = {}
    if chemicals:
        chemical_ids = [chemical.id for chemical in chemicals]
        attachment_rows = await db.execute(
            select(ChemicalMsdsAttachment)
            .where(
                ChemicalMsdsAttachment.chemical_id.in_(chemical_ids),
                ChemicalMsdsAttachment.is_deleted.is_(False),
            )
            .order_by(ChemicalMsdsAttachment.created_at.desc())
        )
        for attachment in attachment_rows.scalars().all():
            attachments.setdefault(attachment.chemical_id, []).append(attachment)
        inventory_rows = await db.execute(
            select(ChemicalInventory).where(
                ChemicalInventory.chemical_id.in_(chemical_ids),
                ChemicalInventory.is_deleted.is_(False),
            )
        )
        for inventory in inventory_rows.scalars().all():
            limit = (
                f"（上限 {inventory.upper_limit:g}{inventory.unit}）"
                if inventory.upper_limit is not None
                else ""
            )
            inventories.setdefault(inventory.chemical_id, []).append(
                f"{inventory.workshop} {float(inventory.quantity):g}"
                f"{inventory.unit}{limit}"
            )

    result: list[SubstanceContext] = []
    for item_id, name in substances:
        chemical = by_id.get(item_id) if item_id else None
        chemical = chemical or by_name.get(name)
        if chemical is None:
            result.append(SubstanceContext(name=name))
            continue
        msds_text = ""
        for attachment in attachments.get(chemical.id, []):
            msds_text = await _read_msds_text(
                attachment.storage_key, attachment.file_name
            )
            if msds_text:
                break
        if not msds_text and chemical.msds_file_path:
            msds_text = await _read_msds_text(
                chemical.msds_file_path,
                chemical.msds_file_name or chemical.msds_file_path,
            )
        result.append(
            SubstanceContext(
                name=name or chemical.name,
                cas_no=chemical.cas_no,
                category=CATEGORY_LABELS.get(chemical.category, chemical.category),
                hazard_statements=chemical.hazard_statements,
                storage_requirements=chemical.storage_requirements,
                remark=chemical.remark,
                msds_text=msds_text,
                inventories=inventories.get(chemical.id, []),
            )
        )

    building = None
    if location.strip():
        building_rows = await db.execute(
            select(CampusBuilding).where(CampusBuilding.is_deleted.is_(False))
        )
        for candidate in building_rows.scalars().all():
            aliases = [str(alias) for alias in (candidate.aliases or [])]
            if location.strip() in (candidate.name, *aliases):
                building = candidate
                break
    return PlanGenerationContext(
        substances=result,
        building_name=building.name if building else location.strip(),
        building_category=building.category if building else "",
    )


async def context_for_params(
    db: AsyncSession, params: EmergencyPlanGenerateRequest
) -> PlanGenerationContext:
    return await build_generation_context(
        db,
        substances=[(item.chemical_id, item.name) for item in params.substances],
        location=params.location,
    )


async def context_for_document(
    db: AsyncSession,
    document: EmergencyPlanDocument,
    generation_params: dict[str, object] | None,
) -> PlanGenerationContext:
    """审核时的资料：优先用生成参数中的物质，导入的预案从标题推断。"""
    substances: list[tuple[UUID | None, str]] = []
    location = ""
    if generation_params:
        try:
            params = EmergencyPlanGenerateRequest.model_validate(generation_params)
        except ValidationError:
            params = None
        if params is not None:
            substances = [(item.chemical_id, item.name) for item in params.substances]
            location = params.location
    if not substances:
        rows = await db.execute(
            select(HazardousChemical.name).where(
                HazardousChemical.is_deleted.is_(False)
            )
        )
        haystack = document.cover.title + "".join(
            chapter.title for chapter in document.chapters
        )
        substances = [
            (None, name) for name in rows.scalars().all() if name and name in haystack
        ]
    return await build_generation_context(db, substances=substances, location=location)


async def load_options(db: AsyncSession) -> EmergencyPlanAiOptions:
    chemical_rows = await db.execute(
        select(HazardousChemical)
        .where(HazardousChemical.is_deleted.is_(False))
        .order_by(HazardousChemical.name.asc())
        .limit(_OPTION_LIMIT)
    )
    chemicals = list(chemical_rows.scalars().all())
    with_attachments: set[UUID] = set()
    if chemicals:
        attachment_rows = await db.execute(
            select(ChemicalMsdsAttachment.chemical_id).where(
                ChemicalMsdsAttachment.chemical_id.in_([c.id for c in chemicals]),
                ChemicalMsdsAttachment.is_deleted.is_(False),
            )
        )
        with_attachments = set(attachment_rows.scalars().all())
    building_rows = await db.execute(
        select(CampusBuilding)
        .where(CampusBuilding.is_deleted.is_(False))
        .order_by(CampusBuilding.sort_order.asc(), CampusBuilding.name.asc())
        .limit(_OPTION_LIMIT)
    )
    recent_org, recent_workshop = await _recent_organizations(db)
    return EmergencyPlanAiOptions(
        chemicals=[
            OptionChemical(
                id=chemical.id,
                name=chemical.name,
                cas_no=chemical.cas_no,
                category=CATEGORY_LABELS.get(chemical.category, chemical.category),
                has_msds=chemical.id in with_attachments
                or bool(chemical.msds_file_path),
            )
            for chemical in chemicals
        ],
        buildings=[
            OptionBuilding(code=item.code, name=item.name, category=item.category)
            for item in building_rows.scalars().all()
        ],
        accident_types=[
            OptionValue(value=key, label=label)
            for key, label in ACCIDENT_TYPE_LABELS.items()
        ],
        levels=[
            OptionValue(value=key, label=label) for key, label in LEVEL_LABELS.items()
        ],
        default_company=DEFAULT_COMPANY,
        default_organization=default_organization("company"),
        default_workshop_organization=default_workshop_organization(),
        recent_organization=recent_org,
        recent_workshop_organization=recent_workshop,
    )


async def _recent_organizations(
    db: AsyncSession,
) -> tuple[PlanOrganization | None, WorkshopOrganization | None]:
    """最近一份公司级预案的组织机构与最近填写的车间应急组（供向导预填）。"""
    rows = await db.execute(
        select(EmergencyPlanContent.content)
        .where(
            EmergencyPlanContent.is_deleted.is_(False),
            EmergencyPlanContent.content.is_not(None),
        )
        .order_by(EmergencyPlanContent.content_updated_at.desc().nulls_last())
        .limit(20)
    )
    organization: PlanOrganization | None = None
    workshop: WorkshopOrganization | None = None
    for raw in rows.scalars().all():
        try:
            document = EmergencyPlanDocument.model_validate(raw)
        except ValidationError:
            continue
        if (
            organization is None
            and document.cover.level == LEVEL_LABELS["company"]
            and document.organization.commander.strip()
        ):
            organization = document.organization
        if (
            workshop is None
            and document.workshop_organization
            and document.workshop_organization.commander.strip()
        ):
            workshop = document.workshop_organization
        if organization and workshop:
            break
    return organization, workshop
