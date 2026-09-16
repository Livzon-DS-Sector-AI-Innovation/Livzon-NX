"""维护保养记录「完成即生成下一期任务」。

业务口径（2026-09 与用户确认）：记录填写「维护日期」即视为本期完成——
- 自动把原记录「是否完成」置为「是」（已是「是」则不动）；
- 自动新建一条下一期任务记录：复制 设备名称/设备编号/维护内容/通知人/
  维保类型；是否完成=「否」、维护日期留空（尚未维护）、生成日期=当天、
  下次维保时间 = 原记录维护日期 + 周期表「周期（月）」；
  维护人/复核人留空，待下一期实际维护时再填写；
- 链的粒度是「设备编号 + 维护内容」：同一编号可并存多条不同维护内容、
  不同周期的任务链，互不影响；
- 防重复：同编号同维护内容下，已存在「下次维保时间 == 预期日期」的记录，
  或已存在未完成且计划不早于预期日期的任务时，跳过该链的生成。

周期匹配：以 QC检测仪器维护保养周期表镜像为准，按「仪器编号 + 维护内容」
（编号与内容均归一化空白）建索引；记录无维护内容且该编号在周期表只有一行
时按编号兜底命中。无维护内容的记录匹配不到周期，不会生成下一期。
展示用 enrich（不回写飞书）：「下次维保时间」为空的行按维护日期+周期补算，
仅在列表/档案展示，飞书侧仍以真实值为准。
"""

from __future__ import annotations

import asyncio
import calendar
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.service.instruments_dashboard import (
    _cell_text,
    _load_page,
    parse_feishu_date,
)

# 并发去重：镜像同步与手动完成可能同时触发下一期生成，串行化查重+创建
_SPAWN_LOCK = asyncio.Lock()

logger = logging.getLogger(__name__)

_TZ_SH = timezone(timedelta(hours=8))

ENTITY = "qc_instr_maintenance"
# 生成下一期任务时从原记录复制的字段。维护人/复核人不复制：下一期尚未
# 维护，留待实际执行时填写；通知人保留（下一期仍通知同一人）。
# User 字段按原始 id 数组原样回写
_SPAWN_COPY_FIELDS = (
    "设备名称",
    "设备编号",
    "维护内容",
    "通知人",
    "维保类型",
)


def _to_int(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _norm_text(value: Any) -> str:
    """归一化文本用于匹配：去首尾与内部全部空白。"""
    return "".join(_cell_text(value).split())


def add_months(base: date, months: int) -> date:
    """基准日期加 N 个月（日值超过目标月天数时取月末）。"""
    month_index = base.year * 12 + (base.month - 1) + months
    year = month_index // 12
    month = month_index % 12 + 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def next_maintenance_date(base: date, months: float) -> date:
    """维护日期 + 周期。

    整数月走月历加法（月末日钳制）；不足 1 个月的小数周期（如周期表里的
    0.5 = 每半月）按 30 天/月 折算成天数，避免 int 截断成 0 退化成同一天。
    """
    if months < 1:
        return base + timedelta(days=max(1, round(30 * months)))
    return add_months(base, int(months))


def _today() -> date:
    return datetime.now(tz=_TZ_SH).date()


def _to_ms(target: date) -> int:
    """日期 -> 飞书 DateTime 字段的毫秒时间戳（东八区当天零点）。"""
    stamp = datetime(target.year, target.month, target.day, tzinfo=_TZ_SH)
    return int(stamp.timestamp() * 1000)


def _parse_row_date(row: dict[str, Any], *keys: str) -> date | None:
    for key in keys:
        parsed = parse_feishu_date(row.get(key))
        if parsed is not None and parsed.year >= 2000:
            return parsed
    return None


class _CycleIndex:
    """周期表索引：精确 (编号, 维护内容) 命中 + 编号单行兜底。"""

    def __init__(self) -> None:
        self.exact: dict[tuple[str, str], dict[str, Any]] = {}
        self.by_code: dict[str, list[dict[str, Any]]] = {}
        self.conflicting: set[tuple[str, str]] = set()

    def add(self, codes: set[str], content: str, info: dict[str, Any]) -> None:
        for code in codes:
            key = (code, content)
            if key in self.exact and self.exact[key] != info:
                # 同编号+同内容存在多套不同周期：按内容精确判定会产生歧义
                self.conflicting.add(key)
            else:
                self.exact.setdefault(key, info)
            bucket = self.by_code.setdefault(code, [])
            if info not in bucket:
                bucket.append(info)

    def lookup(self, code: str, content: str) -> dict[str, Any] | None:
        if not code:
            return None
        if not content:
            # 记录未填维护内容：该编号在周期表有内容的计划唯一时兜底命中
            # （空内容计划不参与匹配，避免生成无意义的空任务）
            bucket = self.by_code.get(code) or []
            with_content = [item for item in bucket if item.get("维护内容")]
            if len(with_content) == 1:
                return with_content[0]
            return None
        key = (code, content)
        if key in self.conflicting:
            return None
        return self.exact.get(key)


async def _load_cycle_index(db: AsyncSession) -> _CycleIndex:
    """周期表按（仪器编号、维护内容）建索引；一格多编号顿号分词。"""
    page = await _load_page(db, "qc_instr_plans")
    index = _CycleIndex()
    for row in page.get("items") or []:
        months = _to_int(row.get("周期（月）"))
        if months is None or months <= 0:
            continue
        info = {
            "months": months,
            "category": _cell_text(row.get("仪器类别")),
            "cycle_text": _cell_text(row.get("维护周期")),
            "维护内容": _norm_text(row.get("维护内容")),
        }
        raw_codes = _cell_text(row.get("仪器编号"))
        codes = {
            token.strip()
            for token in raw_codes.replace("、", ",").split(",")
            if token.strip()
        }
        index.add(codes, _norm_text(row.get("维护内容")), info)
    return index


def _record_code(fields: dict[str, Any]) -> str:
    return _cell_text(fields.get("设备编号")).strip()


def _record_content(fields: dict[str, Any]) -> str:
    return _norm_text(fields.get("维护内容"))


def _copy_value(value: Any) -> Any:
    """把回读形态的字段值转成可写入形态。

    文本列回读是富文本段 [{text,type}]，写入需纯字符串；人员列回读带
    name/avatar 等多余键，写入只需 [{id}]；其余（单选字符串/数字）原样。
    """
    if not isinstance(value, list) or not value:
        return value
    if not all(isinstance(item, dict) for item in value):
        return value
    if all(item.get("id") for item in value):
        return [{"id": str(item["id"])} for item in value]
    return "".join(str(item.get("text") or "") for item in value)


async def enrich_maintenance_schedule(
    db: AsyncSession, items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """展示用：就地填充「下次维保时间」为空的行（按维护日期+周期），不回写飞书。

    剩余天数公式列现已恢复有效，展示直接用公式值，不再补算。
    """
    cycle_index = await _load_cycle_index(db)
    if not cycle_index.exact and not cycle_index.by_code:
        return items
    for item in items:
        if _cell_text(item.get("下次维保时间")):
            continue
        info = cycle_index.lookup(
            _record_code(item), _record_content(item)
        )
        if info is None:
            continue
        base = _parse_row_date(item, "维护日期", "生成日期")
        if base is None:
            continue
        item["下次维保时间"] = next_maintenance_date(
            base, info["months"]
        ).isoformat()
    return items


def _has_open_successor(
    existing: list[dict[str, Any]],
    code: str,
    content: str,
    expected_ms: int,
) -> bool:
    """同编号同维护内容的链是否已有下一期任务（防重复）。"""
    for record in existing:
        fields = record.get("fields") or {}
        if _record_code(fields) != code:
            continue
        if _record_content(fields) != content:
            continue
        next_raw = fields.get("下次维保时间")
        if next_raw == expected_ms:
            return True
        if (
            _cell_text(fields.get("是否完成")) == "否"
            and isinstance(next_raw, (int, float))
            and next_raw >= expected_ms
        ):
            return True
    return False


def _build_code_filter(code: str) -> str:
    return f'CurrentValue.[设备编号] = "{code}"'


async def _ensure_source_completed(
    client: Any,
    table_id: str,
    record_id: str,
    fields: dict[str, Any],
) -> bool:
    """填了维护日期即视为完成：原记录「是否完成」自动置「是」（幂等）。

    就地同步 fields，保证同一次处理内的防重复判定看到完成态。
    """
    if fields.get("是否完成") == "是":
        return False
    await client.update_record(
        table_id,
        record_id,
        {"是否完成": "是"},
        user_id_type="open_id",
    )
    fields["是否完成"] = "是"
    logger.info("维保记录已自动置为完成 record=%s", record_id)
    return True


async def _spawn_next_for_fields_impl(
    db: AsyncSession,
    client: Any,
    table_id: str,
    record_id: str,
    fields: dict[str, Any],
    *,
    existing: list[dict[str, Any]] | None = None,
) -> tuple[str, int] | None:
    """单条记录的完成处理与下一期生成；返回 (新建 record_id, 预期下次时间ms)。

    处理顺序：先把填了维护日期的原记录自动置完成，再按周期匹配生成下一期
    （匹配不到周期时仅置完成、不生成）。fields 为飞书原始字段值（records
    API 回读形态）。existing 传入时用于防重复判定（同设备编号的既有记录），
    否则按设备编号查表。
    """
    done_date = _parse_row_date(fields, "维护日期")
    if done_date is None:
        return None
    await _ensure_source_completed(client, table_id, record_id, fields)
    code = _record_code(fields)
    if not code:
        return None
    content = _record_content(fields)
    cycle_index = await _load_cycle_index(db)
    info = cycle_index.lookup(code, content)
    if info is None:
        return None
    # 记录未填维护内容时，用周期计划的内容补齐生成任务的维护内容
    if not content and info.get("维护内容"):
        fields = dict(fields)
        fields["维护内容"] = info["维护内容"]
        content = str(info["维护内容"])
    expected = next_maintenance_date(done_date, info["months"])
    expected_ms = _to_ms(expected)

    if existing is None:
        existing = await client.search_records(
            table_id,
            filter_str=_build_code_filter(code),
            field_names=["设备编号", "维护内容", "是否完成", "下次维保时间"],
            user_id_type="open_id",
        )
    if _has_open_successor(existing, code, content, expected_ms):
        return None

    new_fields: dict[str, Any] = {
        "生成日期": _to_ms(_today()),
        "是否完成": "否",
        "下次维保时间": expected_ms,
    }
    for key in _SPAWN_COPY_FIELDS:
        value = fields.get(key)
        if value in (None, "", []):
            continue
        new_fields[key] = _copy_value(value)
    record = await client.create_record(table_id, new_fields, user_id_type="open_id")
    record_id = str(record.get("record_id") or "")
    logger.info(
        "已生成下一期维保任务：%s[%s] -> record=%s 下次维保时间=%s",
        code,
        content[:12],
        record_id,
        expected.isoformat(),
    )
    return (record_id, expected_ms) if record_id else None




async def spawn_next_for_fields(
    db: AsyncSession,
    client: Any,
    table_id: str,
    record_id: str,
    fields: dict[str, Any],
    *,
    existing: list[dict[str, Any]] | None = None,
) -> tuple[str, int] | None:
    """单条记录完成处理与下一期生成（并发安全入口，内部串行化）。"""
    async with _SPAWN_LOCK:
        return await _spawn_next_for_fields_impl(
            db, client, table_id, record_id, fields, existing=existing
        )

async def maybe_spawn_next_maintenance(
    db: AsyncSession,
    client: Any,
    table_id: str,
    records: list[dict[str, Any]],
) -> int:
    """镜像同步后批量检测：填了维护日期的行自动置完成并补建下一期任务。

    单条失败仅记日志，不影响同步与其余行。返回生成条数。
    """
    async with _SPAWN_LOCK:
        spawned = 0
        # 同设备编号的既有记录缓存，避免逐条查表
        by_code: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            fields = record.get("fields") or {}
            if fields.get("维护日期") in (None, ""):
                continue
            code = _record_code(fields)
            record_id = str(record.get("record_id") or "")
            if not code or not record_id:
                continue
            try:
                if code not in by_code:
                    by_code[code] = await client.search_records(
                        table_id,
                        filter_str=_build_code_filter(code),
                        field_names=[
                            "设备编号",
                            "维护内容",
                            "是否完成",
                            "下次维保时间",
                        ],
                        user_id_type="open_id",
                    )
                created = await _spawn_next_for_fields_impl(
                    db, client, table_id, record_id, fields, existing=by_code[code]
                )
                if created:
                    spawned += 1
                    record_id, expected_ms = created
                    # 并入缓存（带真实计划时间）：同链后续记录防重复判定可见
                    by_code[code] = by_code[code] + [
                        {
                            "record_id": record_id,
                            "fields": {
                                "设备编号": code,
                                "维护内容": fields.get("维护内容"),
                                "是否完成": "否",
                                "下次维保时间": expected_ms,
                            },
                        }
                    ]
            except Exception as exc:  # noqa: BLE001 - 单条失败不中断同步
                logger.warning(
                    "维保下一期任务生成失败 record=%s: %s",
                    record.get("record_id"),
                    exc,
                )
        if spawned:
            logger.info("维保下一期任务本轮共生成 %d 条", spawned)
        return spawned
