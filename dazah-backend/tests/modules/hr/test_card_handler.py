"""人事飞书卡片回调处理全路径测试：分发、合同审批、岗位调动防重与 HR 表单回写。"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.modules.hr.feishu import card_handler as svc

_REC1 = "11111111-1111-1111-1111-111111111111"
_REC2 = "22222222-2222-2222-2222-222222222222"


def _action_event(module: str, **value: Any) -> dict[str, Any]:
    return {"event": {"action": {"value": {"module": module, **value}}}}


# ── 分发器 ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_card_action_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        svc, "_handle_hr_contract_approval",
        AsyncMock(return_value={"toast": {"content": "合同"}}),
    )
    monkeypatch.setattr(
        svc, "_handle_position_transfer_approval",
        AsyncMock(return_value={"toast": {"content": "调动"}}),
    )
    assert (
        await svc.handle_card_action(_action_event("hr_contract_approval"))
    ) == {"toast": {"content": "合同"}}
    assert (
        await svc.handle_card_action(_action_event("position_transfer_approval"))
    ) == {"toast": {"content": "调动"}}
    # 未知模块 → None
    assert await svc.handle_card_action(_action_event("other")) is None


# ── 合同审批卡片 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_contract_approval_invalid_params() -> None:
    out = await svc._handle_hr_contract_approval(
        {}, {"module": "hr_contract_approval", "action": "bad", "stage": "dept"}
    )
    assert "参数错误" in out["toast"]["content"]


@pytest.mark.asyncio
async def test_contract_approval_best_effort_and_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=SimpleNamespace())
    session_cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "app.core.database.async_session_factory",
        lambda: session_cm,
    )
    monkeypatch.setattr(
        "app.modules.hr.contract_api.process_contract_approval",
        AsyncMock(return_value="已审批过，请勿重复操作"),
    )
    out = await svc._handle_hr_contract_approval(
        {}, {"action": "approve", "employee_number": "E1", "employee_name": "张三",
             "stage": "dept", "leader_name": "李四", "dept_name": "质量部"}
    )
    assert "已审批过" in out["toast"]["content"]

    # 成功分支：更新卡片 + 成功 toast
    monkeypatch.setattr(
        "app.modules.hr.contract_api.process_contract_approval",
        AsyncMock(return_value="部门负责人已同意"),
    )
    update_mock = AsyncMock()
    monkeypatch.setattr(
        "app.modules.hr.contract_api.update_contract_approval_card",
        update_mock,
    )
    out2 = await svc._handle_hr_contract_approval(
        {}, {"action": "approve", "employee_number": "E1", "employee_name": "张三",
             "stage": "dept", "leader_name": "李四", "dept_name": "质量部"}
    )
    assert out2["toast"]["type"] == "success"
    update_mock.assert_awaited_once_with("E1", "张三", "approve", "dept", "质量部")


# ── 岗位调动卡片：防重与异步执行 ────────────────────────


@pytest.mark.asyncio
async def test_position_transfer_approval_dedupe_and_form_value_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_values: dict[str, Any] = {}
    monkeypatch.setattr(
        "app.core.redis.cache_get",
        AsyncMock(side_effect=lambda key: redis_values.get(key)),
    )
    monkeypatch.setattr(
        "app.core.redis.cache_set",
        AsyncMock(side_effect=lambda key, v, **kw: redis_values.__setitem__(key, v)),
    )
    done: list[Any] = []

    async def _fake_do(*a: Any, **k: Any) -> None:
        done.append(a)

    monkeypatch.setattr(svc, "_do_position_transfer_approval", _fake_do)
    # create_task 改为立刻调度（真实语义下为 fire-and-forget）
    monkeypatch.setattr(
        svc.asyncio, "create_task", lambda coro: svc.asyncio.ensure_future(coro)
    )

    # form_value 位于 event.action.form_value
    event = {
        "event": {
            "action": {
                "value": {"module": "position_transfer_approval", "action": "approve",
                          "record_id": _REC1, "node": "n1", "signer": "s1"},
                "form_value": {"salary_change": "是"},
            }
        }
    }
    out = await svc.handle_card_action(event)
    await svc.asyncio.sleep(0)  # 让 fire-and-forget 任务执行
    assert out["toast"]["type"] == "success"
    assert done == [("approve", _REC1, "n1", "s1", {"salary_change": "是"})]

    # 防重：同 key 第二次 → warning
    out2 = await svc.handle_card_action(event)
    assert "请勿重复" in out2["toast"]["content"]

    # form_value 在顶层 event.form_value 与 event.form_value 兜底
    monkeypatch.setattr(
        "app.core.redis.cache_get", AsyncMock(return_value=None)
    )
    done.clear()
    event2 = {
        "event": {"action": {"value": {"module": "position_transfer_approval",
                                       "action": "reject", "record_id": _REC2,
                                       "node": "n2", "signer": "s2"}}},
        "form_value": {"salary_adjust": "降"},
    }
    out3 = await svc.handle_card_action(event2)
    await svc.asyncio.sleep(0)  # 让 fire-and-forget 任务执行
    assert out3["toast"]["type"] == "warning"
    assert done[0][4] == {"salary_adjust": "降"}


# ── HR 表单写入多维表格 ─────────────────────────────────


@pytest.mark.asyncio
async def test_write_hr_form_to_bitable_skip_and_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                scalar_one_or_none=lambda: SimpleNamespace(app_token="t", base_table_id="b")  # noqa: E501
            )
        )
    )
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "app.core.database.async_session_factory", lambda: session_cm
    )
    monkeypatch.setattr(
        "app.modules.hr.feishu_settings_service.get_hr_feishu_app_credentials",
        AsyncMock(return_value=("app", "sec")),
    )
    record = SimpleNamespace(feishu_record_id="rec-1")
    client_instance = AsyncMock()
    monkeypatch.setattr(
        "app.modules.hr.feishu.bitable.BitableClient",
        lambda **kw: client_instance,
    )
    # 无薪资数据 → 直接跳过
    await svc._write_hr_form_to_bitable(record, {})
    client_instance.update_record.assert_not_awaited()

    # 有薪资数据 → 写入
    await svc._write_hr_form_to_bitable(
        record, {"salary_change": "是", "salary_adjust": "上调"}
    )
    client_instance.update_record.assert_awaited_once_with(
        "b", "rec-1", {"薪资职级是否变动": "是", "薪资职级调整为": "上调"}
    )
    # 实体未配置 → 跳过
    session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: None)
    await svc._write_hr_form_to_bitable(
        SimpleNamespace(feishu_record_id="rec-2"), {"salary_change": "是"}
    )


# ── 卡片更新 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_position_transfer_card_by_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace()
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "app.core.database.async_session_factory", lambda: session_cm
    )
    monkeypatch.setattr(
        "app.modules.hr.feishu_settings_service.get_hr_feishu_app_credentials",
        AsyncMock(return_value=("app", "sec")),
    )
    update_mock = AsyncMock()
    monkeypatch.setattr(
        "app.platform.integrations.feishu.notification.update_card",
        update_mock,
    )
    record = SimpleNamespace(employee_name="张三", department_before="A", apply_department="B",  # noqa: E501
                 approval_status="succeeded")
    await svc._update_position_transfer_card_by_id("msg-1", record, "approve")
    assert "✅ 已通过" in update_mock.await_args.args[1]["header"]["title"]["content"]
    # 异常被吞掉仅记日志
    update_mock.side_effect = RuntimeError("down")
    await svc._update_position_transfer_card_by_id("msg-1", record, "reject")


# ── 异步审批全流程（防异常） ────────────────────────────


@pytest.mark.asyncio
async def test_do_position_transfer_approval_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = SimpleNamespace(commit=AsyncMock())
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "app.core.database.async_session_factory", lambda: session_cm
    )
    service = AsyncMock()
    service.get_record = AsyncMock(
        return_value=SimpleNamespace(feishu_approval_message_id=None)
    )
    service.approve_current_node = AsyncMock(
        return_value=SimpleNamespace(feishu_record_id="rec-x", employee_name="张三",
                         department_before="A", apply_department="B",
                         approval_status="ok")
    )
    monkeypatch.setattr(
        "app.modules.hr.service.PositionTransferRecordService",
        lambda sess: service,
    )
    update_mock = AsyncMock()
    monkeypatch.setattr(svc, "_update_position_transfer_card_by_id", update_mock)
    write_mock = AsyncMock()
    monkeypatch.setattr(svc, "_write_hr_form_to_bitable", write_mock)
    await svc._do_position_transfer_approval(
        "approve", _REC1, "n1", "s1", {"salary_change": "是"}
    )
    service.approve_current_node.assert_awaited_once()
    write_mock.assert_awaited_once()
    session.commit.assert_awaited_once()

    # 失败路径：异常被捕获仅记日志
    service.approve_current_node = AsyncMock(side_effect=RuntimeError("db down"))
    await svc._do_position_transfer_approval("reject", _REC2, "n1", "s1", {})
