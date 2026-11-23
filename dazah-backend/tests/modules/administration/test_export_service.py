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


async def test_download_attachment_bytes_prefers_tmp_url(monkeypatch) -> None:
    """有 tmp_url 走 tmp 通道；失败回退 file_token 直下；全失败返回 None。"""
    from app.modules.administration import export_service as es

    calls: list[str] = []

    class _Client:
        async def download_media_via_tmp_url(self, tmp_url: str):
            calls.append("tmp:" + tmp_url)
            if "bad" in tmp_url:
                raise RuntimeError("tmp channel down")
            return (b"png-bytes", "image/png", None)

        async def download_media(self, token: str):
            calls.append("direct:" + token)
            return (b"direct-bytes", "image/png", None)

    # 1) tmp_url 成功
    item = {
        "tmp_url": "https://open.feishu.cn/open-apis/drive/v1/medias/x/download",
        "file_token": "tok-1",
    }
    result = await es._download_attachment_bytes(_Client(), item)
    assert result == b"png-bytes"
    assert calls == ["tmp:https://open.feishu.cn/open-apis/drive/v1/medias/x/download"]

    # 2) tmp 失败 → 回退直下
    calls.clear()
    item["tmp_url"] = "https://open.feishu.cn/open-apis/drive/v1/medias/bad"
    result = await es._download_attachment_bytes(_Client(), item)
    assert result == b"direct-bytes"
    assert calls[-1] == "direct:tok-1"

    # 3) 非 open.feishu 前缀 → 直接走直下
    calls.clear()
    item["tmp_url"] = "https://other.example.com/x"
    result = await es._download_attachment_bytes(_Client(), item)
    assert result == b"direct-bytes"

    # 4) 无 file_token 且 tmp 失败 → None
    calls.clear()
    item["tmp_url"] = "https://open.feishu.cn/open-apis/drive/v1/medias/bad"
    item["file_token"] = ""
    assert await es._download_attachment_bytes(_Client(), item) is None


def test_downscale_helpers() -> None:
    """压图成功/坏内容跳过；头像居中裁方并缩放。"""
    import struct
    import zlib

    from app.modules.administration import export_service as es

    def _png(width: int, height: int) -> bytes:
        def chunk(tag: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + tag
                + data
                + struct.pack(">I", zlib.crc32(tag + data))
            )

        header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b"")
        )

    ok = es._downscale_image(_png(200, 100), 64, 64)
    assert ok is not None and ok[1] <= 64
    assert es._downscale_image(b"not-a-png", 64, 64) is None

    avatar = es._downscale_avatar(_png(80, 40))
    assert avatar is not None and avatar[1] == avatar[2]
    assert es._downscale_avatar(b"garbage") is None


async def test_collect_person_avatar_bytes_empty_emails(monkeypatch) -> None:
    """无邮箱记录 → 不发起下载，返回空映射。"""
    from app.modules.administration import export_service as es

    result = await es._collect_person_avatar_bytes(
        None, [{"fields": {"负责人": "纯文本无邮箱"}}]
    )
    assert result == {}
