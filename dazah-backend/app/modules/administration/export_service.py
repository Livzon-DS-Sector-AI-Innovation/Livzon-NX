"""行政模块镜像台账导出（Excel/PDF，所见即所得）。

导出内容与页面一致：调用方传入展示列（field_id 列表）、筛选与排序，记录
文本按页面同款规则格式化；附件图片经镜像附件通道下载（tmp_url 优先），
PIL 压缩后嵌入单元格；人员列按企业邮箱关联飞书头像并嵌入。
PDF 由 xlsx 经 LibreOffice headless 转换（复用质量模块公开转换能力）。
"""

import asyncio
import io
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.hr.public_api import get_avatar_urls_by_emails

logger = logging.getLogger("dazah.administration.export")

#: 单次导出行数上限（防整表导出拖垮内存与请求时长）
EXPORT_MAX_ROWS = 2000
#: 嵌入图片的显示尺寸（px）
_THUMB_WIDTH = 200
_THUMB_HEIGHT = 110
_AVATAR_SIZE = 24
#: 单元格内嵌入图片数量上限
_MAX_IMAGES_PER_CELL = 6
_IMAGE_EXTENSION_PATTERN = re.compile(r"\.(jpe?g|png|gif|webp|bmp)$", re.IGNORECASE)
_CST = timezone(timedelta(hours=8))
#: openpyxl EMU 换算（1px = 9525 EMU）
_EMU_PER_PX = 9525


def _format_display_text(value: Any) -> str:
    """页面同款文本格式化：布尔→是/否，毫秒时间戳→日期，富文本/人员→文本。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, int | float):
        number = float(value)
        if 1e12 <= number < 1e14:
            local = datetime.fromtimestamp(number / 1000, tz=_CST)
            text = local.strftime("%Y/%m/%d %H:%M:%S")
            return text.removesuffix(" 00:00:00")
        return f"{number:g}" if isinstance(value, float) else str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        items = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("name") or item.get("text") or ""
                if isinstance(text, list):
                    text = "".join(
                        str(part.get("text") or "")
                        if isinstance(part, dict)
                        else str(part)
                        for part in text
                    )
                if text:
                    items.append(str(text))
            elif item is not None:
                items.append(str(item))
        return "、".join(items)
    if isinstance(value, dict):
        for key in ("text", "name", "value"):
            if key in value:
                return _format_display_text(value[key])
        return str(value)
    return str(value)


def _attachment_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict) and item.get("file_token")]


def _image_items(value: Any) -> list[dict[str, Any]]:
    items = _attachment_items(value)
    return [
        item
        for item in items
        if str(item.get("type", "")).startswith("image/")
        or _IMAGE_EXTENSION_PATTERN.search(str(item.get("name", "")))
    ]


def _person_emails(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(item["email"])
        for item in value
        if isinstance(item, dict) and item.get("email")
    ]


async def _download_attachment_bytes(client: Any, item: dict[str, Any]) -> bytes | None:
    """优先 tmp_url 通道（应用无云盘 scope 也可用），失败回退标准下载。"""
    tmp_url = item.get("tmp_url")
    if isinstance(tmp_url, str) and tmp_url.startswith(
        "https://open.feishu.cn/open-apis/"
    ):
        try:
            downloaded = await client.download_media_via_tmp_url(tmp_url)
            return cast(bytes, downloaded[0])
        except Exception:
            logger.info("export attachment tmp_url download failed, trying direct")
    file_token = item.get("file_token")
    if not file_token:
        return None
    try:
        downloaded = await client.download_media(str(file_token))
        return cast(bytes, downloaded[0])
    except Exception:
        logger.info("export attachment direct download failed: %s", file_token)
        return None


def _downscale_image(
    content: bytes, max_width: int, max_height: int
) -> tuple[bytes, int, int] | None:
    """压到限定尺寸内的 JPEG 控制工作簿体积；失败返回 None（跳过嵌入）。"""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(content)) as source:
            converted = source.convert("RGB")
            converted.thumbnail((max_width, max_height))
            buffer = io.BytesIO()
            converted.save(buffer, format="JPEG", quality=80)
            return buffer.getvalue(), converted.width, converted.height
    except Exception:
        logger.info("export image downscale failed, skipping embed")
        return None


def _downscale_avatar(content: bytes) -> tuple[bytes, int, int] | None:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(content)) as source:
            converted = source.convert("RGB")
            side = min(converted.size)
            cropped = converted.crop(
                (
                    (converted.width - side) // 2,
                    (converted.height - side) // 2,
                    (converted.width + side) // 2,
                    (converted.height + side) // 2,
                )
            )
            resized = cropped.resize((_AVATAR_SIZE, _AVATAR_SIZE))
            buffer = io.BytesIO()
            resized.save(buffer, format="PNG")
            return buffer.getvalue(), _AVATAR_SIZE, _AVATAR_SIZE
    except Exception:
        logger.info("export avatar downscale failed, skipping embed")
        return None


async def _collect_person_avatar_bytes(
    db: AsyncSession, records: list[dict[str, Any]]
) -> dict[str, tuple[bytes, int, int]]:
    """下载并裁剪人员头像（按企业邮箱关联）；失败的头像静默跳过。"""
    import httpx

    emails: set[str] = set()
    for record in records:
        for value in (record.get("fields") or {}).values():
            for email in _person_emails(value):
                emails.add(email)
    if not emails:
        return {}
    avatar_by_email = await get_avatar_urls_by_emails(db, sorted(emails)[:100])
    result: dict[str, tuple[bytes, int, int]] = {}
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as http:
        for email, url in avatar_by_email.items():
            try:
                response = await http.get(url)
                response.raise_for_status()
                prepared = _downscale_avatar(response.content)
            except httpx.HTTPError:
                logger.info("export avatar download failed: %s", email)
                continue
            if prepared:
                result[email] = prepared
    return result


def _build_workbook(
    *,
    sheet_title: str,
    columns: list[tuple[str, str]],
    records: list[dict[str, Any]],
    avatar_objects: dict[str, tuple[bytes, int, int]],
    attachment_payloads: dict[tuple[str, str, str], bytes | None],
) -> bytes:
    """构建带图片/头像的工作簿。columns = [(field_name, header)]，顺序即页面列序。"""
    from openpyxl import Workbook
    from openpyxl.cell.cell import Cell
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
    from openpyxl.drawing.xdr import XDRPositiveSize2D
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.worksheet import Worksheet

    workbook = Workbook()
    sheet = cast(Worksheet, workbook.active)
    sheet.title = sheet_title[:31] or "导出"
    header_font = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="F2F3F5")

    attachment_field_names: set[str] = set()
    for index, (field_name, header) in enumerate(columns, start=1):
        cell = sheet.cell(row=1, column=index, value=header)
        cell.font = header_font
        cell.fill = header_fill
        if any(
            _attachment_items((record.get("fields") or {}).get(field_name))
            for record in records
        ):
            attachment_field_names.add(field_name)
        sheet.column_dimensions[get_column_letter(index)].width = 16

    def place_image(
        image: XLImage, column_index: int, row_index: int, offset_px: int
    ) -> None:
        marker = AnchorMarker(
            col=column_index - 1,
            colOff=int(offset_px * _EMU_PER_PX),
            row=row_index - 1,
            rowOff=int(2 * _EMU_PER_PX),
        )
        image.anchor = OneCellAnchor(
            _from=marker,
            ext=XDRPositiveSize2D(
                int(image.width * _EMU_PER_PX), int(image.height * _EMU_PER_PX)
            ),
        )
        sheet.add_image(image)

    for row_index, record in enumerate(records, start=2):
        record_fields = record.get("fields") or {}
        record_id = str(record.get("record_id"))
        row_has_image = False
        for column_index, (field_name, _header) in enumerate(columns, start=1):
            value = record_fields.get(field_name)
            cell = cast(Cell, sheet.cell(row=row_index, column=column_index))
            cell.value = _format_display_text(value)
            cell.alignment = Alignment(vertical="center", wrap_text=True)

            if field_name in attachment_field_names:
                offset_px = 0
                for item in _image_items(value)[:_MAX_IMAGES_PER_CELL]:
                    key = (record_id, field_name, str(item.get("file_token")))
                    content = attachment_payloads.get(key)
                    prepared = (
                        _downscale_image(content, _THUMB_WIDTH, _THUMB_HEIGHT)
                        if content
                        else None
                    )
                    if not prepared:
                        continue
                    payload, image_width, _image_height = prepared
                    place_image(
                        XLImage(io.BytesIO(payload)), column_index, row_index, offset_px
                    )
                    offset_px += image_width + 4
                    row_has_image = True

            for email in _person_emails(value):
                prepared = avatar_objects.get(email)
                if not prepared:
                    continue
                payload, _avatar_w, _avatar_h = prepared
                place_image(XLImage(io.BytesIO(payload)), column_index, row_index, 0)
                cell.alignment = Alignment(vertical="center", wrap_text=True, indent=3)
                row_has_image = True

        if row_has_image:
            sheet.row_dimensions[row_index].height = 62

    for column_index, (field_name, header) in enumerate(columns, start=1):
        if field_name in attachment_field_names:
            column_width: int | float = (_THUMB_WIDTH + _MAX_IMAGES_PER_CELL * 10) / 7
        else:
            lengths = [len(str(header))] + [
                len(_format_display_text((record.get("fields") or {}).get(field_name)))
                for record in records
            ]
            column_width = max(8.0, min(44.0, max(lengths) * 1.9 + 2))
        sheet.column_dimensions[get_column_letter(column_index)].width = column_width

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


async def export_binding_records(
    db: AsyncSession,
    service: Any,
    *,
    page_key: str,
    binding_id: uuid.UUID,
    file_format: str,
    columns: list[str] | None,
    filters: list[dict[str, str]],
    sort_field: str | None,
    sort_direction: str,
) -> tuple[bytes, str, str]:
    """导出绑定表筛选后的全量记录。返回 (content, filename, mime)。"""
    page = await service.page_records(
        page_key=page_key,
        binding_id=binding_id,
        page=1,
        page_size=EXPORT_MAX_ROWS,
        keyword=None,
        sort_field=sort_field,
        sort_direction=sort_direction,
        filters=filters,
    )
    fields_meta = {item["field_id"]: item for item in page["fields"]}
    field_order = list(columns or [])
    if not field_order:
        field_order = [
            item["field_id"]
            for item in page["fields"]
            if any(
                (record.get("fields") or {}).get(item["field_name"])
                not in (None, "", [])
                for record in page["records"]
            )
        ]
    unknown = [field_id for field_id in field_order if field_id not in fields_meta]
    if unknown:
        raise AppException(message="导出列包含不属于该数据表的字段", status_code=404)
    column_specs = [
        (fields_meta[field_id]["field_name"], fields_meta[field_id]["field_name"])
        for field_id in field_order
    ]

    records = page["records"]
    avatar_objects = await _collect_person_avatar_bytes(db, records)
    app_token = str((page["dataset"].get("table") or {}).get("app_token") or "")
    client = service.client_for_resource(app_token)

    # 预下载全部嵌入图片（并发受控），构建阶段纯同步
    image_items: list[tuple[tuple[str, str, str], dict[str, Any]]] = []
    for record in records:
        record_fields = record.get("fields") or {}
        record_id = str(record.get("record_id"))
        for field_name, value in record_fields.items():
            for item in _image_items(value)[:_MAX_IMAGES_PER_CELL]:
                image_items.append(
                    ((record_id, field_name, str(item.get("file_token"))), item)
                )

    async def _download_one(
        entry: tuple[tuple[str, str, str], dict[str, Any]],
    ) -> tuple[tuple[str, str, str], bytes | None]:
        key, item = entry
        return key, await _download_attachment_bytes(client, item)

    semaphore = asyncio.Semaphore(8)

    async def _bounded(
        entry: tuple[tuple[str, str, str], dict[str, Any]],
    ) -> tuple[tuple[str, str, str], bytes | None]:
        async with semaphore:
            return await _download_one(entry)

    attachment_payloads: dict[tuple[str, str, str], bytes | None] = {}
    if image_items:
        results = await asyncio.gather(
            *(_bounded(entry) for entry in image_items), return_exceptions=True
        )
        for entry_result in results:
            if isinstance(entry_result, BaseException):
                logger.info("export attachment download failed: %s", entry_result)
                continue
            key, payload = entry_result
            attachment_payloads[key] = payload

    sheet_title = str(page["dataset"].get("tab_label") or page_key)
    xlsx_bytes = await asyncio.to_thread(
        _build_workbook,
        sheet_title=sheet_title,
        columns=column_specs,
        records=records,
        avatar_objects=avatar_objects,
        attachment_payloads=attachment_payloads,
    )

    if file_format == "xlsx":
        return (
            xlsx_bytes,
            "mirror-export.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    if file_format == "pdf":
        from app.modules.quality.public_api import office_content_to_pdf

        pdf_bytes = await asyncio.to_thread(
            office_content_to_pdf, xlsx_bytes, f"{sheet_title}.xlsx"
        )
        if not pdf_bytes:
            raise AppException(
                message="PDF 转换失败，请改用 Excel 导出", status_code=502
            )
        return pdf_bytes, "mirror-export.pdf", "application/pdf"
    raise AppException(message="不支持的导出格式", status_code=400)
