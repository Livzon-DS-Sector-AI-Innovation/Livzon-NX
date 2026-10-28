"""设备报修二维码批量出码（平台 → PDF 打印张贴）。

设计约束（内网保密版方案）：
- 码内容是纯文本「报修 {车间全名} {设备名} {设备编号}」，不编码任何
  URL/token/签名——扫码者用飞书扫一扫识别文本后复制发到维修群即可建单；
- 车间全名进码，保证规则引擎（_match_workshops/_match_equipments）直接
  命中，链路不依赖 LLM 在线；
- 排版使用已有 Pillow（A4 一页 12 枚 + 裁切线），二维码用 segno 生成。
"""

from __future__ import annotations

import io
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.equipment.models.equipment import Equipment
from app.modules.equipment.models.workshop import EquipmentWorkshop

logger = logging.getLogger(__name__)

# A4 @150dpi；3 列 × 4 行 = 一页 12 枚
_PAGE_W, _PAGE_H = 1240, 1754
_COLS, _ROWS = 3, 4
_QR_SIZE = 300
_MARGIN = 24
_CUT_COLOR = (176, 174, 170)

# 中文字体：Linux 容器内为 Noto CJK（Dockerfile 已安装），
# Windows 宿主用于本地测试时回落微软雅黑/黑体
_FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
)


def build_repair_text(
    workshop_name: str, equipment_name: str, equipment_no: str
) -> str:
    """设备标签二维码携带的报修文本（规则引擎可直接命中）。"""
    return f"报修 {workshop_name} {equipment_name} {equipment_no}".strip()


@dataclass(frozen=True)
class QrcodeItem:
    """单枚设备码的排版输入。"""

    workshop_name: str
    equipment_name: str
    equipment_no: str

    @property
    def repair_text(self) -> str:
        return build_repair_text(
            self.workshop_name, self.equipment_name, self.equipment_no
        )


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    raise RuntimeError(
        "未找到可用中文字体（Noto CJK / 微软雅黑），无法生成设备码 PDF"
    )


def _make_qr(text: str) -> Image.Image:
    import segno

    buf = io.BytesIO()
    segno.make(text, error="m").save(buf, kind="png", scale=10, border=2)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def _draw_cut_lines(draw: ImageDraw.ImageDraw) -> None:
    """整页横向/纵向裁切线（细灰线，裁切后不残留大片墨迹）。"""
    cell_w, cell_h = _PAGE_W // _COLS, _PAGE_H // _ROWS
    for i in range(1, _COLS):
        x = i * cell_w
        draw.line([(x, 0), (x, _PAGE_H)], fill=_CUT_COLOR, width=1)
    for i in range(1, _ROWS):
        y = i * cell_h
        draw.line([(0, y), (_PAGE_W, y)], fill=_CUT_COLOR, width=1)


def _draw_cell(
    draw: ImageDraw.ImageDraw,
    page: Image.Image,
    item: QrcodeItem,
    col: int,
    row: int,
    fonts: dict[str, ImageFont.FreeTypeFont],
) -> None:
    cell_w, cell_h = _PAGE_W // _COLS, _PAGE_H // _ROWS
    left = col * cell_w
    top = row * cell_h
    cx = left + cell_w // 2

    # 设备名（截断防溢出）
    name = item.equipment_name
    if len(name) > 14:
        name = name[:13] + "…"
    draw.text((cx, top + 46), name, font=fonts["name"], fill=(29, 27, 24), anchor="ma")

    sub = f"{item.workshop_name} · {item.equipment_no or '无编号'}"
    draw.text((cx, top + 92), sub, font=fonts["sub"], fill=(90, 88, 84), anchor="ma")

    qr = _make_qr(item.repair_text).resize((_QR_SIZE, _QR_SIZE))
    page.paste(qr, (cx - _QR_SIZE // 2, top + 130))

    draw.text(
        (cx, top + 130 + _QR_SIZE + 18),
        "扫一扫，复制后发到维修群报修",
        font=fonts["guide"],
        fill=(120, 118, 114),
        anchor="ma",
    )


def render_qrcode_pdf(items: Sequence[QrcodeItem]) -> bytes:
    """把设备码排版为多页 A4 PDF，返回字节流。"""
    if not items:
        raise ValueError("没有可出码的设备")

    fonts = {
        "name": _load_font(40),
        "sub": _load_font(28),
        "guide": _load_font(24),
    }
    per_page = _COLS * _ROWS
    pages: list[Image.Image] = []
    for start in range(0, len(items), per_page):
        page = Image.new("RGB", (_PAGE_W, _PAGE_H), (255, 255, 255))
        draw = ImageDraw.Draw(page)
        _draw_cut_lines(draw)
        for idx, item in enumerate(items[start : start + per_page]):
            _draw_cell(
                draw, page, item, idx % _COLS, idx // _COLS, fonts
            )
        pages.append(page)

    out = io.BytesIO()
    pages[0].save(
        out,
        format="PDF",
        save_all=True,
        append_images=pages[1:],
        resolution=150.0,
    )
    return out.getvalue()


async def generate_workshop_qrcode_pdf(
    db: AsyncSession, workshop_code: str
) -> tuple[bytes, str]:
    """按车间生成设备码 PDF；返回 (pdf 字节, 车间名)。"""
    workshop = (
        (
            await db.execute(
                select(EquipmentWorkshop).where(
                    EquipmentWorkshop.code == workshop_code,
                    EquipmentWorkshop.is_deleted == False,  # noqa: E712
                )
            )
        )
        .scalars()
        .first()
    )
    if workshop is None:
        raise LookupError(f"车间不存在: {workshop_code}")

    rows = (
        (
            await db.execute(
                select(Equipment)
                .where(
                    Equipment.workshop_code == workshop_code,
                    Equipment.is_deleted == False,  # noqa: E712
                )
                .order_by(Equipment.equipment_no)
            )
        )
        .scalars()
        .all()
    )
    items = [
        QrcodeItem(
            workshop_name=workshop.name,
            equipment_name=row.name,
            equipment_no=row.equipment_no or "",
        )
        for row in rows
    ]
    logger.info("设备码出码: workshop=%s, 数量=%d", workshop_code, len(items))
    return render_qrcode_pdf(items), workshop.name
