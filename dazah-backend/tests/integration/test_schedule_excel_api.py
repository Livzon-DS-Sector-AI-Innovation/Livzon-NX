"""排产 Excel 存档端点集成测试。

- HTTP 层：真实路由 + 真实 Excel 解析 + 真实原件文件读写；
  服务层 DB 调用用 mock 隔离（conftest 的共享回滚会话不承载多写用例）。
- 落库冒烟：直接用 db_session 走 service 全链路（真库）。

认证：平台 /api/v1 需要用户上下文，override get_current_user 提供内存用户。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import openpyxl  # type: ignore[import-untyped]
import pytest
from httpx import AsyncClient

import app.modules.production.schedule_excel_api as schedule_api
from app.main import app
from app.modules.production import schedule_excel_service
from app.modules.production.schedule_excel_models import ScheduleExcelArchive
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User

API_PREFIX = "/api/v1/production/schedule-excel"


def _make_xlsx_bytes(rows_count: int = 300) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "排产快照"
    ws.merge_cells("A1:B1")
    ws["A1"] = "2026年9月排产计划表"
    for i in range(rows_count):
        ws.cell(row=2 + i, column=1, value=f"批次{i}")
        ws.cell(row=2 + i, column=2, value=i + 1)
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _fake_archive(**overrides: Any) -> ScheduleExcelArchive:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "file_name": "2026-09排产.xlsx",
        "sheet_name": "排产快照",
        "original_path": "schedule_excel/fake.xlsx",
        "rows": [["a"], ["b"]],
        "merges": [],
        "col_widths": [80],
        "row_count": 2,
        "col_count": 1,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return ScheduleExcelArchive(**defaults)


@pytest.fixture
def isolated_uploads(tmp_path: Any, monkeypatch: Any) -> None:
    """上传原件写入临时目录，避免污染开发 uploads。"""
    upload_root = tmp_path / "uploads"
    (upload_root / "schedule_excel").mkdir(parents=True)
    (upload_root / "schedule_excel" / "fake.xlsx").write_bytes(
        _make_xlsx_bytes(2)
    )
    settings = SimpleNamespace(UPLOAD_DIR=str(upload_root))
    monkeypatch.setattr(schedule_api, "get_settings", lambda: settings)


@pytest.fixture
def mock_db_service(monkeypatch: Any) -> None:
    """HTTP 层不触碰数据库：mock 服务层 DB 函数。"""
    monkeypatch.setattr(
        schedule_api.schedule_excel_service,
        "create_archive",
        AsyncMock(
            return_value=_fake_archive(
                rows=[["x"] * 3] * 301,
                row_count=301,
                col_count=3,
            )
        ),
    )
    monkeypatch.setattr(
        schedule_api.schedule_excel_service,
        "list_archives",
        AsyncMock(
            return_value=([(_fake_archive(row_count=5), "排产测试员")], 1)
        ),
    )
    monkeypatch.setattr(
        schedule_api.schedule_excel_service,
        "get_user_name",
        AsyncMock(return_value="排产测试员"),
    )
    monkeypatch.setattr(
        schedule_api.schedule_excel_service,
        "delete_archive",
        AsyncMock(),
    )

    async def _fake_get(
        _db: Any, archive_id: uuid.UUID
    ) -> ScheduleExcelArchive | None:
        if str(archive_id) == "00000000-0000-0000-0000-000000000000":
            return None
        archive = _fake_archive()
        archive.id = archive_id
        return archive

    monkeypatch.setattr(
        schedule_api.schedule_excel_service,
        "get_archive",
        _fake_get,
    )


@pytest.fixture
async def auth_client(client: AsyncClient) -> AsyncIterator[AsyncClient]:
    async def _override_current_user() -> User:
        return User(
            id=uuid.uuid4(),
            name="排产接口测试用户",
            username=f"schedule-api-{uuid.uuid4().hex[:10]}",
            role="admin",
            status="active",
            auth_source="local",
            grant_version=0,
        )

    app.dependency_overrides[get_current_user] = _override_current_user
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def _upload(client: AsyncClient) -> dict[str, Any]:
    response = await client.post(
        API_PREFIX,
        files={
            "file": (
                "2026-09排产.xlsx",
                _make_xlsx_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 200
    return body["data"]


@pytest.mark.anyio
async def test_upload_parses_real_file_and_archives(
    auth_client: AsyncClient,
    mock_db_service: None,
    isolated_uploads: None,
) -> None:
    data = await _upload(auth_client)
    assert data["file_name"] == "2026-09排产.xlsx"
    assert data["sheet_name"] == "排产快照"
    assert data["row_count"] == 301  # mock 层返回的存档计数
    # 真实解析结果确实传给了服务层：300 行全量 + 合并单元格
    call = schedule_api.schedule_excel_service.create_archive.await_args
    assert call is not None
    kwargs = call.kwargs
    assert len(kwargs["rows"]) == 301
    assert kwargs["merges"] == [
        {"s": {"r": 0, "c": 0}, "e": {"r": 0, "c": 1}}
    ]
    assert kwargs["file_name"] == "2026-09排产.xlsx"


@pytest.mark.anyio
async def test_list_detail_download_delete_roundtrip(
    auth_client: AsyncClient,
    mock_db_service: None,
    isolated_uploads: None,
) -> None:
    client = auth_client

    listing = await client.get(f"{API_PREFIX}?page=1&page_size=20")
    assert listing.status_code == 200
    assert listing.json()["code"] == 200

    archive_id = str(uuid.uuid4())
    detail = await client.get(f"{API_PREFIX}/{archive_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["id"] == archive_id

    download = await client.get(f"{API_PREFIX}/{archive_id}/file")
    assert download.status_code == 200
    assert download.content[:2] == b"PK"  # 原件（真实 xlsx）zip 魔数

    deleted = await client.delete(f"{API_PREFIX}/{archive_id}")
    assert deleted.status_code == 200
    schedule_api.schedule_excel_service.delete_archive.assert_awaited_once()


@pytest.mark.anyio
async def test_missing_archive_returns_404(
    auth_client: AsyncClient,
    mock_db_service: None,
) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await auth_client.get(f"{API_PREFIX}/{missing}")).status_code == 404
    assert (
        await auth_client.delete(f"{API_PREFIX}/{missing}")
    ).status_code == 404


@pytest.mark.anyio
async def test_upload_rejects_bad_extension_and_corrupted_file(
    auth_client: AsyncClient,
    mock_db_service: None,
    isolated_uploads: None,
) -> None:
    client = auth_client
    bad = await client.post(
        API_PREFIX,
        files={"file": ("plan.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert bad.status_code == 400

    corrupted = await client.post(
        API_PREFIX,
        files={
            "file": (
                "broken.xlsx",
                b"not a real xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert corrupted.status_code == 400
    assert "解析失败" in corrupted.json()["message"]


@pytest.mark.anyio
async def test_unauthenticated_requests_are_rejected(client: AsyncClient) -> None:
    assert (await client.get(API_PREFIX)).status_code == 401


@pytest.mark.anyio
async def test_service_persistence_roundtrip() -> None:
    """落库冒烟：service 全链路（测试体内自建会话，避免共享 fixture 跨循环）。"""
    from sqlalchemy import pool as sa_pool
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from tests.db_safety import get_pytest_database_url

    engine = create_async_engine(
        get_pytest_database_url(get_settings()),
        poolclass=sa_pool.NullPool,
    )
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            parsed = schedule_excel_service.parse_workbook_bytes(
                _make_xlsx_bytes(5)
            )
            archive = await schedule_excel_service.create_archive(
                session,
                file_name="冒烟.xlsx",
                sheet_name=parsed["sheet_name"],
                original_path="schedule_excel/smoke.xlsx",
                rows=parsed["rows"],
                merges=parsed["merges"],
                col_widths=parsed["col_widths"],
                row_count=parsed["row_count"],
                col_count=parsed["col_count"],
            )
            archive_id = archive.id
            assert archive.row_count == 6

            fetched = await schedule_excel_service.get_archive(session, archive_id)
            assert fetched is not None
            assert fetched.file_name == "冒烟.xlsx"

            items, total = await schedule_excel_service.list_archives(
                session, page=1, page_size=10
            )
            assert total >= 1
            assert any(
                archive.id == archive_id
                for archive, _created_by_name in items
            )
            # 冒烟记录未指定 created_by → 上传人为空
            for archive, created_by_name in items:
                if archive.id == archive_id:
                    assert created_by_name is None

            await schedule_excel_service.delete_archive(session, fetched)
            assert (
                await schedule_excel_service.get_archive(session, archive_id)
                is None
            )
    finally:
        await engine.dispose()
