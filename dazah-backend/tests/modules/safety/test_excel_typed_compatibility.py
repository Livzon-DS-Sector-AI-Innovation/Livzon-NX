from openpyxl import Workbook

from app.modules.safety.document_parser import _extract_xlsx_to_markdown
from app.modules.safety.template_export.config import TemplateConfig
from app.modules.safety.template_export.filler import ExcelTemplateFiller


def test_markdown_keeps_ragged_rows_and_page_setup(tmp_path):
    workbook = Workbook()
    sheet = workbook.worksheets[0]
    sheet.append(["岗位", "风险", "人数"])
    sheet.append(["发酵", "一般", 2])
    sheet.append(["提炼"])
    path = tmp_path / "风险.xlsx"
    workbook.save(path)
    text = _extract_xlsx_to_markdown(str(path))
    assert "| 发酵 | 一般 | 2 |" in text
    assert "| 提炼 |  |  |" in text
    filler = ExcelTemplateFiller(TemplateConfig())
    filler._apply_page_setup(sheet)
    assert sheet.sheet_properties.pageSetUpPr.fitToPage is True
