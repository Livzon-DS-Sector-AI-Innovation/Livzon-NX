"""人事审批卡片回调处理（经由人事专属飞书应用的 WebSocket 长连接）。

从平台 event_handler 迁回人事模块：卡片由人事应用发送、由人事应用接收回调，
卡片更新同样使用人事模块自己的飞书凭证（模块独立，不影响平台登录应用）。
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def handle_card_action(event: dict[str, Any]) -> dict[str, Any] | None:
    """人事应用长连接的 card.action.trigger 分发器。"""
    action_value = event.get("event", {}).get("action", {}).get("value", {})
    if action_value.get("module") == "hr_contract_approval":
        return await _handle_hr_contract_approval(event, action_value)
    if action_value.get("module") == "position_transfer_approval":
        return await _handle_position_transfer_approval(event, action_value)
    return None


async def _handle_hr_contract_approval(
    event_data: dict[str, Any],
    value: dict[str, Any],
) -> dict[str, Any]:
    """合同审批卡片回调（两级：dept/supervisor）——飞书卡片内直接审批，不跳转浏览器。

    按钮 value 结构：
    {module: hr_contract_approval, action, employee_number, employee_name,
     stage, leader_name, dept_name}
    审批完成后返回 toast 提示，并将卡片按钮置灰。
    """
    action = value.get("action", "")
    emp_no = value.get("employee_number", "")
    emp_name = value.get("employee_name", "")
    stage = value.get("stage", "dept")
    leader_name = value.get("leader_name", "")
    dept_name = value.get("dept_name", "")

    logger.info(
        "[合同卡片回调] action=%s stage=%s emp=%s(%s) signer=%s",
        action,
        stage,
        emp_name,
        emp_no,
        leader_name,
    )

    if action not in ("approve", "reject") or stage not in ("dept", "supervisor"):
        return {"toast": {"type": "warning", "content": "参数错误，请重新发起审批"}}

    from app.core.database import async_session_factory
    from app.modules.hr.contract_api import (
        process_contract_approval,
        update_contract_approval_card,
    )

    async with async_session_factory() as session:
        status_text = await process_contract_approval(
            employee_number=emp_no,
            employee_name=emp_name,
            action=action,
            leader_name=leader_name,
            stage=stage,
            db=session,
        )

    # 防重/参数/失败：直接提示，不更新卡片
    best_effort_toasts = (
        "已审批过，请勿重复操作",
        "回调参数错误，请重新发起审批",
        "处理失败，请联系 HR 处理",
    )
    if status_text in best_effort_toasts:
        return {"toast": {"type": "warning", "content": f"{emp_name}：{status_text}"}}

    # 审批成功：更新卡片（按钮置灰）
    await update_contract_approval_card(emp_no, emp_name, action, stage, dept_name)

    approved = "同意" in status_text or "等待分管领导审批" in status_text
    toast_type = "success" if approved else "warning"
    return {"toast": {"type": toast_type, "content": f"{emp_name}：{status_text}"}}


# ── 岗位调动审批卡片回调 ──


async def _handle_position_transfer_approval(
    event_data: dict[str, Any],
    value: dict[str, Any],
) -> dict[str, Any]:
    """处理岗位调动审批卡片按钮回调。"""
    action = value.get("action", "")
    record_id = value.get("record_id", "")
    node = value.get("node", "")
    signer = value.get("signer", "")
    # 提取卡片表单值（HR节点的薪资职级字段）
    # Feishu WebSocket 事件中 form_value 可能在多处：
    # event.action.form_value 或 event.form_value
    event_inner = event_data.get("event", {})
    action_inner = event_inner.get("action", {})
    form_value = action_inner.get("form_value", {})
    if not form_value:
        form_value = event_inner.get("form_value", {})
    if not form_value:
        form_value = event_data.get("form_value", {})

    logger.info(
        "[岗位调动卡片回调] action=%s record=%s node=%s signer=%s form_value=%s"
        " raw_action_keys=%s raw_event_keys=%s",
        action,
        record_id,
        node,
        signer,
        form_value,
        list(action_inner.keys()) if action_inner else [],
        list(event_inner.keys()) if event_inner else [],
    )

    # 防重复
    from app.core.redis import cache_get, cache_set

    approval_key = f"hr:position_transfer:{record_id}:{node}:{action}"
    already = await cache_get(approval_key)
    if already:
        logger.info("[岗位调动卡片回调] %s 已审批（防重复）", signer)
        return {"toast": {"type": "warning", "content": "已审批，请勿重复操作"}}

    # 先标记（防重入），再异步执行
    await cache_set(approval_key, "1", ex=86400 * 7)

    asyncio.create_task(
        _do_position_transfer_approval(action, record_id, node, signer, form_value)
    )

    toast_type = "success" if action == "approve" else "warning"
    toast_content = "已通过" if action == "approve" else "已拒绝"
    return {"toast": {"type": toast_type, "content": toast_content}}


async def _do_position_transfer_approval(
    action: str,
    record_id: str,
    node: str,
    signer: str,
    form_value: dict[str, Any] | None = None,
) -> None:
    """异步执行岗位调动审批操作。"""
    from app.core.database import async_session_factory

    try:
        from uuid import UUID

        from app.modules.hr.schemas import (
            PositionTransferApproveNodeRequest,
            PositionTransferRejectNodeRequest,
        )
        from app.modules.hr.service import PositionTransferRecordService

        async with async_session_factory() as session:
            service = PositionTransferRecordService(session)

            # 先保存当前卡片的 message_id（approve/reject 后会被下一节点的通知覆盖）
            record_before = await service.get_record(UUID(record_id))
            old_message_id = record_before.feishu_approval_message_id

            req: PositionTransferApproveNodeRequest | PositionTransferRejectNodeRequest
            if action == "approve":
                req = PositionTransferApproveNodeRequest(opinion="同意")
                record = await service.approve_current_node(UUID(record_id), req)
            else:
                req = PositionTransferRejectNodeRequest(opinion="不同意")
                record = await service.reject_current_node(UUID(record_id), req)

            # 用旧的 message_id 更新当前卡片状态（不影响下一节点的新卡片）
            if old_message_id:
                await _update_position_transfer_card_by_id(
                    old_message_id,
                    record,
                    action,
                )

            # HR 节点：把薪资职级表单值写入多维表格
            if form_value and record.feishu_record_id:
                await _write_hr_form_to_bitable(record, form_value)

            await session.commit()

        logger.info("[岗位调动卡片回调] 完成: record=%s action=%s", record_id, action)
    except Exception:
        logger.exception(
            "[岗位调动卡片回调] 操作失败: record=%s action=%s",
            record_id,
            action,
        )


async def _write_hr_form_to_bitable(
    record: Any,
    form_value: dict[str, Any],
) -> None:
    """把 HR 审批卡片中的薪资职级表单值写入飞书多维表格。"""
    try:
        from sqlalchemy import select

        from app.core.database import async_session_factory
        from app.modules.hr.feishu.bitable import BitableClient
        from app.modules.hr.feishu_settings_service import get_hr_feishu_app_credentials
        from app.modules.hr.models import HrFeishuEntitySetting

        salary_change = form_value.get("salary_change", "")
        salary_adjust = form_value.get("salary_adjust", "")
        logger.info(
            "[岗位调动HR表单] form_value=%s, salary_change=%s, salary_adjust=%s",
            form_value,
            salary_change,
            salary_adjust,
        )
        if not salary_change and not salary_adjust:
            logger.info("[岗位调动HR表单] 无薪资数据，跳过写入")
            return

        async with async_session_factory() as session:
            result = await session.execute(
                select(HrFeishuEntitySetting).where(
                    HrFeishuEntitySetting.entity_code == "position_transfer",
                    HrFeishuEntitySetting.is_deleted.is_(False),
                )
            )
            entity = result.scalar_one_or_none()
            app_id, app_secret = await get_hr_feishu_app_credentials(session)
            if not entity or not entity.app_token or not entity.base_table_id:
                logger.warning("[岗位调动HR表单] 实体设置未找到")
                return

        client = BitableClient(
            app_token=entity.app_token,
            app_id=app_id,
            app_secret=app_secret,
        )
        fields = {}
        if salary_change:
            fields["薪资职级是否变动"] = salary_change
        if salary_adjust:
            fields["薪资职级调整为"] = salary_adjust
        logger.info(
            "[岗位调动HR表单] 写入多维表格: table=%s record=%s fields=%s",
            entity.base_table_id,
            record.feishu_record_id,
            fields,
        )
        await client.update_record(
            entity.base_table_id,
            record.feishu_record_id,
            fields,
        )
        logger.info("[岗位调动HR表单] 写入成功: %s", fields)
    except Exception:
        logger.exception("[岗位调动HR表单] 写入多维表格失败")


async def _update_position_transfer_card_by_id(
    message_id: str,
    record: Any,
    action: str,
) -> None:
    """审批后用指定的 message_id 更新飞书卡片状态。"""
    try:
        from app.core.database import async_session_factory
        from app.modules.hr.feishu_settings_service import get_hr_feishu_app_credentials
        from app.platform.integrations.feishu.notification import update_card

        async with async_session_factory() as session:
            app_id, app_secret = await get_hr_feishu_app_credentials(session)

        status_text = "✅ 已通过" if action == "approve" else "❌ 已拒绝"
        template = "green" if action == "approve" else "red"

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"岗位调动审批 - {status_text}",
                },
                "template": template,
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": f"申请人：{record.employee_name}",
                    },
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": (
                            f"原部门：{record.department_before} -> "
                            f"申请部门：{record.apply_department}"
                        ),
                    },
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": f"审批状态：{record.approval_status}",
                    },
                },
            ],
        }
        await update_card(message_id, card, app_id=app_id, app_secret=app_secret)
    except Exception:
        logger.warning("[岗位调动卡片回调] 更新卡片失败")
