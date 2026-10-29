"""目标责任与绩效：年度安全目标、责任书签订与责任制季度考核。"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException, NotFoundException
from app.modules.safety.models import (
    SafetyDutyAssessment,
    SafetyDutyAssessmentItem,
    SafetyTarget,
    SafetyTargetAgreement,
    SafetyTargetRecord,
)
from app.modules.safety.schemas.targets import (
    SafetyDutyAssessmentCreate,
    SafetyDutyAssessmentDepartmentStat,
    SafetyDutyAssessmentItemInput,
    SafetyDutyAssessmentQuarterStat,
    SafetyDutyAssessmentStatsResponse,
    SafetyDutyAssessmentUpdate,
    SafetyDutyTemplateItem,
    SafetyDutyTemplateResponse,
    SafetyTargetAgreementCreate,
    SafetyTargetAgreementDepartmentStat,
    SafetyTargetAgreementStatsResponse,
    SafetyTargetAgreementUpdate,
    SafetyTargetCreate,
    SafetyTargetDepartmentStat,
    SafetyTargetRecordCreate,
    SafetyTargetRecordUpdate,
    SafetyTargetStatsResponse,
    SafetyTargetUpdate,
)

_SEED_PATH = (
    Path(__file__).resolve().parents[1]
    / "seeds"
    / "target_responsibility_2026.json"
)

_CN_DIGITS = str.maketrans(
    "０１２３４５６７８９〇一二三四五六七八九", "01234567890123456789"
)


def build_search_text(
    title: str, category: str, owner_department: str, owner_name: str, metric: str
) -> str:
    return " ".join(
        part for part in (title, category, owner_department, owner_name, metric) if part
    )


def normalize_department_key(name: str) -> str:
    """部门匹配键：全半角/中文数字归一后仅保留字母数字与汉字。"""
    translated = name.strip().lower().translate(_CN_DIGITS)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", translated)


def grade_for_score(score: float) -> str:
    """责任制考核等级：>=95 优秀 / >=90 良好 / >=80 合格 / <80 不合格。"""
    if score >= 95:
        return "优秀"
    if score >= 90:
        return "良好"
    if score >= 80:
        return "合格"
    return "不合格"


@lru_cache(maxsize=1)
def _load_responsibility_seed() -> dict[str, Any]:
    """2026 责任书与责任制考核模板种子（来源：2026 安全目标责任书/考核表文档）。"""
    payload: dict[str, Any] = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    return payload


def find_assessment_template(department: str) -> SafetyDutyTemplateResponse:
    templates = _load_responsibility_seed().get("assessment_templates", [])
    key = normalize_department_key(department)
    best: tuple[int, dict[str, Any]] | None = None
    for tpl in templates:
        tpl_key = normalize_department_key(tpl.get("name", ""))
        if not tpl_key:
            continue
        if tpl_key == key:
            best = (len(tpl_key), tpl)
            break
        common = 0
        for a, b in zip(tpl_key, key):
            if a != b:
                break
            common += 1
        # 一方为另一方前缀（如 “安全部负责人”匹配“安全部”），按公共长度择优
        if common >= min(len(tpl_key), 2) and (
            tpl_key.startswith(key) or key.startswith(tpl_key)
        ):
            if best is None or common > best[0]:
                best = (common, tpl)
    if best is None:
        return SafetyDutyTemplateResponse(name=department, category="", matched=False)
    tpl = best[1]
    return SafetyDutyTemplateResponse(
        name=tpl.get("name", ""),
        category=tpl.get("category", ""),
        assessed=tpl.get("assessed", ""),
        items=[
            SafetyDutyTemplateItem(
                content=item.get("content", ""),
                rule=item.get("rule", ""),
                standard_score=float(item.get("standard_score") or 0),
            )
            for item in tpl.get("items", [])
        ],
        matched=True,
    )


class SafetyTargetService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_targets(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        year: int | None = None,
        category: str | None = None,
        department: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[SafetyTarget], int]:
        conditions: list[ColumnElement[bool]] = [SafetyTarget.is_deleted.is_(False)]
        if year is not None:
            conditions.append(SafetyTarget.year == year)
        if category:
            conditions.append(SafetyTarget.category == category)
        if department:
            conditions.append(SafetyTarget.owner_department == department)
        if status:
            conditions.append(SafetyTarget.status == status)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    SafetyTarget.title.ilike(pattern),
                    SafetyTarget.search_text.ilike(pattern),
                )
            )

        total = (
            await self.db.execute(
                select(func.count()).select_from(SafetyTarget).where(*conditions)
            )
        ).scalar() or 0

        result = await self.db.execute(
            select(SafetyTarget)
            .options(selectinload(SafetyTarget.records))
            .where(*conditions)
            .order_by(
                SafetyTarget.year.desc(),
                SafetyTarget.category.asc(),
                SafetyTarget.created_at.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().unique().all()), total

    async def get_target(self, target_id: UUID) -> SafetyTarget | None:
        result = await self.db.execute(
            select(SafetyTarget)
            .options(selectinload(SafetyTarget.records))
            .where(
                SafetyTarget.id == target_id,
                SafetyTarget.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_key(
        self, year: int, title: str, owner_department: str
    ) -> SafetyTarget | None:
        result = await self.db.execute(
            select(SafetyTarget).where(
                SafetyTarget.year == year,
                SafetyTarget.title == title,
                SafetyTarget.owner_department == owner_department,
                SafetyTarget.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create_target(
        self, data: SafetyTargetCreate, user_id: UUID | None = None
    ) -> SafetyTarget:
        if await self.get_by_key(data.year, data.title, data.owner_department):
            raise AppException(
                status_code=409, message="同年度/部门下已存在同名安全目标"
            )
        target = SafetyTarget(
            year=data.year,
            title=data.title,
            category=data.category,
            metric=data.metric,
            target_value=data.target_value,
            unit=data.unit,
            owner_department=data.owner_department,
            owner_name=data.owner_name,
            deadline=data.deadline,
            status=data.status,
            remark=data.remark,
            search_text=build_search_text(
                data.title,
                data.category,
                data.owner_department,
                data.owner_name,
                data.metric,
            ),
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(target)
        await self.db.flush()
        return target

    async def update_target(
        self, target_id: UUID, data: SafetyTargetUpdate, user_id: UUID | None = None
    ) -> SafetyTarget:
        target = await self.get_target(target_id)
        if target is None:
            raise NotFoundException("安全目标不存在")

        changes = data.model_dump(exclude_unset=True)
        new_year = changes.get("year", target.year)
        new_title = changes.get("title", target.title)
        new_department = changes.get("owner_department", target.owner_department)
        if (new_year, new_title, new_department) != (
            target.year,
            target.title,
            target.owner_department,
        ):
            existing = await self.get_by_key(new_year, new_title, new_department)
            if existing is not None and existing.id != target.id:
                raise AppException(
                    status_code=409, message="同年度/部门下已存在同名安全目标"
                )
        for field, value in changes.items():
            setattr(target, field, value)
        target.search_text = build_search_text(
            target.title,
            target.category,
            target.owner_department,
            target.owner_name,
            target.metric,
        )
        target.updated_by = user_id
        await self.db.flush()
        return target

    async def delete_target(self, target_id: UUID) -> bool:
        target = await self.get_target(target_id)
        if target is None:
            return False
        target.is_deleted = True
        await self.db.flush()
        return True

    async def create_record(
        self,
        target_id: UUID,
        data: SafetyTargetRecordCreate,
        user_id: UUID | None = None,
    ) -> SafetyTargetRecord:
        target = await self.get_target(target_id)
        if target is None:
            raise NotFoundException("安全目标不存在")
        existing = await self.get_record(target_id, data.period)
        if existing is not None:
            raise AppException(
                status_code=409, message="该考核期已有进度记录，请直接编辑"
            )
        record = SafetyTargetRecord(
            target_id=target_id,
            period=data.period,
            actual_value=data.actual_value,
            completion_pct=data.completion_pct,
            note=data.note,
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def get_record(
        self, target_id: UUID, period: str
    ) -> SafetyTargetRecord | None:
        result = await self.db.execute(
            select(SafetyTargetRecord).where(
                SafetyTargetRecord.target_id == target_id,
                SafetyTargetRecord.period == period,
                SafetyTargetRecord.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def update_record(
        self,
        target_id: UUID,
        period: str,
        data: SafetyTargetRecordUpdate,
        user_id: UUID | None = None,
    ) -> SafetyTargetRecord:
        record = await self.get_record(target_id, period)
        if record is None:
            raise NotFoundException("进度记录不存在")
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            setattr(record, field, value)
        record.updated_by = user_id
        await self.db.flush()
        return record

    async def delete_record(self, target_id: UUID, period: str) -> bool:
        record = await self.get_record(target_id, period)
        if record is None:
            return False
        record.is_deleted = True
        await self.db.flush()
        return True

    async def get_stats(self, *, year: int | None = None) -> SafetyTargetStatsResponse:
        conditions: list[ColumnElement[bool]] = [SafetyTarget.is_deleted.is_(False)]
        if year is not None:
            conditions.append(SafetyTarget.year == year)
        result = await self.db.execute(
            select(
                SafetyTarget.category,
                SafetyTarget.owner_department,
                SafetyTarget.status,
            ).where(*conditions)
        )
        rows = result.all()

        category_order: list[str] = []
        department_rows: dict[str, list[str]] = {}
        for category, department, status in rows:
            if category not in category_order:
                category_order.append(category)
            if department:
                department_rows.setdefault(department, []).append(status)

        departments = [
            SafetyTargetDepartmentStat(
                department=department,
                total=len(statuses),
                achieved=sum(1 for s in statuses if s == "achieved"),
                not_achieved=sum(1 for s in statuses if s == "not_achieved"),
                in_progress=sum(1 for s in statuses if s == "in_progress"),
            )
            for department, statuses in department_rows.items()
        ]
        return SafetyTargetStatsResponse(
            total=len(rows),
            achieved=sum(1 for _, _, s in rows if s == "achieved"),
            in_progress=sum(1 for _, _, s in rows if s == "in_progress"),
            not_achieved=sum(1 for _, _, s in rows if s == "not_achieved"),
            categories=category_order,
            departments=departments,
        )


def _agreement_search_text(
    department: str, position: str, category: str, party_a: str, party_b: str
) -> str:
    return " ".join(
        part for part in (department, position, category, party_a, party_b) if part
    )


class SafetyTargetAgreementService:
    """安全目标责任书签订台账：按年度×部门×岗位跟踪签订状态。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_agreements(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        year: int | None = None,
        department: str | None = None,
        category: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[SafetyTargetAgreement], int]:
        conditions: list[ColumnElement[bool]] = [
            SafetyTargetAgreement.is_deleted.is_(False)
        ]
        if year is not None:
            conditions.append(SafetyTargetAgreement.year == year)
        if department:
            conditions.append(SafetyTargetAgreement.department == department)
        if category:
            conditions.append(SafetyTargetAgreement.category == category)
        if status:
            conditions.append(SafetyTargetAgreement.status == status)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    SafetyTargetAgreement.department.ilike(pattern),
                    SafetyTargetAgreement.position.ilike(pattern),
                    SafetyTargetAgreement.search_text.ilike(pattern),
                )
            )

        total = (
            await self.db.execute(
                select(func.count())
                .select_from(SafetyTargetAgreement)
                .where(*conditions)
            )
        ).scalar() or 0

        result = await self.db.execute(
            select(SafetyTargetAgreement)
            .where(*conditions)
            .order_by(
                SafetyTargetAgreement.year.desc(),
                SafetyTargetAgreement.category.asc(),
                SafetyTargetAgreement.department.asc(),
                SafetyTargetAgreement.position.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def get_agreement(self, agreement_id: UUID) -> SafetyTargetAgreement | None:
        result = await self.db.execute(
            select(SafetyTargetAgreement).where(
                SafetyTargetAgreement.id == agreement_id,
                SafetyTargetAgreement.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_key(
        self, year: int, department: str, position: str
    ) -> SafetyTargetAgreement | None:
        result = await self.db.execute(
            select(SafetyTargetAgreement).where(
                SafetyTargetAgreement.year == year,
                SafetyTargetAgreement.department == department,
                SafetyTargetAgreement.position == position,
                SafetyTargetAgreement.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create_agreement(
        self, data: SafetyTargetAgreementCreate, user_id: UUID | None = None
    ) -> SafetyTargetAgreement:
        if await self.get_by_key(data.year, data.department, data.position):
            raise AppException(
                status_code=409, message="同年度/部门/岗位下已存在责任书记录"
            )
        agreement = SafetyTargetAgreement(
            year=data.year,
            department=data.department,
            position=data.position,
            category=data.category,
            party_a=data.party_a,
            party_b=data.party_b,
            status=data.status,
            signed_date=data.signed_date,
            expires_date=data.expires_date,
            goals_text=data.goals_text,
            remark=data.remark,
            search_text=_agreement_search_text(
                data.department,
                data.position,
                data.category,
                data.party_a,
                data.party_b,
            ),
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(agreement)
        await self.db.flush()
        return agreement

    async def update_agreement(
        self,
        agreement_id: UUID,
        data: SafetyTargetAgreementUpdate,
        user_id: UUID | None = None,
    ) -> SafetyTargetAgreement:
        agreement = await self.get_agreement(agreement_id)
        if agreement is None:
            raise NotFoundException("责任书记录不存在")

        changes = data.model_dump(exclude_unset=True)
        new_year = changes.get("year", agreement.year)
        new_department = changes.get("department", agreement.department)
        new_position = changes.get("position", agreement.position)
        if (new_year, new_department, new_position) != (
            agreement.year,
            agreement.department,
            agreement.position,
        ):
            existing = await self.get_by_key(new_year, new_department, new_position)
            if existing is not None and existing.id != agreement.id:
                raise AppException(
                    status_code=409, message="同年度/部门/岗位下已存在责任书记录"
                )
        for field, value in changes.items():
            setattr(agreement, field, value)
        agreement.search_text = _agreement_search_text(
            agreement.department,
            agreement.position,
            agreement.category,
            agreement.party_a,
            agreement.party_b,
        )
        agreement.updated_by = user_id
        await self.db.flush()
        return agreement

    async def delete_agreement(self, agreement_id: UUID) -> bool:
        agreement = await self.get_agreement(agreement_id)
        if agreement is None:
            return False
        agreement.is_deleted = True
        await self.db.flush()
        return True

    async def get_stats(
        self, *, year: int | None = None
    ) -> SafetyTargetAgreementStatsResponse:
        conditions: list[ColumnElement[bool]] = [
            SafetyTargetAgreement.is_deleted.is_(False)
        ]
        if year is not None:
            conditions.append(SafetyTargetAgreement.year == year)
        result = await self.db.execute(
            select(
                SafetyTargetAgreement.department,
                SafetyTargetAgreement.status,
            ).where(*conditions)
        )
        rows = result.all()

        department_rows: dict[str, list[str]] = {}
        for department, status in rows:
            department_rows.setdefault(department, []).append(status)
        departments = [
            SafetyTargetAgreementDepartmentStat(
                department=department,
                total=len(statuses),
                signed=sum(1 for s in statuses if s == "signed"),
            )
            for department, statuses in sorted(department_rows.items())
        ]
        total = len(rows)
        signed = sum(1 for _, s in rows if s == "signed")
        return SafetyTargetAgreementStatsResponse(
            total=total,
            signed=signed,
            unsigned=total - signed,
            sign_rate=round(signed / total * 100, 1) if total else 0.0,
            departments=departments,
        )


def _assessment_search_text(
    department: str, person_name: str, assessor: str
) -> str:
    return " ".join(part for part in (department, person_name, assessor) if part)


def _build_assessment_items(
    assessment_id: UUID, inputs: list[SafetyDutyAssessmentItemInput]
) -> list[SafetyDutyAssessmentItem]:
    items: list[SafetyDutyAssessmentItem] = []
    for idx, item in enumerate(inputs):
        score = (
            item.score
            if item.score is not None
            else max(0.0, item.standard_score - item.deduction_score)
        )
        items.append(
            SafetyDutyAssessmentItem(
                assessment_id=assessment_id,
                sort_order=idx,
                content=item.content,
                rule=item.rule,
                standard_score=item.standard_score,
                deduction_score=item.deduction_score,
                score=score,
                remark=item.remark,
            )
        )
    return items


def _summarize_assessment(items: list[SafetyDutyAssessmentItem]) -> tuple[float, str]:
    total = round(sum(item.score for item in items), 1)
    return total, grade_for_score(total)


class SafetyDutyAssessmentService:
    """安全生产责任制季度考核：部门/负责人按季度百分制考核。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_assessments(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        year: int | None = None,
        quarter: int | None = None,
        department: str | None = None,
        grade: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[SafetyDutyAssessment], int]:
        conditions: list[ColumnElement[bool]] = [
            SafetyDutyAssessment.is_deleted.is_(False)
        ]
        if year is not None:
            conditions.append(SafetyDutyAssessment.year == year)
        if quarter is not None:
            conditions.append(SafetyDutyAssessment.quarter == quarter)
        if department:
            conditions.append(SafetyDutyAssessment.department == department)
        if grade:
            conditions.append(SafetyDutyAssessment.grade == grade)
        if keyword:
            pattern = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    SafetyDutyAssessment.department.ilike(pattern),
                    SafetyDutyAssessment.person_name.ilike(pattern),
                    SafetyDutyAssessment.assessor.ilike(pattern),
                    SafetyDutyAssessment.search_text.ilike(pattern),
                )
            )

        total = (
            await self.db.execute(
                select(func.count())
                .select_from(SafetyDutyAssessment)
                .where(*conditions)
            )
        ).scalar() or 0

        result = await self.db.execute(
            select(SafetyDutyAssessment)
            .options(selectinload(SafetyDutyAssessment.items))
            .where(*conditions)
            .order_by(
                SafetyDutyAssessment.year.desc(),
                SafetyDutyAssessment.quarter.desc(),
                SafetyDutyAssessment.department.asc(),
                SafetyDutyAssessment.created_at.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().unique().all()), total

    async def get_assessment(self, assessment_id: UUID) -> SafetyDutyAssessment | None:
        result = await self.db.execute(
            select(SafetyDutyAssessment)
            .options(selectinload(SafetyDutyAssessment.items))
            .where(
                SafetyDutyAssessment.id == assessment_id,
                SafetyDutyAssessment.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_key(
        self, year: int, quarter: int, department: str, person_name: str
    ) -> SafetyDutyAssessment | None:
        result = await self.db.execute(
            select(SafetyDutyAssessment).where(
                SafetyDutyAssessment.year == year,
                SafetyDutyAssessment.quarter == quarter,
                SafetyDutyAssessment.department == department,
                SafetyDutyAssessment.person_name == person_name,
                SafetyDutyAssessment.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create_assessment(
        self, data: SafetyDutyAssessmentCreate, user_id: UUID | None = None
    ) -> SafetyDutyAssessment:
        if await self.get_by_key(
            data.year, data.quarter, data.department, data.person_name
        ):
            raise AppException(
                status_code=409, message="该季度已存在此部门/人员的考核记录"
            )
        items = _build_assessment_items(UUID(int=0), data.items)
        total_score, grade = _summarize_assessment(items)
        assessment = SafetyDutyAssessment(
            year=data.year,
            quarter=data.quarter,
            department=data.department,
            person_name=data.person_name,
            assessor=data.assessor,
            assessment_date=data.assessment_date,
            total_score=total_score,
            grade=grade,
            remark=data.remark,
            search_text=_assessment_search_text(
                data.department, data.person_name, data.assessor
            ),
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(assessment)
        await self.db.flush()
        for item in items:
            item.assessment_id = assessment.id
            self.db.add(item)
        await self.db.flush()
        return assessment

    async def update_assessment(
        self,
        assessment_id: UUID,
        data: SafetyDutyAssessmentUpdate,
        user_id: UUID | None = None,
    ) -> SafetyDutyAssessment:
        assessment = await self.get_assessment(assessment_id)
        if assessment is None:
            raise NotFoundException("考核记录不存在")

        changes = data.model_dump(exclude_unset=True)
        new_year = changes.get("year", assessment.year)
        new_quarter = changes.get("quarter", assessment.quarter)
        new_department = changes.get("department", assessment.department)
        new_person = changes.get("person_name", assessment.person_name)
        if (new_year, new_quarter, new_department, new_person) != (
            assessment.year,
            assessment.quarter,
            assessment.department,
            assessment.person_name,
        ):
            existing = await self.get_by_key(
                new_year, new_quarter, new_department, new_person
            )
            if existing is not None and existing.id != assessment.id:
                raise AppException(
                    status_code=409, message="该季度已存在此部门/人员的考核记录"
                )

        item_inputs = changes.pop("items", None)
        for field, value in changes.items():
            setattr(assessment, field, value)

        if item_inputs is not None:
            await self.db.execute(
                update(SafetyDutyAssessmentItem)
                .where(SafetyDutyAssessmentItem.assessment_id == assessment.id)
                .values(is_deleted=True, updated_by=user_id)
            )
            items = _build_assessment_items(
                assessment.id,
                [SafetyDutyAssessmentItemInput(**raw) for raw in item_inputs],
            )
            self.db.add_all(items)
        else:
            items = list(assessment.items)

        total_score, grade = _summarize_assessment(items)
        assessment.total_score = total_score
        assessment.grade = grade
        assessment.search_text = _assessment_search_text(
            assessment.department, assessment.person_name, assessment.assessor
        )
        assessment.updated_by = user_id
        await self.db.flush()
        return assessment

    async def delete_assessment(self, assessment_id: UUID) -> bool:
        assessment = await self.get_assessment(assessment_id)
        if assessment is None:
            return False
        assessment.is_deleted = True
        await self.db.execute(
            update(SafetyDutyAssessmentItem)
            .where(SafetyDutyAssessmentItem.assessment_id == assessment.id)
            .values(is_deleted=True)
        )
        await self.db.flush()
        return True

    async def get_stats(
        self, *, year: int | None = None
    ) -> SafetyDutyAssessmentStatsResponse:
        conditions: list[ColumnElement[bool]] = [
            SafetyDutyAssessment.is_deleted.is_(False)
        ]
        if year is not None:
            conditions.append(SafetyDutyAssessment.year == year)
        result = await self.db.execute(
            select(
                SafetyDutyAssessment.quarter,
                SafetyDutyAssessment.department,
                SafetyDutyAssessment.total_score,
            ).where(*conditions)
        )
        rows = result.all()

        quarter_rows: dict[int, list[float]] = {}
        department_rows: dict[str, list[float]] = {}
        for quarter, department, total_score in rows:
            quarter_rows.setdefault(quarter, []).append(total_score)
            department_rows.setdefault(department, []).append(total_score)

        scores = [score for _, _, score in rows]
        return SafetyDutyAssessmentStatsResponse(
            total=len(rows),
            avg_score=round(sum(scores) / len(scores), 1) if scores else 0.0,
            excellent=sum(1 for s in scores if s >= 95),
            good=sum(1 for s in scores if 90 <= s < 95),
            qualified=sum(1 for s in scores if 80 <= s < 90),
            unqualified=sum(1 for s in scores if s < 80),
            quarters=[
                SafetyDutyAssessmentQuarterStat(
                    quarter=quarter,
                    count=len(list_scores),
                    avg_score=round(sum(list_scores) / len(list_scores), 1),
                )
                for quarter, list_scores in sorted(quarter_rows.items())
            ],
            departments=[
                SafetyDutyAssessmentDepartmentStat(
                    department=department,
                    count=len(list_scores),
                    avg_score=round(sum(list_scores) / len(list_scores), 1),
                )
                for department, list_scores in sorted(department_rows.items())
            ],
        )
