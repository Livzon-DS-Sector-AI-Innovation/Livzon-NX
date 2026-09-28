"""Product and card visibility for requests authorized as production overview."""

from fastapi import HTTPException

from app.platform.identity.data_scope import (
    current_page_key,
    current_page_visible_sections,
)

PRODUCT_NAMES = {
    "MC": "霉酚酸",
    "LN": "盐酸林可霉素",
    "DR": "多拉菌素",
    "FA": "L-苯丙氨酸",
    "LV": "洛伐他汀",
    "MV": "美伐他汀",
    "TY": "L-色氨酸",
    "FL": "2%氟苯尼考预混剂",
}


def overview_visible_sections() -> set[str] | None:
    if current_page_key.get() != "production:overview":
        return None
    sections = current_page_visible_sections.get()
    return None if sections is None else set(sections)


def require_overview_section(section: str) -> None:
    visible = overview_visible_sections()
    if visible is not None and section not in visible:
        raise HTTPException(403, "未获授权查看生产管理概览中的该数据")


def require_overview_product_name(product_name: str | None) -> None:
    visible = overview_visible_sections()
    if visible is not None and not any(
        code in visible and name == product_name
        for code, name in PRODUCT_NAMES.items()
    ):
        raise HTTPException(403, "未获授权查看生产管理概览中的该产品")
