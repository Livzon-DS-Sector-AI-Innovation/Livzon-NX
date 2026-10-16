"""页面表格镜像补强测试：tmp_url 下载、日期边界、危限作业镜像扫描。"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from app.modules.safety.feishu import bitable_client as bitable_module
from app.modules.safety.feishu.bitable_client import (
    BITABLE_BASE,
    SafetyBitableClient,
)
from app.modules.safety.repository import _special_operation_date_bounds


def _client() -> SafetyBitableClient:
    client = SafetyBitableClient(app_token="app-token", table_id="tbl-1")
    client._token = AsyncMock(return_value="tenant-token")  # type: ignore[method-assign]
    return client


class _SeqHttp:
    """按顺序消费 GET 响应；记录每次 GET 的 URL。"""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self.queue = list(responses)
        self.gets: list[str] = []

    def __call__(self, *args: object, **kwargs: object) -> "_SeqHttp":
        return self

    async def __aenter__(self) -> "_SeqHttp":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, url: str, **kwargs: object) -> httpx.Response:
        self.gets.append(url)
        return self.queue.pop(0)


def _response(payload: object, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status, json=payload, request=httpx.Request("GET", BITABLE_BASE)
    )


@pytest.mark.anyio
async def test_download_via_tmp_url_exchanges_and_downloads() -> None:
    client = _client()
    fake = _SeqHttp(
        [
            _response(
                {
                    "code": 0,
                    "data": {
                        "tmp_download_urls": [
                            {"tmp_download_url": "https://internal/stream/x"}
                        ]
                    },
                }
            ),
            httpx.Response(
                200,
                content=b"file-bytes",
                request=httpx.Request("GET", "https://internal/stream/x"),
            ),
        ]
    )
    original = bitable_module.httpx.AsyncClient
    bitable_module.httpx.AsyncClient = fake  # type: ignore[assignment]
    try:
        data = await client.download_attachment_via_tmp_url(
            "https://open/medias/batch_get_tmp_download_url?x=1"
        )
    finally:
        bitable_module.httpx.AsyncClient = original

    assert data == b"file-bytes"
    assert fake.gets[0].startswith("https://open/medias/batch_get_tmp_download_url")
    assert fake.gets[1] == "https://internal/stream/x"


@pytest.mark.anyio
async def test_download_via_tmp_url_rejects_empty_and_failures() -> None:
    client = _client()
    assert await client.download_attachment_via_tmp_url("") is None

    fake = _SeqHttp([_response({"code": 99991672}, status=500)])
    original = bitable_module.httpx.AsyncClient
    bitable_module.httpx.AsyncClient = fake  # type: ignore[assignment]
    try:
        assert await client.download_attachment_via_tmp_url("https://x") is None
    finally:
        bitable_module.httpx.AsyncClient = original

    # 非 JSON 响应
    fake2 = _SeqHttp(
        [
            httpx.Response(
                200,
                content=b"not-json",
                request=httpx.Request("GET", BITABLE_BASE),
            )
        ]
    )
    bitable_module.httpx.AsyncClient = fake2  # type: ignore[assignment]
    try:
        assert await client.download_attachment_via_tmp_url("https://x") is None
    finally:
        bitable_module.httpx.AsyncClient = original

    # 响应里没有可用的下载地址
    fake3 = _SeqHttp([_response({"code": 0, "data": {"tmp_download_urls": []}})])
    bitable_module.httpx.AsyncClient = fake3  # type: ignore[assignment]
    try:
        assert await client.download_attachment_via_tmp_url("https://x") is None
    finally:
        bitable_module.httpx.AsyncClient = original


def test_special_operation_date_bounds_parses_and_tolerates_garbage() -> None:
    start, end = _special_operation_date_bounds("2026-10-10", "2026-10-11")
    assert start == datetime(2026, 10, 10, tzinfo=UTC)
    assert end == datetime(2026, 10, 12, tzinfo=UTC)
    # 非法日期原样返回 None
    assert _special_operation_date_bounds("垃圾", None) == (None, None)
    assert _special_operation_date_bounds(None, "垃圾") == (None, None)
    assert _special_operation_date_bounds(None, None) == (None, None)


# ── 危限扫描参与关键作业重算（DB 级） ──


@pytest.mark.anyio
async def test_recalculate_critical_flags_uses_hazardous_mirror_levels(
    db_session,
) -> None:
    from app.modules.safety.models import (
        SafetyPageTableMirrorRecord,
        SpecialOperationReport,
    )
    from app.modules.safety.service.special_operation_report import (
        SpecialOperationReportService,
    )

    await db_session.execute(
        SafetyPageTableMirrorRecord.__table__.insert().values(
            page_key="safety:ops-safety:special-danger-work",
            record_id="rec-mirror-1",
            fields={
                "申请编号": {"text": "SA-MIRROR-1"},
                "作业分级": "受限空间作业（涉及有毒有害、易燃易爆）",
            },
            is_deleted=False,
        )
    )
    # 否定写法不命中
    await db_session.execute(
        SafetyPageTableMirrorRecord.__table__.insert().values(
            page_key="safety:ops-safety:special-danger-work",
            record_id="rec-mirror-2",
            fields={
                "申请编号": "SA-MIRROR-2",
                "作业分级": "受限空间作业（不涉及有毒有害）",
            },
            is_deleted=False,
        )
    )
    report = SpecialOperationReport(
        report_no="SA-MIRROR-1",
        operation_type="confined_space",
        operation_level="grade2",
        status="approved",
        is_critical=False,
    )
    db_session.add(report)
    await db_session.commit()

    try:
        service = SpecialOperationReportService(db_session)
        result = await service.recalculate_critical_flags()

        assert result["total"] >= 1
        await db_session.refresh(report)
        assert report.is_critical is True
        assert "受限空间" in (report.is_critical_reason or "")
    finally:
        await db_session.rollback()
        await db_session.execute(
            SafetyPageTableMirrorRecord.__table__.delete().where(
                SafetyPageTableMirrorRecord.record_id.in_(
                    ["rec-mirror-1", "rec-mirror-2"]
                )
            )
        )
        await db_session.execute(
            SpecialOperationReport.__table__.delete().where(
                SpecialOperationReport.report_no == "SA-MIRROR-1"
            )
        )
        await db_session.commit()
