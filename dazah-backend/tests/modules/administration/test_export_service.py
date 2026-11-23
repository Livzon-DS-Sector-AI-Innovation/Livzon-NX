"""镜像台账导出服务测试（工作簿构建与文本格式化，不依赖数据库）。"""

import io
import zipfile
from typing import Any

from openpyxl import load_workbook

from app.modules.administration.export_service import (
    _build_workbook,
    _format_display_text,
)


def test_format_display_text_cases() -> None:
    assert _format_display_text(True) == "是"
    assert _format_display_text(False) == "否"
    assert _format_display_text(1782230400000) == "2026/06/24"
    assert _format_display_text(1.5) == "1.5"
    assert _format_display_text([{"name": "常晶晶"}]) == "常晶晶"
    rich = [{"text": [{"text": "关于"}, {"text": "换行"}]}]
    assert _format_display_text(rich) == "关于换行"
    assert _format_display_text({"text": "合同章"}) == "合同章"
    assert _format_display_text(None) == ""


def _png_bytes() -> bytes:
    """最小合法 PNG（1x1 像素），供 openpyxl 嵌入。"""
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data))
        )

    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + chunk(b"IEND", b"")


def test_build_workbook_embeds_images_avatars_and_formats_values() -> None:
    fields_meta_columns = [
        ("放置日期", "放置日期"),
        ("申请人", "申请人"),
        ("废旧物资照片", "废旧物资照片"),
    ]
    records: list[dict[str, Any]] = [
        {
            "record_id": "rec-1",
            "fields": {
                "放置日期": 1782230400000,
                "申请人": [
                    {"id": "ou_abc", "name": "常晶晶", "email": "chang@livzon.cn"}
                ],
                "废旧物资照片": [
                    {
                        "name": "photo.jpeg",
                        "file_token": "tok1",
                        "type": "image/jpeg",
                        "tmp_url": "",
                    }
                ],
            },
        }
    ]
    avatar_png = _png_bytes()
    content = _build_workbook(
        sheet_title="放置申请",
        columns=fields_meta_columns,
        records=records,
        avatar_objects={"chang@livzon.cn": (avatar_png, 24, 24)},
        attachment_payloads={("rec-1", "废旧物资照片", "tok1"): _png_bytes()},
    )
    assert zipfile.is_zipfile(io.BytesIO(content))
    workbook = load_workbook(io.BytesIO(content))
    sheet = workbook.active
    assert sheet.title == "放置申请"
    assert [cell.value for cell in sheet[1]] == ["放置日期", "申请人", "废旧物资照片"]
    assert sheet.cell(row=2, column=1).value == "2026/06/24"
    assert sheet.cell(row=2, column=2).value == "常晶晶"
    # 图片嵌入：1 张附件缩略图 + 1 张人员头像
    assert len(sheet._images) == 2
