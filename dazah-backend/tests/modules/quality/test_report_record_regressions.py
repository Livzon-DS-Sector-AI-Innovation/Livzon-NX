from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.exceptions import AppException
from app.modules.quality.schemas import DeviationReportRecordListItem
from app.modules.quality.service import quality_feishu_pages as pages
from app.modules.quality.service import quality_feishu_sync as sync
from app.modules.quality.service import quality_management as management


def test_attachment_parser_preserves_file_token_without_temporary_url():
    assert sync._parse_attachment_field(
        [{"name": "报告.docx", "file_token": "ft_report", "type": "application/docx"}]
    ) == [
        {
            "name": "报告.docx",
            "url": "",
            "type": "application/docx",
            "size": 0,
            "file_token": "ft_report",
        }
    ]


@pytest.mark.parametrize(
    "attachments",
    [
        None,
        [],
        [
            {
                "name": "测试.png",
                "file_token": "ft_image",
                "url": "https://example.test/image.png",
                "type": "image/png",
                "size": 10,
            },
        ],
    ],
)
async def test_report_list_preserves_attachments(monkeypatch, attachments):
    entity = SimpleNamespace(table_id="table", field_mappings={})
    runtime = SimpleNamespace(
        is_enabled=lambda: True, get_entity_config=lambda *a, **k: entity
    )
    monkeypatch.setattr(
        sync.feishu_sync, "_resolve_runtime", AsyncMock(return_value=runtime)
    )
    monkeypatch.setattr(
        sync.feishu_sync,
        "search_records",
        AsyncMock(
            return_value=[
                {
                    "record_id": "record",
                    "fields": {"偏差内容": "测试", "附件": attachments},
                },
            ]
        ),
    )
    monkeypatch.setattr(
        management.repository, "get_deviations_by_codes", AsyncMock(return_value=[])
    )
    result = await pages.list_report_records(SimpleNamespace(), page=1, page_size=20)
    assert result["items"][0]["attachments"] == (attachments or None)


@pytest.mark.parametrize("code", [None, "PC-2609001"])
@pytest.mark.parametrize("write_id", ["ou_new", "on_new"])
async def test_edit_reporter_without_code_preserves_existing_attachments(
    monkeypatch, code, write_id
):
    from app.modules.quality.service import person_directory

    monkeypatch.setattr(
        person_directory,
        "resolve_person_by_open_id",
        AsyncMock(return_value={"name": "新报告人", "department": "QC"}),
    )
    monkeypatch.setattr(
        sync,
        "_resolve_contact_bitable_user_value",
        AsyncMock(return_value=[{"id": write_id}]),
    )
    update = AsyncMock()
    monkeypatch.setattr(pages, "_update_entity_record", update)
    await pages.update_deviation_report_record(
        SimpleNamespace(),
        "record",
        {
            "deviation_code": code,
            "description": "测试",
            "product_batch": "产品",
            "reporter_open_id": "ou_new",
        },
    )
    fields = update.await_args.args[3]
    assert fields["报告人"] == [{"id": write_id}]
    assert update.await_args.kwargs["user_id_type"] == (
        "union_id" if write_id.startswith("on_") else "open_id"
    )
    assert fields["部门"] == "QC"
    assert "附件" not in fields
    assert "偏差编号" not in fields


async def test_report_update_maps_feishu_connection_failure_to_503(monkeypatch):
    from app.modules.quality.service import person_directory

    monkeypatch.setattr(
        person_directory,
        "resolve_person_by_open_id",
        AsyncMock(return_value={"name": "报告人", "department": "QA"}),
    )
    monkeypatch.setattr(
        sync,
        "_resolve_contact_bitable_user_value",
        AsyncMock(return_value=[{"id": "ou_reporter"}]),
    )
    monkeypatch.setattr(
        pages,
        "_update_entity_record",
        AsyncMock(side_effect=httpx.ConnectError("飞书连接失败")),
    )

    with pytest.raises(AppException) as exc_info:
        await pages.update_deviation_report_record(
            SimpleNamespace(),
            "record",
            {
                "description": "测试",
                "product_batch": "产品",
                "reporter_open_id": "ou_reporter",
            },
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "飞书服务暂时无法连接，请稍后重试"


@pytest.mark.parametrize("failure", [None, httpx.ConnectError("unavailable")])
async def test_save_report_api_without_code(client, monkeypatch, failure):
    from app.modules.quality.service import person_directory

    monkeypatch.setattr(
        person_directory,
        "resolve_person_by_open_id",
        AsyncMock(return_value={"name": "新报告人", "department": "QC"}),
    )
    monkeypatch.setattr(
        sync,
        "_resolve_contact_bitable_user_value",
        AsyncMock(return_value=[{"id": "on_reporter"}]),
    )
    # 实际调用路由和保存 Service，外部写入处才打桩；不允许恢复为全表回读。
    old_read = AsyncMock(side_effect=AssertionError("保存不应依赖全表回读"))
    monkeypatch.setattr(pages, "get_deviation_report_record", old_read)
    update = AsyncMock(side_effect=failure)
    monkeypatch.setattr(pages, "_update_entity_record", update)

    response = await client.put(
        "/api/v1/quality/deviation-report-records/record",
        json={
            "description": "测试",
            "product_batch": "产品",
            "reporter_open_id": "ou_reporter",
        },
    )
    if failure is not None:
        assert response.status_code == 503
        assert response.json()["message"] == "飞书服务暂时无法连接，请稍后重试"
    else:
        assert response.status_code == 200
        record = DeviationReportRecordListItem.model_validate(response.json()["data"])
        assert record.deviation_code is None
        assert record.reporters == [{"id": "on_reporter"}]
        fields = update.await_args.args[3]
        assert "偏差编号" not in fields
        assert "附件" not in fields
    old_read.assert_not_awaited()


async def test_report_attachment_is_checked_against_its_record(monkeypatch):
    from app.core.exceptions import NotFoundException
    from app.modules.quality.service import inspection_feishu_crud as attachments

    runtime = SimpleNamespace(app_id="test", app_secret="test")
    entity = SimpleNamespace(app_token="test", table_id="table")
    monkeypatch.setattr(
        attachments,
        "_resolve_runtime_entity",
        AsyncMock(return_value=(runtime, entity)),
    )
    client = SimpleNamespace(
        get_record=AsyncMock(
            return_value={
                "record_id": "record",
                "fields": {"附件": [{"file_token": "owned"}]},
            }
        )
    )
    monkeypatch.setattr(attachments, "BitableClient", lambda **kwargs: client)
    with pytest.raises(NotFoundException):
        await attachments.get_inspection_feishu_attachment_content(
            SimpleNamespace(), "deviation_report_record", "record", "another_file"
        )
    # 附件代理新增支持不能意外开放通用记录写入。
    with pytest.raises(AppException):
        attachments.validate_bitable_crud_entity("deviation_report_record")
