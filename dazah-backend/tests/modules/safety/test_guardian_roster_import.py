"""监护人名单 Excel 导入与 API 测试：解析器单测 + API + 落库集成。

解析器为纯函数（不依赖数据库）；API 测试挂子 FastAPI 真实调路由；
集成测试走 db_session（独立测试库），覆盖整表替换口径与增删改/导出。
"""

from __future__ import annotations

import io
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any
from uuid import uuid4

import openpyxl
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.safety.api.guardian_roster import guardian_roster_router
from app.modules.safety.models import GuardianRoster
from app.modules.safety.service.guardian_roster_import import (
    ParsedGuardian,
    _parse_exam_date,
    merge_records,
    parse_guardian_workbook,
    parse_sheet,
)
from app.platform.identity.models import User

_MARK = "GRIMP"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_HEADER = [
    "姓名",
    "联系电话",
    "部门",
    "岗位",
    "分数",
    "题目数量",
    "考试名称",
    "考试时长",
    "考试时间",
]


def _xlsx_bytes(sheets: dict[str, list[list[Any]]]) -> bytes:
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        ws = workbook.create_sheet(title=name)
        for r_idx, row in enumerate(rows, start=1):
            for c_idx, value in enumerate(row, start=1):
                if value is not None:
                    ws.cell(row=r_idx, column=c_idx, value=value)
    buf = io.BytesIO()
    workbook.save(buf)
    return buf.getvalue()


def _guardian_sheets() -> dict[str, list[list[Any]]]:
    """贴近真实《监护人考试合格名单》的工作簿：汇总 + 按车间分表。"""
    return {
        "汇总": [
            list(_HEADER),
            ["101（102）车间"],  # 车间分组标题行
            [
                f"{_MARK}吴鹏",
                17795224747,
                "101/102车间",
                "消毒",
                85,
                50,
                "监护人考试2",
                379,
                "2026-10-22 00:00:00",
            ],
            [
                f"{_MARK}徐明",
                "13995428112",
                "101/102车间",
                "消毒",
                88,
                50,
                "监护人考试",
                701,
                "2026-10-22 00:00:00",
            ],
            ["103车间"],
            [
                f"{_MARK}马银鹏",
                13519510120,
                "103车间",
                "消毒",
                80,
                50,
                "监护人考试",
                796,
                "2026-10-22 00:00:00",
            ],
            [None] * 9,  # 整行空
            ["制表：安全部", None, None, None, None, None, None, None, None],
        ],
        "101（102）": [
            list(_HEADER),
            [
                f"{_MARK}吴鹏",
                17795224747.0,
                "101/102车间",
                "消毒",
                92,
                50,
                "监护人考试",
                608,
                datetime(2026, 10, 29, 9, 30),
            ],
            [
                f"{_MARK}缺部门",
                13800000000,
                None,
                "消毒",
                88,
                50,
                "监护人考试",
                100,
                "2026-10-22 00:00:00",
            ],
        ],
    }


def _build_matrix(name: str, rows: list[list[Any]]):  # noqa: ANN202
    from app.modules.safety.service.hazard_ledger_import import _build_matrix

    return _build_matrix(name, rows, [])


# ── 解析器单测 ──


def test_parse_sheet_skips_group_and_footer_rows() -> None:
    """车间分组标题行、空行、制表行静默跳过；缺车间列记错误行。"""
    sheets = _guardian_sheets()
    result = parse_sheet(_build_matrix("汇总", sheets["汇总"]))
    assert [item.person_name for item in result.records] == [
        f"{_MARK}吴鹏",
        f"{_MARK}徐明",
        f"{_MARK}马银鹏",
    ]
    record = result.records[0]
    assert record.workshop == "101/102车间"
    assert record.phone == "17795224747"  # 数字电话转文本
    assert record.position == "消毒"
    assert record.score == 85
    assert record.exam_name == "监护人考试2"
    assert record.exam_date == date(2026, 10, 22)  # 文本日期时间
    assert not result.errors

    sub = parse_sheet(_build_matrix("101（102）", sheets["101（102）"]))
    assert [item.person_name for item in sub.records] == [f"{_MARK}吴鹏"]
    assert sub.records[0].phone == "17795224747"  # 浮点整数值电话
    assert sub.records[0].exam_date == date(2026, 10, 29)  # datetime 实例
    assert sub.errors == [{"row": 3, "reason": "缺少车间/部门，已跳过"}]


def test_parse_sheet_header_variants() -> None:
    """表头别名（车间/部门、成绩、手机）与标题行偏移均能识别。"""
    rows = [
        ["2026年10月监护人考试合格名单"],
        ["车间", "姓名", "成绩", "手机号", "考试日期", "备注"],
        [
            "203车间",
            f"{_MARK}李发铎",
            86,
            "15349566059",
            "2026/10/22",
            "班长",
        ],
    ]
    result = parse_sheet(_build_matrix("表单", rows))
    assert len(result.records) == 1
    record = result.records[0]
    assert record.workshop == "203车间"
    assert record.score == 86
    assert record.phone == "15349566059"
    assert record.exam_date == date(2026, 10, 22)
    assert record.remark == "班长"


def test_parse_sheet_skips_merged_group_title_rows() -> None:
    """汇总表分组标题跨列合并展开后整行同文本，不得解析成人员；
    「103车间」也不得被提取出假分数 103。"""
    from app.modules.safety.service.hazard_ledger_import import _build_matrix

    rows = [
        list(_HEADER),
        ["103车间"] + [None] * 8,
        [
            f"{_MARK}马银鹏",
            13519510120,
            "103车间",
            "消毒",
            80,
            50,
            "监护人考试",
            796,
            "2026-10-22 00:00:00",
        ],
    ]
    # 真实《汇总》子表的标题行是 A:I 跨列合并（_build_matrix 用 1-based 四元组）
    matrix = _build_matrix("汇总", rows, [(2, 1, 2, 9)])
    result = parse_sheet(matrix)
    assert [item.person_name for item in result.records] == [f"{_MARK}马银鹏"]
    assert not result.errors


def test_parse_score_rejects_partial_digit_text() -> None:
    from app.modules.safety.service.guardian_roster_import import _parse_score

    assert _parse_score("103车间") is None
    assert _parse_score("85") == 85
    assert _parse_score("85分") == 85
    assert _parse_score(85) == 85
    assert _parse_score("缺考") is None
    assert _parse_score(1500) is None


def test_parse_exam_date_variants() -> None:
    assert _parse_exam_date("2026-10-22 00:00:00") == date(2026, 10, 22)
    assert _parse_exam_date("2026/10/22") == date(2026, 10, 22)
    assert _parse_exam_date("2026年10月22日") == date(2026, 10, 22)
    assert _parse_exam_date("2026.10.22") == date(2026, 10, 22)
    assert _parse_exam_date(datetime(2026, 10, 22, 9, 30)) == (date(2026, 10, 22))
    assert _parse_exam_date("") is None
    assert _parse_exam_date("未参加") is None


def test_merge_records_by_name_and_phone() -> None:
    """同名不同电话是两个人；同姓名电话跨子表合并取最新一次考试。"""
    sheets = _guardian_sheets()
    summary = parse_sheet(_build_matrix("汇总", sheets["汇总"]))
    sub = parse_sheet(_build_matrix("101（102）", sheets["101（102）"]))
    merged, duplicates = merge_records(summary.records + sub.records)
    names = [item.person_name for item in merged]
    assert names == [f"{_MARK}吴鹏", f"{_MARK}徐明", f"{_MARK}马银鹏"]
    assert duplicates == 1  # 吴鹏在汇总与分表重复
    wu = merged[0]
    # 最新考试（10-29）覆盖汇总里的 10-22 场次
    assert wu.exam_date == date(2026, 10, 29)
    assert wu.score == 92
    assert wu.exam_name == "监护人考试"

    other_phone = ParsedGuardian(
        sheet="汇总",
        row_index=99,
        person_name=f"{_MARK}吴鹏",
        workshop="103车间",
        phone="13900000000",
    )
    merged2, duplicates2 = merge_records(summary.records + [other_phone])
    assert duplicates2 == 0  # 不同电话不合并
    assert len(merged2) == 4


def test_parse_workbook_default_selects_summary_sheet() -> None:
    data = parse_guardian_workbook(
        _xlsx_bytes(_guardian_sheets()), "2026年10月监护人考试合格名单.xlsx"
    )
    by_sheet = {sheet["sheet"]: sheet for sheet in data["sheets"]}
    assert by_sheet["汇总"]["default_selected"] is True
    assert by_sheet["汇总"]["row_count"] == 3
    assert by_sheet["101（102）"]["default_selected"] is False
    assert by_sheet["汇总"]["workshops"] == ["101/102车间", "103车间"]


# ── API + 落库集成 ──


@pytest.fixture
async def import_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid4(),
        name=f"{_MARK}用户{uuid4().hex[:8]}",
        role="user",
        status="active",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def import_client(
    db_session: AsyncSession,
    import_user: User,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.chdir(tmp_path)  # 导入存档写到临时目录
    application = FastAPI()
    application.include_router(guardian_roster_router, prefix="/api/v1/safety")
    application.dependency_overrides[get_current_user] = lambda: import_user

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    application.dependency_overrides.pop(get_db, None)


async def _cleanup_imported(db: AsyncSession) -> None:
    ids = list(
        await db.scalars(
            select(GuardianRoster.id).where(
                GuardianRoster.person_name.like(f"{_MARK}%")
            )
        )
    )
    if ids:
        await db.execute(delete(GuardianRoster).where(GuardianRoster.id.in_(ids)))
    await db.commit()


async def test_import_parse_and_commit_replace_flow(
    import_client: AsyncClient, db_session: AsyncSession
) -> None:
    try:
        content = _xlsx_bytes(_guardian_sheets())
        files = {
            "file": (
                "2026年10月监护人考试合格名单.xlsx",
                content,
                _XLSX_MIME,
            )
        }
        parse_res = await import_client.post(
            "/api/v1/safety/guardian-roster/import/parse", files=files
        )
        assert parse_res.status_code == 200
        preview = parse_res.json()["data"]
        assert {sheet["sheet"] for sheet in preview["sheets"]} == {
            "汇总",
            "101（102）",
        }
        assert preview["current_total"] == 0
        assert preview["merged_total"] == 3  # 吴鹏跨表合并

        import_res = await import_client.post(
            "/api/v1/safety/guardian-roster/import",
            files=files,
            data={"sheets": '["汇总"]'},
        )
        assert import_res.status_code == 200
        result = import_res.json()["data"]
        assert result["imported"] == 3
        assert result["replaced"] == 0

        list_res = await import_client.get("/api/v1/safety/guardian-roster")
        assert list_res.status_code == 200
        data = list_res.json()["data"]
        assert data["total"] == 3
        assert data["workshops"] == [
            {"workshop": "101/102车间", "count": 2},
            {"workshop": "103车间", "count": 1},
        ]

        # 再次导入：以最新导入为准，整表替换
        import_again = await import_client.post(
            "/api/v1/safety/guardian-roster/import",
            files=files,
            data={"sheets": '["汇总"]'},
        )
        assert import_again.status_code == 200
        again = import_again.json()["data"]
        assert again["replaced"] == 3
        assert again["imported"] == 3

        final = await import_client.get("/api/v1/safety/guardian-roster")
        assert final.json()["data"]["total"] == 3  # 旧行已软删
    finally:
        await _cleanup_imported(db_session)


async def test_crud_and_export_flow(
    import_client: AsyncClient, db_session: AsyncSession
) -> None:
    try:
        create_res = await import_client.post(
            "/api/v1/safety/guardian-roster",
            json={
                "person_name": f"{_MARK}手工新增",
                "workshop": "203车间",
                "phone": "13800001234",
                "position": "机修",
                "exam_date": "2026-11-01",
            },
        )
        assert create_res.status_code == 200
        guardian_id = create_res.json()["data"]["id"]

        update_res = await import_client.put(
            f"/api/v1/safety/guardian-roster/{guardian_id}",
            json={"position": "班长", "remark": "岗位调整"},
        )
        assert update_res.status_code == 200
        assert update_res.json()["data"]["position"] == "班长"

        keyword_res = await import_client.get(
            "/api/v1/safety/guardian-roster",
            params={"keyword": "手工新增"},
        )
        assert keyword_res.status_code == 200
        assert keyword_res.json()["data"]["total"] == 1

        workshop_res = await import_client.get(
            "/api/v1/safety/guardian-roster",
            params={"workshop": "101车间"},
        )
        assert workshop_res.json()["data"]["total"] == 0

        export_res = await import_client.get(
            "/api/v1/safety/guardian-roster/export",
            params={"workshop": "203车间"},
        )
        assert export_res.status_code == 200
        assert export_res.headers["content-type"] == _XLSX_MIME
        assert "attachment" in export_res.headers["content-disposition"]
        workbook = openpyxl.load_workbook(io.BytesIO(export_res.content))
        sheet = workbook.active
        assert [cell.value for cell in sheet[1][:4]] == [
            "姓名",
            "车间/部门",
            "联系电话",
            "岗位",
        ]
        rows = [[cell.value for cell in row] for row in sheet.iter_rows(min_row=2)]
        assert len(rows) == 1
        assert rows[0][:4] == [
            f"{_MARK}手工新增",
            "203车间",
            "13800001234",
            "班长",
        ]
        assert rows[0][7] == "岗位调整"

        delete_res = await import_client.delete(
            f"/api/v1/safety/guardian-roster/{guardian_id}"
        )
        assert delete_res.status_code == 200
        after = await import_client.get("/api/v1/safety/guardian-roster")
        assert after.json()["data"]["total"] == 0
    finally:
        await _cleanup_imported(db_session)


async def test_import_rejects_bad_sheets_param(
    import_client: AsyncClient,
) -> None:
    content = _xlsx_bytes(_guardian_sheets())
    res = await import_client.post(
        "/api/v1/safety/guardian-roster/import",
        files={
            "file": (
                "2026年10月监护人考试合格名单.xlsx",
                content,
                _XLSX_MIME,
            )
        },
        data={"sheets": "not-json"},
    )
    assert res.status_code == 400
