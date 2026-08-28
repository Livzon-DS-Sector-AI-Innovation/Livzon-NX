"""Generate onboarding training record documents from templates."""

import logging
from io import BytesIO
from pathlib import Path

from docx import Document

from app.modules.hr.date_format import fmt_date_obj
from app.modules.hr.models import Employee

logger = logging.getLogger(__name__)


OLD_TEMPLATE_NAME = "7.3新员工入职培训记录.docx"


def _find_template() -> Path:
    """Locate the docx template, trying several path candidates."""
    candidates = [
        Path("员工培训教育管理规程") / OLD_TEMPLATE_NAME,
        Path("../员工培训教育管理规程") / OLD_TEMPLATE_NAME,
        Path(__file__).resolve().parent.parent.parent.parent
        / "员工培训教育管理规程"
        / OLD_TEMPLATE_NAME,
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(f"模板文件未找到: {OLD_TEMPLATE_NAME}")


def generate_onboarding_training_record(employee: Employee) -> BytesIO:
    """Fill the onboarding training record template with employee data.

    Returns a BytesIO buffer containing the generated docx.
    """
    template_path = _find_template()
    doc = Document(str(template_path))

    if not doc.tables:
        raise ValueError("模板中未找到表格")

    table = doc.tables[0]

    # Old factory template: 21 rows x 12 cols
    # Row 1: 姓名 | 01 | 性别 | 02... | 工作卡号 | 03...
    table.rows[1].cells[1].text = employee.name or ""
    for idx in (3, 4, 5):
        table.rows[1].cells[idx].text = employee.gender or ""
    for idx in (9, 10, 11):
        table.rows[1].cells[idx].text = employee.employee_number or ""

    # Row 2: 部门 | 04... | 拟定岗位 | 05...
    for idx in (1, 2):
        table.rows[2].cells[idx].text = employee.department or ""
    for idx in (6, 7, 8, 9, 10, 11):
        table.rows[2].cells[idx].text = employee.position or ""

    # Row 3: 报到日期 | 06... | 转正日期 | 07...
    hire_date_str = fmt_date_obj(employee.hire_date)
    for idx in (1, 2):
        table.rows[3].cells[idx].text = hire_date_str
    # 转正日期数据库中无对应字段，留空
    for idx in (6, 7, 8, 9, 10, 11):
        table.rows[3].cells[idx].text = ""

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer
