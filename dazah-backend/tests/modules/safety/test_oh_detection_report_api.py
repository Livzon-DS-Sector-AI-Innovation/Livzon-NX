"""职业健康检测报告 API 测试（sub_app + 测试库 + 夹具 PDF 全链路）。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

import app.modules.safety.service.oh_detection_report as oh_module
from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.safety.api.oh_detection_reports import oh_detection_reports_router
from app.modules.safety.models import OhDetectionReport, OhDetectionResult
from app.modules.safety.service.oh_detection_report import clear_parse_cache
from app.platform.identity.models import User

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "oh_detection_mini.pdf"
_REPORT_NO = "TEST-J-2026-001"


@pytest.fixture(autouse=True)
def _isolated_upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oh_module, "_UPLOAD_DIR", str(tmp_path / "oh-detection"))
    clear_parse_cache()


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid4(), name=f"职健导入{uuid4().hex[:8]}", role="user", status="active"
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def sub_app(test_user: User) -> FastAPI:
    application = FastAPI()
    application.include_router(oh_detection_reports_router, prefix="/api/v1/safety")
    application.dependency_overrides[get_current_user] = lambda: test_user
    return application


@pytest.fixture
async def client(
    sub_app: FastAPI, db_session: AsyncSession
) -> AsyncIterator[AsyncClient]:
    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    sub_app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=sub_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    sub_app.dependency_overrides.pop(get_db, None)


async def _cleanup(db: AsyncSession) -> None:
    await db.execute(
        delete(OhDetectionResult).where(
            OhDetectionResult.report_id.in_(
                __import__("sqlalchemy")
                .select(OhDetectionReport.id)
                .where(OhDetectionReport.report_no == _REPORT_NO)
            )
        )
    )
    await db.execute(
        delete(OhDetectionReport).where(OhDetectionReport.report_no == _REPORT_NO)
    )
    await db.commit()


async def _upload(client: AsyncClient, endpoint: str, **fields: str) -> object:
    return await client.post(
        f"/api/v1/safety/oh-detection-reports/{endpoint}",
        files={"file": ("mini.pdf", FIXTURE.read_bytes(), "application/pdf")},
        data=fields,
    )


async def test_parse_endpoint_returns_preview(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    resp = await _upload(client, "parse")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["report_no"] == _REPORT_NO
    assert data["company_name"] == "测试制药有限公司"
    assert data["detection_agency"] == "宁夏测试检测技术有限公司"
    assert data["total_points"] == 10
    assert data["parse_mode"] == "rules"
    assert len(data["tables"]) == 2
    assert data["tables"][0]["table_ref"] == "表5-2"
    assert data["existing_report_id"] is None


async def test_import_list_results_file_delete_flow(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    imported = await _upload(client, "import", detection_date="2026-09-15")
    assert imported.status_code == 200, imported.text
    payload = imported.json()["data"]
    assert payload["imported_count"] == 10
    assert payload["replaced"] is False
    # 导入自动同步监测记录（夹具车间: 101车间/102车间/201车间）
    assert payload["monitors_synced"] == 3
    from sqlalchemy import select

    from app.modules.safety.models import OhHazardMonitor

    monitors = (
        (
            await db_session.execute(
                select(OhHazardMonitor)
                .where(
                    OhHazardMonitor.monitor_no.like(
                        f"{_REPORT_NO}-M%"
                    ),
                    OhHazardMonitor.is_deleted.is_(False),
                )
                .order_by(OhHazardMonitor.monitor_no)
            )
        )
        .scalars()
        .all()
    )
    assert len(monitors) == 3
    dust_monitor = monitors[0]
    assert dust_monitor.workplace == "101车间"
    assert dust_monitor.status == "completed"
    assert dust_monitor.detection_type == "commissioned"
    results = dust_monitor.detection_results or []
    assert results and results[0]["factor_name"] == "谷物粉尘"
    assert results[0]["factor_category"] == "dust"
    assert results[0]["compliance_status"] == "compliant"
    report_id = payload["report"]["id"]
    assert payload["report"]["detection_date"] == "2026-09-15"
    assert payload["report"]["total_points"] == 10

    # 列表与统计
    listed = await client.get("/api/v1/safety/oh-detection-reports")
    assert listed.status_code == 200
    body = listed.json()
    assert any(i["id"] == report_id for i in body["data"])
    assert body["meta"]["report_count"] >= 1

    # 明细筛选：仅噪声 + 采样点记录
    results = await client.get(
        f"/api/v1/safety/oh-detection-reports/{report_id}/results",
        params={"factor_category": "noise", "record_type": "point"},
    )
    assert results.status_code == 200
    rows = results.json()["data"]
    assert rows and all(r["factor_category"] == "noise" for r in rows)
    assert all(r["record_type"] == "point" for r in rows)
    # 明细筛选：噪声作业岗位
    noise_rows = await client.get(
        f"/api/v1/safety/oh-detection-reports/{report_id}/results",
        params={"is_noise_post": "true"},
    )
    assert len(noise_rows.json()["data"]) == 5
    # 关键词筛选
    keyword = await client.get(
        f"/api/v1/safety/oh-detection-reports/{report_id}/results",
        params={"keyword": "投料口"},
    )
    assert len(keyword.json()["data"]) == 1

    # 原始文件下载
    download = await client.get(f"/api/v1/safety/oh-detection-reports/{report_id}/file")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content == FIXTURE.read_bytes()

    # 详情
    detail = await client.get(f"/api/v1/safety/oh-detection-reports/{report_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["report_no"] == _REPORT_NO

    # 删除（软删）后列表不可见, 且其生成的监测记录级联软删
    deleted = await client.delete(f"/api/v1/safety/oh-detection-reports/{report_id}")
    assert deleted.status_code == 200
    listed2 = await client.get("/api/v1/safety/oh-detection-reports")
    assert all(i["id"] != report_id for i in listed2.json()["data"])
    from sqlalchemy import func as _func
    from sqlalchemy import select as _select

    from app.modules.safety.models import OhHazardMonitor as _Ohm

    active_monitors = (
        await db_session.execute(
            _select(_func.count())
            .select_from(_Ohm)
            .where(
                _Ohm.monitor_no.like(f"{_REPORT_NO}-M%"),
                _Ohm.is_deleted.is_(False),
            )
        )
    ).scalar()
    assert active_monitors == 0
    await _cleanup(db_session)


async def test_reimport_same_report_no_replaces_results(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    first = await _upload(client, "import")
    report_id = first.json()["data"]["report"]["id"]
    # 预览应提示同编号覆盖
    preview = await _upload(client, "parse")
    assert preview.json()["data"]["existing_report_id"] == report_id

    second = await _upload(client, "import", remark="覆盖重导")
    payload = second.json()["data"]
    assert payload["replaced"] is True
    assert payload["report"]["id"] == report_id
    assert payload["report"]["remark"] == "覆盖重导"

    # 明细无重复：仍是 10 条
    results = await client.get(
        f"/api/v1/safety/oh-detection-reports/{report_id}/results",
        params={"page_size": 100},
    )
    assert len(results.json()["data"]) == 10
    # 监测记录刷新不重复：仍是 3 条有效
    from sqlalchemy import func, select

    from app.modules.safety.models import OhHazardMonitor

    active_monitors = (
        await db_session.execute(
            select(func.count())
            .select_from(OhHazardMonitor)
            .where(
                OhHazardMonitor.monitor_no.like(f"{_REPORT_NO}-M%"),
                OhHazardMonitor.is_deleted.is_(False),
            )
        )
    ).scalar()
    assert active_monitors == 3
    await _cleanup(db_session)


async def test_parse_rejects_invalid_files(client: AsyncClient) -> None:
    wrong_ext = await client.post(
        "/api/v1/safety/oh-detection-reports/parse",
        files={"file": ("report.docx", b"x", "application/msword")},
    )
    assert wrong_ext.status_code == 422

    empty = await client.post(
        "/api/v1/safety/oh-detection-reports/parse",
        files={"file": ("report.pdf", b"", "application/pdf")},
    )
    assert empty.status_code == 422


async def test_import_rejects_bad_date_format(client: AsyncClient) -> None:
    resp = await _upload(client, "import", detection_date="2026/09/15")
    assert resp.status_code == 422
    assert "检测日期" in resp.json()["detail"]


async def test_import_without_report_no_errors(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """编号识别失败且未手工填写时给出可预期业务错误。"""

    class _Doc(oh_module._ExtractedDoc):
        pass

    doc = _Doc(first_page_text="无编号报告")
    doc.page_texts = ["无编号报告"]
    doc.fragments = [
        oh_module._TableFragment(
            caption="表5-4 氢氧化钠检测结果一览表",
            grid=[
                [
                    "序号", "车间", "岗位", "采样点",
                    "CME（mg/m3）", "MAC（mg/m3）", "结果判定",
                ],
                ["1", "A车间", "酸化", "钠化罐", "0.032", "2", "未超标"],
            ],
        )
    ]
    monkeypatch.setattr(oh_module, "_extract_pdf", lambda _b: doc)
    clear_parse_cache()
    resp = await _upload(client, "import")
    assert resp.status_code == 422
    assert "报告编号" in resp.json()["detail"]
