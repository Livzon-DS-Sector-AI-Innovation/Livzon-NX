"""设备台账上传存档测试。

覆盖：上传成功后存档落库与回看协议（列表/详情/原件下载/软删）、
存档与已导入台账数据的独立性、导入失败不留存档。
"""

import io
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from openpyxl import Workbook

from app.modules.equipment.service.equipment_ledger_archive import (
    _column_letter,
    parse_ledger_snapshot,
)

HEADERS = [
    "序号",
    "设备编号",
    "设备名称",
    "规格型号",
    "技术参数",
    "生产厂家",
    "出厂日期",
    "出厂编号",
    "入厂日期",
    "安装地点",
    "备注",
]

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _ledger_bytes(rows: list[list[Any]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _uid() -> str:
    return uuid.uuid4().hex[:6].upper()


async def _upload(
    client: AsyncClient, excel: bytes, *, workshop: str = "201-1"
) -> Any:
    return await client.post(
        "/api/v1/equipment/equipments/import",
        files={"file": ("ledger.xlsx", excel, XLSX_MIME)},
        data={"workshop": workshop},
    )


# ---------- 纯解析函数 ----------


def test_parse_snapshot_serializes_and_keeps_structure() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADERS)
    sheet.append(
        [1, "IMP-001", "发酵罐", None, None, None, None, None, None, None, None]
    )
    sheet.merge_cells("B2:C2")
    buffer = io.BytesIO()
    workbook.save(buffer)
    snapshot = parse_ledger_snapshot(buffer.getvalue())
    assert snapshot["sheet_name"] == "Sheet"
    assert snapshot["rows"][0] == HEADERS
    assert snapshot["rows"][1][1] == "IMP-001"
    # 空单元格序列化为空串；None 序列化为 0 列宽缺失 → 回退 80
    assert snapshot["rows"][1][3] == ""
    assert snapshot["merges"] == [{"s": {"r": 1, "c": 1}, "e": {"r": 1, "c": 2}}]
    assert snapshot["row_count"] == 2
    assert snapshot["col_count"] == len(HEADERS)
    assert all(width == 80 for width in snapshot["col_widths"])


def test_parse_snapshot_rejects_invalid_bytes() -> None:
    with pytest.raises(Exception):
        parse_ledger_snapshot(b"not an excel file")


def test_column_letter_wraps_past_z() -> None:
    assert _column_letter(1) == "A"
    assert _column_letter(26) == "Z"
    assert _column_letter(27) == "AA"
    assert _column_letter(52) == "AZ"


# ---------- 接口：上传 → 存档回看 → 删除 ----------


async def test_import_archives_and_roundtrip(
    client: AsyncClient, isolated_equipment_uploads: Any
) -> None:
    excel = _ledger_bytes(
        [
            [
                1, f"ARC-{_uid()}", "发酵罐", "PJ-500L",
                None, None, None, None, None, "档案车间", None,
            ],
            [
                2, f"ARC-{_uid()}", "离心机",
                None, None, None, None, None, None, "档案车间", None,
            ],
        ]
    )

    response = await _upload(client, excel, workshop="103")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["created"] == 2
    archive_id = data["archive_id"]
    assert archive_id

    # 列表：含导入摘要与车间，可按车间过滤
    list_response = await client.get(
        "/api/v1/equipment/equipments/import-archives",
        params={"page": 1, "page_size": 10, "workshop": "103"},
    )
    assert list_response.status_code == 200
    items = list_response.json()["data"]
    assert len(items) == 1
    assert items[0]["id"] == archive_id
    assert items[0]["workshop_code"] == "103"
    assert items[0]["file_name"] == "ledger.xlsx"
    assert items[0]["import_summary"]["created"] == 2
    assert "rows" not in items[0]
    other_workshop = await client.get(
        "/api/v1/equipment/equipments/import-archives",
        params={"page": 1, "page_size": 10, "workshop": "101-1"},
    )
    assert other_workshop.json()["data"] == []

    # 详情：回看完整表格快照
    detail = await client.get(
        f"/api/v1/equipment/equipments/import-archives/{archive_id}"
    )
    assert detail.status_code == 200
    detail_data = detail.json()["data"]
    assert detail_data["rows"][0] == HEADERS
    assert len(detail_data["rows"]) == 3
    assert detail_data["col_count"] == len(HEADERS)
    assert detail_data["sheet_name"]

    # 原件下载：与上传内容一致
    download = await client.get(
        f"/api/v1/equipment/equipments/import-archives/{archive_id}/file"
    )
    assert download.status_code == 200
    assert download.content == excel

    # 删除存档后：台账数据不受影响，存档不可再见
    deleted = await client.delete(
        f"/api/v1/equipment/equipments/import-archives/{archive_id}"
    )
    assert deleted.status_code == 200
    assert (
        await client.get(
            f"/api/v1/equipment/equipments/import-archives/{archive_id}"
        )
    ).status_code == 404
    emptied = await client.get(
        "/api/v1/equipment/equipments/import-archives",
        params={"page": 1, "page_size": 10},
    )
    assert emptied.json()["data"] == []
    kept = await client.get(
        "/api/v1/equipment/equipments",
        params={"keyword": "ARC-", "page": 1, "page_size": 20},
    )
    assert len(kept.json()["data"]) == 2


async def test_repeated_upload_appends_new_archive(
    client: AsyncClient, isolated_equipment_uploads: Any
) -> None:
    excel = _ledger_bytes(
        [
            [
                1, f"ARC2-{_uid()}", "发酵罐",
                None, None, None, None, None, None, "档案车间", None,
            ]
        ]
    )
    first = await _upload(client, excel)
    second = await _upload(client, excel)
    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["archive_id"] != second.json()["data"][
        "archive_id"
    ]
    # 第二次全部转为更新；两份存档并存（新在前）
    assert second.json()["data"]["updated"] == 1
    listing = await client.get(
        "/api/v1/equipment/equipments/import-archives",
        params={"page": 1, "page_size": 10},
    )
    items = listing.json()["data"]
    assert len(items) == 2
    assert items[0]["id"] == second.json()["data"]["archive_id"]


async def test_failed_import_leaves_no_archive(
    client: AsyncClient, isolated_equipment_uploads: Any
) -> None:
    response = await client.post(
        "/api/v1/equipment/equipments/import",
        files={"file": ("ledger.xlsx", b"broken bytes", XLSX_MIME)},
        data={"workshop": "103"},
    )
    assert response.status_code == 400
    listing = await client.get(
        "/api/v1/equipment/equipments/import-archives",
        params={"page": 1, "page_size": 10},
    )
    assert listing.json()["data"] == []


async def test_archive_detail_not_found(client: AsyncClient) -> None:
    missing = str(uuid.uuid4())
    assert (
        await client.get(
            f"/api/v1/equipment/equipments/import-archives/{missing}"
        )
    ).status_code == 404
