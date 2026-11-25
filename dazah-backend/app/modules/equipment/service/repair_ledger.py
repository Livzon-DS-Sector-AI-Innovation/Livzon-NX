"""设备检修台账（飞书多维表格镜像）服务。

车间在飞书多维表格登记维修记录（列：车间及地点 / 设备名称·型号 /
维修日期 / 维修人员 / 故障描述·原因 / 更换备件 / 维修后状态 / 备注），
本服务按车间配置镜像到本地 ``equipment.repair_records``：

- 同步策略：检修表数据量小（每车间每年数百行内），采用整表拉取 +
  UPSERT + 删除对账的幂等全量同步，天然覆盖新增、修改与飞书侧删除，
  不引入水位排序的复杂度。
- 页面只读展示与频次分析；不回写飞书，不与设备台账关联，
  按表内「设备名称/型号」原文聚合。
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import String, delete, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.exceptions import AppException
from app.core.llm.encryption import encrypt_api_key, mask_api_key
from app.modules.equipment.models.feishu_app import EquipmentFeishuApp
from app.modules.equipment.models.repair_ledger import (
    RepairFeishuConfig,
    RepairRecord,
    RepairSummarySettings,
    RepairSyncState,
)
from app.modules.equipment.schemas.repair_ledger import RepairConfigUpdateRequest
from app.modules.equipment.service import feishu_app as feishu_app_service
from app.platform.identity.models import User
from app.platform.integrations.feishu.bitable import BitableClient
from app.platform.integrations.feishu.utils import (
    extract_wiki_node_token,
    normalize_app_token,
    normalize_table_id,
    resolve_wiki_bitable_app_token,
)

logger = logging.getLogger(__name__)

_CST = timezone(timedelta(hours=8))

# 镜像列宽（与 ORM 模型一致）；飞书自由文本超宽时截断，原文保留在 raw_fields
_WORKSHOP_TEXT_MAX = 200
_EQUIPMENT_TEXT_MAX = 200
_PERSON_TEXT_MAX = 500
_RESULT_MAX = 100

# 飞书列名关键字 → 镜像字段（按序匹配，先具体后宽泛）
_FIELD_MATCHERS: list[tuple[tuple[str, ...], str]] = [
    (("日期",), "repaired_at"),
    (("人员",), "person_text"),
    (("备件",), "spare_parts"),
    (("状态",), "result"),
    (("车间", "地点"), "workshop_text"),
    (("故障", "原因", "描述"), "fault_desc"),
    (("备注",), "remark"),
    (("设备",), "equipment_text"),
]

# ── 配置 ────────────────────────────────────────────────────────


@dataclass
class RepairEffectiveConfig:
    app_id: str
    app_secret: str
    app_token: str
    table_id: str
    base_url: str
    is_enabled: bool

    @property
    def enabled(self) -> bool:
        return bool(
            self.is_enabled
            and self.app_id
            and self.app_secret
            and self.app_token
            and self.table_id
        )


def _empty_config() -> RepairEffectiveConfig:
    return RepairEffectiveConfig(
        app_id="",
        app_secret="",
        app_token="",
        table_id="",
        base_url="",
        is_enabled=False,
    )


def _row_config(row: RepairFeishuConfig) -> RepairEffectiveConfig:
    app = row.feishu_app
    return RepairEffectiveConfig(
        app_id=(app.app_id if app is not None else "").strip(),
        app_secret=(
            feishu_app_service.decrypt_app_secret(app.app_secret)
            if app is not None
            else ""
        ),
        app_token=(row.app_token or "").strip(),
        table_id=(row.table_id or "").strip(),
        base_url=(row.base_url or "").strip(),
        is_enabled=row.is_enabled,
    )


async def _get_config_row(
    db: AsyncSession, workshop_code: str
) -> RepairFeishuConfig | None:
    result = await db.execute(
        select(RepairFeishuConfig).where(
            RepairFeishuConfig.workshop_code == workshop_code,
            RepairFeishuConfig.is_deleted == False,  # noqa: E712
        )
    )
    return result.scalars().first()


async def get_effective_config(
    db: AsyncSession, workshop_code: str
) -> RepairEffectiveConfig:
    row = await _get_config_row(db, workshop_code)
    return _row_config(row) if row is not None else _empty_config()


async def is_sync_enabled(db: AsyncSession, workshop_code: str) -> bool:
    return (await get_effective_config(db, workshop_code)).enabled


async def list_enabled_workshops(db: AsyncSession) -> list[str]:
    """已启用检修镜像同步的车间代码（调度器按此生成同步任务）。"""
    rows = (
        (
            await db.execute(
                select(RepairFeishuConfig.workshop_code).where(
                    RepairFeishuConfig.is_deleted == False,  # noqa: E712
                    RepairFeishuConfig.is_enabled == True,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )
    return sorted(set(rows))


async def get_config_detail(db: AsyncSession, workshop_code: str) -> dict[str, Any]:
    row = await _get_config_row(db, workshop_code)
    config = _row_config(row) if row is not None else _empty_config()
    return {
        "workshop_code": workshop_code,
        "feishu_app_id": row.feishu_app_id if row is not None else None,
        "app_name": (row.feishu_app.name if row is not None and row.feishu_app else ""),
        "app_id": config.app_id,
        "app_secret_masked": mask_api_key(config.app_secret)
        if config.app_secret
        else "",
        "app_secret_configured": bool(config.app_secret),
        "app_token": config.app_token,
        "table_id": config.table_id,
        "base_url": config.base_url,
        "is_enabled": config.is_enabled,
        "enabled": config.enabled,
        "last_test_status": row.last_test_status if row is not None else None,
        "last_test_error": row.last_test_error if row is not None else None,
        "last_tested_at": row.last_tested_at if row is not None else None,
    }


def _normalized_base_url(value: str | None) -> str:
    stripped = (value or "").strip()
    if not stripped:
        return ""
    if not stripped.startswith("https://"):
        raise AppException(message="多维表格完整链接需以 https:// 开头")
    return stripped[:500]


async def _resolve_app_token(
    *, app_id: str, app_secret: str, raw_app_token: str
) -> str:
    """知识库（/wiki/）链接解析为真实 App Token；其余按 URL/裸 Token 归一。"""
    node_token = extract_wiki_node_token(raw_app_token)
    if node_token:
        if not app_id or not app_secret:
            raise AppException(message="解析知识库链接需先选择已配置 Secret 的应用")
        try:
            return await resolve_wiki_bitable_app_token(
                app_id=app_id,
                app_secret=app_secret,
                node_token=node_token,
            )
        except AppException:
            raise
        except Exception as exc:
            raise AppException(
                message=f"解析知识库多维表格失败：{str(exc)[:200]}"
            ) from exc
    return normalize_app_token(raw_app_token) or ""


async def _resolve_target_app(
    db: AsyncSession, data: RepairConfigUpdateRequest
) -> EquipmentFeishuApp:
    """解析配置指向的飞书应用：下拉选择优先，其次手输登记。"""
    if data.feishu_app_id is not None:
        app = await feishu_app_service.get_app_by_id(db, data.feishu_app_id)
        if app is None:
            raise AppException(message="所选应用不存在或已删除", status_code=404)
        return app

    manual_app_id = data.app_id.strip()
    submitted_secret = (data.app_secret or "").strip()
    if not manual_app_id:
        raise AppException(
            message="请选择已登记应用，或填写新应用的 App ID 与 App Secret"
        )
    app = await feishu_app_service.get_app_by_app_id(db, manual_app_id)
    if app is not None:
        stored_secret = feishu_app_service.decrypt_app_secret(app.app_secret)
        if submitted_secret and submitted_secret != mask_api_key(stored_secret):
            raise AppException(
                message=(
                    f"该 App ID 已登记（{app.name}），请直接下拉选择；"
                    "如需更换密钥请在应用管理中修改"
                ),
            )
        return app
    if not submitted_secret:
        raise AppException(
            message="新 App ID 需同时填写 App Secret（保存后登记为可复用应用）"
        )
    app = EquipmentFeishuApp(
        name=(data.app_name.strip() or manual_app_id),
        app_id=manual_app_id,
        app_secret=encrypt_api_key(submitted_secret),
    )
    db.add(app)
    await db.flush()
    return app


async def update_config(
    db: AsyncSession, workshop_code: str, data: RepairConfigUpdateRequest
) -> dict[str, Any]:
    row = await _get_config_row(db, workshop_code)
    app = await _resolve_target_app(db, data)
    secret = feishu_app_service.decrypt_app_secret(app.app_secret)

    app_token = await _resolve_app_token(
        app_id=app.app_id,
        app_secret=secret,
        raw_app_token=data.app_token.strip(),
    )
    table_id = normalize_table_id(data.table_id) or ""
    if table_id.startswith("vew"):
        raise AppException(
            message=(
                "Table ID 以 vew 开头是视图 ID，"
                "请使用数据表 ID（链接中 table= 参数，以 tbl 开头）"
            ),
        )
    is_enabled = data.is_enabled
    if is_enabled and (not secret or not app_token or not table_id):
        raise AppException(
            message="启用同步需选择已配置 Secret 的应用，并填写多维表格链接与数据表",
        )

    if row is None:
        row = RepairFeishuConfig(workshop_code=workshop_code)
        db.add(row)
    row.feishu_app_id = app.id
    row.is_enabled = is_enabled
    row.app_token = app_token
    row.table_id = table_id
    row.base_url = _normalized_base_url(data.base_url)
    await db.commit()
    return await get_config_detail(db, workshop_code)


async def test_config(db: AsyncSession, workshop_code: str) -> dict[str, Any]:
    """连接测试：用当前配置拉 1 条记录，并把结果落回配置行。"""
    config = await get_effective_config(db, workshop_code)
    row = await _get_config_row(db, workshop_code)
    try:
        if not config.enabled:
            raise AppException(
                message="同步未启用或配置不完整（应用凭据 / 表格链接 / 数据表）"
            )
        client = _build_client(config)
        page = await client.search_records_page(
            config.table_id,
            page_size=1,
            automatic_fields=True,
            timeout=30.0,
        )
        total_text = page.get("total")
        total_label = str(total_text) if total_text is not None else "？"
        result: dict[str, Any] = {
            "success": True,
            "message": f"连接成功，数据表共 {total_label} 条记录",
        }
    except AppException as error:
        result = {"success": False, "message": error.message}
    except Exception as error:  # noqa: BLE001
        # 飞书网络、超时等未知失败：落为一次失败的测试结果，不上升为接口 500；
        # 异常详情可能含接口地址，只保留异常类型
        result = {
            "success": False,
            "message": f"连接测试失败（{type(error).__name__}），请稍后重试并检查网络",
        }
    if row is not None:
        row.last_tested_at = datetime.now(UTC)
        row.last_test_status = "success" if result["success"] else "failed"
        row.last_test_error = None if result["success"] else result["message"]
    await db.commit()
    return result


# ── 飞书字段值规范化 ─────────────────────────────────────────────


def _text_value(value: Any) -> str | None:
    """富文本段列表 / 普通值 → 纯文本。"""
    if value is None:
        return None
    if isinstance(value, list):
        parts = [
            (seg or {}).get("text", "") if isinstance(seg, dict) else str(seg)
            for seg in value
        ]
        joined = "".join(parts).strip()
        return joined or None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return str(value).strip() or None


def _person_segment(seg: Any) -> str | None:
    """单个人员对象 → 显示名：中文名、英文名、open_id 依次兜底。"""
    if isinstance(seg, dict):
        return next(
            (
                str(seg[key])
                for key in ("name", "en_name", "id")
                if isinstance(seg.get(key), str) and seg[key].strip()
            ),
            None,
        )
    return str(seg) if seg is not None else None


def _person_value(value: Any) -> str | None:
    """人员字段（[{id,name}]）/ 文本 → 「张三、李四」。"""
    if value is None:
        return None
    if isinstance(value, list):
        names = [_person_segment(seg) for seg in value]
        joined = "、".join(name.strip() for name in names if name and name.strip())
        return joined or None
    return _text_value(value)


def _date_value(value: Any) -> date | None:
    """毫秒时间戳 / ISO 字符串 → date。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=_CST).date()
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _datetime_value(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=_CST)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None or len(value) <= limit:
        return value
    return value[:limit]


# 需要特殊解析的镜像列；未列出的列一律按文本处理
_TEXT_PARSER: Callable[[Any], Any] = _text_value
_VALUE_PARSERS: dict[str, Callable[[Any], Any]] = {
    "repaired_at": _date_value,
    "person_text": _person_value,
}


def normalize_record_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """飞书记录 fields → 检修记录镜像列；其余列保留在 raw_fields。

    列名按关键字匹配（「维修日期」→ repaired_at、「更换备件」→
    spare_parts…），兼容车间自建表列名的细微出入；同一镜像列
    命中多个飞书列时取最后一个非空值。
    """
    values: dict[str, Any] = {}
    for field_name, field_value in (fields or {}).items():
        for keywords, target in _FIELD_MATCHERS:
            if not any(keyword in field_name for keyword in keywords):
                continue
            parsed = _VALUE_PARSERS.get(target, _TEXT_PARSER)(field_value)
            if parsed is not None:
                values[target] = parsed
            break
    return values


# ── 同步 ────────────────────────────────────────────────────────


def _build_client(config: RepairEffectiveConfig) -> BitableClient:
    return BitableClient(
        app_token=config.app_token,
        app_id=config.app_id,
        app_secret=config.app_secret,
    )


async def _get_state(db: AsyncSession, workshop_code: str) -> RepairSyncState:
    state = (
        await db.execute(
            select(RepairSyncState).where(
                RepairSyncState.workshop_code == workshop_code,
                RepairSyncState.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if state is None:
        state = RepairSyncState(workshop_code=workshop_code, total_rows=0)
        db.add(state)
        await db.flush()
    return state


async def _fetch_all_records(
    client: BitableClient, table_id: str
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        page = await client.search_records_page(
            table_id,
            page_size=500,
            automatic_fields=True,
            timeout=60.0,
            page_token=page_token,
        )
        records.extend(page["items"])
        if not page["has_more"]:
            break
        page_token = page["page_token"]
    return records


# ── 维修人员头像解析 ──────────────────────────────────────────────
# 与菌种页同一套思路：人员字段按 open_id 精确取，手打文本按姓名匹配
# 通讯录（全量拉一次建索引）；通讯录无权限或未匹配时降级为仅姓名，
# 不影响同步本身。


def _extract_person_refs(fields: dict[str, Any]) -> list[dict[str, str]]:
    """「维修人员」列原文 → 待解析引用（open_id / 姓名 / 字段自带头像）。

    飞书人员字段返回 [{"id": "ou_…", "name": …, "avatar_url": …}]——
    头像已随表格数据带回，无需再查通讯录；文本列返回
    ["张三", "李四"] 或纯字符串。列名按关键字「人员」匹配。
    """
    for field_name, value in (fields or {}).items():
        if "人员" not in field_name:
            continue
        refs: list[dict[str, str]] = []
        if isinstance(value, list):
            for seg in value:
                if isinstance(seg, dict):
                    open_id = seg.get("id")
                    if open_id:
                        refs.append(
                            {
                                "open_id": str(open_id),
                                "name": str(seg.get("name") or ""),
                                "avatar_url": str(seg.get("avatar_url") or ""),
                            }
                        )
                elif seg is not None and str(seg).strip():
                    refs.append({"name": str(seg).strip()})
        elif isinstance(value, str) and value.strip():
            refs.append({"name": value.strip()})
        return refs
    return []


class _PersonResolver:
    """一次同步内复用的维修人员解析器（按 open_id / 按姓名）。"""

    def __init__(self, client: BitableClient) -> None:
        # BitableClient 持有底层 FeishuClient，通讯录走同一个应用凭据
        self._request = client.client.request
        self._by_open_id: dict[str, dict[str, Any]] = {}
        self._by_name: dict[str, dict[str, Any]] | None = None
        self._directory_failed = False

    async def _fetch_user(self, open_id: str) -> dict[str, Any]:
        data = await self._request(
            "GET", f"/contact/v3/users/{open_id}", params={"user_id_type": "open_id"}
        )
        user = (data.get("data") or {}).get("user") or {}
        avatar = user.get("avatar") or {}
        return {
            "name": str(user.get("name") or ""),
            "open_id": open_id,
            "avatar_url": avatar.get("avatar_240") or avatar.get("avatar_72") or None,
        }

    async def _name_directory(self) -> dict[str, dict[str, Any]]:
        """全量通讯录建「姓名 → 人」索引；无权限时返回空并记住失败。"""
        if self._by_name is not None or self._directory_failed:
            return self._by_name or {}
        directory: dict[str, dict[str, Any]] = {}
        page_token: str | None = None
        try:
            while True:
                params: dict[str, Any] = {
                    "department_id": "0",
                    "page_size": 50,
                    "user_id_type": "open_id",
                }
                if page_token:
                    params["page_token"] = page_token
                data = await self._request(
                    "GET", "/contact/v3/users/find_by_department", params=params
                )
                payload = data.get("data") or {}
                for user in payload.get("items") or []:
                    name = str(user.get("name") or "").strip()
                    if not name:
                        continue
                    avatar = user.get("avatar") or {}
                    directory.setdefault(
                        name,
                        {
                            "name": name,
                            "open_id": str(user.get("open_id") or "") or None,
                            "avatar_url": avatar.get("avatar_240")
                            or avatar.get("avatar_72")
                            or None,
                        },
                    )
                if not payload.get("has_more"):
                    break
                page_token = payload.get("page_token")
        except Exception:  # noqa: BLE001 —— 通讯录权限缺失等，降级为仅姓名
            logger.warning("repair ledger contact directory unavailable")
            self._directory_failed = True
            return {}
        self._by_name = directory
        return directory

    async def resolve(self, refs: list[dict[str, str]]) -> list[dict[str, Any]] | None:
        """解析一组人员引用；全部解析不到头像时返回 None（展示回退原文）。"""
        resolved: list[dict[str, Any]] = []
        for ref in refs:
            open_id = ref.get("open_id")
            info: dict[str, Any]
            if open_id and ref.get("avatar_url"):
                # 人员字段自带头像：直接采用，不依赖通讯录权限
                info = {
                    "name": ref.get("name") or "",
                    "open_id": open_id,
                    "avatar_url": ref["avatar_url"],
                }
            elif open_id:
                info = await self._resolve_by_open_id(open_id, ref.get("name") or "")
            else:
                info = await self._resolve_by_name(ref.get("name") or "")
            if info.get("name") or info.get("open_id"):
                resolved.append(
                    {
                        "name": str(info.get("name") or info.get("open_id") or ""),
                        "open_id": info.get("open_id") or None,
                        "avatar_url": info.get("avatar_url") or None,
                    }
                )
        # 全部都没有头像时视为未解析（前端回退 person_text 原文展示）
        if not resolved or not any(item["avatar_url"] for item in resolved):
            return None
        return resolved

    async def _resolve_by_open_id(
        self, open_id: str, fallback_name: str
    ) -> dict[str, Any]:
        cached = self._by_open_id.get(open_id)
        if cached is None:
            try:
                cached = await self._fetch_user(open_id)
            except Exception:  # noqa: BLE001 —— 单人失败不影响其余
                logger.warning("repair ledger contact resolve failed: %s", open_id)
                cached = {"name": "", "open_id": open_id, "avatar_url": None}
            self._by_open_id[open_id] = cached
        info = dict(cached)
        info["name"] = info.get("name") or fallback_name
        return info

    async def _resolve_by_name(self, name: str) -> dict[str, Any]:
        if not name:
            return {"name": "", "open_id": None, "avatar_url": None}
        info = (await self._name_directory()).get(name)
        if info is None:
            return {"name": name, "open_id": None, "avatar_url": None}
        return dict(info)


async def sync_workshop(
    db: AsyncSession, workshop_code: str, *, config: RepairEffectiveConfig | None = None
) -> dict[str, Any]:
    """同步一个车间的检修镜像表。返回 {synced, total}；失败抛 AppException。"""
    if config is None:
        config = await get_effective_config(db, workshop_code)
    if not config.enabled:
        raise AppException(message="检修镜像同步未配置（缺少应用凭据或表格 ID）")

    state = await _get_state(db, workshop_code)
    client = _build_client(config)
    try:
        records = await _fetch_all_records(client, config.table_id)
    except AppException:
        raise
    except Exception as error:  # noqa: BLE001
        hint = ""
        if "WrongTableId" in str(error) or "1254004" in str(error):
            hint = "（Table ID 无效：vew 开头是视图 ID，应为 tbl 开头）"
        raise AppException(
            message=f"飞书多维表格访问失败：{str(error)[:200]}{hint}"
        ) from error

    values_by_field_limit = {
        "workshop_text": _WORKSHOP_TEXT_MAX,
        "equipment_text": _EQUIPMENT_TEXT_MAX,
        "person_text": _PERSON_TEXT_MAX,
        "result": _RESULT_MAX,
    }
    person_resolver = _PersonResolver(client)
    keep_ids: set[str] = set()
    for item in records:
        record_id = str(item.get("record_id") or "")
        if not record_id:
            continue
        keep_ids.add(record_id)
        fields = item.get("fields") or {}
        values = normalize_record_fields(fields)
        # 维修人员：人员字段/文本 → 结构化（姓名+头像）；解析不到时为空
        person_refs = _extract_person_refs(fields)
        persons = await person_resolver.resolve(person_refs) if person_refs else None
        column_values: dict[str, Any] = {
            "workshop_code": workshop_code,
            "record_id": record_id,
            "repaired_at": values.get("repaired_at"),
            "fault_desc": values.get("fault_desc"),
            "spare_parts": values.get("spare_parts"),
            "remark": values.get("remark"),
            "persons": persons,
            "raw_fields": fields,
            "last_modified_at": _datetime_value(item.get("last_modified_time")),
        }
        for field, limit in values_by_field_limit.items():
            column_values[field] = _truncate(values.get(field), limit)
        existing = (
            await db.execute(
                select(RepairRecord).where(
                    RepairRecord.workshop_code == workshop_code,
                    RepairRecord.record_id == record_id,
                    RepairRecord.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            for key, value in column_values.items():
                setattr(existing, key, value)
        else:
            db.add(RepairRecord(**column_values))

    # 删除对账：飞书侧已删的行物理删除（镜像表无业务外键）
    stale_rows = (
        (
            await db.execute(
                select(RepairRecord.record_id).where(
                    RepairRecord.workshop_code == workshop_code,
                    RepairRecord.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )
    stale_ids = [rid for rid in stale_rows if rid not in keep_ids]
    if stale_ids:
        await db.execute(
            delete(RepairRecord).where(
                RepairRecord.workshop_code == workshop_code,
                RepairRecord.record_id.in_(stale_ids),
            )
        )

    total = (
        await db.execute(
            select(func.count(RepairRecord.id)).where(
                RepairRecord.workshop_code == workshop_code,
                RepairRecord.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one()
    state.total_rows = int(total)
    state.last_run_at = datetime.now(UTC)
    state.last_status = "success"
    state.last_message = None
    if records:
        newest = max(
            (_datetime_value(item.get("last_modified_time")) for item in records),
            key=lambda dt: dt or datetime.min.replace(tzinfo=UTC),
        )
        if newest is not None:
            state.last_synced_at = max(
                newest, state.last_synced_at or datetime.min.replace(tzinfo=UTC)
            )
    await db.flush()
    logger.info(
        "repair ledger mirror synced: %s fetched=%d total=%d",
        workshop_code,
        len(records),
        total,
    )
    return {"synced": len(records), "total": int(total)}


async def sync_enabled(
    db: AsyncSession, workshop_code: str | None = None
) -> dict[str, dict[str, Any]]:
    """同步一个或全部启用车间；单车间失败不影响其余。"""
    workshops = [workshop_code] if workshop_code else await list_enabled_workshops(db)
    results: dict[str, dict[str, Any]] = {}
    for code in workshops:
        try:
            config = await get_effective_config(db, code)
            if not config.enabled:
                results[code] = {"error": "同步未启用或配置不完整"}
                continue
            results[code] = await sync_workshop(db, code, config=config)
            await db.commit()
        except AppException as error:
            await db.rollback()
            state = await _get_state(db, code)
            state.last_run_at = datetime.now(UTC)
            state.last_status = "failed"
            state.last_message = error.message
            await db.commit()
            results[code] = {"error": error.message}
        except Exception as error:  # noqa: BLE001
            await db.rollback()
            logger.exception("repair ledger sync aborted at %s", code)
            state = await _get_state(db, code)
            state.last_run_at = datetime.now(UTC)
            state.last_status = "failed"
            state.last_message = (
                f"同步中断已回滚：{type(error).__name__}: {str(error)[:200]}"
            )
            await db.commit()
            results[code] = {"error": state.last_message}
    return results


async def get_sync_state(db: AsyncSession, workshop_code: str) -> dict[str, Any]:
    state = await _get_state(db, workshop_code)
    return {
        "workshop_code": workshop_code,
        "total_rows": state.total_rows,
        "last_synced_at": state.last_synced_at,
        "last_run_at": state.last_run_at,
        "last_status": state.last_status,
        "last_message": state.last_message,
        "enabled": await is_sync_enabled(db, workshop_code),
    }


# ── 查询 ────────────────────────────────────────────────────────


def _record_conditions(
    *,
    workshop: str | None = None,
    workshops: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    keyword: str | None = None,
    equipment: str | None = None,
    person: str | None = None,
    fault: str | None = None,
    result_status: str | None = None,
) -> list[Any]:
    """检修记录的公共筛选条件（单车间与跨车间汇总共用）。"""
    conditions: list[Any] = [RepairRecord.is_deleted == False]  # noqa: E712
    if workshop:
        conditions.append(RepairRecord.workshop_code == workshop)
    if workshops:
        conditions.append(RepairRecord.workshop_code.in_(workshops))
    if date_from is not None:
        conditions.append(RepairRecord.repaired_at >= date_from)
    if date_to is not None:
        conditions.append(RepairRecord.repaired_at <= date_to)
    if equipment:
        conditions.append(RepairRecord.equipment_text == equipment)
    if person:
        # 姓名可能来自结构化 persons，也可能只留在原文 person_text
        pattern = f"%{person.strip()}%"
        conditions.append(
            or_(
                RepairRecord.person_text.ilike(pattern),
                func.cast(RepairRecord.persons, String).ilike(pattern),
            )
        )
    if fault:
        conditions.append(RepairRecord.fault_desc.ilike(f"%{fault.strip()}%"))
    if result_status:
        conditions.append(RepairRecord.result == result_status)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        conditions.append(
            or_(
                RepairRecord.equipment_text.ilike(pattern),
                RepairRecord.fault_desc.ilike(pattern),
                RepairRecord.person_text.ilike(pattern),
                RepairRecord.workshop_text.ilike(pattern),
            )
        )
    return conditions


async def list_records(
    db: AsyncSession,
    *,
    workshop: str | None = None,
    workshops: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    keyword: str | None = None,
    equipment: str | None = None,
    person: str | None = None,
    fault: str | None = None,
    result_status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[RepairRecord], int]:
    """检修记录分页查询；workshop 缺省跨车间。"""
    conditions = _record_conditions(
        workshop=workshop,
        workshops=workshops,
        date_from=date_from,
        date_to=date_to,
        keyword=keyword,
        equipment=equipment,
        person=person,
        fault=fault,
        result_status=result_status,
    )
    stmt = select(RepairRecord).where(*conditions)
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        (
            await db.execute(
                stmt.order_by(
                    desc(RepairRecord.repaired_at), desc(RepairRecord.created_at)
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


async def frequency(
    db: AsyncSession,
    *,
    workshop: str | None = None,
    date_from: date | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """设备维修频次排行：按设备名称原文聚合次数与最近维修日期。"""
    conditions = [
        RepairRecord.is_deleted == False,  # noqa: E712
        RepairRecord.equipment_text.isnot(None),
    ]
    if workshop:
        conditions.append(RepairRecord.workshop_code == workshop)
    if date_from is not None:
        conditions.append(RepairRecord.repaired_at >= date_from)
    rows = (
        await db.execute(
            select(
                RepairRecord.equipment_text,
                func.count(RepairRecord.id).label("times"),
                func.max(RepairRecord.repaired_at).label("last_repaired_at"),
            )
            .where(*conditions)
            .group_by(RepairRecord.equipment_text)
            .order_by(desc("times"), desc("last_repaired_at"))
            .limit(limit)
        )
    ).all()
    return [
        {
            "equipment_text": equipment_text,
            "times": int(times),
            "last_repaired_at": last_repaired_at,
        }
        for equipment_text, times, last_repaired_at in rows
    ]


async def distinct_results(db: AsyncSession, workshop: str | None) -> list[str]:
    """维修后状态去重列表（筛选用）。"""
    conditions = [
        RepairRecord.is_deleted == False,  # noqa: E712
        RepairRecord.result.isnot(None),
    ]
    if workshop:
        conditions.append(RepairRecord.workshop_code == workshop)
    rows = (
        (
            await db.execute(
                select(RepairRecord.result)
                .where(*conditions)
                .distinct()
                .order_by(RepairRecord.result)
            )
        )
        .scalars()
        .all()
    )
    return [str(value) for value in rows]


async def filter_options(
    db: AsyncSession, workshop: str | None
) -> dict[str, list[str]]:
    """筛选下拉的去重选项：维修人员 / 故障描述 / 设备名称。

    人员优先取结构化 persons 的姓名，回退 person_text 原文按顿号拆分；
    故障与设备按出现次数降序（高频问题排前面，选起来更快）。
    """
    conditions = [RepairRecord.is_deleted == False]  # noqa: E712
    if workshop:
        conditions.append(RepairRecord.workshop_code == workshop)

    person_rows = (
        await db.execute(
            select(
                func.jsonb_array_elements(RepairRecord.persons)
                .op("->>")("name")
                .label("name"),
                func.count(func.distinct(RepairRecord.id)).label("times"),
            )
            .where(*conditions, RepairRecord.persons.isnot(None))
            .group_by("name")
            .order_by(func.count(func.distinct(RepairRecord.id)).desc(), "name")
        )
    ).all()
    persons = {str(row.name): int(row.times) for row in person_rows if row.name}
    # 未解析的原文按顿号拆出的人名也计入（次数按行数近似）
    text_rows = (
        (
            await db.execute(
                select(RepairRecord.person_text).where(
                    *conditions, RepairRecord.person_text.isnot(None)
                )
            )
        )
        .scalars()
        .all()
    )
    for raw in text_rows:
        for name in str(raw).split("、"):
            name = name.strip()
            if name:
                persons[name] = persons.get(name, 0) + 1

    async def ranked(column: InstrumentedAttribute[str | None]) -> list[str]:
        rows_ = (
            await db.execute(
                select(column, func.count())
                .where(*conditions, column.isnot(None))
                .group_by(column)
                .order_by(func.count().desc(), column)
                .limit(500)
            )
        ).all()
        return [str(row[0]) for row in rows_]

    return {
        "persons": sorted(persons, key=lambda name: (-persons[name], name)),
        "faults": await ranked(RepairRecord.fault_desc),
        "equipments": await ranked(RepairRecord.equipment_text),
    }


# ── 跨车间检修汇总 ───────────────────────────────────────────────

# 汇总一次拉取的最大记录数：超过时要求缩小时间范围，避免页面聚合失控
_SUMMARY_MAX_ROWS = 20_000
# 口径：状态原文包含以下关键词即计入「异常/待处理」
_ABNORMAL_KEYWORDS = ("停机", "待处理", "未完成", "待观察")
# 统计跨度超过该天数时，趋势按月聚合（否则按周）
_TREND_MONTHLY_THRESHOLD_DAYS = 120


def _person_names(record: RepairRecord) -> list[str]:
    """记录里的维修人员姓名：结构化 persons 优先，回退原文按分隔符拆分。"""
    names: list[str] = []
    for item in record.persons or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = str(item).strip()
        if name:
            names.append(name)
    if not names and record.person_text:
        names = [
            part.strip()
            for part in re.split(r"[、,，/]", record.person_text)
            if part.strip()
        ]
    return list(dict.fromkeys(names))


def _trend_period(value: date, granularity: str) -> str:
    if granularity == "month":
        return value.strftime("%Y-%m")
    return (value - timedelta(days=value.weekday())).isoformat()


async def summary(
    db: AsyncSession,
    *,
    workshops: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    keyword: str | None = None,
    equipment: str | None = None,
    person: str | None = None,
    fault: str | None = None,
    result_status: str | None = None,
    top_limit: int = 10,
) -> dict[str, Any]:
    """跨车间检修汇总：KPI、车间对比、高频榜单与趋势。

    与单车间列表使用同一套筛选条件；设备按「车间+设备名称原文」分组，
    不跨车间合并（原文可能同名不同物）。无迁移，只读聚合。
    """
    conditions = _record_conditions(
        workshops=workshops,
        date_from=date_from,
        date_to=date_to,
        keyword=keyword,
        equipment=equipment,
        person=person,
        fault=fault,
        result_status=result_status,
    )
    rows = list(
        (
            await db.execute(
                select(RepairRecord)
                .where(*conditions)
                .order_by(
                    desc(RepairRecord.repaired_at), desc(RepairRecord.created_at)
                )
                .limit(_SUMMARY_MAX_ROWS + 1)
            )
        )
        .scalars()
        .all()
    )
    if len(rows) > _SUMMARY_MAX_ROWS:
        raise AppException(
            message=(
                f"符合条件的记录超过 {_SUMMARY_MAX_ROWS} 条，"
                "请缩小时间范围或筛选条件后再汇总"
            ),
            status_code=400,
        )

    # 车间清单：启用车间 + 本次记录中出现的车间；车间筛选时只留选中项
    from app.modules.equipment.service import workshop as workshop_service

    enabled = await workshop_service.list_enabled(db)
    universe: dict[str, str] = {item.code: item.name for item in enabled}
    if workshops:
        selected = set(workshops)
        universe = {
            code: name for code, name in universe.items() if code in selected
        }
        for code in workshops:
            universe.setdefault(code, code)
    for record in rows:
        universe.setdefault(record.workshop_code, record.workshop_code)

    stats: dict[str, dict[str, Any]] = {
        code: {
            "name": name,
            "count": 0,
            "equipment": set(),
            "persons": set(),
            "abnormal": 0,
            "last": None,
        }
        for code, name in universe.items()
    }

    equipment_counts: dict[tuple[str, str], int] = {}
    equipment_last: dict[tuple[str, str], date] = {}
    equipment_keys: set[tuple[str, str]] = set()
    fault_counts: dict[str, int] = {}
    fault_equipment: dict[str, set[tuple[str, str]]] = {}
    fault_workshops: dict[str, dict[str, int]] = {}
    fault_last: dict[str, date] = {}
    person_info: dict[str, dict[str, Any]] = {}
    trend_counts: dict[tuple[str, str], int] = {}
    trend_equipment: dict[tuple[str, str], set[str]] = {}

    dates = [record.repaired_at for record in rows if record.repaired_at]
    if date_from is not None:
        effective_to = date_to or date.today()
        days = max((effective_to - date_from).days + 1, 1)
    elif dates:
        days = max((max(dates) - min(dates)).days + 1, 1)
    else:
        days = 1
    granularity = (
        "month"
        if date_from is None or days > _TREND_MONTHLY_THRESHOLD_DAYS
        else "week"
    )

    abnormal_count = 0
    for record in rows:
        code = record.workshop_code
        state = stats[code]
        state["count"] += 1

        equipment_text = (record.equipment_text or "").strip()
        if equipment_text:
            key = (code, equipment_text)
            state["equipment"].add(equipment_text)
            equipment_keys.add(key)
            equipment_counts[key] = equipment_counts.get(key, 0) + 1
            if record.repaired_at is not None:
                previous = equipment_last.get(key)
                if previous is None or record.repaired_at > previous:
                    equipment_last[key] = record.repaired_at

        for name in _person_names(record):
            state["persons"].add(name)
            info = person_info.setdefault(
                name,
                {
                    "times": 0,
                    "workshops": set(),
                    "workshop_times": {},
                    "last": None,
                    "open_id": None,
                    "avatar_url": None,
                },
            )
            info["times"] += 1
            info["workshops"].add(code)
            workshop_times = info["workshop_times"]
            workshop_times[code] = workshop_times.get(code, 0) + 1
            if record.repaired_at is not None:
                last = info["last"]
                if last is None or record.repaired_at > last:
                    info["last"] = record.repaired_at
        for item in record.persons or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            ref = person_info.get(name)
            if ref is None:
                continue
            if not ref["open_id"] and item.get("open_id"):
                ref["open_id"] = str(item["open_id"])
            if not ref["avatar_url"] and item.get("avatar_url"):
                ref["avatar_url"] = str(item["avatar_url"])

        is_abnormal = bool(
            record.result
            and any(keyword in record.result for keyword in _ABNORMAL_KEYWORDS)
        )
        if is_abnormal:
            abnormal_count += 1
            state["abnormal"] += 1

        if record.repaired_at is not None:
            last = state["last"]
            if last is None or record.repaired_at > last:
                state["last"] = record.repaired_at

        fault_text = re.sub(r"\s+", "", record.fault_desc or "").strip()
        if fault_text:
            fault_counts[fault_text] = fault_counts.get(fault_text, 0) + 1
            workshop_counts = fault_workshops.setdefault(fault_text, {})
            workshop_counts[code] = workshop_counts.get(code, 0) + 1
            if equipment_text:
                fault_equipment.setdefault(fault_text, set()).add(
                    (code, equipment_text)
                )
            if record.repaired_at is not None:
                last = fault_last.get(fault_text)
                if last is None or record.repaired_at > last:
                    fault_last[fault_text] = record.repaired_at

        if record.repaired_at is not None:
            period = _trend_period(record.repaired_at, granularity)
            trend_key = (period, code)
            trend_counts[trend_key] = trend_counts.get(trend_key, 0) + 1
            if equipment_text:
                trend_equipment.setdefault(trend_key, set()).add(equipment_text)

    previous_total: int | None = None
    change_rate: float | None = None
    if date_from is not None:
        previous_to = date_from - timedelta(days=1)
        previous_from = previous_to - timedelta(days=days - 1)
        previous_conditions = _record_conditions(
            workshops=workshops,
            date_from=previous_from,
            date_to=previous_to,
            keyword=keyword,
            equipment=equipment,
            person=person,
            fault=fault,
            result_status=result_status,
        )
        previous_total = int(
            (
                await db.execute(
                    select(func.count(RepairRecord.id)).where(
                        *previous_conditions
                    )
                )
            ).scalar_one()
        )
        if previous_total:
            change_rate = round(
                (len(rows) - previous_total) / previous_total * 100, 1
            )

    config_rows = (
        (
            await db.execute(
                select(RepairFeishuConfig).where(
                    RepairFeishuConfig.is_deleted == False  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )
    state_rows = (
        (
            await db.execute(
                select(RepairSyncState).where(
                    RepairSyncState.is_deleted == False  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )
    configs = {row.workshop_code: row for row in config_rows}
    sync_states = {row.workshop_code: row for row in state_rows}

    workshop_items: list[dict[str, Any]] = []
    for code, state in stats.items():
        config = configs.get(code)
        configured = bool(config and config.app_token and config.table_id)
        enabled_sync = bool(
            config is not None and configured and config.is_enabled
        )
        sync_state = sync_states.get(code)
        if not configured:
            status = "not_configured"
        elif not enabled_sync:
            status = "disabled"
        elif sync_state and sync_state.last_status == "failed":
            status = "sync_failed"
        elif state["count"] == 0:
            status = "no_records"
        else:
            status = "normal"
        workshop_items.append(
            {
                "workshop_code": code,
                "workshop_name": state["name"],
                "repair_count": state["count"],
                "equipment_count": len(state["equipment"]),
                "person_count": len(state["persons"]),
                "abnormal_count": state["abnormal"],
                "last_repaired_at": state["last"],
                "last_synced_at": (
                    sync_state.last_synced_at if sync_state else None
                ),
                "last_sync_status": (
                    sync_state.last_status if sync_state else None
                ),
                "configured": configured,
                "enabled": enabled_sync,
                "status": status,
            }
        )
    workshop_items.sort(
        key=lambda item: (-item["repair_count"], item["workshop_code"])
    )

    top_equipment = [
        {
            "workshop_code": code,
            "workshop_name": stats[code]["name"],
            "equipment_text": equipment_text,
            "times": times,
            "last_repaired_at": equipment_last.get((code, equipment_text)),
        }
        for (code, equipment_text), times in sorted(
            equipment_counts.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        )[:top_limit]
    ]

    top_faults = [
        {
            "fault_desc": fault_text,
            "times": times,
            "equipment_count": len(fault_equipment.get(fault_text, set())),
            "workshops": [
                {
                    "workshop_code": code,
                    "workshop_name": stats[code]["name"],
                    "times": workshop_times,
                }
                for code, workshop_times in sorted(
                    fault_workshops.get(fault_text, {}).items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ],
            "last_repaired_at": fault_last.get(fault_text),
        }
        for fault_text, times in sorted(
            fault_counts.items(),
            key=lambda item: (
                -item[1],
                -len(fault_equipment.get(item[0], set())),
                item[0],
            ),
        )[:top_limit]
    ]

    top_persons = [
        {
            "name": name,
            "open_id": info["open_id"],
            "avatar_url": info["avatar_url"],
            "times": info["times"],
            "workshop_count": len(info["workshops"]),
            "workshops": [
                {
                    "workshop_code": code,
                    "workshop_name": stats[code]["name"],
                    "times": workshop_times,
                }
                for code, workshop_times in sorted(
                    info["workshop_times"].items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ],
            "last_repaired_at": info["last"],
        }
        for name, info in sorted(
            person_info.items(), key=lambda item: (-item[1]["times"], item[0])
        )[:top_limit]
    ]

    trend = [
        {
            "period": period,
            "workshop_code": code,
            "workshop_name": stats[code]["name"],
            "count": count,
            "equipment_count": len(trend_equipment.get((period, code), set())),
        }
        for (period, code), count in sorted(
            trend_counts.items(), key=lambda item: (item[0][0], item[0][1])
        )
    ]

    return {
        "kpi": {
            "total_count": len(rows),
            "equipment_count": len(equipment_keys),
            "workshop_count": sum(
                1 for state in stats.values() if state["count"] > 0
            ),
            "total_workshops": len(stats),
            "person_count": len(person_info),
            "abnormal_count": abnormal_count,
            "daily_average": round(len(rows) / days, 1),
            "previous_total_count": previous_total,
            "change_rate": change_rate,
        },
        "workshops": workshop_items,
        "top_equipment": top_equipment,
        "top_faults": top_faults,
        "top_persons": top_persons,
        "trend": trend,
        "trend_granularity": granularity,
    }


# ── 检修汇总全厂默认设置 ─────────────────────────────────────────

_SUMMARY_SETTINGS_SCOPE = "global"
_SUMMARY_SORT_FIELDS = frozenset(
    {
        "workshop",
        "repair_count",
        "equipment_count",
        "abnormal_count",
        "person_count",
        "last_repaired_at",
    }
)
_SUMMARY_RANGE_KEYS = frozenset({"30d", "90d", "year", "last-year", "all"})
_SUMMARY_DEFAULT_SETTINGS: dict[str, Any] = {
    "sort_field": "workshop",
    "sort_order": "ascend",
    "range_key": "30d",
    "workshops": None,
}


async def _summary_settings_row(
    db: AsyncSession,
) -> RepairSummarySettings | None:
    rows = (
        await db.execute(
            select(RepairSummarySettings).where(
                RepairSummarySettings.scope == _SUMMARY_SETTINGS_SCOPE,
                RepairSummarySettings.is_deleted == False,  # noqa: E712
            )
        )
    ).scalars()
    return rows.first()


async def get_summary_settings(db: AsyncSession) -> dict[str, Any]:
    """读取全厂默认设置；没有配置行时返回系统默认。"""
    row = await _summary_settings_row(db)
    if row is None:
        return {
            **_SUMMARY_DEFAULT_SETTINGS,
            "updated_by_name": None,
            "updated_at": None,
        }
    updated_by_name = None
    if row.updated_by is not None:
        updated_by_name = (
            await db.execute(
                select(User.name).where(User.id == row.updated_by)
            )
        ).scalar_one_or_none()
    return {
        "sort_field": row.sort_field,
        "sort_order": row.sort_order,
        "range_key": row.range_key,
        "workshops": row.workshops,
        "updated_by_name": updated_by_name,
        "updated_at": row.updated_at,
    }


async def can_edit_summary_settings(
    db: AsyncSession, user: User | None
) -> bool:
    """保存默认设置需要设备检修页的 operate 授权（管理员由权限服务放行）。"""
    if user is None:
        return False
    from app.platform.identity.page_permissions import PagePermissionService

    grants = await PagePermissionService().effective_grants(db, user=user)
    return any(
        grant.page_key == "equipment:maintenance"
        and "operate" in grant.permissions
        for grant in grants
    )


async def update_summary_settings(
    db: AsyncSession,
    *,
    sort_field: str,
    sort_order: str,
    range_key: str,
    workshops: list[str] | None,
    updated_by: uuid.UUID | None,
) -> dict[str, Any]:
    """保存全厂默认设置；车间列表按当前启用车间过滤。"""
    if sort_field not in _SUMMARY_SORT_FIELDS:
        raise AppException(message="排序字段不正确", status_code=400)
    if sort_order not in {"ascend", "descend"}:
        raise AppException(message="排序方向不正确", status_code=400)
    if range_key not in _SUMMARY_RANGE_KEYS:
        raise AppException(message="时间范围不正确", status_code=400)

    from app.modules.equipment.service import workshop as workshop_service

    enabled_codes = {
        item.code for item in await workshop_service.list_enabled(db)
    }
    codes = [code for code in (workshops or []) if code in enabled_codes]

    row = await _summary_settings_row(db)
    if row is None:
        row = RepairSummarySettings(scope=_SUMMARY_SETTINGS_SCOPE)
        db.add(row)
    row.sort_field = sort_field
    row.sort_order = sort_order
    row.range_key = range_key
    row.workshops = codes or None
    row.updated_by = updated_by
    await db.commit()
    await db.refresh(row)
    return await get_summary_settings(db)


async def reset_summary_settings(
    db: AsyncSession, *, updated_by: uuid.UUID | None
) -> dict[str, Any]:
    """恢复系统默认设置（保留修改人/时间便于追溯）。"""
    return await update_summary_settings(
        db,
        sort_field="workshop",
        sort_order="ascend",
        range_key="30d",
        workshops=None,
        updated_by=updated_by,
    )


# 导出 Excel 列定义：主表 6 列 + 展开卡独有的车间及地点、备注
EXPORT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("repaired_at", "维修日期"),
    ("workshop_text", "车间及地点"),
    ("equipment_text", "设备名称/型号"),
    ("fault_desc", "故障描述/原因"),
    ("person_text", "维修人员"),
    ("spare_parts", "更换备件"),
    ("result", "维修后状态"),
    ("remark", "备注"),
)
_EXPORT_MAX_ROWS = 10_000
# 各列建议宽度（字符）：日期/状态窄、设备与故障宽、备注最宽
_EXPORT_COLUMN_WIDTHS = (12, 20, 24, 32, 18, 24, 12, 28)


async def export_records_xlsx(
    db: AsyncSession,
    *,
    workshop: str | None = None,
    workshops: list[str] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    keyword: str | None = None,
    equipment: str | None = None,
    person: str | None = None,
    fault: str | None = None,
    result_status: str | None = None,
) -> tuple[bytes, int]:
    """按当前筛选条件导出全部命中记录为 xlsx，返回（文件字节, 行数）。

    与 list_records 同一套筛选；超过上限抛业务错误提示收窄范围。
    """
    rows, total = await list_records(
        db,
        workshop=workshop,
        workshops=workshops,
        date_from=date_from,
        date_to=date_to,
        keyword=keyword,
        equipment=equipment,
        person=person,
        fault=fault,
        result_status=result_status,
        page=1,
        page_size=_EXPORT_MAX_ROWS + 1,
    )
    if total > _EXPORT_MAX_ROWS:
        raise AppException(
            message=(
                f"符合条件的记录共 {total} 条，超过导出上限 {_EXPORT_MAX_ROWS} 条，"
                "请缩小时间范围或筛选条件后重试"
            )
        )

    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.worksheet import Worksheet

    workbook = Workbook()
    # Workbook.active 的类型标注是可选联合，新建工作簿必有活动页
    sheet = workbook.active
    assert isinstance(sheet, Worksheet)
    sheet.title = "检修记录"
    header_fill = PatternFill("solid", fgColor="F2F1EE")
    header_font = Font(bold=True)
    for col, (_, title) in enumerate(EXPORT_COLUMNS, start=1):
        cell = sheet.cell(row=1, column=col, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")
    for col, width in enumerate(_EXPORT_COLUMN_WIDTHS, start=1):
        sheet.column_dimensions[get_column_letter(col)].width = width
    for row_index, record in enumerate(rows, start=2):
        for col, (key, _) in enumerate(EXPORT_COLUMNS, start=1):
            value = getattr(record, key)
            if key == "repaired_at":
                # 日期列写成真正的日期类型，Excel 里可继续排序/筛选
                sheet.cell(
                    row=row_index, column=col, value=value
                ).number_format = "yyyy-mm-dd"
            else:
                sheet.cell(row=row_index, column=col, value=value or "")
    sheet.freeze_panes = "A2"

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue(), len(rows)
