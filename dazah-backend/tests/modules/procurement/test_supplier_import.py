from io import BytesIO

from openpyxl import Workbook

from app.modules.procurement.service import (
    _build_supplier_from_row,
    _parse_supplier_table_file,
)


def test_parse_supplier_xlsx_extracts_columns_and_common_fields() -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "供应商清单"
    worksheet.append(
        [
            "供应商代码",
            "供应商名称",
            "物料编码",
            "物料名称",
            "生产厂家编码",
            "生产厂家名称",
            "采购品类名称",
            "最后更新人",
            "最后更新日期",
        ]
    )
    worksheet.append(
        [
            "9113WX201",
            "石家庄衡诺生物科技有限公司",
            40000054,
            "玉米浆(LN),槽车",
            "9113WX201",
            "石家庄衡诺生物科技有限公司",
            "原辅料",
            "甄宁",
            "2026-06-23",
        ]
    )
    output = BytesIO()
    workbook.save(output)

    columns, rows, sheet_name = _parse_supplier_table_file(
        output.getvalue(),
        "供应商清单.xlsx",
    )
    supplier = _build_supplier_from_row(
        raw_data=rows[0][1],
        columns=columns,
        file_name="供应商清单.xlsx",
        sheet_name=sheet_name,
        row_number=rows[0][0],
    )

    assert sheet_name == "供应商清单"
    assert columns == [
        "供应商代码",
        "供应商名称",
        "物料编码",
        "物料名称",
        "生产厂家编码",
        "生产厂家名称",
        "采购品类名称",
        "最后更新人",
        "最后更新日期",
    ]
    assert len(rows) == 1
    assert supplier.supplier_code == "9113WX201"
    assert supplier.supplier_name == "石家庄衡诺生物科技有限公司"
    assert supplier.material_code == "40000054"
    assert supplier.material_name == "玉米浆(LN),槽车"
    assert supplier.purchase_category == "原辅料"
    assert str(supplier.last_updated_date) == "2026-06-23"
