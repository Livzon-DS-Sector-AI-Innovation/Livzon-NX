"""Generate practical exam result document (APP13-SMP-HR-002-14) from docx template.

一人一份：每个参训人员生成一份实操考核结果表（可多页），导出时打包成 zip。
另支持"导入实操试题"：解析 APP13 格式的 docx，提取实操考核情况描述与培训日期。
模板保真填充，仅改填写区。
"""

import copy
import logging
import re
import zipfile
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table

from app.modules.hr.date_format import fmt_date_str
from app.modules.hr.error_contract import HrBusinessError, HrBusinessErrorCode
from app.modules.hr.schemas import PracticalExamExportRequest, PracticalExamPersonItem
from app.modules.hr.template_filler import fill_whole_cell, header_fmt_source

logger = logging.getLogger(__name__)

TEMPLATE_NAME = "APP13-SMP-HR-002-14实操培训考核结果表.docx"


def _find_template() -> Path:
    candidates = [
        Path("员工培训教育管理规程") / TEMPLATE_NAME,
        Path(__file__).resolve().parent.parent.parent
        / "员工培训教育管理规程"
        / TEMPLATE_NAME,
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(f"模板文件未找到: {TEMPLATE_NAME}")


def _fill_table(
    table: Any, person: Any, data: PracticalExamExportRequest, fmt_src: Any
) -> None:
    # R1: 部门 | 姓名
    fill_whole_cell(table.rows[1].cells[1], person.department or "", fmt_src)
    fill_whole_cell(table.rows[1].cells[5], person.name or "", fmt_src)
    # R2: 培训内容 | 培训日期
    fill_whole_cell(table.rows[2].cells[1], data.training_content or "", fmt_src)
    fill_whole_cell(table.rows[2].cells[5], fmt_date_str(data.training_date), fmt_src)
    # R3: 实操考核情况描述（大块空白）
    fill_whole_cell(table.rows[3].cells[0], person.description or "", fmt_src)
    # R4: 评估人/日期（落款标签后空白格）
    fill_whole_cell(table.rows[4].cells[5], data.assessor or "", fmt_src)


def _fill_person_only(
    table: Any, person: Any, data: PracticalExamExportRequest, fmt_src: Any
) -> None:
    "以导入的实操试题文件为基底时，只填 部门/姓名/培训日期，其"
    "余（培训内容、试题结构、方框）原样保留."
    fill_whole_cell(table.rows[1].cells[1], person.department or "", fmt_src)
    fill_whole_cell(table.rows[1].cells[5], person.name or "", fmt_src)
    fill_whole_cell(table.rows[2].cells[5], fmt_date_str(data.training_date), fmt_src)


def _imported_template_path() -> Path:
    """最近一次导入的实操试题 docx 的保存路径（导出时作为基底，保留试题结构/方框）。"""
    return Path(__file__).resolve().parent / "_practical_imported_template.docx"


def save_practical_exam_template(content: bytes) -> None:
    path = _imported_template_path()
    temp = NamedTemporaryFile(dir=path.parent, delete=False)
    temp_path = Path(temp.name)
    try:
        with temp:
            temp.write(content)
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def _load_question_template(source: BytesIO) -> Table:
    invalid_template = HrBusinessError(
        400,
        "实操试题模板不符合 APP13 格式，请使用 APP13 实操培训考核结果表，"
        "保留部门、姓名、培训日期和考核情况描述的表格结构后重新导入。",
        HrBusinessErrorCode.HR_PRACTICAL_EXAM_TEMPLATE_INVALID,
    )
    try:
        doc = Document(source)
        if doc.tables:
            table = doc.tables[0]
            rows = table.rows
            if len(rows) >= 4 and rows[3].cells:
                identification = rows[1].cells
                training = rows[2].cells
                if len(identification) >= 6 and len(training) >= 6:
                    distinct_identity_cells = {
                        identification[index]._tc for index in (0, 1, 4, 5)
                    }
                    if len(distinct_identity_cells) == 4 and all(
                        re.sub(r"\s+", "", cells[label].text) == text
                        and cells[label]._tc is not cells[value]._tc
                        for cells, label, value, text in (
                            (identification, 0, 1, "部门"),
                            (identification, 4, 5, "姓名"),
                            (training, 4, 5, "培训日期"),
                        )
                    ):
                        return table
    except (
        ValueError,
        KeyError,
        IndexError,
        zipfile.BadZipFile,
        PackageNotFoundError,
        SyntaxError,
    ) as exc:
        raise invalid_template from exc
    raise invalid_template


def _safe_filename(s: str | None, maxlen: int = 40) -> str:
    """去掉文件名非法字符，截断到 maxlen."""
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "", s or "").strip()
    return s[:maxlen] or "未命名"


def _make_person_doc(
    person: PracticalExamPersonItem,
    data: PracticalExamExportRequest,
    template: bytes,
    *,
    imported: bool,
) -> BytesIO:
    """生成单个人员的 APP13 文档（独立 docx，可多页）.

    若存在最近导入的实操试题文件，则以该文件为基底、只填部门/姓名/培训日期，
    完整保留试题的段落结构/方框；否则用空白模板完整填充。
    """
    doc = Document(BytesIO(template))
    if doc.tables:
        table = doc.tables[0]
        fmt_src = header_fmt_source(table)
        if imported:
            _fill_person_only(table, person, data, fmt_src)
        else:
            _fill_table(table, person, data, fmt_src)
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def generate_practical_exam_zip(data: PracticalExamExportRequest) -> BytesIO:
    """为每个参训人员生成一份实操考核结果表并打包成 zip."""
    persons = data.persons or []
    if not persons:
        persons = [PracticalExamPersonItem(name="")]
    imported_path = _imported_template_path()
    imported = imported_path.is_file()
    template = (imported_path if imported else _find_template()).read_bytes()
    if imported:
        _load_question_template(BytesIO(template))
    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, person in enumerate(persons, start=1):
            doc_buf = _make_person_doc(person, data, template, imported=imported)
            name = person.name or f"人员{i}"
            fname = (
                f"{_safe_filename(data.training_date)}"
                f"-{_safe_filename(data.training_content)}"
                f"-{_safe_filename(name)}实操.docx"
            )
            zf.writestr(fname, doc_buf.getvalue())
    zip_buf.seek(0)
    return zip_buf


def parse_practical_exam_questions(content: bytes) -> dict[str, str]:
    """解析导入的 APP13 格式 docx，提取实操考核情况描述与培训日期.

    模板结构：R1 部门/姓名（导入时留空），R2 培训内容/培训日期，R3
    实操考核情况描述（整行大格）。
    """
    table = _load_question_template(BytesIO(content))
    return {
        "description": table.rows[3].cells[0].text.strip(),
        "training_date": table.rows[2].cells[5].text.strip(),
    }


def generate_practical_exam_result(data: PracticalExamExportRequest) -> BytesIO:
    """按 APP13 模板保真生成实操培训考核结果表 Word（每人一页，单文档）."""
    doc = Document(str(_find_template()))
    if not doc.tables:
        raise ValueError("模板文件中未找到表格")

    fmt_src = header_fmt_source(doc.tables[0])
    persons = data.persons or []
    base_tbl_xml = copy.deepcopy(doc.tables[0]._tbl)

    if not persons:
        _fill_table(doc.tables[0], PracticalExamPersonItem(name=""), data, fmt_src)
    for idx, person in enumerate(persons):
        if idx == 0:
            _fill_table(doc.tables[0], person, data, fmt_src)
        else:
            doc.add_page_break()  # type: ignore[no-untyped-call]
            doc.element.body.append(copy.deepcopy(base_tbl_xml))
            _fill_table(doc.tables[-1], person, data, fmt_src)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer
