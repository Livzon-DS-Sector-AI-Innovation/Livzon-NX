"""设备检修台账：配置校验、连接测试、同步编排、查询与接口层测试。

与 test_repair_ledger_mirror.py 互补：那里覆盖字段映射、单表同步与频次聚合，
这里覆盖配置保存的各校验分支、连接测试结果落库、多车间同步互不影响，
以及经 ASGI 实际路由的接口行为。外部飞书调用一律用替身，不访问真实服务。
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.llm.encryption import decrypt_api_key, encrypt_api_key, mask_api_key
from app.main import app
from app.modules.equipment.models.feishu_app import EquipmentFeishuApp
from app.modules.equipment.models.repair_ledger import (
    RepairFeishuConfig,
    RepairRecord,
    RepairSyncState,
)
from app.modules.equipment.schemas.repair_ledger import RepairConfigUpdateRequest
from app.modules.equipment.service import repair_ledger as service
from app.platform.identity.deps import get_current_user


@pytest.fixture(autouse=True)
def _test_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        get_settings(), "LLM_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )


def _code() -> str:
    return f"t{uuid.uuid4().hex[:6]}"


async def _config(db: AsyncSession, code: str, *, enabled: bool = True) -> None:
    app = EquipmentFeishuApp(
        name=f"检修应用-{code}",
        app_id=f"cli_{code}",
        app_secret=encrypt_api_key("secret"),
    )
    db.add(app)
    await db.flush()
    db.add(
        RepairFeishuConfig(
            workshop_code=code,
            feishu_app_id=app.id,
            app_token=f"base-{code}",
            table_id=f"tbl-{code}",
            is_enabled=enabled,
        )
    )
    await db.flush()


async def _purge(db: AsyncSession, codes: list[str], app_row_ids: list[Any]) -> None:
    """服务层会提交事务，测试结束前显式清理自己创建的行。"""
    await db.rollback()
    for model in (RepairRecord, RepairSyncState, RepairFeishuConfig):
        await db.execute(delete(model).where(model.workshop_code.in_(codes)))
    # _config 为每个车间登记的应用 App ID 固定为 cli_<车间代码>
    await db.execute(
        delete(EquipmentFeishuApp).where(
            EquipmentFeishuApp.app_id.in_([f"cli_{code}" for code in codes])
        )
    )
    if app_row_ids:
        await db.execute(
            delete(EquipmentFeishuApp).where(EquipmentFeishuApp.id.in_(app_row_ids))
        )
    await db.commit()


async def _purge_apps(db: AsyncSession, app_id_prefixes: list[str]) -> None:
    """按 App ID 前缀清理登记过程中创建的应用。"""
    await db.rollback()
    for prefix in app_id_prefixes:
        await db.execute(
            delete(EquipmentFeishuApp).where(
                EquipmentFeishuApp.app_id.like(f"{prefix}%")
            )
        )
    await db.commit()


class _Client:
    """可配置的飞书多维表格客户端替身：按页返回，或直接抛错。"""

    def __init__(
        self, pages: list[dict[str, Any]] | None = None, error: Exception | None = None
    ) -> None:
        self._pages = list(pages or [])
        self._error = error
        self.calls: list[dict[str, Any]] = []

    async def search_records_page(self, table_id: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"table_id": table_id, **kwargs})
        if self._error is not None:
            raise self._error
        if self._pages:
            return self._pages.pop(0)
        return {"items": [], "has_more": False, "page_token": None, "total": 0}


def _route_clients(
    clients: dict[str, _Client], monkeypatch: pytest.MonkeyPatch
) -> None:
    """按配置里的 app_token 把客户端替身分发给各车间。"""

    def build(config: service.RepairEffectiveConfig) -> _Client:
        return clients[config.app_token]

    monkeypatch.setattr(service, "_build_client", build)


def _item(record_id: str | None, equipment: str = "离心泵A") -> dict[str, Any]:
    body: dict[str, Any] = {
        "fields": {"设备名称/型号": equipment, "维修日期": 1_790_000_000_000},
        "last_modified_time": 1_790_000_100_000,
    }
    if record_id is not None:
        body["record_id"] = record_id
    return body


def _page(
    items: list[dict[str, Any]], *, has_more: bool = False, total: int | None = None
) -> dict[str, Any]:
    return {
        "items": items,
        "has_more": has_more,
        "page_token": "next-page" if has_more else None,
        "total": total,
    }


# ── 配置 ──────────────────────────────────────────────────────────


async def test_list_enabled_workshops_returns_only_enabled_ones(
    db_session: AsyncSession,
) -> None:
    on_a, on_b, off = _code(), _code(), _code()
    await _config(db_session, on_a)
    await _config(db_session, on_b)
    await _config(db_session, off, enabled=False)
    try:
        enabled = await service.list_enabled_workshops(db_session)
        assert on_a in enabled and on_b in enabled
        assert off not in enabled
        assert enabled == sorted(enabled)
    finally:
        await _purge(db_session, [on_a, on_b, off], [])


async def test_update_config_rejects_incomplete_or_unsafe_input(
    db_session: AsyncSession,
) -> None:
    code = _code()
    app_id = f"cli_new_{code}"
    try:
        # 完整链接只接受 https
        with pytest.raises(AppException, match="https://"):
            await service.update_config(
                db_session,
                code,
                RepairConfigUpdateRequest(
                    app_id=app_id,
                    app_secret="s",
                    app_token="bascn1",
                    table_id="tbl1",
                    base_url="http://example.feishu.cn/base/bascn1",
                ),
            )

        await db_session.rollback()

        # 启用同步时表格与数据表必填
        with pytest.raises(AppException, match="启用同步需"):
            await service.update_config(
                db_session,
                code,
                RepairConfigUpdateRequest(
                    app_id=app_id, app_secret="s", is_enabled=True
                ),
            )

        await db_session.rollback()

        # 新应用必须带 Secret；不存在的已登记应用返回 404
        with pytest.raises(AppException, match="需同时填写"):
            await service.update_config(
                db_session, code, RepairConfigUpdateRequest(app_id=app_id)
            )
        with pytest.raises(AppException, match="不存在") as missing:
            await service.update_config(
                db_session,
                code,
                RepairConfigUpdateRequest(
                    feishu_app_id=uuid.uuid4(), app_token="bascn1", table_id="tbl1"
                ),
            )
        assert missing.value.status_code == 404
        assert await service._get_config_row(db_session, code) is None  # noqa: SLF001
    finally:
        await _purge(db_session, [code], [])
        await _purge_apps(db_session, [app_id])


async def test_update_config_resolves_wiki_link_with_the_selected_app(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    code = _code()
    resolve = AsyncMock(return_value="bascn_from_wiki")
    monkeypatch.setattr(service, "resolve_wiki_bitable_app_token", resolve)
    try:
        detail = await service.update_config(
            db_session,
            code,
            RepairConfigUpdateRequest(
                app_id=f"cli_wiki_{code}",
                app_secret="s",
                app_token="https://x.feishu.cn/wiki/NodeABC?table=tblWIKI",
                table_id="tblWIKI",
                is_enabled=True,
            ),
        )
        resolve.assert_awaited_once_with(
            app_id=f"cli_wiki_{code}", app_secret="s", node_token="NodeABC"
        )
        assert detail["app_token"] == "bascn_from_wiki"
        assert detail["table_id"] == "tblWIKI"
        assert detail["enabled"] is True
    finally:
        await _purge(db_session, [code], [])
        await _purge_apps(db_session, [f"cli_wiki_{code}"])


async def test_update_config_reports_wiki_resolution_problems(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    code = _code()
    request = RepairConfigUpdateRequest(
        app_id=f"cli_wiki_{code}",
        app_secret="s",
        app_token="https://x.feishu.cn/wiki/NodeABC",
        table_id="tblWIKI",
    )
    decrypt = service.feishu_app_service.decrypt_app_secret
    try:
        # 所选应用没有可用 Secret 时无法解析知识库链接
        monkeypatch.setattr(
            service.feishu_app_service, "decrypt_app_secret", lambda _s: ""
        )
        with pytest.raises(AppException, match="需先选择已配置 Secret"):
            await service.update_config(db_session, code, request)
        await db_session.rollback()

        # 知识库节点解析失败：转成明确的业务错误
        monkeypatch.setattr(service.feishu_app_service, "decrypt_app_secret", decrypt)
        monkeypatch.setattr(
            service,
            "resolve_wiki_bitable_app_token",
            AsyncMock(side_effect=RuntimeError("node not found")),
        )
        with pytest.raises(AppException, match="解析知识库多维表格失败"):
            await service.update_config(db_session, code, request)
    finally:
        await _purge(db_session, [code], [])
        await _purge_apps(db_session, [f"cli_wiki_{code}"])


async def test_update_config_reuses_a_registered_app_only_with_its_masked_secret(
    db_session: AsyncSession,
) -> None:
    code = _code()
    app = EquipmentFeishuApp(
        name="已登记应用",
        app_id=f"cli_dup_{code}",
        app_secret=encrypt_api_key("stored"),
    )
    db_session.add(app)
    await db_session.flush()
    await db_session.commit()
    try:
        with pytest.raises(AppException, match="已登记"):
            await service.update_config(
                db_session,
                code,
                RepairConfigUpdateRequest(
                    app_id=f"cli_dup_{code}",
                    app_secret="another-secret",
                    app_token="bascn1",
                ),
            )
        await db_session.rollback()

        detail = await service.update_config(
            db_session,
            code,
            RepairConfigUpdateRequest(
                app_id=f"cli_dup_{code}",
                app_secret=mask_api_key("stored"),
                app_token="bascn1",
                table_id="tbl1",
                is_enabled=True,
            ),
        )
        assert detail["feishu_app_id"] == app.id
        assert detail["app_secret_configured"] is True
        registered = (
            (
                await db_session.execute(
                    select(EquipmentFeishuApp).where(
                        EquipmentFeishuApp.app_id == f"cli_dup_{code}"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert registered == [app]
    finally:
        await _purge(db_session, [code], [app.id])


# ── 连接测试 ──────────────────────────────────────────────────────


async def test_test_config_records_each_outcome_on_the_config_row(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    code = _code()
    await _config(db_session, code)
    client = _Client(pages=[_page([_item("r1")], total=12)])
    _route_clients({f"base-{code}": client}, monkeypatch)
    try:
        result = await service.test_config(db_session, code)
        assert result == {"success": True, "message": "连接成功，数据表共 12 条记录"}
        assert client.calls[0]["page_size"] == 1
        row = await service._get_config_row(db_session, code)  # noqa: SLF001
        assert row.last_test_status == "success"
        assert row.last_test_error is None
        assert row.last_tested_at is not None

        # 飞书未返回 total 时给出占位而不是报错
        _route_clients(
            {f"base-{code}": _Client(pages=[_page([_item("r1")])])}, monkeypatch
        )
        assert (await service.test_config(db_session, code))["message"].endswith(
            "共 ？ 条记录"
        )

        # 飞书调用出现未知异常（网络、超时等）：落为失败结果，
        # 不向接口抛 500，也不泄露异常详情
        _route_clients(
            {
                f"base-{code}": _Client(
                    error=RuntimeError("https://open.feishu.cn/secret")
                )
            },
            monkeypatch,
        )
        failed = await service.test_config(db_session, code)
        assert failed["success"] is False
        assert "RuntimeError" in failed["message"]
        assert "secret" not in failed["message"]
        row = await service._get_config_row(db_session, code)  # noqa: SLF001
        assert row.last_test_status == "failed"
        assert row.last_test_error == failed["message"]
    finally:
        await _purge(db_session, [code], [])


async def test_test_config_reports_an_unconfigured_workshop(
    db_session: AsyncSession,
) -> None:
    result = await service.test_config(db_session, _code())
    assert result["success"] is False
    assert "未启用" in result["message"]


# ── 同步编排 ──────────────────────────────────────────────────────


async def test_sync_enabled_keeps_one_workshop_failure_from_affecting_others(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    ok, paged, broken, disabled, crashed = (_code() for _ in range(5))
    for code in (ok, paged, broken, crashed):
        await _config(db_session, code)
    await _config(db_session, disabled, enabled=False)
    clients: dict[str, _Client] = {
        # 没有 record_id 的行会被跳过，不计入镜像
        f"base-{ok}": _Client(pages=[_page([_item("ok-1"), _item(None)], total=1)]),
        # 分页：第一页之后还有一页，翻页令牌要带回飞书
        f"base-{paged}": _Client(
            pages=[
                _page([_item("pg-1")], has_more=True),
                _page([_item("pg-2")], total=2),
            ]
        ),
        f"base-{broken}": _Client(error=RuntimeError("WrongTableId tbl-x")),
        f"base-{crashed}": _Client(pages=[_page([_item("cr-1", "crash-me")])]),
    }
    # 同步失败会回滚当前事务；先把配置提交，和生产环境一致（配置早已落库）
    await db_session.commit()
    _route_clients(clients, monkeypatch)

    real_normalize = service.normalize_record_fields

    def normalize(fields: dict[str, Any]) -> dict[str, Any]:
        if fields.get("设备名称/型号") == "crash-me":
            raise RuntimeError("boom")
        return real_normalize(fields)

    monkeypatch.setattr(service, "normalize_record_fields", normalize)
    codes = [ok, paged, broken, disabled, crashed]
    try:
        results = await service.sync_enabled(db_session)

        assert results[ok] == {"synced": 2, "total": 1}
        assert [call["page_token"] for call in clients[f"base-{paged}"].calls] == [
            None,
            "next-page",
        ]
        assert results[paged] == {"synced": 2, "total": 2}
        # 全量同步只处理已启用的车间；未启用的车间只在被点名同步时返回说明
        assert disabled not in results
        assert (
            "同步未启用"
            in (await service.sync_enabled(db_session, disabled))[disabled]["error"]
        )
        assert "Table ID 无效" in results[broken]["error"]
        assert "同步中断已回滚" in results[crashed]["error"]

        # 成功与失败都落在各自的同步状态行上
        states = {
            row.workshop_code: row
            for row in (await db_session.execute(select(RepairSyncState))).scalars()
            if row.workshop_code in {ok, paged, broken, crashed}
        }
        assert states[ok].last_status == "success" and states[ok].total_rows == 1
        assert states[paged].last_status == "success" and states[paged].total_rows == 2
        assert states[broken].last_status == "failed"
        assert states[crashed].last_status == "failed"

        # 只同步一个车间：飞书侧已清空，本地随之删除对账；其他车间不受影响
        clients[f"base-{ok}"] = _Client(pages=[_page([], total=0)])
        assert await service.sync_enabled(db_session, ok) == {
            ok: {"synced": 0, "total": 0}
        }
        assert (await service.get_sync_state(db_session, ok))["total_rows"] == 0
        assert (await service.get_sync_state(db_session, paged))["total_rows"] == 2
        assert (await service.get_sync_state(db_session, paged))["enabled"] is True
    finally:
        await _purge(db_session, codes, [])


async def test_sync_workshop_refuses_an_unconfigured_workshop(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(AppException, match="未配置"):
        await service.sync_workshop(db_session, _code())


# ── 飞书取值规范化 ────────────────────────────────────────────────


def test_value_helpers_tolerate_the_shapes_feishu_returns() -> None:
    # 富文本分段、普通字符串与数字都能落成文本
    assert (
        service._text_value([{"text": "机械密封"}, {"text": "泄漏"}]) == "机械密封泄漏"
    )  # noqa: SLF001
    assert service._text_value(["裸段"]) == "裸段"
    assert service._text_value("  去空白  ") == "去空白"
    assert service._text_value(42) == "42"
    assert service._text_value([]) is None
    assert service._text_value(None) is None

    # 人员字段：中文名、英文名兜底，多个人用顿号连接
    assert (
        service._person_value(  # noqa: SLF001
            [{"id": "ou_1", "name": "张三"}, {"id": "ou_2", "en_name": "Li Si"}]
        )
        == "张三、Li Si"
    )
    assert service._person_value(["王五"]) == "王五"  # noqa: SLF001
    assert service._person_value([{"id": "ou_3"}]) == "ou_3"  # noqa: SLF001
    assert service._person_value("张三") == "张三"  # noqa: SLF001
    assert service._person_value([]) is None  # noqa: SLF001

    # 日期：毫秒时间戳、ISO 字符串、无法识别的原文
    assert service._date_value(1_790_000_000_000) is not None  # noqa: SLF001
    assert service._date_value("2026-11-01") == date(2026, 11, 1)  # noqa: SLF001
    assert service._date_value("201年9月") is None  # noqa: SLF001
    assert service._datetime_value("not-a-time") is None  # noqa: SLF001
    assert service._truncate("abcdef", 3) == "abc"  # noqa: SLF001
    assert service._truncate("abc", 3) == "abc"  # noqa: SLF001
    assert service._truncate(None, 3) is None  # noqa: SLF001
    assert decrypt_api_key(encrypt_api_key("round-trip")) == "round-trip"


# ── 查询 ──────────────────────────────────────────────────────────


async def test_queries_cover_the_remaining_filters(
    db_session: AsyncSession,
) -> None:
    code = _code()
    today = date(2026, 11, 20)
    db_session.add_all(
        [
            RepairRecord(
                workshop_code=code,
                record_id=f"{code}-1",
                equipment_text="离心泵A",
                repaired_at=today,
                fault_desc="机械密封泄漏",
                result="正常运行",
            ),
            RepairRecord(
                workshop_code=code,
                record_id=f"{code}-2",
                equipment_text="离心泵A",
                repaired_at=today - timedelta(days=3),
                fault_desc="异响",
                person_text="张三",
                result="待观察",
            ),
            RepairRecord(
                workshop_code=code,
                record_id=f"{code}-3",
                equipment_text="薄膜蒸发器 4",
                repaired_at=today - timedelta(days=60),
                fault_desc="密封泄漏",
            ),
        ]
    )
    await db_session.flush()
    await db_session.commit()
    try:
        # 不限时间，条数上限生效：按次数降序
        ranking = await service.frequency(db_session, workshop=code, limit=1)
        assert [item["equipment_text"] for item in ranking] == ["离心泵A"]
        assert ranking[0]["times"] == 2

        # 截止日期、维修后状态、按故障描述 / 人员 / 车间原文搜索、分页
        rows, total = await service.list_records(
            db_session, workshop=code, date_to=today - timedelta(days=1)
        )
        assert total == 2
        rows, total = await service.list_records(
            db_session, workshop=code, result_status="待观察"
        )
        assert total == 1 and rows[0].fault_desc == "异响"
        assert (await service.list_records(db_session, workshop=code, keyword="密封"))[
            1
        ] == 2
        assert (await service.list_records(db_session, workshop=code, keyword="张三"))[
            1
        ] == 1
        assert (
            await service.list_records(db_session, workshop=code, keyword="薄膜蒸发器")
        )[1] == 1
        rows, total = await service.list_records(
            db_session, workshop=code, page=2, page_size=2
        )
        assert total == 3 and len(rows) == 1

        assert set(await service.distinct_results(db_session, None)) >= {
            "正常运行",
            "待观察",
        }
        assert await service.distinct_results(db_session, code) == [
            "待观察",
            "正常运行",
        ]
    finally:
        await _purge(db_session, [code], [])


# ── 调度 ──────────────────────────────────────────────────────────


async def test_generator_syncs_every_enabled_workshop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.equipment.scheduled import RepairLedgerMirrorSyncGenerator

    session = SimpleNamespace(commit=AsyncMock())
    monkeypatch.setattr(
        service,
        "list_enabled_workshops",
        AsyncMock(return_value=["101-1", "201-1"]),
    )
    sync_enabled = AsyncMock(return_value={"101-1": {"synced": 1, "total": 1}})
    monkeypatch.setattr(service, "sync_enabled", sync_enabled)

    generator = RepairLedgerMirrorSyncGenerator()
    assert await generator.find_due(session) == ["101-1", "201-1"]

    await generator.execute_one(session, "101-1")
    sync_enabled.assert_awaited_once_with(session, "101-1")
    session.commit.assert_awaited_once()


# ── 接口层 ────────────────────────────────────────────────────────


async def test_config_write_read_test_and_manual_sync_endpoints(
    _equipment_session: AsyncSession,
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    code = _code()
    app = EquipmentFeishuApp(
        name="接口测试应用",
        app_id=f"cli_api_{code}",
        app_secret=encrypt_api_key("secret"),
    )
    _equipment_session.add(app)
    await _equipment_session.flush()
    # 连接测试不访问真实飞书：用替身模拟飞书不可达
    _route_clients({"bascn9": _Client(error=ConnectionError("offline"))}, monkeypatch)
    try:
        saved = await client.put(
            f"/api/v1/equipment/repair/config?workshop={code}",
            json={
                "feishu_app_id": str(app.id),
                "app_token": "bascn9",
                "table_id": "tbl9",
                "base_url": "",
                "is_enabled": True,
            },
        )
        assert saved.status_code == 200
        assert saved.json()["data"]["table_id"] == "tbl9"
        assert saved.json()["data"]["enabled"] is True

        detail = await client.get(f"/api/v1/equipment/repair/config?workshop={code}")
        assert detail.json()["data"]["app_name"] == "接口测试应用"

        tested = await client.post(
            f"/api/v1/equipment/repair/config/test?workshop={code}"
        )
        assert tested.status_code == 200
        assert tested.json()["data"]["success"] is False
        assert "ConnectionError" in tested.json()["data"]["message"]

        # 未配置的车间手动同步：返回说明而不是报错
        unconfigured = _code()
        synced = await client.post(
            f"/api/v1/equipment/repair/sync?workshop={unconfigured}"
        )
        assert synced.status_code == 200
        assert "error" in synced.json()["data"][unconfigured]

        # 校验失败是明确的 4xx，而不是 500
        invalid = await client.put(
            f"/api/v1/equipment/repair/config?workshop={_code()}",
            json={"feishu_app_id": str(uuid.uuid4())},
        )
        assert invalid.status_code == 404
    finally:
        await _purge(_equipment_session, [code], [app.id])


async def test_repair_endpoints_require_a_logged_in_user(
    client: AsyncClient,
) -> None:
    async def _anonymous() -> None:
        return None

    app.dependency_overrides[get_current_user] = _anonymous
    valid_config = {
        "app_token": "bascn1",
        "table_id": "tbl1",
        "base_url": "",
        "is_enabled": False,
    }
    try:
        for path in (
            "/api/v1/equipment/repair/records?workshop=201-1",
            "/api/v1/equipment/repair/frequency?workshop=201-1",
            "/api/v1/equipment/repair/results?workshop=201-1",
            "/api/v1/equipment/repair/sync-status?workshop=201-1",
            "/api/v1/equipment/repair/config?workshop=201-1",
        ):
            response = await client.get(path)
            assert response.status_code == 401, path
        sync = await client.post("/api/v1/equipment/repair/sync?workshop=201-1")
        assert sync.status_code == 401
        test = await client.post("/api/v1/equipment/repair/config/test?workshop=201-1")
        assert test.status_code == 401
        update = await client.put(
            "/api/v1/equipment/repair/config?workshop=201-1", json=valid_config
        )
        assert update.status_code == 401
    finally:
        app.dependency_overrides.pop(get_current_user, None)
