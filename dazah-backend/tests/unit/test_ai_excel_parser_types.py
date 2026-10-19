from openpyxl import Workbook

from app.platform.integrations.ai.document_parser import DocumentParser


def test_document_parser_reads_excel_scalars_without_external_ai(tmp_path):
    workbook = Workbook()
    sheet = workbook.worksheets[0]
    sheet.title = "能耗"
    sheet.append(["项目", "用量"])
    sheet.append(["饮用水", 123.5])
    path = tmp_path / "数据.xlsx"
    workbook.save(path)
    result = DocumentParser._extract_xlsx(str(path))
    assert "## Sheet: 能耗" in result
    assert "饮用水\t123.5" in result
