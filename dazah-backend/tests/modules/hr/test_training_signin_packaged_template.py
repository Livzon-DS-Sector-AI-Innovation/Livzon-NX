from datetime import date
from pathlib import Path

import pytest
from docx import Document

from app.modules.hr.schemas import TrainingSignInSheetInput
from app.modules.hr.signin_document_generator import generate_training_sign_in_sheet


@pytest.mark.parametrize(("attendee_count", "page_count"), [(11, 1), (43, 2)])
def test_signin_exports_using_packaged_template(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    attendee_count: int,
    page_count: int,
) -> None:
    monkeypatch.chdir(tmp_path)
    attendees = [f"测试学员{i:02d}" for i in range(1, attendee_count + 1)]
    payload = TrainingSignInSheetInput(
        training_date=date(2026, 8, 20),
        department="质量部",
        topic="签到表导出验证",
        employee_names=attendees,
        employee_dept_map=dict.fromkeys(attendees, "质量部"),
    )

    exported = Document(generate_training_sign_in_sheet(payload))

    assert len(exported.tables) == page_count
    assert exported.tables[0].rows[4].cells[2].text == payload.topic
    cells = {
        cell.text
        for table in exported.tables
        for row in table.rows
        for cell in row.cells
    }
    assert set(attendees) <= cells
