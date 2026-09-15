"""仪器台账 Excel 批量导入：列头识别、人员/日期解析、新增/更新分流。"""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pytest
from openpyxl import Workbook

from app.core.exceptions import AppException
from app.modules.quality.service import instrument_import as importer

pytestmark = pytest.mark.anyio

HEADERS = ["序号", "设备编号", "名称", "型号规格", "负责人", "入厂日期"]


def _build_xlsx(rows: list[list[Any]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _install_mocks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    code_index: dict[str, str] | None = None,
) -> dict[str, list[Any]]:
    calls: dict[str, list[Any]] = {"create": [], "update": [], "sync": []}

    async def fake_list(
        db: Any, entity_code: str, *, page: int = 1, page_size: int = 500
    ):
        items = [
            {"record_id": record_id, "设备编号": code}
            for code, record_id in (code_index or {}).items()
        ]
        return {
            "items": items,
            "total": len(items),
            "page": 1,
            "page_size": page_size,
            "configured": True,
            "fields": [],
            "last_sync_time": None,
        }

    async def fake_resolve(db: Any, name: str, department: str | None = None):
        if name in {"张三", "李四"}:
            return {"open_id": f"ou_{name}", "name": name}
        return None

    async def fake_create(
        db: Any, entity_code: str, fields: dict[str, Any], actor_user_id=None
    ):
        calls["create"].append((entity_code, fields))
        return {"record_id": f"rec-new-{len(calls['create'])}"}

    async def fake_update(
        db: Any,
        entity_code: str,
        record_id: str,
        fields: dict[str, Any],
        actor_user_id=None,
    ):
        calls["update"].append((entity_code, record_id, fields))
        return {"record_id": record_id}

    async def fake_sync(db: Any, entity_code: str, *, incremental: bool = True):
        calls["sync"].append((entity_code, incremental))
        return {"synced": 9, "removed": 0, "total": 9}

    monkeypatch.setattr(importer, "list_instrument_mirror", fake_list)
    monkeypatch.setattr(importer, "resolve_person_by_name", fake_resolve)
    monkeypatch.setattr(importer, "create_inspection_feishu_record", fake_create)
    monkeypatch.setattr(importer, "update_inspection_feishu_record", fake_update)
    monkeypatch.setattr(importer, "sync_instrument_page", fake_sync)
    return calls


async def test_preview_maps_columns_and_detects_create_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_mocks(monkeypatch, code_index={"QC-1-2-010": "rec-old"})
    content = _build_xlsx(
        [
            ["1", "QC-1-2-100", "气相色谱仪", "Agilent 8890", "张三", "2026/1/31"],
            ["2", "QC-1-2-010", "HPLC", "U3000", "李四、王五", "2026-02-05"],
            ["3", "", "无编号设备", "", "", ""],
        ]
    )

    preview = await importer.preview_instrument_import(None, content)

    assert preview["column_map"]["设备编号"] == "设备编号"
    assert preview["column_map"]["设备名称"] == "名称"
    assert preview["column_map"]["规格型号"] == "型号规格"
    assert preview["column_map"]["入厂日期"] == "入厂日期"
    assert "序号" in preview["unmatched_columns"]
    assert preview["create_count"] == 1
    assert preview["update_count"] == 1
    assert preview["error_count"] == 1  # 缺设备编号的行

    rows = {row["row_number"]: row for row in preview["rows"]}
    assert rows[2]["mode"] == "create"
    assert rows[2]["fields"]["入厂日期"] == "2026-01-31"
    assert rows[2]["fields"]["使用负责人"] == [{"id": "ou_张三"}]
    assert rows[3]["mode"] == "update"
    assert rows[3]["record_id"] == "rec-old"
    assert any("王五" in warning for warning in rows[3]["warnings"])
    assert "未匹配到在职人员" in rows[3]["warnings"][-1]
    assert calls["create"] == [] and calls["update"] == []  # 预览不写数据


async def test_confirm_writes_feishu_and_refreshes_mirror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_mocks(monkeypatch, code_index={"QC-1-2-010": "rec-old"})
    content = _build_xlsx(
        [
            ["1", "QC-1-2-100", "气相色谱仪", "Agilent 8890", "张三", "20260131"],
            ["2", "QC-1-2-010", "HPLC（已维修）", "U3000", "", ""],
        ]
    )

    result = await importer.confirm_instrument_import(
        None, content, operator_user_id="u-1"
    )

    assert result["success"] == 2
    assert result["created"] == 1
    assert result["updated"] == 1
    assert result["failed"] == 0
    assert result["mirror_synced"] == 9
    # 新增：写全部非空字段（人员按 [{id}] 提交，日期归一化）
    entity_code, fields = calls["create"][0]
    assert entity_code == "qc_instr_equipment"
    assert fields["设备编号"] == "QC-1-2-100"
    assert fields["设备名称"] == "气相色谱仪"
    assert fields["规格型号"] == "Agilent 8890"
    assert fields["使用负责人"] == [{"id": "ou_张三"}]
    assert fields["入厂日期"] == "2026-01-31"
    # 更新：只写非空字段，定位到已有 record_id
    _, record_id, update_fields = calls["update"][0]
    assert update_fields["设备编号"] == "QC-1-2-010"
    assert update_fields["设备名称"] == "HPLC（已维修）"
    assert update_fields["规格型号"] == "U3000"  # 非空列一并更新，空列跳过
    # 导入完成后全量刷一次镜像
    assert calls["sync"] == [("qc_instr_equipment", False)]


async def test_confirm_collects_row_errors_without_abort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_mocks(monkeypatch)

    async def failing_create(
        db: Any, entity_code: str, fields: dict[str, Any], actor_user_id=None
    ):
        if fields.get("设备名称") == "坏设备":
            raise AppException(message="飞书写入失败", status_code=502)
        return {"record_id": "rec-ok"}

    monkeypatch.setattr(importer, "create_inspection_feishu_record", failing_create)
    content = _build_xlsx(
        [
            ["1", "QC-1-2-100", "好设备", "", "", ""],
            ["2", "QC-1-2-101", "坏设备", "", "", ""],
        ]
    )

    result = await importer.confirm_instrument_import(None, content)

    assert result["failed"] == 1
    assert result["created"] == 1
    assert result["error_details"][0]["row_number"] == 3
    assert "飞书写入失败" in result["error_details"][0]["message"]


async def test_preview_requires_code_column(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_mocks(monkeypatch)
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["名称", "品牌"])
    sheet.append(["某仪器", "某品牌"])
    buffer = BytesIO()
    workbook.save(buffer)

    with pytest.raises(AppException) as exc_info:
        await importer.preview_instrument_import(None, buffer.getvalue())
    assert "设备编号" in exc_info.value.message


async def test_bad_date_format_reports_row_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_mocks(monkeypatch)
    content = _build_xlsx([["1", "QC-1-2-100", "某仪器", "", "", "31/1/2026"]])

    result = await importer.confirm_instrument_import(None, content)

    assert result["failed"] == 1
    assert result["created"] == 0
    assert "日期格式无法识别" in result["error_details"][0]["message"]
    assert calls["sync"] == []  # 全部失败时不刷镜像
