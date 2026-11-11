"""8 大作业票「飞书聊天全流程」业务服务。

状态机：``wp_form:{open_id}:{permit_type}``（Redis JSON，30 分钟滑动过期）：
``{type, level, step, values, sign: {sign_key: image_key}, summary_message_id}``

职责：
- 发起：意图/菜单 → 分步卡片（默认模板预填）；
- 分步保存/上一步/取消；
- 提交：发起行签名齐全校验 → 建票 → 发起签名落库 → 默认模板落库 →
  引擎 submit（默认审批人）→ 推审批卡给第一级审批人；
- 审批：签名（免登手写板已落库）或复用最近签名 → 引擎 approve →
  推下一级审批卡 / 验票卡；
- 验票 / 完工验收 / 作业期间复检录入（卡片表单提交）。

卡片渲染在 ``work_permit_card_forms``；推卡通道在 ``work_permit_notify``。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.redis import cache_delete, cache_get, cache_set
from app.modules.safety.models import (
    WorkPermitFormDefault,
    WorkPermitSignature,
)
from app.modules.safety.schemas.work_permit import WorkPermitCreate
from app.modules.safety.service import work_permit as permit_service
from app.modules.safety.service.work_permit_card_forms import (
    base_form_values,
    build_menu_card,
    build_receipt_card,
    build_step_card,
    build_summary_card,
    next_step,
    prev_step,
    steps_for,
)
from app.modules.safety.service.work_permit_signatures import (
    reuse_or_none,
    save_signature_row,
)
from app.modules.safety.service.work_permit_templates import (
    PERMIT_TEMPLATES,
    PERSON_ROLE_LABELS,
    get_template,
)
from app.platform.identity.models import User

logger = logging.getLogger(__name__)

FORM_TTL_SECONDS = 1800
INITIATOR_SIGN_KEYS = ("initiator", "briefer", "briefer_receiver")

_INTENT_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("动火", "hot_work"),
    ("受限", "confined_space"),
    ("高处", "height_work"),
    ("吊装", "lifting"),
    ("临时用电", "temporary_electricity"),
    ("临电", "temporary_electricity"),
    ("动土", "excavation"),
    ("断路", "road_breaking"),
    ("盲板", "blind_plate"),
)


def _state_key(open_id: str, permit_type: str) -> str:
    return f"wp_form:{open_id}:{permit_type}"


def parse_intent(text: str) -> dict[str, Any]:
    """文本意图：返回 {act, permit_type?}。"""
    normalized = (text or "").strip()
    if not normalized:
        return {"act": "unknown"}
    for keyword, permit_type in _INTENT_KEYWORDS:
        if keyword in normalized:
            return {"act": "start_form", "permit_type": permit_type}
    if any(word in normalized for word in ("菜单", "帮助", "作业票", "怎么")):
        return {"act": "menu"}
    if "复检" in normalized:
        return {"act": "gas_list"}
    if "取消" in normalized:
        return {"act": "cancel"}
    return {"act": "unknown"}


class ChatFlowService:
    """聊天卡片流程：状态机 + 提交/审批处理。"""

    def __init__(self, db: AsyncSession, *, open_id: str, union_id: str = "") -> None:
        self.db = db
        self.open_id = open_id
        self.union_id = union_id
        self.user: User | None = None

    # ── 基础 ──

    async def ensure_user(self) -> User:
        if self.user is not None:
            return self.user
        result = await self.db.execute(
            select_user_by_open_id(self.open_id, self.union_id)
        )
        user: User | None = result.scalar_one_or_none()
        if user is None:
            raise AppException(
                status_code=403,
                message="当前飞书账号未绑定平台用户，请联系管理员绑定后使用",
            )
        # 回写当前应用维度的 open_id（open_id 跨应用不通用；通讯录选人
        # 回传的是本应用 open_id，回写后人员解析可直接命中）
        if self.open_id and user.feishu_open_id != self.open_id:
            user.feishu_open_id = self.open_id
            try:
                await self.db.commit()
            except Exception:
                logger.exception("回写飞书 open_id 失败: %s", user.id)
                await self.db.rollback()
        self.user = user
        return user

    async def _load_state(self, permit_type: str) -> dict[str, Any] | None:
        raw = await cache_get(_state_key(self.open_id, permit_type))
        if not raw:
            return None
        try:
            state = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return state if isinstance(state, dict) else None

    async def _save_state(self, state: dict[str, Any]) -> None:
        await cache_set(
            _state_key(self.open_id, state["type"]),
            json.dumps(state, ensure_ascii=False, default=str),
            ex=FORM_TTL_SECONDS,
        )

    async def clear_state(self, permit_type: str) -> None:
        await cache_delete(_state_key(self.open_id, permit_type))

    # ── 发起 ──

    async def start_form(self, permit_type: str) -> dict[str, Any]:
        user = await self.ensure_user()
        if permit_type not in PERMIT_TEMPLATES:
            raise AppException(status_code=422, message="未知票种")
        defaults_row = await self.db.execute(
            select_defaults(user.id, permit_type)
        )
        default_row = defaults_row.scalar_one_or_none()
        defaults = (default_row.values if default_row else None) or {}
        values = base_form_values(permit_type, defaults)
        values["level"] = _sanitize_level(permit_type, values.get("level"))
        # 实施时间不沿用历史记忆（避免旧日期导致时长超有效期），
        # 默认当天 08:00–17:00（选择器无默认值，状态里兜底）
        today = datetime.now().strftime("%Y-%m-%d")
        values["planned_start"] = f"{today} 08:00"
        values["planned_end"] = f"{today} 17:00"
        state: dict[str, Any] = {
            "type": permit_type,
            "step": 1,
            "values": values,
            "sign": dict(defaults.get("sign") or {}) if defaults else {},
        }
        await self._save_state(state)
        return build_step_card(permit_type, 1, state["values"], self.open_id)

    async def save_step(
        self,
        permit_type: str,
        step: int,
        form_value: dict[str, Any],
        *,
        message_id: str = "",
    ) -> dict[str, Any]:
        state = await self._load_state(permit_type)
        if state is None:
            raise AppException(status_code=410, message="表单已过期，请重新发起")
        values = state.setdefault("values", {})
        if step == 2:
            # 人员步需查库（选人解析 + 证件自动关联），走异步合并
            await self._merge_persons(permit_type, values, form_value)
        else:
            _merge_form_values(permit_type, step, values, form_value)
        # 第①步就地校验（时间倒置/超有效期）：停留本步回卡提示，不抛错
        if step == 1:
            warn = await self._step1_warnings(permit_type, values)
            if warn:
                await self._save_state(state)
                card = build_step_card(permit_type, 1, values, self.open_id)
                card["body"]["elements"].insert(
                    0, {"tag": "markdown", "content": f"⚠️ **{warn}**"}
                )
                return card
        # 第⑥步就地校验：未指派且无默认审批人的节点，停留本步提示
        if step == 6:
            missing = self._missing_approvers(permit_type, values)
            if missing:
                await self._save_state(state)
                card = build_step_card(permit_type, 6, values, self.open_id)
                card["body"]["elements"].insert(
                    0,
                    {
                        "tag": "markdown",
                        "content": (
                            "⚠️ **以下审批节点还没有审批人**："
                            + "、".join(missing)
                            + "。请从通讯录选择，或先在平台维护默认审批人。"
                        ),
                    },
                )
                return card
        next_s = next_step(permit_type, step)
        # 最后一步（汇总）即终点：直接返回汇总卡（next_step 对最末步才返回
        # None，若只判 None 会导致倒数第二步保存后落在占位卡"汇总生成中…"）
        at_summary = next_s is None or next_s == steps_for(permit_type)[-1]
        state["step"] = next_s or step
        if at_summary and message_id:
            # 进入汇总步：记录原消息 id，签名后按此 PATCH 刷新
            state["summary_message_id"] = message_id
        await self._save_state(state)
        if next_s == 6:
            # 进入审批人指派步：注入默认审批人姓名供提示
            await self._inject_approver_defaults(permit_type, values)
            await self._save_state(state)
            return build_step_card(permit_type, 6, values, self.open_id)
        if at_summary:
            await self._resolve_assignment_names(values)
            await self._save_state(state)
            return await self.build_summary(permit_type)
        assert next_s is not None  # at_summary 已提前返回
        return build_step_card(permit_type, next_s, values, self.open_id)

    async def _inject_approver_defaults(
        self, permit_type: str, values: dict[str, Any]
    ) -> None:
        """查各 approve 节点的默认审批人姓名（WorkPermitApproverConfig）。"""
        from app.modules.safety.models import WorkPermitApproverConfig
        from app.modules.safety.service.work_permit_templates import (
            active_nodes_for_level,
        )

        level = str(values.get("level") or "none")
        node_keys = [
            str(n.get("key"))
            for n in active_nodes_for_level(permit_type, level)
            if str(n.get("kind")) == "approve"
        ]
        if not node_keys:
            values["approver_defaults"] = {}
            return
        rows = (
            await self.db.execute(
                select(WorkPermitApproverConfig.node_key, User.name)
                .join(
                    User,
                    User.id == WorkPermitApproverConfig.approver_user_id,
                )
                .where(
                    WorkPermitApproverConfig.permit_type == permit_type,
                    WorkPermitApproverConfig.node_key.in_(node_keys),
                    WorkPermitApproverConfig.is_deleted.is_(False),
                )
            )
        ).all()
        values["approver_defaults"] = {row[0]: row[1] or "" for row in rows}

    async def _resolve_assignment_names(
        self, values: dict[str, Any]
    ) -> None:
        """把已指派的飞书人员 id 解析为平台用户名（汇总展示用）。"""
        raw = values.get("assignments") or {}
        if not raw:
            values["assignment_names"] = {}
            return
        names: dict[str, str] = {}
        for node_key, feishu_id in raw.items():
            user = await self._user_by_feishu_id(str(feishu_id))
            names[node_key] = user.name if user else str(feishu_id)
        values["assignment_names"] = names

    async def _user_by_feishu_id(self, feishu_id: str) -> User | None:
        """select_person 回传 id 兼容解析：open_id / union_id / 工号。

        通讯录选人回传的是本应用 open_id（跨应用不通用）；本库命中不到时
        经飞书通讯录 API 取 tenant user_id / 姓名再匹配，避免显示 ou_id。
        """
        from sqlalchemy import or_

        result = await self.db.execute(
            select(User)
            .where(
                or_(
                    User.feishu_open_id == feishu_id,
                    User.feishu_union_id == feishu_id,
                    User.username == feishu_id,
                ),
                User.is_deleted.is_(False),
            )
            .limit(1)
        )
        user = result.scalar_one_or_none()
        if user is not None:
            return user
        name, tenant_user_id = await feishu_user_info(feishu_id)
        if tenant_user_id:
            by_username = await self.db.execute(
                select(User)
                .where(
                    User.username == tenant_user_id,
                    User.is_deleted.is_(False),
                )
                .limit(1)
            )
            user = by_username.scalar_one_or_none()
            if user is not None:
                return user
        if name:
            by_name = await self.db.execute(
                select(User)
                .where(User.name == name, User.is_deleted.is_(False))
                .limit(1)
            )
            return by_name.scalar_one_or_none()
        return None

    async def _merge_persons(
        self,
        permit_type: str,
        values: dict[str, Any],
        form_value: dict[str, Any],
    ) -> None:
        """第②步人员合并：通讯录选人（自动关联证件）+ 外部人员手工录入。"""
        template = get_template(permit_type)
        existing_map = {
            str(p.get("role")): p for p in (values.get("persons") or [])
        }
        persons: list[dict[str, Any]] = []
        for role in template.person_roles:
            role_key = str(role["role"])
            picked = form_value.get(f"person__{role_key}")
            if isinstance(picked, (list, tuple)):
                picked = picked[0] if picked else ""
            picked_text = str(picked or "").strip()
            ext_name = _optional(form_value.get(f"person_ext_name__{role_key}"))
            ext_cert = _optional(form_value.get(f"person_ext_cert__{role_key}"))
            prev = existing_map.get(role_key) or {}
            if picked_text:
                user = await self._user_by_feishu_id(picked_text)
                if user is None:
                    # 库内无匹配：用通讯录姓名显示（不再暴露 ou_id），
                    # 并按姓名尝试关联证件
                    contact_name, _tenant = await feishu_user_info(picked_text)
                    display_name = contact_name or picked_text
                    entry = {"role": role_key, "name": display_name}
                    if contact_name:
                        cert = await self._certificate_by_name(
                            contact_name, role_key
                        )
                        if cert is not None:
                            entry.update(_cert_snapshot(cert))
                    persons.append(entry)
                    continue
                entry: dict[str, Any] = {
                    "role": role_key,
                    "name": user.name,
                    "user_id": str(user.id),
                }
                cert = await self._certificate_for_user(user.id, role_key)
                if cert is not None:
                    entry.update(_cert_snapshot(cert))
                persons.append(entry)
            elif ext_name:
                entry = {
                    "role": role_key,
                    "name": ext_name,
                    "external": True,
                }
                if ext_cert:
                    entry["certificate_no"] = ext_cert
                persons.append(entry)
            elif prev:
                persons.append(prev)
        values["persons"] = persons
        # 汇总签字行显示所选人员姓名
        values["person_sign_names"] = {
            str(p.get("role")): str(p.get("name") or "") for p in persons
        }

    async def _certificate_by_name(
        self, person_name: str, role_key: str
    ) -> Any:
        """按姓名取有效证件（通讯录人员未绑定平台账号时的兜底关联）。"""
        from app.modules.safety.models import SpecialWorkCertificate

        result = await self.db.execute(
            select(SpecialWorkCertificate)
            .where(
                SpecialWorkCertificate.person_name == person_name,
                SpecialWorkCertificate.is_deleted.is_(False),
                SpecialWorkCertificate.status.in_(("valid", "expiring")),
            )
            .order_by(SpecialWorkCertificate.expiry_date.desc())
            .limit(1)
        )
        cert = result.scalar_one_or_none()
        del role_key
        return cert

    async def _certificate_for_user(
        self, user_id: Any, role_key: str
    ) -> Any:
        """取该用户有效特种作业证件（优先角色建议类别、最近到期）。"""
        from app.modules.safety.models import SpecialWorkCertificate
        from app.modules.safety.service.work_permit_templates import (
            PERSON_ROLE_CERT_CATEGORIES,
        )

        categories = list(PERSON_ROLE_CERT_CATEGORIES.get(role_key) or ())
        base_conditions = [
            SpecialWorkCertificate.identity_user_id == user_id,
            SpecialWorkCertificate.is_deleted.is_(False),
            SpecialWorkCertificate.status.in_(("valid", "expiring")),
        ]
        for conds in (
            base_conditions
            + (
                [
                    SpecialWorkCertificate.certificate_category.in_(categories)
                ]
                if categories
                else []
            ),
            base_conditions,
        ):
            result = await self.db.execute(
                select(SpecialWorkCertificate)
                .where(*conds)
                .order_by(SpecialWorkCertificate.expiry_date.desc())
                .limit(1)
            )
            cert = result.scalar_one_or_none()
            if cert is not None:
                return cert
        return None

    async def set_level(self, permit_type: str, level: str) -> dict[str, Any]:
        """第①步级别按钮切换（重渲染当前步卡片）。"""
        state = await self._load_state(permit_type)
        if state is None:
            raise AppException(status_code=410, message="表单已过期，请重新发起")
        values = state.setdefault("values", {})
        values["level"] = _sanitize_level(permit_type, level)
        await self._save_state(state)
        return build_step_card(
            permit_type,
            int(state.get("step") or 1),
            values,
            self.open_id,
        )

    async def _step1_warnings(
        self, permit_type: str, values: dict[str, Any]
    ) -> str | None:
        """第①步就地校验：结束时间/实施时长（不抛错，回卡提示）。"""
        from app.modules.safety.service import work_permit as permit_service

        start = _parse_dt_strict(values.get("planned_start"))
        end = _parse_dt_strict(values.get("planned_end"))
        if start is None or end is None:
            return None
        if end <= start:
            return "实施结束时间必须晚于开始时间，请重新选择时间"
        settings = await permit_service.get_runtime_settings(self.db)
        limit = await permit_service._validity_hours(
            settings,
            permit_type,
            _sanitize_level(permit_type, values.get("level")),
        )
        if limit:
            hours = (end - start).total_seconds() / 3600
            if hours > limit:
                return (
                    f"实施时长 {hours:.1f}h 超过当前级别有效期 {limit:g}h，"
                    "请缩短时间或调整级别"
                )
        return None

    def _missing_approvers(
        self, permit_type: str, values: dict[str, Any]
    ) -> list[str]:
        """第⑥步校验：既无指派也无默认审批人的 approve 节点名。"""
        from app.modules.safety.service.work_permit_templates import (
            active_nodes_for_level,
        )

        level = _sanitize_level(permit_type, values.get("level"))
        assignments = values.get("assignments") or {}
        defaults = values.get("approver_defaults") or {}
        missing: list[str] = []
        for node in active_nodes_for_level(permit_type, level):
            if str(node.get("kind")) != "approve":
                continue
            key = str(node.get("key"))
            if str(assignments.get(key) or "").strip():
                continue
            if str(defaults.get(key) or "").strip():
                continue
            missing.append(str(node.get("name")))
        return missing

    async def toggle_check(
        self, permit_type: str, field: str, key: str
    ) -> dict[str, Any]:
        """第④步逐项勾选切换（风险辨识/安全措施），返回重渲染的步骤卡。"""
        state = await self._load_state(permit_type)
        if state is None:
            raise AppException(status_code=410, message="表单已过期，请重新发起")
        values = state.setdefault("values", {})
        picked = {str(item) for item in (values.get(field) or [])}
        if key in picked:
            picked.discard(key)
        else:
            picked.add(key)
        values[field] = sorted(picked)
        await self._save_state(state)
        step = int(state.get("step") or 1)
        return build_step_card(permit_type, step, values, self.open_id)

    async def form_prev(self, permit_type: str, step: int) -> dict[str, Any]:
        state = await self._load_state(permit_type)
        if state is None:
            raise AppException(status_code=410, message="表单已过期，请重新发起")
        prev = prev_step(permit_type, step)
        state["step"] = prev or 1
        await self._save_state(state)
        return build_step_card(
            permit_type, state["step"], state["values"], self.open_id
        )

    async def cancel(self, permit_type: str) -> dict[str, Any]:
        await self.clear_state(permit_type)
        return build_menu_card(self.open_id)

    async def my_drafts(self, *, message_id: str = "") -> dict[str, Any]:
        """列出当前进行中的表单（继续填写卡；停在汇总步时直接回汇总卡）。

        从菜单恢复到汇总步时，汇总内容会以 ACK 回卡更新到当前消息，
        需把 ``summary_message_id`` 重绑到该消息，签名后刷新才正确。
        """
        for permit_type in PERMIT_TEMPLATES:
            state = await self._load_state(permit_type)
            if not state:
                continue
            step = int(state.get("step") or 1)
            if step >= steps_for(permit_type)[-1]:
                if message_id:
                    state["summary_message_id"] = message_id
                    await self._save_state(state)
                return await self.build_summary(permit_type)
            return build_step_card(
                permit_type, step, state.get("values") or {}, self.open_id
            )
        return build_menu_card(self.open_id)

    async def build_summary(self, permit_type: str) -> dict[str, Any]:
        state = await self._load_state(permit_type)
        if state is None:
            raise AppException(status_code=410, message="表单已过期，请重新发起")
        # 文档票面"作业申请时间"默认当前时刻
        values = state.setdefault("values", {})
        if not values.get("apply_time"):
            values["apply_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            await self._save_state(state)

        sign_keys = initiator_sign_keys(permit_type)
        sign_status = {
            key: "signed" if state.get("sign", {}).get(key) else ""
            for key in sign_keys
        }
        return build_summary_card(
            permit_type,
            _sanitize_level(permit_type, state.get("level")),
            state.get("values") or {},
            sign_status,
            {
                key: await self._sign_url(permit_type, key)
                for key in sign_keys
                if not sign_status[key]
            },
        )

    async def _sign_url(self, permit_type: str, sign_key: str) -> str:
        from app.modules.safety.service.work_permit_signatures import (
            build_sign_url,
            create_sign_token,
        )

        token = create_sign_token(
            permit_id=UUID(int=0),
            round_no=1,
            sign_key=sign_key,
            node_id=None,
            open_id=self.open_id,
            signer_name=row_name_for(permit_type, sign_key),
            permit_type=permit_type,
        )
        return build_sign_url(token)

    async def bind_summary_message(
        self, permit_type: str, message_id: str
    ) -> None:
        state = await self._load_state(permit_type)
        if state:
            state["summary_message_id"] = message_id
            await self._save_state(state)

    async def save_initiator_signature(
        self, permit_type: str, sign_key: str, image_key: str
    ) -> None:
        state = await self._load_state(permit_type)
        if state is None:
            return
        state.setdefault("sign", {})[sign_key] = image_key
        await self._save_state(state)

    async def use_default_sign(self, permit_type: str, sign_key: str) -> dict[str, Any]:
        """汇总卡「用我的默认签名」：复用本人最近手写签名，免开手写板。"""
        from app.modules.safety.service.work_permit_signatures import (
            latest_person_signature,
        )

        user = await self.ensure_user()
        state = await self._load_state(permit_type)
        if state is None:
            raise AppException(status_code=410, message="表单已过期，请重新发起")
        row = await latest_person_signature(self.db, signer_user_id=user.id)
        if row is None:
            raise AppException(
                status_code=422,
                message="你还没有历史手写签名，请点「🖊 手写签名」先写一次",
            )
        state.setdefault("sign", {})[sign_key] = row.image_key
        await self._save_state(state)
        return await self.build_summary(permit_type)

    async def my_gas_permits(self) -> list[Any]:
        """我在作业中、需要周期气体复检的票（最近 3 张）。"""
        from app.modules.safety.models import WorkPermit
        from app.modules.safety.service.work_permit_templates import (
            PERMIT_STATUS_ACTIVE,
        )

        user = await self.ensure_user()
        gas_types = [
            code
            for code, template in PERMIT_TEMPLATES.items()
            if template.gas_cycle_minutes
        ]
        if not gas_types:
            return []
        result = await self.db.execute(
            select(WorkPermit)
            .where(
                WorkPermit.created_by == user.id,
                WorkPermit.status == PERMIT_STATUS_ACTIVE,
                WorkPermit.permit_type.in_(gas_types),
                WorkPermit.is_deleted.is_(False),
            )
            .order_by(WorkPermit.created_at.desc())
            .limit(3)
        )
        return list(result.scalars().all())

    async def refresh_summary_card(self, permit_type: str) -> None:
        """签名完成后刷新汇总卡（PATCH 原消息）。"""
        state = await self._load_state(permit_type)
        message_id = (state or {}).get("summary_message_id")
        if not message_id or not state:
            return
        from app.modules.safety.feishu.notification import update_card

        card = await self.build_summary(permit_type)
        await update_card(str(message_id), card)

    # ── 提交 ──

    async def submit(
        self, permit_type: str, form_value: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        state = await self._load_state(permit_type)
        if state is None:
            raise AppException(status_code=410, message="表单已过期，请重新发起")
        user = await self.ensure_user()
        values = state.get("values") or {}
        if form_value:
            # 汇总卡提交表单携带：措施数量备注 / 关联作业票编号
            if _optional(form_value.get("measures_note")):
                values["measures_note"] = _optional(
                    form_value.get("measures_note")
                )
            if _optional(form_value.get("related_permits")):
                values["related_permits"] = _optional(
                    form_value.get("related_permits")
                )
        sign = state.get("sign") or {}
        missing = [key for key in initiator_sign_keys(permit_type) if not sign.get(key)]
        if missing:
            raise AppException(
                status_code=422,
                message=(
                    "还有签字行未完成手写签名：" + "、".join(missing)
                ),
            )
        payload = build_create_payload(
            permit_type,
            _sanitize_level(permit_type, state.get("level")),
            values,
        )
        permit = await permit_service.create_permit(self.db, payload, user)
        # 审批人指派（第⑥步选人）：飞书 id → 平台用户 id（引擎期望 dict）
        assignments_input: dict[str, str] = {}
        for node_key, feishu_id in (values.get("assignments") or {}).items():
            assigned_user = await self._user_by_feishu_id(str(feishu_id))
            if assigned_user is not None:
                assignments_input[str(node_key)] = str(assigned_user.id)
        # 发起行签名落库
        person_names = {
            p.get("role"): p.get("name") for p in (permit.persons or [])
        }
        for sign_key in initiator_sign_keys(permit_type):
            await save_signature_row(
                self.db,
                permit_id=permit.id,
                round_no=1,
                sign_key=sign_key,
                node_id=None,
                signer_user_id=user.id,
                signer_name=str(
                    person_names.get(_role_for_sign_key(sign_key)) or user.name
                ),
                image_key=str(sign[sign_key]),
            )
        # 默认模板记忆
        await self._save_form_defaults(user.id, permit_type, values)
        # 提交审批（默认审批人）
        from uuid import UUID as _UUID

        assignments_uuid: dict[str, _UUID | None] = {
            key: (_UUID(value) if value else None)
            for key, value in assignments_input.items()
        }
        submitted, warnings = await permit_service.submit_permit(
            self.db, permit.id, assignments_uuid, user
        )
        # 作业前气体分析落库（文档票面气体区数据来源）
        gas = dict(values.get("gas") or {})
        if any(str(v or "").strip() for v in gas.values()):
            from app.modules.safety.schemas.work_permit import GasAnalysisCreate

            try:
                await permit_service.add_gas_analysis(
                    self.db,
                    permit.id,
                    GasAnalysisCreate(
                        phase="pre_work",
                        sampled_at=_parse_datetime(
                            str(gas.get("gas_time") or "")
                        ),
                        analysis_point=gas.get("gas_point") or None,
                        items=[
                            {
                                "name": gas.get("gas_name") or "代表性气体",
                                "standard": None,
                                "value": gas.get("gas_value") or None,
                            }
                        ],
                        analyst_name=gas.get("gas_analyst") or None,
                    ),
                    user,
                )
            except Exception:
                logger.exception(
                    "聊天提交作业前气体分析落库失败: permit=%s", permit.permit_no
                )
        await self.db.commit()
        await self.clear_state(permit_type)
        await self._push_approval_card(submitted.id)
        receipt = build_receipt_card(
            permit.permit_no,
            "已提交审批",
            "已提交审批" + (f"；提示：{'；'.join(warnings)}" if warnings else ""),
        )
        return receipt

    async def _save_form_defaults(
        self, user_id: UUID, permit_type: str, values: dict[str, Any]
    ) -> None:

        result = await self.db.execute(
            select_defaults(user_id, permit_type)
        )
        row = result.scalar_one_or_none()
        snapshot = {
            "apply_department": values.get("apply_department"),
            "work_description": values.get("work_description"),
            "work_location": values.get("work_location"),
            "work_unit": values.get("work_unit"),
            "planned_start": values.get("planned_start"),
            "planned_end": values.get("planned_end"),
            "type_data": values.get("type_data") or {},
            "persons": values.get("persons") or [],
            "gas": values.get("gas") or {},
            "risk": values.get("risk") or [],
            "measures": values.get("measures") or {},
            "measures_note": values.get("measures_note") or "",
            "related_permits": values.get("related_permits") or "",
            "level": _sanitize_level(permit_type, values.get("level")),
        }
        if row is None:
            self.db.add(
                WorkPermitFormDefault(
                    user_id=user_id,
                    permit_type=permit_type,
                    values=snapshot,
                    created_by=user_id,
                    updated_by=user_id,
                )
            )
        else:
            row.values = snapshot
        await self.db.flush()

    # ── 审批 / 验票 / 验收 / 复检 ──

    async def approve(self, permit_id: UUID, node_id: UUID) -> dict[str, Any]:
        user = await self.ensure_user()
        permit = await permit_service.get_permit(self.db, permit_id)
        node = await _get_node(self.db, permit_id, node_id)
        _ensure_assignee(node, user)
        # 签名：节点已签（免登板）或复用本人最近手写签名（默认签名）
        existing = await _node_signature(
            self.db, permit.id, permit.approval_round, node.id, node.node_key
        )
        if existing is None:
            reused = await reuse_or_none(self.db, signer_user_id=user.id)
            if reused is None:
                raise AppException(
                    status_code=422,
                    message="请先点卡片上的「🖊 手写签名」完成签名（下次可默认沿用）",
                )
            await save_signature_row(
                self.db,
                permit_id=permit.id,
                round_no=permit.approval_round,
                sign_key=node.node_key,
                node_id=node.id,
                signer_user_id=user.id,
                signer_name=user.name,
                image_key=reused,
            )
        permit_obj = await permit_service.approve_node(
            self.db, permit_id, node.id, None, user
        )
        await self.db.commit()
        await self._push_flow_after_action(permit_obj)
        # 回执告诉审批人"已推进到哪"，避免误以为没生效
        progress = await self._progress_text(permit_obj)
        return build_receipt_card(
            permit_obj.permit_no,
            "已同意",
            f"节点「{node.node_name}」已同意\n{progress}",
        )

    async def reject(
        self,
        permit_id: UUID,
        node_id: UUID,
        opinion: str,
    ) -> dict[str, Any]:
        user = await self.ensure_user()
        node = await _get_node(self.db, permit_id, node_id)
        _ensure_assignee(node, user)
        permit_obj = await permit_service.reject_node(
            self.db, permit_id, node.id, opinion, user
        )
        await self.db.commit()
        await self._notify_creator_rejected(permit_obj, opinion)
        return build_receipt_card(
            permit_obj.permit_no,
            "已驳回",
            f"驳回意见：{opinion}",
        )

    async def verify(self, permit_id: UUID) -> dict[str, Any]:
        user = await self.ensure_user()
        permit_obj = await permit_service.verify_permit(
            self.db, permit_id, user
        )
        await self.db.commit()
        await self._push_flow_after_action(permit_obj)
        return build_receipt_card(
            permit_obj.permit_no,
            "已开工",
            "验票完成，作业开始。请按周期提交气体复检。",
        )

    async def accept(self, permit_id: UUID) -> dict[str, Any]:
        user = await self.ensure_user()
        permit_obj = await permit_service.accept_permit(self.db, permit_id, {}, user)
        await self.db.commit()
        await self._push_flow_after_action(permit_obj)
        return build_receipt_card(
            permit_obj.permit_no,
            "已完工",
            "完工验收完成，可下载 PDF 存档。",
        )

    async def save_gas(
        self, permit_id: UUID, form_value: dict[str, Any]
    ) -> dict[str, Any]:
        user = await self.ensure_user()
        from app.modules.safety.schemas.work_permit import GasAnalysisCreate

        payload = GasAnalysisCreate(
            phase="on_duty",
            sampled_at=_parse_datetime(str(form_value.get("gas_time") or "")),
            analysis_point=_optional(form_value.get("gas_point")),
            items=[
                {
                    "name": str(form_value.get("gas_name") or "可燃气体"),
                    "standard": _optional(form_value.get("gas_standard")),
                    "value": _optional(form_value.get("gas_value")),
                }
            ],
            analyst_name=_optional(form_value.get("gas_analyst")),
        )
        item = await permit_service.add_gas_analysis(
            self.db, permit_id, payload, user
        )
        await self.db.commit()
        return build_receipt_card(
            "复检记录",
            "已录入",
            f"{item.sampled_at:%m-%d %H:%M} {item.analysis_point or ''}",
        )

    # ── 推卡 ──

    async def _push_approval_card(self, permit_id: UUID) -> None:
        from app.modules.safety.service.work_permit_notify import (
            push_approval_card_for_next_node,
        )

        await push_approval_card_for_next_node(self.db, permit_id)

    async def _progress_text(self, permit: Any) -> str:
        """回执进度文案：下一待办节点 / 等待验票 / 已完工。"""
        from app.modules.safety.models import WorkPermitNode
        from app.modules.safety.service.work_permit_templates import (
            PERMIT_STATUS_ACTIVE,
            PERMIT_STATUS_APPROVED,
            PERMIT_STATUS_COMPLETED,
            PERMIT_STATUS_PENDING,
        )

        if str(permit.status) == PERMIT_STATUS_PENDING:
            node = (
                await self.db.execute(
                    select(WorkPermitNode).where(
                        WorkPermitNode.permit_id == permit.id,
                        WorkPermitNode.round == permit.approval_round,
                        WorkPermitNode.status == "pending",
                        WorkPermitNode.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if node is not None:
                return f"➡️ 下一节点：**{node.node_name}**（待办卡已推送）"
            return "➡️ 审批已推进"
        if str(permit.status) == PERMIT_STATUS_APPROVED:
            return "✅ 全部签批完成，等待验票开工"
        if str(permit.status) == PERMIT_STATUS_ACTIVE:
            return "✅ 已开工，作业中；完工后需验收"
        if str(permit.status) == PERMIT_STATUS_COMPLETED:
            return "✅ 已完工，可下载 PDF 存档"
        return ""

    async def _push_flow_after_action(self, permit: Any) -> None:
        from app.modules.safety.service.work_permit_notify import (
            push_approval_card_for_next_node,
        )

        await push_approval_card_for_next_node(self.db, permit.id)

    async def _notify_creator_rejected(self, permit: Any, opinion: str) -> None:
        """整票驳回后通知创建人（与网页链路 notify_after_transition 同口径）。"""
        from app.modules.safety.service.work_permit_notify import (
            notify_status_change,
        )

        try:
            await notify_status_change(
                self.db,
                permit,
                title="已被驳回",
                extra=f"驳回意见：{opinion}；修改后可在平台重新提交，或发起新申请",
            )
        except Exception:
            logger.exception("驳回通知创建人失败: %s", getattr(permit, "permit_no", ""))


# ── 模块级工具 ──


def _parse_dt_strict(text: Any) -> datetime | None:
    """严格解析 YYYY-MM-DD HH:MM（校验用，失败返回 None）。"""
    value = str(text or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _cert_snapshot(cert: Any) -> dict[str, str]:
    """证件行 → 人员快照字段（随票存档）。"""
    return {
        "certificate_id": str(cert.id),
        "certificate_no": cert.certificate_no or "",
        "certificate_category": cert.certificate_category,
        "certificate_expiry": (
            cert.expiry_date.isoformat() if cert.expiry_date else ""
        ),
        "certificate_status": cert.status,
    }


async def feishu_user_info(open_id: str) -> tuple[str, str]:
    """经飞书通讯录取 (姓名, tenant user_id)；失败返回 ("", "")。

    通讯录选人只回传本应用 open_id，库里通常存的是其他应用的 open_id，
    直接查库会落到 ou_xxx 显示。此接口需要应用具备
    ``contact:user.base:readonly`` 权限；无权限时静默降级。
    """
    import httpx

    try:
        from app.modules.safety.feishu.client import (
            get_safety_feishu_client,
            get_safety_tenant_token,
        )

        client = await get_safety_feishu_client()
        token = await get_safety_tenant_token(client)
        async with httpx.AsyncClient(timeout=8) as http:
            resp = await http.get(
                "https://open.feishu.cn/open-apis/contact/v3/users/"
                f"{open_id}",
                params={"user_id_type": "open_id"},
                headers={"Authorization": f"Bearer {token}"},
            )
            payload = resp.json()
        if payload.get("code") != 0:
            logger.info(
                "安全飞书通讯录查询未成功: open_id=%s code=%s msg=%s",
                open_id,
                payload.get("code"),
                payload.get("msg"),
            )
            return "", ""
        user = (payload.get("data") or {}).get("user") or {}
        return str(user.get("name") or ""), str(user.get("user_id") or "")
    except Exception:
        logger.exception("安全飞书通讯录查询异常: %s", open_id)
        return "", ""


def select_user_by_open_id(open_id: str, union_id: str = "") -> Any:
    """按 open_id 精确匹配优先，union_id 兜底（跨应用一致）。

    union_id 可能命中多行（如 HR 同步影子行与登录账号同 union_id），
    open_id 命中优先、其余按最近更新取一条，避免 MultipleResultsFound。
    """
    from sqlalchemy import case, or_

    from app.platform.identity.models import User

    conditions = [User.feishu_open_id == open_id]
    if union_id:
        conditions.append(User.feishu_union_id == union_id)
    return (
        select(User)
        .where(or_(*conditions), User.is_deleted.is_(False))
        .order_by(
            case((User.feishu_open_id == open_id, 0), else_=1),
            User.updated_at.desc(),
        )
        .limit(1)
    )


def select_defaults(user_id: UUID, permit_type: str) -> Any:
    from app.modules.safety.models import WorkPermitFormDefault

    return select(WorkPermitFormDefault).where(
        WorkPermitFormDefault.user_id == user_id,
        WorkPermitFormDefault.permit_type == permit_type,
        WorkPermitFormDefault.is_deleted.is_(False),
    )


def _ensure_assignee(node: Any, user: User) -> None:
    assigned = node.assigned_approver_id
    if assigned and assigned != user.id and user.role != "admin":
        raise AppException(status_code=403, message="该节点未指派给你")


async def _get_node(
    db: AsyncSession, permit_id: UUID, node_id: UUID
) -> Any:
    from sqlalchemy import select

    from app.modules.safety.models import WorkPermitNode

    result = await db.execute(
        select(WorkPermitNode).where(
            WorkPermitNode.id == node_id,
            WorkPermitNode.permit_id == permit_id,
            WorkPermitNode.is_deleted.is_(False),
        )
    )
    node = result.scalar_one_or_none()
    if node is None:
        raise AppException(status_code=404, message="审批节点不存在")
    return node


async def _node_signature(
    db: AsyncSession,
    permit_id: UUID,
    round_no: int,
    node_id: UUID,
    sign_key: str,
) -> Any:
    result = await db.execute(
        select(WorkPermitSignature).where(
            WorkPermitSignature.permit_id == permit_id,
            WorkPermitSignature.round == round_no,
            WorkPermitSignature.node_id == node_id,
            WorkPermitSignature.sign_key == sign_key,
            WorkPermitSignature.is_deleted.is_(False),
        )
    )
    return result.scalar_one_or_none()


def initiator_sign_keys(permit_type: str) -> tuple[str, ...]:
    if permit_type == "hot_work":
        return ("initiator", "briefer", "briefer_receiver")
    return ("initiator", "briefer", "briefer_receiver")


def _role_for_sign_key(sign_key: str) -> str:
    return {
        "initiator": "work_leader",
        "briefer": "briefer",
        "briefer_receiver": "briefer_receiver",
    }.get(sign_key, sign_key)


def row_name_for(permit_type: str, sign_key: str) -> str:
    role = _role_for_sign_key(sign_key)
    return PERSON_ROLE_LABELS.get(role, sign_key)


def build_create_payload(
    permit_type: str, permit_level: str, values: dict[str, Any]
) -> WorkPermitCreate:
    import datetime as dt_module

    def _parse(value: str | None) -> dt_module.datetime | None:
        text = (value or "").strip()
        if not text:
            return None
        try:
            return dt_module.datetime.strptime(text, "%Y-%m-%d %H:%M")
        except ValueError:
            try:
                return dt_module.datetime.fromisoformat(text)
            except ValueError:
                return None

    persons = []
    for person in values.get("persons") or []:
        if not person.get("name"):
            continue
        entry: dict[str, Any] = {
            "role": person["role"],
            "name": person["name"],
        }
        # 携带选人/证件快照（外部人员仅 name + certificate_no）
        for key in (
            "user_id",
            "certificate_id",
            "certificate_no",
            "certificate_category",
        ):
            if person.get(key):
                entry[key] = person[key]
        persons.append(entry)
    measures: list[dict[str, Any]] = []
    selected = values.get("measures") or {}
    fills_map: dict[str, dict[str, str]] = values.get("measure_fills") or {}
    items: list[tuple[Any, Any]]
    if isinstance(selected, dict):
        items = list(selected.items())
    else:
        items = [(key, "yes") for key in selected]
    for key, value in items:
        measures.append(
            {
                "key": key,
                "status": "yes" if value else "not_applicable",
                "fills": dict(fills_map.get(str(key)) or {}),
            }
        )
    return WorkPermitCreate(
        permit_type=permit_type,
        permit_level=permit_level,
        apply_department=_optional(values.get("apply_department")),
        work_description=_optional(values.get("work_description")),
        work_location=_optional(values.get("work_location")),
        work_unit=_optional(values.get("work_unit")),
        planned_start_time=_parse(values.get("planned_start")),
        planned_end_time=_parse(values.get("planned_end")),
        persons=persons,
        risk_identifications=list(values.get("risk") or []),
        safety_measures=measures,
        type_data=dict(values.get("type_data") or {}),
        related_legacy_no_text=_optional(values.get("related_permits")),
        remark=_optional(values.get("remark")),
    )


def _optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_datetime(text: str) -> Any:
    import datetime as dt_module

    text = (text or "").strip()
    if not text:
        return dt_module.datetime.now()
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt_module.datetime.strptime(text, pattern)
        except ValueError:
            continue
    try:
        return dt_module.datetime.fromisoformat(text)
    except ValueError:
        return dt_module.datetime.now()


def _sanitize_level(permit_type: str, level: Any) -> str:
    """级别净化：非法值（如历史表单记忆残留的 none）回退模板最低档。"""
    template = get_template(permit_type)
    if not template.levels:
        return "none"
    text = str(level or "").strip()
    from app.modules.safety.service.work_permit_card_forms import default_level

    return text if text in template.levels else default_level(template.levels)


def _combine_dt(form_value: dict[str, Any], base: str) -> str | None:
    """把 ``{base}_date`` + ``{base}_time`` 组合为 ``YYYY-MM-DD HH:MM``。

    date_picker 回传可能是毫秒/秒时间戳或日期字符串；picker_time 回传
    ``HH:MM`` 或秒数。任一缺失返回 None（不覆盖已填值）。
    """
    from datetime import datetime

    raw_date = form_value.get(f"{base}_date")
    raw_time = form_value.get(f"{base}_time")
    if raw_date in (None, ""):
        return None

    def _to_date(value: Any) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        if text.isdigit():
            ts = int(text)
            if ts > 10**12:
                ts //= 1000
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        return text[:10]

    def _to_time(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return "00:00"
        if ":" in text:
            return text[:5]
        if text.isdigit():
            secs = int(text) % 86400
            return f"{secs // 3600:02d}:{(secs % 3600) // 60:02d}"
        return text[:5]

    date_text = _to_date(raw_date)
    if not date_text:
        return None
    return f"{date_text} {_to_time(raw_time)}"


def _merge_form_values(
    permit_type: str,
    step: int,
    values: dict[str, Any],
    form_value: dict[str, Any],
) -> None:
    template = get_template(permit_type)
    if step == 1:
        for key in (
            "apply_department",
            "work_description",
            "work_location",
            "work_unit",
        ):
            if key in form_value:
                values[key] = _optional(form_value.get(key)) or ""
        for base in ("planned_start", "planned_end"):
            combined = _combine_dt(form_value, base)
            if combined:
                values[base] = combined
        if "permit_level" in form_value and str(
            form_value["permit_level"] or ""
        ).strip():
            values["level"] = _sanitize_level(
                permit_type, form_value.get("permit_level")
            )
        else:
            # select 无默认值且用户未选时，保持/回退合法级别
            values["level"] = _sanitize_level(permit_type, values.get("level"))
        # 票面差异字段：multi_select 逐行 tf__{key}__{opt} 组合为列表；
        # datetime 由日期时间组件组合；其余字符串
        td = values.setdefault("type_data", {})
        for field in template.type_fields:
            key = str(field["key"])
            if str(field.get("type")) == "datetime":
                combined = _combine_dt(form_value, key)
                if combined:
                    td[key] = combined
                continue
            if str(field.get("type")) == "multi_select":
                # 兼容两种形态：下拉多选回传 key→list；逐行 tf__{key}__{opt}
                picked = [
                    name.split("__", 2)[2]
                    for name, val in form_value.items()
                    if name.startswith(f"tf__{key}__") and str(val) == "yes"
                ]
                raw_multi = form_value.get(key)
                if isinstance(raw_multi, (list, tuple)):
                    selected = [str(v) for v in raw_multi if str(v).strip()]
                    if selected:
                        picked = selected
                elif isinstance(raw_multi, str) and raw_multi.strip():
                    picked = [raw_multi.strip()]
                if picked:
                    td[key] = picked
                continue
            if key in form_value:
                raw = form_value[key]
                if isinstance(raw, (list, tuple)):
                    td[key] = [str(item) for item in raw if str(item).strip()]
                else:
                    td[key] = str(raw)
        return
    if step == 2:
        return
    if step == 3:
        gas = {
            k: _optional(v)
            for k, v in form_value.items()
            if not k.endswith(("_date", "_time"))
        }
        combined = _combine_dt(form_value, "gas_time")
        if combined:
            gas["gas_time"] = combined
        values["gas"] = gas
        return
    if step == 4:
        # 风险辨识：下拉多选回传 key→list；兼容旧逐行 risk__{项} 形态
        if not form_value:
            return
        raw_risk = form_value.get("risk")
        if isinstance(raw_risk, (list, tuple)):
            picked = [str(item) for item in raw_risk if str(item).strip()]
            if picked:
                values["risk"] = picked
                return
        elif isinstance(raw_risk, str) and raw_risk.strip():
            values["risk"] = [
                item.strip() for item in raw_risk.split("、") if item.strip()
            ]
            return
        values["risk"] = [
            name.removeprefix("risk__")
            for name, val in form_value.items()
            if name.startswith("risk__") and str(val) == "yes"
        ]
        return

    if step == 5:
        # 安全措施逐行：m__{key}=是/否；f__{key}__{fill}=数量填空
        if not form_value:
            return
        values["measures"] = [
            name.removeprefix("m__")
            for name, val in form_value.items()
            if name.startswith("m__") and str(val) == "yes"
        ]
        fills: dict[str, dict[str, str]] = {}
        for name, val in form_value.items():
            if name.startswith("f__") and str(val or "").strip():
                _, m_key, fill_key = name.split("__", 2)
                fills.setdefault(m_key, {})[fill_key] = str(val).strip()
        values["measure_fills"] = fills
        return

    if step == 6:
        # 审批人指派：assign_{node_key}=飞书人员 id（提交时解析为平台用户）
        assignments = values.setdefault("assignments", {})
        for name, val in form_value.items():
            if not name.startswith("assign_"):
                continue
            node_key = name.removeprefix("assign_")
            if isinstance(val, (list, tuple)):
                val = val[0] if val else ""
            if str(val or "").strip():
                assignments[node_key] = str(val).strip()
        return


__all__ = ["ChatFlowService", "parse_intent"]
