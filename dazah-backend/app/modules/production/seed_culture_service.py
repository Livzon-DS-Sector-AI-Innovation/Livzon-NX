"""摇瓶种子制备记录 service."""
from datetime import date as date_type
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.production.seed_culture_repository import SeedCultureRepository

# 人员环节列 → 绩效角色标签（列值与飞书位表人员字段一一对应）
ROLE_LABELS: dict[str, str] = {
    "prepare_operator": "配制",
    "sterilization_operator": "消毒",
    "shaker_setup_operator": "摇床摆放",
    "inoculation_operator": "接种",
    "merge_operator": "并瓶",
    "tank_setup_operator": "进罐",
    "workshop_inoculation_operator": "车间接种",
}


def _person_attr(person: Any, attr: str) -> Any:
    """人员引用兼容两种形态：JSONB 反序列化的 dict 与对象属性。"""
    if isinstance(person, dict):
        return person.get(attr)
    return getattr(person, attr, None)


def aggregate_person_monthly(
    records: list[Any],
    month_start: date_type,
    month_end: date_type,
) -> list[dict[str, Any]]:
    """按 月 × 人 聚合菌种参与情况（月度绩效依据）。

    以 prepare_date 归属月份；同一人一 batch 担任多环节计 1 批、
    各环节分别计数；身份以 open_id 优先、缺省按姓名归组。
    返回按参与批次数降序的行列表。
    """
    stats: dict[str, dict[str, Any]] = {}
    for record in records:
        prepare_date = getattr(record, "prepare_date", None)
        if prepare_date is None or not (month_start <= prepare_date <= month_end):
            continue
        batch_no = str(getattr(record, "batch_no", ""))
        for role_col, label in ROLE_LABELS.items():
            for person in getattr(record, role_col, None) or []:
                name = str(_person_attr(person, "name") or "")
                open_id = _person_attr(person, "open_id")
                key = open_id or f"name:{name}"
                entry = stats.get(key)
                if entry is None:
                    entry = {
                        "key": key,
                        "name": name,
                        "open_id": open_id,
                        "avatar_url": _person_attr(person, "avatar_url"),
                        "batch_set": set(),
                        "role_counts": {lab: 0 for lab in ROLE_LABELS.values()},
                        "details": [],
                    }
                    stats[key] = entry
                if name and not entry["name"]:
                    entry["name"] = name
                avatar = _person_attr(person, "avatar_url")
                if avatar and not entry["avatar_url"]:
                    entry["avatar_url"] = avatar
                entry["batch_set"].add(batch_no)
                entry["role_counts"][label] += 1
                entry["details"].append(
                    {
                        "date": prepare_date.isoformat(),
                        "batch_no": batch_no,
                        "role": label,
                    }
                )
    # 同名归并：手工录入（无 open_id）并入同名飞书成员组，绩效行以人为准
    by_name: dict[str, dict[str, Any]] = {}
    for entry in stats.values():
        if entry["open_id"] and entry["name"]:
            by_name.setdefault(entry["name"], entry)
    merged_names: list[str] = []
    for key, entry in list(stats.items()):
        if entry["open_id"] or not entry["name"]:
            continue
        canonical = by_name.get(entry["name"])
        if canonical is None or canonical is entry:
            continue
        canonical["batch_set"] |= entry["batch_set"]
        for lab, count in entry["role_counts"].items():
            canonical["role_counts"][lab] += count
        canonical["details"].extend(entry["details"])
        merged_names.append(key)
    for key in merged_names:
        stats.pop(key)

    rows: list[dict[str, Any]] = []
    for entry in stats.values():
        batch_set = entry.pop("batch_set")
        entry["total_batches"] = len(batch_set)
        entry["details"].sort(key=lambda d: (d["date"], d["batch_no"]))
        rows.append(entry)
    rows.sort(key=lambda r: (-r["total_batches"], r["name"]))
    return rows


class SeedCultureService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = SeedCultureRepository(session)

    @staticmethod
    def _prepare_data(data: dict[str, Any]) -> dict[str, Any]:
        for field in ("prepare_date", "shaker_start_date"):
            if (
                field in data
                and data[field] is not None
                and isinstance(data[field], str)
            ):
                data[field] = date_type.fromisoformat(data[field])
        return data

    async def list_records(
        self,
        page: int = 1,
        page_size: int = 20,
        batch_no: str | None = None,
        product_name: str | None = None,
    ) -> Any:
        return await self.repo.list(
            page=page, page_size=page_size, batch_no=batch_no, product_name=product_name
        )

    async def get_record(self, record_id: UUID) -> Any:
        return await self.repo.get_by_id(record_id)

    async def create_record(self, data: dict[str, Any]) -> Any:
        return await self.repo.create(self._prepare_data(data))

    async def update_record(self, record_id: UUID, data: dict[str, Any]) -> Any:
        record = await self.repo.update(record_id, self._prepare_data(data))
        if not record:
            raise ValueError(f"Seed culture {record_id} not found")
        return record

    async def delete_record(self, record_id: UUID) -> Any:
        if not await self.repo.delete(record_id):
            raise ValueError(f"Seed culture {record_id} not found")

    async def person_monthly(
        self, product_name: str, month: str
    ) -> list[dict[str, Any]]:
        """人员月度工作统计（绩效依据）：月 × 人 × 环节聚合。

        聚合输入限定单产品当月全部在册记录（量级为百级，取整页上限）。
        """
        month_start = date_type.fromisoformat(f"{month}-01")
        month_end = month_start + timedelta(days=31)
        month_end = month_end.replace(day=1) - timedelta(days=1)
        records, _total = await self.repo.list(
            page=1, page_size=1000, product_name=product_name
        )
        return aggregate_person_monthly(records, month_start, month_end)
