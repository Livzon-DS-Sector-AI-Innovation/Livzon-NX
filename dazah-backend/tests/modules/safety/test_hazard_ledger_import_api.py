"""危险源辨识台账 Excel 导入端点的路由测试。"""

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import openpyxl
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.modules.safety.api import hazard_identifications as api


def _workbook_bytes() -> bytes:
    """生成一个最小作业活动分级管控清单工作簿。"""
    workbook = openpyxl.Workbook()
    ws = workbook.active
    ws.title = "消毒"
    rows = [
        ["作业活动安全风险分级管控措施清单"],
        ["单位名称："],
        ["风险点", None, None, "危险源", None, "可能发生的事故类型及后果",
         "时态（过去、现在、将来）", "状态（正常、异常、紧急）", "安全风险等级评定",
         None, None, None, None, "风险管控措施", None, None, None, "管控主体",
         None, None, "检查频次"],
        ["序号", "类别", "名称", "作业步骤", "危险源辨识", None, None, None,
         "可能性L", "暴露频次E", "严重性C", "危险度D", "风险等级",
         "工程措施", "管理措施", "个体防护", "应急措施", "管控层级",
         "责任单位", "责任人员", None],
        [1, "常规作业", "罐内发酵", "打开进料阀门", "管道憋压", "其他伤害",
         "现在", "正常", 1, 6, 1, 6, "低风险",
         "加防护罩", "定期检查", "手套", "应急卡", "班组级", "消毒班", "李涛",
         "每月一次"],
    ]
    for r_idx, row in enumerate(rows, start=1):
        for c_idx, value in enumerate(row, start=1):
            if value is not None:
                ws.cell(row=r_idx, column=c_idx, value=value)
    buf = io.BytesIO()
    workbook.save(buf)
    return buf.getvalue()


@pytest.fixture
def db_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def sub_app(db_session: AsyncMock) -> FastAPI:
    application = FastAPI()
    application.include_router(
        api.hazard_identifications_router, prefix="/api/v1/safety"
    )
    application.dependency_overrides[get_db] = lambda: db_session
    application.dependency_overrides[api.get_current_user] = lambda: SimpleNamespace(
        id=uuid4(), role="user"
    )
    return application


@pytest.fixture
def client(sub_app: FastAPI):
    return AsyncClient(transport=ASGITransport(app=sub_app), base_url="http://test")


async def test_parse_endpoint_returns_sheet_preview(client: AsyncClient):
    resp = await client.post(
        "/api/v1/safety/hazard-identifications/import/parse",
        files={"file": ("作业活动分级管控总清单101-102.xlsx", _workbook_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["department_guess"] == "101-102车间"
    assert payload["total_valid_rows"] == 1
    sheet = payload["sheets"][0]
    assert sheet["name"] == "消毒"
    assert sheet["format"] == "activity"
    assert sheet["row_count"] == 1
    assert sheet["sample_rows"][0]["hazard_desc"] == "管道憋压"
    assert sheet["sample_rows"][0]["level"] == "四级/低风险"


async def test_parse_endpoint_rejects_unsupported_extension(client: AsyncClient):
    resp = await client.post(
        "/api/v1/safety/hazard-identifications/import/parse",
        files={"file": ("清单.csv", b"a,b,c", "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 400
    assert "仅支持" in body["message"]


async def test_import_endpoint_returns_commit_result(
    client: AsyncClient, monkeypatch, db_session
):
    fake_commit = AsyncMock(
        return_value={
            "imported": 3,
            "skipped_existing": 1,
            "duplicate_in_file": 0,
            "failed_sheets": [],
            "row_errors": [],
            "archive_path": "uploads/safety/hazard-import/x.xlsx",
        }
    )
    monkeypatch.setattr(
        api.HazardLedgerImportService, "commit", fake_commit
    )
    resp = await client.post(
        "/api/v1/safety/hazard-identifications/import",
        files={"file": ("作业活动分级管控总清单101-102.xlsx", _workbook_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"department": "101-102车间", "sheets": '["消毒"]'},
    )
    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["imported"] == 3
    assert payload["skipped_existing"] == 1
    assert payload["archive_path"].startswith("uploads/")
    fake_commit.assert_awaited_once()
    assert fake_commit.call_args.args[2] == "101-102车间"
    assert fake_commit.call_args.args[3] == ["消毒"]
    db_session.commit.assert_awaited_once()


async def test_import_endpoint_rejects_bad_sheets_json(client: AsyncClient):
    resp = await client.post(
        "/api/v1/safety/hazard-identifications/import",
        files={"file": ("清单.xlsx", _workbook_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"department": "", "sheets": "not-json"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 400
    assert "子表参数格式错误" in body["message"]


async def test_filter_options_endpoint_returns_departments_and_positions(
    client: AsyncClient, monkeypatch
):
    from app.modules.safety.service import SafetyService

    fake = AsyncMock(
        return_value={
            "departments": ["101-102车间", "201一车间"],
            "positions": [
                {"department": "101-102车间", "position": "消毒"},
                {"department": "201一车间", "position": "压滤"},
            ],
        }
    )
    monkeypatch.setattr(SafetyService, "get_hazard_filter_options", fake)

    resp = await client.get("/api/v1/safety/hazard-identifications/filter-options")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["departments"] == ["101-102车间", "201一车间"]
    assert data["positions"][0] == {"department": "101-102车间", "position": "消毒"}
    fake.assert_awaited_once()
