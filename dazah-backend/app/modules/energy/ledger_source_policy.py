"""Shared manual-input boundaries for native energy entry and imports."""

from pydantic import JsonValue

SOURCE_CATEGORIES = {
    "饮用水码": "drinking_water",
    "冰水码": "chilled_water",
    "蒸汽码": "steam",
    "循环水码": "circulating_water",
    "空气码": "air",
    "电量": "electricity",
}

ELECTRICITY_CALCULATED_HEADERS = {
    "总计",
    "合计",
    "小计",
    "其他",
    "差额",
    "差值",
    "分表总和",
}


def calculated_columns(name: str, headers: list[JsonValue]) -> set[int]:
    """Identify derived electricity fields even when an export lost formulas."""
    return {
        index + 1
        for index, header in enumerate(headers)
        if name == "电量"
        and "".join(str(header or "").split()) in ELECTRICITY_CALCULATED_HEADERS
    }


def input_column_allowed(
    name: str, headers: list[JsonValue], column: int, computed: set[int]
) -> bool:
    if name not in SOURCE_CATEGORIES or not 2 <= column <= len(headers):
        return False
    label = str(headers[column - 1] or "").strip()
    if not label or "大罐数量" in label or column in computed:
        return False
    if column in calculated_columns(name, headers):
        return False
    # Detached columns in the reviewed circulation template are copied steam
    # fields, not confirmed circulation meters. Preserve them for review only.
    if name == "循环水码" and any(
        not str(headers[index] or "").strip()
        and not str(headers[index + 1] or "").strip()
        for index in range(1, column - 2)
    ):
        return False
    return True


def calculated_electricity_field(sheet: str, name: str) -> bool:
    label = "".join(name.split("·")[-1].split("〔")[0].split())
    return sheet == "电量" and label in ELECTRICITY_CALCULATED_HEADERS


def manual_input_allowed(
    sheet: str, name: str, reading_type: str, category: str = ""
) -> bool:
    if not sheet:
        return not (
            category == "electricity" and calculated_electricity_field("电量", name)
        )
    if sheet not in SOURCE_CATEGORIES or calculated_electricity_field(sheet, name):
        return False
    return reading_type == ("direct" if sheet == "电量" else "counter")
