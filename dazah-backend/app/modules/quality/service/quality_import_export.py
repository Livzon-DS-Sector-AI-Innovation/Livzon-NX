"""Quality module import/export service for CAPA and Deviation (Word docx format)."""

import uuid
from datetime import date, datetime, timedelta
from io import BytesIO
from copy import deepcopy

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality import repository as repo
from app.modules.quality.models import CAPA, Deviation


def _parse_date(value) -> datetime | None:
    """Parse date from various formats."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip().replace(".", "-").replace("/", "-")
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _parse_bool(value) -> bool | None:
    """Parse boolean from various formats."""
    if value is None or value == "":
        return None
    s = str(value).strip().lower()
    if s in ("是", "yes", "true", "1", "y"):
        return True
    if s in ("否", "no", "false", "0", "n"):
        return False
    return None


def _clean_text(value) -> str:
    """Clean text value."""
    if not value:
        return ""
    return str(value).strip()


def _parse_date_value(value) -> date | None:
    parsed = _parse_date(value)
    if parsed is None:
        return None
    return parsed.date()


def _is_empty_row(row_data: dict[str, str]) -> bool:
    return not any(_clean_text(value) for value in row_data.values())


CHANGE_HEADERS = [
    "序号",
    "变更控制号",
    "变更申请部门",
    "变更对象",
    "变更内容",
    "变更等级",
    "变更申请日期",
    "变更计划批准日期",
    "变更正式执行日期",
    "变更关闭日期",
]


def _change_row_to_data(row_data: dict[str, str]) -> dict:
    return {
        "serial_number": row_data.get("序号") or None,
        "change_code": row_data.get("变更控制号", ""),
        "applicant_department": row_data.get("变更申请部门") or None,
        "change_object": row_data.get("变更对象") or None,
        "change_content": row_data.get("变更内容") or None,
        "change_level": row_data.get("变更等级") or None,
        "application_date": _parse_date_value(row_data.get("变更申请日期", "")),
        "planned_approval_date": _parse_date_value(
            row_data.get("变更计划批准日期", "")
        ),
        "execution_date": _parse_date_value(row_data.get("变更正式执行日期", "")),
        "closure_date": _parse_date_value(row_data.get("变更关闭日期", "")),
    }


async def preview_change_import(
    db: AsyncSession,
    file_content: bytes,
) -> dict:
    """Preview change control import from Word docx."""
    import docx

    doc = docx.Document(BytesIO(file_content))
    if not doc.tables:
        return {
            "headers": [],
            "valid_rows": 0,
            "error_rows": [
                {"row_number": 0, "error_message": "文档中未找到表格"}
            ],
            "total_rows": 0,
        }

    table = doc.tables[0]
    headers = [_clean_text(cell.text) for cell in table.rows[0].cells]

    valid_rows = 0
    error_rows = []

    for row_idx, row in enumerate(table.rows[1:], start=2):
        row_data = {
            _clean_text(headers[i]): _clean_text(row.cells[i].text)
            for i in range(len(headers))
        }
        if _is_empty_row(row_data):
            continue

        change_code = row_data.get("变更控制号", "")
        errors = []
        if not change_code:
            errors.append("变更控制号不能为空")
        else:
            exists = await repo.exists_by_change_code(db, change_code)
            if exists:
                errors.append(f"变更控制号已存在: {change_code}")

        if errors:
            error_rows.append(
                {
                    "row_number": row_idx,
                    "error_message": "; ".join(errors),
                    "row_data": row_data,
                }
            )
        else:
            valid_rows += 1

    return {
        "headers": headers,
        "valid_rows": valid_rows,
        "error_rows": error_rows,
        "total_rows": valid_rows + len(error_rows),
    }


async def confirm_change_import(
    db: AsyncSession,
    file_content: bytes,
    skip_duplicates: bool = True,
    update_existing: bool = False,
) -> dict:
    """Confirm change control import from Word docx."""
    import docx

    doc = docx.Document(BytesIO(file_content))
    if not doc.tables:
        return {
            "success_count": 0,
            "update_count": 0,
            "skip_count": 0,
            "error_count": 1,
            "error_details": [{"row": 0, "error": "文档中未找到表格"}],
        }

    table = doc.tables[0]
    headers = [_clean_text(cell.text) for cell in table.rows[0].cells]

    success_count = 0
    update_count = 0
    skip_count = 0
    error_count = 0
    error_details = []

    for row_idx, row in enumerate(table.rows[1:], start=2):
        row_data = {
            _clean_text(headers[i]): _clean_text(row.cells[i].text)
            for i in range(len(headers))
        }
        if _is_empty_row(row_data):
            continue

        try:
            change_code = row_data.get("变更控制号", "")
            if not change_code:
                error_count += 1
                error_details.append({"row": row_idx, "error": "变更控制号为空"})
                continue

            existing = await repo.get_change_by_code(db, change_code)
            data = _change_row_to_data(row_data)
            if existing:
                if update_existing:
                    await repo.update_change(db, existing, data)
                    update_count += 1
                elif skip_duplicates:
                    skip_count += 1
                else:
                    error_count += 1
                    error_details.append(
                        {"row": row_idx, "error": f"变更控制号已存在: {change_code}"}
                    )
                continue

            await repo.create_change(db, data)
            success_count += 1
        except Exception as e:
            error_count += 1
            error_details.append({"row": row_idx, "error": str(e)})

    await db.commit()

    return {
        "success_count": success_count,
        "update_count": update_count,
        "skip_count": skip_count,
        "error_count": error_count,
        "error_details": error_details,
    }


async def export_changes(
    db: AsyncSession,
    template_content: bytes | None = None,
    change_code: str | None = None,
    applicant_department: str | None = None,
    change_object: str | None = None,
    change_level: str | None = None,
    application_date_from: str | None = None,
    application_date_to: str | None = None,
    planned_approval_date_from: str | None = None,
    planned_approval_date_to: str | None = None,
    execution_date_from: str | None = None,
    execution_date_to: str | None = None,
    closure_date_from: str | None = None,
    closure_date_to: str | None = None,
    content_keyword: str | None = None,
) -> bytes:
    """Export change control data to Word docx."""
    import docx

    changes, _ = await repo.get_changes(
        db,
        change_code=change_code,
        applicant_department=applicant_department,
        change_object=change_object,
        change_level=change_level,
        application_date_from=_parse_date_value(application_date_from),
        application_date_to=_parse_date_value(application_date_to),
        planned_approval_date_from=_parse_date_value(planned_approval_date_from),
        planned_approval_date_to=_parse_date_value(planned_approval_date_to),
        execution_date_from=_parse_date_value(execution_date_from),
        execution_date_to=_parse_date_value(execution_date_to),
        closure_date_from=_parse_date_value(closure_date_from),
        closure_date_to=_parse_date_value(closure_date_to),
        content_keyword=content_keyword,
        page=1,
        page_size=10000,
    )

    if template_content:
        doc = docx.Document(BytesIO(template_content))
        table = doc.tables[0]
        for i in range(len(table.rows) - 1, 0, -1):
            tr = table.rows[i]._tr
            table._tbl.remove(tr)
    else:
        doc = docx.Document()
        doc.add_heading("变更管理台账", level=1)
        table = doc.add_table(rows=1, cols=len(CHANGE_HEADERS))
        table.style = "Table Grid"
        for i, header in enumerate(CHANGE_HEADERS):
            table.rows[0].cells[i].text = header

    for idx, change in enumerate(changes, start=1):
        row = table.add_row()
        row.cells[0].text = change.serial_number or str(idx)
        row.cells[1].text = change.change_code or ""
        row.cells[2].text = change.applicant_department or ""
        row.cells[3].text = change.change_object or ""
        row.cells[4].text = change.change_content or ""
        row.cells[5].text = change.change_level or ""
        row.cells[6].text = (
            change.application_date.strftime("%Y.%m.%d")
            if change.application_date
            else ""
        )
        row.cells[7].text = (
            change.planned_approval_date.strftime("%Y.%m.%d")
            if change.planned_approval_date
            else ""
        )
        row.cells[8].text = (
            change.execution_date.strftime("%Y.%m.%d")
            if change.execution_date
            else ""
        )
        row.cells[9].text = (
            change.closure_date.strftime("%Y.%m.%d")
            if change.closure_date
            else ""
        )

    output = BytesIO()
    doc.save(output)
    output.seek(0)
    return output.getvalue()


# ============ CAPA Import/Export (Word docx) ============

async def preview_capa_import(
    db: AsyncSession,
    file_content: bytes,
) -> dict:
    """Preview CAPA import from Word docx."""
    import docx

    doc = docx.Document(BytesIO(file_content))
    if not doc.tables:
        return {"valid_rows": 0, "error_rows": [{"row_number": 0, "error_message": "文档中未找到表格"}], "total_rows": 0}

    table = doc.tables[0]
    headers = [_clean_text(cell.text) for cell in table.rows[0].cells]

    valid_rows = 0
    error_rows = []

    for row_idx, row in enumerate(table.rows[1:], start=2):
        row_data = {_clean_text(headers[i]): _clean_text(row.cells[i].text) for i in range(len(headers))}
        errors = []

        capa_code = row_data.get("CAPA编号", "")
        if not capa_code:
            errors.append("CAPA编号不能为空")
        else:
            exists = await repo.exists_by_capa_code(db, capa_code)
            if exists:
                errors.append(f"CAPA编号已存在: {capa_code}")

        if errors:
            error_rows.append({"row_number": row_idx, "error_message": "; ".join(errors), "row_data": row_data})
        else:
            valid_rows += 1

    return {"valid_rows": valid_rows, "error_rows": error_rows, "total_rows": valid_rows + len(error_rows)}


async def confirm_capa_import(
    db: AsyncSession,
    file_content: bytes,
    skip_duplicates: bool = True,
    update_existing: bool = False,
) -> dict:
    """Confirm CAPA import from Word docx with deduplication."""
    import docx
    import re

    doc = docx.Document(BytesIO(file_content))
    if not doc.tables:
        return {"success_count": 0, "error_count": 1, "error_details": [{"row": 0, "error": "文档中未找到表格"}]}

    table = doc.tables[0]
    headers = [_clean_text(cell.text) for cell in table.rows[0].cells]

    success_count = 0
    skip_count = 0
    update_count = 0
    error_count = 0
    error_details = []

    for row_idx, row in enumerate(table.rows[1:], start=2):
        row_data = {_clean_text(headers[i]): _clean_text(row.cells[i].text) for i in range(len(headers))}
        try:
            capa_code = row_data.get("CAPA编号", "")
            if not capa_code:
                error_count += 1
                error_details.append({"row": row_idx, "error": "CAPA编号为空"})
                continue

            existing = await repo.get_capa_by_code(db, capa_code)
            if existing:
                if update_existing:
                    # Update existing record
                    qa_info = row_data.get("QA质量员/日期", "")
                    qa_confirmer = None
                    qa_confirm_date = None
                    if qa_info:
                        match = re.match(r'([^\d]+)(\d{4}[\.\-/]\d{2}[\.\-/]\d{2})', qa_info)
                        if match:
                            qa_confirmer = match.group(1).strip()
                            qa_confirm_date = _parse_date(match.group(2))
                        else:
                            qa_confirmer = qa_info

                    update_data = {
                        "title": row_data.get("CAPA简述", ""),
                        "source_code": row_data.get("来源编号", ""),
                        "department": row_data.get("事件部门", ""),
                        "affected_product": row_data.get("涉及产品", ""),
                        "evaluation_result": row_data.get("CAPA效果评估", ""),
                        "closure_date": _parse_date(row_data.get("关闭日期", "")),
                        "qa_confirmer": qa_confirmer,
                        "qa_confirm_date": qa_confirm_date,
                    }
                    await repo.update_capa(db, existing, update_data)
                    update_count += 1
                elif skip_duplicates:
                    skip_count += 1
                else:
                    error_count += 1
                    error_details.append({"row": row_idx, "error": f"CAPA编号已存在: {capa_code}"})
                continue

            # Parse QA质量员/日期 (format: "杨小芹2026.03.11")
            qa_info = row_data.get("QA质量员/日期", "")
            qa_confirmer = None
            qa_confirm_date = None
            if qa_info:
                match = re.match(r'([^\d]+)(\d{4}[\.\-/]\d{2}[\.\-/]\d{2})', qa_info)
                if match:
                    qa_confirmer = match.group(1).strip()
                    qa_confirm_date = _parse_date(match.group(2))
                else:
                    qa_confirmer = qa_info

            data = {
                "capa_code": capa_code,
                "title": row_data.get("CAPA简述", ""),
                "source_code": row_data.get("来源编号", ""),
                "department": row_data.get("事件部门", ""),
                "affected_product": row_data.get("涉及产品", ""),
                "evaluation_result": row_data.get("CAPA效果评估", ""),
                "closure_date": _parse_date(row_data.get("关闭日期", "")),
                "qa_confirmer": qa_confirmer,
                "qa_confirm_date": qa_confirm_date,
                "status": "draft",
            }

            await repo.create_capa(db, data)
            success_count += 1
        except Exception as e:
            error_count += 1
            error_details.append({"row": row_idx, "error": str(e)})

    await db.commit()

    return {
        "success_count": success_count,
        "update_count": update_count,
        "skip_count": skip_count,
        "error_count": error_count,
        "error_details": error_details,
    }


async def export_capas(
    db: AsyncSession,
    template_content: bytes | None = None,
    status: str | None = None,
    source: str | None = None,
    category: str | None = None,
    keyword: str | None = None,
    capa_code: str | None = None,
    affected_product: str | None = None,
    source_code: str | None = None,
    evaluation_result: str | None = None,
    closure_date_from: str | None = None,
    closure_date_to: str | None = None,
    department: str | None = None,
    qa_confirmer: str | None = None,
) -> bytes:
    """Export CAPA data to Word docx, preserving template format."""
    import docx
    from docx.shared import Pt

    # Get data
    closure_start = datetime.fromisoformat(closure_date_from) if closure_date_from else None
    closure_end = datetime.fromisoformat(closure_date_to) + timedelta(days=1) if closure_date_to else None
    capas, _ = await repo.get_capas(
        db,
        status,
        source,
        category,
        None,
        keyword,
        capa_code,
        affected_product,
        source_code,
        evaluation_result,
        closure_start,
        closure_end,
        department,
        qa_confirmer,
        1,
        10000,
    )

    if template_content:
        # Use template
        doc = docx.Document(BytesIO(template_content))
        table = doc.tables[0]

        # Clear existing data rows (keep header)
        for i in range(len(table.rows) - 1, 0, -1):
            tr = table.rows[i]._tr
            table._tbl.remove(tr)

        # Add data rows
        for capa in capas:
            row = table.add_row()
            row.cells[0].text = capa.capa_code
            row.cells[1].text = capa.created_at.strftime("%Y.%m.%d") if capa.created_at else ""
            row.cells[2].text = capa.department or ""
            row.cells[3].text = capa.affected_product or ""
            row.cells[4].text = capa.source_code or ""
            row.cells[5].text = capa.title or ""
            row.cells[6].text = capa.evaluation_result or ""
            row.cells[7].text = capa.closure_date.strftime("%Y.%m.%d") if capa.closure_date else ""
            qa_info = ""
            if capa.qa_confirmer:
                qa_info = capa.qa_confirmer
                if capa.qa_confirm_date:
                    qa_info += capa.qa_confirm_date.strftime("%Y.%m.%d")
            row.cells[8].text = qa_info
    else:
        # Create new document
        doc = docx.Document()
        doc.add_heading("CAPA登记汇总表", level=1)
        table = doc.add_table(rows=1, cols=9)
        table.style = "Table Grid"

        # Header
        headers = ["CAPA编号", "启动日期", "事件部门", "涉及产品", "来源编号", "CAPA简述", "CAPA效果评估", "关闭日期", "QA质量员/日期"]
        for i, header in enumerate(headers):
            table.rows[0].cells[i].text = header

        # Data
        for capa in capas:
            row = table.add_row()
            row.cells[0].text = capa.capa_code
            row.cells[1].text = capa.created_at.strftime("%Y.%m.%d") if capa.created_at else ""
            row.cells[2].text = capa.department or ""
            row.cells[3].text = capa.affected_product or ""
            row.cells[4].text = capa.source_code or ""
            row.cells[5].text = capa.title or ""
            row.cells[6].text = capa.evaluation_result or ""
            row.cells[7].text = capa.closure_date.strftime("%Y.%m.%d") if capa.closure_date else ""
            qa_info = ""
            if capa.qa_confirmer:
                qa_info = capa.qa_confirmer
                if capa.qa_confirm_date:
                    qa_info += capa.qa_confirm_date.strftime("%Y.%m.%d")
            row.cells[8].text = qa_info

    output = BytesIO()
    doc.save(output)
    output.seek(0)
    return output.getvalue()


# ============ Deviation Import/Export (Word docx) ============

async def preview_deviation_import(
    db: AsyncSession,
    file_content: bytes,
) -> dict:
    """Preview Deviation import from Word docx."""
    import docx

    doc = docx.Document(BytesIO(file_content))
    if not doc.tables:
        return {"valid_rows": 0, "error_rows": [{"row_number": 0, "error_message": "文档中未找到表格"}], "total_rows": 0}

    table = doc.tables[0]
    headers = [_clean_text(cell.text) for cell in table.rows[0].cells]

    valid_rows = 0
    error_rows = []

    for row_idx, row in enumerate(table.rows[1:], start=2):
        row_data = {_clean_text(headers[i]): _clean_text(row.cells[i].text) for i in range(len(headers))}
        errors = []

        deviation_code = row_data.get("偏差编号", "")
        if not deviation_code:
            errors.append("偏差编号不能为空")
        else:
            exists = await repo.exists_by_deviation_code(db, deviation_code)
            if exists:
                errors.append(f"偏差编号已存在: {deviation_code}")

        if errors:
            error_rows.append({"row_number": row_idx, "error_message": "; ".join(errors), "row_data": row_data})
        else:
            valid_rows += 1

    return {"valid_rows": valid_rows, "error_rows": error_rows, "total_rows": valid_rows + len(error_rows)}


async def confirm_deviation_import(
    db: AsyncSession,
    file_content: bytes,
    skip_duplicates: bool = True,
    update_existing: bool = False,
) -> dict:
    """Confirm Deviation import from Word docx with deduplication."""
    import docx

    doc = docx.Document(BytesIO(file_content))
    if not doc.tables:
        return {"success_count": 0, "error_count": 1, "error_details": [{"row": 0, "error": "文档中未找到表格"}]}

    table = doc.tables[0]
    headers = [_clean_text(cell.text) for cell in table.rows[0].cells]

    success_count = 0
    skip_count = 0
    update_count = 0
    error_count = 0
    error_details = []

    for row_idx, row in enumerate(table.rows[1:], start=2):
        row_data = {_clean_text(headers[i]): _clean_text(row.cells[i].text) for i in range(len(headers))}
        try:
            deviation_code = row_data.get("偏差编号", "")
            if not deviation_code:
                error_count += 1
                error_details.append({"row": row_idx, "error": "偏差编号为空"})
                continue

            existing = await repo.get_deviation_by_code(db, deviation_code)
            if existing:
                if update_existing:
                    # Update existing record
                    product_batch = row_data.get("产品名称/批号", "")
                    parts = product_batch.split("\n") if product_batch else []
                    affected_items = parts[0].strip() if len(parts) > 0 else None
                    batch_number = parts[1].strip() if len(parts) > 1 else None

                    has_occurred_text = row_data.get("偏差是否曾发生", "")
                    has_occurred_before = None
                    if "否" in has_occurred_text and "是" not in has_occurred_text.replace("□是", ""):
                        has_occurred_before = False
                    elif "是" in has_occurred_text and "□" not in has_occurred_text:
                        has_occurred_before = True

                    level_text = row_data.get("偏差等级", "")
                    level_map = {"次要偏差": "minor", "中等偏差": "moderate", "严重偏差": "major"}
                    level = level_map.get(level_text, level_text.lower() if level_text else None)

                    update_data = {
                        "title": row_data.get("偏差简要描述", "")[:100] or deviation_code,
                        "department": row_data.get("事件部门", ""),
                        "description": row_data.get("偏差简要描述", ""),
                        "batch_number": batch_number,
                        "affected_items": affected_items,
                        "has_occurred_before": has_occurred_before,
                        "root_cause_analysis": row_data.get("根本原因", ""),
                        "level": level,
                        "corrective_actions": row_data.get("纠正预防措施", ""),
                        "material_disposition": row_data.get("产品/物料处理结果", ""),
                        "investigation_completed_at": _parse_date(row_data.get("调查完成时间", "")),
                    }
                    await repo.update_deviation(db, existing, update_data)
                    update_count += 1
                elif skip_duplicates:
                    skip_count += 1
                else:
                    error_count += 1
                    error_details.append({"row": row_idx, "error": f"偏差编号已存在: {deviation_code}"})
                continue

            # Parse 产品名称/批号
            product_batch = row_data.get("产品名称/批号", "")
            parts = product_batch.split("\n") if product_batch else []
            affected_items = parts[0].strip() if len(parts) > 0 else None
            batch_number = parts[1].strip() if len(parts) > 1 else None

            # Parse 偏差是否曾发生 (format: "□是 编号：\n否")
            has_occurred_text = row_data.get("偏差是否曾发生", "")
            has_occurred_before = None
            if "否" in has_occurred_text and "是" not in has_occurred_text.replace("□是", ""):
                has_occurred_before = False
            elif "是" in has_occurred_text and "□" not in has_occurred_text:
                has_occurred_before = True

            # Parse 偏差等级
            level_text = row_data.get("偏差等级", "")
            level_map = {"次要偏差": "minor", "中等偏差": "moderate", "严重偏差": "major"}
            level = level_map.get(level_text, level_text.lower() if level_text else None)

            data = {
                "deviation_code": deviation_code,
                "title": row_data.get("偏差简要描述", "")[:100] or deviation_code,
                "department": row_data.get("事件部门", ""),
                "description": row_data.get("偏差简要描述", ""),
                "batch_number": batch_number,
                "affected_items": affected_items,
                "has_occurred_before": has_occurred_before,
                "root_cause_analysis": row_data.get("根本原因", ""),
                "level": level,
                "corrective_actions": row_data.get("纠正预防措施", ""),
                "material_disposition": row_data.get("产品/物料处理结果", ""),
                "investigation_completed_at": _parse_date(row_data.get("调查完成时间", "")),
                "status": "draft",
            }

            await repo.create_deviation(db, data)
            success_count += 1
        except Exception as e:
            error_count += 1
            error_details.append({"row": row_idx, "error": str(e)})

    await db.commit()

    return {
        "success_count": success_count,
        "update_count": update_count,
        "skip_count": skip_count,
        "error_count": error_count,
        "error_details": error_details,
    }


async def export_deviations(
    db: AsyncSession,
    template_content: bytes | None = None,
    status: str | None = None,
    level: str | None = None,
    department: str | None = None,
    keyword: str | None = None,
) -> bytes:
    """Export Deviation data to Word docx, preserving template format."""
    import docx

    deviations, _ = await repo.get_deviations(db, status, level, department, keyword, None, 1, 10000)
    level_map = {"minor": "次要偏差", "moderate": "中等偏差", "major": "严重偏差"}

    if template_content:
        doc = docx.Document(BytesIO(template_content))
        table = doc.tables[0]

        # Clear existing data rows (keep header)
        for i in range(len(table.rows) - 1, 0, -1):
            tr = table.rows[i]._tr
            table._tbl.remove(tr)

        # Add data rows
        for idx, d in enumerate(deviations, start=1):
            row = table.add_row()
            row.cells[0].text = str(idx)
            row.cells[1].text = d.deviation_code
            product_batch = ""
            if d.affected_items and d.affected_items != "—":
                product_batch = d.affected_items
            if d.batch_number and d.batch_number != "—":
                product_batch += f"\n{d.batch_number}"
            row.cells[2].text = product_batch or "—"
            row.cells[3].text = d.description or d.title or ""
            # 偏差是否曾发生
            if d.has_occurred_before is True:
                row.cells[4].text = "是"
            elif d.has_occurred_before is False:
                row.cells[4].text = "□是 编号：\n否"
            else:
                row.cells[4].text = "□是 编号：\n否"
            row.cells[5].text = d.root_cause_analysis or ""
            row.cells[6].text = level_map.get(d.level, d.level or "")
            row.cells[7].text = d.investigation_completed_at.strftime("%Y.%m.%d") if d.investigation_completed_at else ""
            row.cells[8].text = d.corrective_actions or ""
            row.cells[9].text = d.material_disposition or "—"
            row.cells[10].text = "是" if d.status == "closed" else "否"
    else:
        doc = docx.Document()
        doc.add_heading("偏差登记表", level=1)
        table = doc.add_table(rows=1, cols=11)
        table.style = "Table Grid"

        headers = ["序号", "偏差编号", "产品名称/批号", "偏差简要描述", "偏差是否曾发生", "根本原因", "偏差等级", "调查完成时间", "纠正预防措施", "产品/物料处理结果", "是否关闭"]
        for i, header in enumerate(headers):
            table.rows[0].cells[i].text = header

        for idx, d in enumerate(deviations, start=1):
            row = table.add_row()
            row.cells[0].text = str(idx)
            row.cells[1].text = d.deviation_code
            product_batch = ""
            if d.affected_items and d.affected_items != "—":
                product_batch = d.affected_items
            if d.batch_number and d.batch_number != "—":
                product_batch += f"\n{d.batch_number}"
            row.cells[2].text = product_batch or "—"
            row.cells[3].text = d.description or d.title or ""
            if d.has_occurred_before is True:
                row.cells[4].text = "是"
            elif d.has_occurred_before is False:
                row.cells[4].text = "□是 编号：\n否"
            else:
                row.cells[4].text = "□是 编号：\n否"
            row.cells[5].text = d.root_cause_analysis or ""
            row.cells[6].text = level_map.get(d.level, d.level or "")
            row.cells[7].text = d.investigation_completed_at.strftime("%Y.%m.%d") if d.investigation_completed_at else ""
            row.cells[8].text = d.corrective_actions or ""
            row.cells[9].text = d.material_disposition or "—"
            row.cells[10].text = "是" if d.status == "closed" else "否"

    output = BytesIO()
    doc.save(output)
    output.seek(0)
    return output.getvalue()
