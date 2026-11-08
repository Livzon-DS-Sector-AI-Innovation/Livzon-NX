"""8 大特殊作业票 API 测试：建票/提交/逐级审批/驳回重签/验票/验收/气体分析。

用子 FastAPI 挂 work_permits_router 并覆盖依赖（同 hazchem API 测试模式），
走 AsyncClient 真实调用路由。飞书通知 mock 掉，存储强制本地回退。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import AppException
from app.modules.safety.api.work_permits import work_permits_router
from app.modules.safety.models import (
    SafetyFeishuAppSettings,
    SpecialWorkCertificate,
    WorkPermit,
    WorkPermitGasAnalysis,
    WorkPermitNode,
    WorkPermitRelation,
    WorkPermitSetting,
)
from app.platform.identity.models import User

_PERMIT_MARK = "WP测试"


class NotifySpy:
    """记录 send_user_card 调用的异步替身。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def __call__(self, open_id: str, title: str, content: str,
                       elements=None, id_type: str = "open_id") -> bool:
        self.calls.append(
            {"open_id": open_id, "title": title, "content": content}
        )
        return True


@pytest.fixture
async def notify_spy(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[NotifySpy]:
    spy = NotifySpy()
    monkeypatch.setattr(
        "app.modules.safety.feishu.notification.send_user_card", spy
    )
    yield spy


@pytest.fixture
async def users(db_session: AsyncSession) -> dict[str, User]:
    creator = User(
        id=uuid4(),
        name=f"{_PERMIT_MARK}申请人{uuid4().hex[:6]}",
        role="user",
        status="active",
    )
    approver = User(
        id=uuid4(),
        name=f"{_PERMIT_MARK}审批人{uuid4().hex[:6]}",
        role="user",
        status="active",
        feishu_open_id=f"ou-wp-test-{uuid4().hex[:12]}",
    )
    admin = User(
        id=uuid4(),
        name=f"{_PERMIT_MARK}管理员{uuid4().hex[:6]}",
        role="admin",
        status="active",
    )
    db_session.add_all([creator, approver, admin])
    await db_session.flush()
    return {"creator": creator, "approver": approver, "admin": admin}


@pytest.fixture
async def work_app(
    db_session: AsyncSession, users: dict[str, User]
) -> FastAPI:
    application = FastAPI()

    @application.exception_handler(AppException)
    async def _app_exception_handler(request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.status_code, "message": exc.message, "data": None},
        )

    application.include_router(work_permits_router, prefix="/api/v1/safety")
    application.dependency_overrides[get_current_user] = lambda: users["creator"]

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_db] = _override_get_db
    return application


@pytest.fixture
async def api_client(
    work_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_files.storage.is_enabled",
        lambda: False,
    )
    transport = ASGITransport(app=work_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _switch_user(work_app: FastAPI, user: User) -> None:
    work_app.dependency_overrides[get_current_user] = lambda: user


async def _cleanup(db: AsyncSession) -> None:
    permit_ids = list(
        await db.scalars(
            select(WorkPermit.id).where(WorkPermit.remark.like(f"{_PERMIT_MARK}%"))
        )
    )
    if permit_ids:
        await db.execute(
            delete(WorkPermitNode).where(WorkPermitNode.permit_id.in_(permit_ids))
        )
        await db.execute(
            delete(WorkPermitGasAnalysis).where(
                WorkPermitGasAnalysis.permit_id.in_(permit_ids)
            )
        )
        await db.execute(
            delete(WorkPermitRelation).where(
                WorkPermitRelation.permit_id.in_(permit_ids)
                | WorkPermitRelation.related_permit_id.in_(permit_ids)
            )
        )
        await db.execute(
            delete(WorkPermit).where(WorkPermit.id.in_(permit_ids))
        )
    await db.execute(
        delete(SafetyFeishuAppSettings).where(
            SafetyFeishuAppSettings.app_id.like(f"{_PERMIT_MARK}%")
        )
    )
    await db.execute(
        delete(SpecialWorkCertificate).where(
            SpecialWorkCertificate.person_name.like(f"{_PERMIT_MARK}%")
        )
    )
    await db.execute(
        delete(WorkPermitSetting).where(
            WorkPermitSetting.setting_key == "cert_check_strict"
        )
    )
    await db.commit()


def _payload(**overrides) -> dict:
    now = datetime.now(UTC)
    base = {
        "permit_type": "blind_plate",
        "permit_level": "none",
        "apply_department": "一车间",
        "work_description": f"{_PERMIT_MARK}更换反应釜盲板",
        "work_location": "车间东侧",
        "planned_start_time": (now + timedelta(hours=1)).isoformat(),
        "planned_end_time": (now + timedelta(hours=3)).isoformat(),
        "type_data": {
            "blind_action": "堵盲板",
            "equipment_pipe_name": "R101 出料管",
        },
        "persons": [{"role": "work_leader", "name": "张三"}],
        "remark": f"{_PERMIT_MARK}{uuid4().hex[:8]}",
    }
    base.update(overrides)
    return base


async def _create_permit(
    client: AsyncClient, **overrides
) -> dict:
    response = await client.post(
        "/api/v1/safety/work-permits", json=_payload(**overrides)
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _blind_assignments(approver_id) -> list[dict]:
    return [
        {
            "node_key": "safety_officer_opinion",
            "approver_user_id": str(approver_id),
        },
        {
            "node_key": "workshop_leader_opinion",
            "approver_user_id": str(approver_id),
        },
    ]


async def test_create_and_meta_roundtrip(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    meta = await api_client.get("/api/v1/safety/work-permits/meta")
    assert meta.status_code == 200, meta.text
    meta_data = meta.json()["data"]
    assert len(meta_data["permit_types"]) == 8
    assert "hot_work" in meta_data["gas_types"]
    assert meta_data["gas_cycle_minutes"]["confined_space"] == 120
    assert any(
        item["value"] == "electrician"
        for item in meta_data["certificate_categories"]
    )

    permit = await _create_permit(api_client)
    assert permit["permit_no"].startswith("MB-")
    assert permit["status"] == "draft"
    assert permit["type_data"]["blind_action"] == "堵盲板"

    detail = await api_client.get(f"/api/v1/safety/work-permits/{permit['id']}")
    assert detail.status_code == 200
    assert detail.json()["data"]["id"] == permit["id"]
    await _cleanup(db_session)


async def test_create_rejects_bad_payload(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    missing = await api_client.post(
        "/api/v1/safety/work-permits", json=_payload(type_data={})
    )
    assert missing.status_code == 422
    assert "设备、管道名称" in missing.json()["message"]

    bad_level = await api_client.post(
        "/api/v1/safety/work-permits", json=_payload(permit_level="grade3")
    )
    assert bad_level.status_code == 422

    bad_role = await api_client.post(
        "/api/v1/safety/work-permits",
        json=_payload(persons=[{"role": "pilot", "name": "李四"}]),
    )
    assert bad_role.status_code == 422
    await _cleanup(db_session)


async def test_submit_requires_approver_and_validity(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    permit = await _create_permit(api_client)
    blocked = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/submit",
        json={"assignments": []},
    )
    assert blocked.status_code == 422
    assert "安全员意见" in blocked.json()["message"]

    # 动火一级默认有效期 8h：11h 实施时长必须拦截
    now = datetime.now(UTC)
    hot = await _create_permit(
        api_client,
        permit_type="hot_work",
        permit_level="grade1",
        type_data={"hot_work_location": "罐区", "hot_work_methods": ["焊接"]},
        planned_start_time=(now + timedelta(hours=1)).isoformat(),
        planned_end_time=(now + timedelta(hours=12)).isoformat(),
    )
    hot_blocked = await api_client.post(
        f"/api/v1/safety/work-permits/{hot['id']}/submit",
        json={"assignments": []},
    )
    assert hot_blocked.status_code == 422
    assert "有效期" in hot_blocked.json()["message"]
    await _cleanup(db_session)


async def test_full_flow_approve_then_accept(
    api_client: AsyncClient,
    work_app: FastAPI,
    db_session: AsyncSession,
    users: dict[str, User],
) -> None:
    await _cleanup(db_session)
    approver = users["approver"]
    permit = await _create_permit(api_client)

    submitted = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/submit",
        json={"assignments": _blind_assignments(approver.id)},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["status"] == "pending_approval"

    detail = await api_client.get(f"/api/v1/safety/work-permits/{permit['id']}")
    nodes = detail.json()["data"]["nodes"]
    assert len(nodes) == 3  # 安全员意见 → 车间负责人意见 → 完工验收
    assert nodes[0]["status"] == "pending"
    assert nodes[0]["assigned_approver_name"] == approver.name

    # 未指派给当前登录用户：403
    forbidden = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/nodes/{nodes[0]['id']}/approve"
    )
    assert forbidden.status_code == 403

    _switch_user(work_app, approver)
    approve1 = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/nodes/{nodes[0]['id']}/approve",
        json={"opinion": "同意"},
    )
    assert approve1.status_code == 200, approve1.text

    detail = await api_client.get(f"/api/v1/safety/work-permits/{permit['id']}")
    nodes = detail.json()["data"]["nodes"]
    assert nodes[0]["status"] == "approved"
    assert nodes[1]["status"] == "pending"

    # 非当前节点签批：409
    wrong_node = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/nodes/{nodes[2]['id']}/approve"
    )
    assert wrong_node.status_code == 409

    approve2 = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/nodes/{nodes[1]['id']}/approve"
    )
    assert approve2.status_code == 200, approve2.text

    detail = await api_client.get(f"/api/v1/safety/work-permits/{permit['id']}")
    assert detail.json()["data"]["status"] == "approved"

    # 无验票环节的票直接完工验收（切回创建人）
    _switch_user(work_app, users["creator"])
    accepted = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/accept",
        json={"type_data": {}},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["data"]["status"] == "completed"
    await _cleanup(db_session)


async def test_reject_and_resubmit_new_round(
    api_client: AsyncClient,
    work_app: FastAPI,
    db_session: AsyncSession,
    users: dict[str, User],
) -> None:
    await _cleanup(db_session)
    approver = users["approver"]
    permit = await _create_permit(api_client)
    submitted = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/submit",
        json={"assignments": _blind_assignments(approver.id)},
    )
    assert submitted.status_code == 200
    detail = await api_client.get(f"/api/v1/safety/work-permits/{permit['id']}")
    node = detail.json()["data"]["nodes"][0]

    _switch_user(work_app, approver)
    rejected = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/nodes/{node['id']}/reject",
        json={"opinion": "盲板参数不全，请补充"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["data"]["status"] == "rejected"
    _switch_user(work_app, users["creator"])

    detail = await api_client.get(f"/api/v1/safety/work-permits/{permit['id']}")
    data = detail.json()["data"]
    assert data["reject_opinion"] == "盲板参数不全，请补充"
    assert data["approval_round"] == 1

    edited = await api_client.put(
        f"/api/v1/safety/work-permits/{permit['id']}",
        json={
            "type_data": {
                "blind_action": "堵盲板",
                "equipment_pipe_name": "R101 出料管",
                "medium": "物料A",
            }
        },
    )
    assert edited.status_code == 200, edited.text

    resubmitted = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/submit",
        json={"assignments": _blind_assignments(approver.id)},
    )
    assert resubmitted.status_code == 200, resubmitted.text

    detail = await api_client.get(f"/api/v1/safety/work-permits/{permit['id']}")
    data = detail.json()["data"]
    assert data["status"] == "pending_approval"
    assert data["approval_round"] == 2
    assert len(data["nodes"]) == 6  # 第 1 轮 3 节点 + 第 2 轮 3 节点
    await _cleanup(db_session)


async def test_verify_gas_accept_flow(
    api_client: AsyncClient,
    work_app: FastAPI,
    db_session: AsyncSession,
    users: dict[str, User],
) -> None:
    await _cleanup(db_session)
    approver = users["approver"]
    now = datetime.now(UTC)
    permit = await _create_permit(
        api_client,
        permit_type="hot_work",
        permit_level="grade2",
        type_data={"hot_work_location": "动火点A", "hot_work_methods": ["打磨"]},
        planned_start_time=(now + timedelta(hours=1)).isoformat(),
        planned_end_time=(now + timedelta(hours=3)).isoformat(),
    )
    submitted = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/submit",
        json={
            "assignments": [
                {"node_key": "safety_officer", "approver_user_id": str(approver.id)},
                {
                    "node_key": "workshop_leader",
                    "approver_user_id": str(approver.id),
                },
                {"node_key": "safety_dept", "approver_user_id": str(approver.id)},
            ]
        },
    )
    assert submitted.status_code == 200, submitted.text

    gas = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/gas-analyses",
        json={
            "phase": "pre_work",
            "sampled_at": now.isoformat(),
            "items": [{"name": "可燃气体", "standard": "0", "value": "0"}],
            "oxygen_value": "20.9",
            "analyst_name": "分析员",
        },
    )
    assert gas.status_code == 200, gas.text

    # 作业期间复检在开工前录入必须 409
    early = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/gas-analyses",
        json={"phase": "on_duty", "sampled_at": now.isoformat()},
    )
    assert early.status_code == 409

    for _ in range(4):
        detail = await api_client.get(f"/api/v1/safety/work-permits/{permit['id']}")
        data = detail.json()["data"]
        if data["status"] != "pending_approval":
            break
        pending = [n for n in data["nodes"] if n["status"] == "pending"]
        assert pending, detail.text
        # 无指派的确认节点由创建人处理，审批节点由指派审批人签
        _switch_user(
            work_app,
            users["creator"] if pending[0]["assigned_approver_id"] is None else approver,
        )
        approved = await api_client.post(
            f"/api/v1/safety/work-permits/{permit['id']}/nodes/{pending[0]['id']}/approve"
        )
        assert approved.status_code == 200, approved.text

    detail = await api_client.get(f"/api/v1/safety/work-permits/{permit['id']}")
    assert detail.json()["data"]["status"] == "approved"

    _switch_user(work_app, users["creator"])
    verified = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/verify"
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["data"]["status"] == "active"

    on_duty = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/gas-analyses",
        json={
            "phase": "on_duty",
            "sampled_at": datetime.now(UTC).isoformat(),
            "analysis_point": "动火点",
            "items": [{"name": "可燃气体", "standard": "0", "value": "0"}],
        },
    )
    assert on_duty.status_code == 200

    detail = await api_client.get(f"/api/v1/safety/work-permits/{permit['id']}")
    data = detail.json()["data"]
    assert len(data["gas_analyses"]) == 2
    assert data["next_gas_due_at"] is not None

    accepted = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/accept",
        json={"type_data": {}},
    )
    assert accepted.status_code == 200
    assert accepted.json()["data"]["status"] == "completed"
    await _cleanup(db_session)


async def test_relation_cancel_and_reassign(
    api_client: AsyncClient,
    work_app: FastAPI,
    db_session: AsyncSession,
    users: dict[str, User],
) -> None:
    await _cleanup(db_session)
    approver = users["approver"]
    permit_a = await _create_permit(api_client)
    permit_b = await _create_permit(api_client)

    linked = await api_client.post(
        f"/api/v1/safety/work-permits/{permit_a['id']}/relations",
        json={"related_permit_id": permit_b["id"]},
    )
    assert linked.status_code == 200, linked.text
    relations = linked.json()["data"]["relations"]
    assert len(relations) == 1
    assert relations[0]["related_permit_no"] == permit_b["permit_no"]

    duplicate = await api_client.post(
        f"/api/v1/safety/work-permits/{permit_a['id']}/relations",
        json={"related_permit_id": permit_b["id"]},
    )
    assert duplicate.status_code == 409

    self_link = await api_client.post(
        f"/api/v1/safety/work-permits/{permit_a['id']}/relations",
        json={"related_permit_id": permit_a["id"]},
    )
    assert self_link.status_code == 422

    # 提交后管理员可改派；非管理员改派 403
    submitted = await api_client.post(
        f"/api/v1/safety/work-permits/{permit_a['id']}/submit",
        json={"assignments": _blind_assignments(approver.id)},
    )
    assert submitted.status_code == 200
    detail = await api_client.get(f"/api/v1/safety/work-permits/{permit_a['id']}")
    pending = detail.json()["data"]["nodes"][0]

    forbidden_reassign = await api_client.post(
        f"/api/v1/safety/work-permits/{permit_a['id']}/nodes/{pending['id']}/reassign",
        json={"approver_user_id": str(users["creator"].id)},
    )
    assert forbidden_reassign.status_code == 403

    _switch_user(work_app, users["admin"])
    reassigned = await api_client.post(
        f"/api/v1/safety/work-permits/{permit_a['id']}/nodes/{pending['id']}/reassign",
        json={"approver_user_id": str(users["creator"].id)},
    )
    assert reassigned.status_code == 200, reassigned.text

    # 作废
    _switch_user(work_app, users["creator"])
    cancelled = await api_client.post(
        f"/api/v1/safety/work-permits/{permit_a['id']}/cancel"
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "cancelled"
    await _cleanup(db_session)


async def test_list_stats_and_notify(
    api_client: AsyncClient,
    db_session: AsyncSession,
    users: dict[str, User],
    notify_spy: NotifySpy,
) -> None:
    await _cleanup(db_session)
    permit = await _create_permit(api_client)

    listed = await api_client.get(
        "/api/v1/safety/work-permits",
        params={"keyword": _PERMIT_MARK, "permit_type": "blind_plate"},
    )
    assert listed.status_code == 200
    data = listed.json()["data"]
    assert data["total"] >= 1
    assert any(item["id"] == permit["id"] for item in data["items"])

    stats = await api_client.get("/api/v1/safety/work-permits/stats")
    assert stats.status_code == 200
    assert stats.json()["data"]["draft"] >= 1

    # 启用作业票通知后，提交触发待办卡片（发给首个节点审批人）
    db_session.add(
        SafetyFeishuAppSettings(
            app_id=f"{_PERMIT_MARK}app{uuid4().hex[:6]}",
            app_secret="secret",
            is_enabled=True,
            permit_notify_enabled=True,
        )
    )
    await db_session.flush()
    submitted = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/submit",
        json={"assignments": _blind_assignments(users["approver"].id)},
    )
    assert submitted.status_code == 200, submitted.text
    assert notify_spy.calls, "提交后应发送飞书待办卡片"
    assert any("审批" in call["title"] for call in notify_spy.calls)
    await _cleanup(db_session)


async def _add_certificate(
    db: AsyncSession,
    name: str,
    category: str = "welding_cutting",
    status: str = "valid",
) -> SpecialWorkCertificate:
    cert = SpecialWorkCertificate(
        person_name=name,
        certificate_category=category,
        certificate_no=f"WP{uuid4().hex[:12]}",
        expiry_date=datetime.now(UTC).date() + timedelta(days=400),
        status=status,
    )
    db.add(cert)
    await db.flush()
    return cert


async def test_permit_settings_roundtrip(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    got = await api_client.get("/api/v1/safety/work-permit-settings")
    assert got.status_code == 200, got.text
    assert got.json()["data"]["cert_check_strict"] is False

    put = await api_client.put(
        "/api/v1/safety/work-permit-settings",
        json={"cert_check_strict": True},
    )
    assert put.status_code == 200, put.text
    assert put.json()["data"]["cert_check_strict"] is True
    got_again = await api_client.get("/api/v1/safety/work-permit-settings")
    assert got_again.json()["data"]["cert_check_strict"] is True
    await _cleanup(db_session)


async def test_submit_cert_soft_warning(
    api_client: AsyncClient, db_session: AsyncSession, users: dict[str, User]
) -> None:
    """作业人未关联证件：默认软提示，提交成功且 warnings 带文案。"""
    await _cleanup(db_session)
    permit = await _create_permit(
        api_client,
        persons=[{"role": "worker", "name": f"{_PERMIT_MARK}李四"}],
    )
    submitted = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/submit",
        json={"assignments": _blind_assignments(users["approver"].id)},
    )
    assert submitted.status_code == 200, submitted.text
    warnings = submitted.json()["data"]["warnings"]
    assert any("未关联证件" in item for item in warnings)
    await _cleanup(db_session)


async def test_submit_cert_strict_block(
    api_client: AsyncClient, db_session: AsyncSession, users: dict[str, User]
) -> None:
    """cert_check_strict 开启后证件问题拦截提交，关闭后恢复软提示。"""
    await _cleanup(db_session)
    db_session.add(
        WorkPermitSetting(setting_key="cert_check_strict", setting_value=True)
    )
    await db_session.flush()
    permit = await _create_permit(
        api_client,
        persons=[{"role": "worker", "name": f"{_PERMIT_MARK}王五"}],
    )
    submitted = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/submit",
        json={"assignments": _blind_assignments(users["approver"].id)},
    )
    assert submitted.status_code == 422, submitted.text
    assert "证件校验未通过" in submitted.json()["message"]

    await db_session.execute(
        delete(WorkPermitSetting).where(
            WorkPermitSetting.setting_key == "cert_check_strict"
        )
    )
    await db_session.flush()
    resubmitted = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/submit",
        json={"assignments": _blind_assignments(users["approver"].id)},
    )
    assert resubmitted.status_code == 200, resubmitted.text
    assert any(
        "未关联证件" in item for item in resubmitted.json()["data"]["warnings"]
    )
    await _cleanup(db_session)


async def test_submit_cert_category_and_holder_mismatch(
    api_client: AsyncClient, db_session: AsyncSession, users: dict[str, User]
) -> None:
    """证件类别不符 + 持有人姓名不一致：两条软提示同时返回。"""
    await _cleanup(db_session)
    cert = await _add_certificate(db_session, f"{_PERMIT_MARK}王五", category="forklift")
    permit = await _create_permit(
        api_client,
        persons=[
            {
                "role": "worker",
                "name": f"{_PERMIT_MARK}张三",
                "certificate_id": str(cert.id),
                "certificate_no": cert.certificate_no,
                "certificate_category": "forklift",
            }
        ],
    )
    submitted = await api_client.post(
        f"/api/v1/safety/work-permits/{permit['id']}/submit",
        json={"assignments": _blind_assignments(users["approver"].id)},
    )
    assert submitted.status_code == 200, submitted.text
    warnings = submitted.json()["data"]["warnings"]
    assert any("类别" in item and "建议" in item for item in warnings)
    assert any(f"持有人为「{_PERMIT_MARK}王五」" in item for item in warnings)
    await _cleanup(db_session)
