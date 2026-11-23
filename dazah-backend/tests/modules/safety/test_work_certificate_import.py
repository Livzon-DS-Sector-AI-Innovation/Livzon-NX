"""持证人员汇总表 Excel 导入测试：解析器单测 + API + 落库集成。

解析器为纯函数（不依赖数据库）；API 测试挂子 FastAPI 真实调路由；
集成测试走 db_session（独立测试库），覆盖首导与重复导入的
created/updated/unchanged 口径。
"""

from __future__ import annotations

import io
from collections.abc import AsyncIterator
from datetime import date
from typing import Any
from uuid import uuid4

import openpyxl
import pytest
import xlrd  # type: ignore[import-untyped]
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.safety.api.work_certificates import work_certificates_router
from app.modules.safety.models import SpecialWorkCertificate
from app.modules.safety.service.work_certificate_import import (
    match_sheet_rule,
    merge_records,
    normalize_department,
    parse_certificate_workbook,
    parse_date_cell,
    parse_sheet,
)
from app.platform.identity.models import User

_MARK = "CERTIMP"


def _xlsx_bytes(
    sheets: dict[str, list[list[Any]]],
    merges: dict[str, list[str]] | None = None,
) -> bytes:
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        ws = workbook.create_sheet(title=name)
        for r_idx, row in enumerate(rows, start=1):
            for c_idx, value in enumerate(row, start=1):
                if value is not None:
                    ws.cell(row=r_idx, column=c_idx, value=value)
        for rng in (merges or {}).get(name, []):
            ws.merge_cells(rng)
    buf = io.BytesIO()
    workbook.save(buf)
    return buf.getvalue()


# ── 解析器单测 ──


def test_match_sheet_rules_cover_summary_tabs() -> None:
    """13 个子表名映射到正确类别；特种设备管理人员优先于管理人员命中。"""
    expected = {
        "管理人员": "hazmat_safety_manager",
        "电焊": "welding_cutting",
        "高处": "high_altitude_maintenance",
        "受限空间": "confined_space",
        "电工（高）": "electrician",
        "电工（低）": "electrician",
        "仪表": "instrument",
        "司炉工": "boiler_operator",
        "水质化验": "water_quality_analyst",
        "叉车": "forklift",
        "压力容器": "pressure_vessel",
        "特种设备管理人员（A证)": "special_equipment_management",
        "起重": "crane_operator",
    }
    for name, category in expected.items():
        rule = match_sheet_rule(name)
        assert rule is not None, name
        assert rule.category == category, name
    high = match_sheet_rule("电工（高）")
    assert high is not None and high.default_scope == "高压电工作业"
    low = match_sheet_rule("电工（低）")
    assert low is not None and low.default_scope == "低压电工作业"
    assert match_sheet_rule("说明页") is None


def test_match_sheet_rule_label_exact() -> None:
    """类别中文 label（导出子表名）精确命中，优先于关键词规则。"""
    expected = {
        "焊接与热切割作业": "welding_cutting",
        "电工作业": "electrician",
        # 「起重司索工」label 若走关键词会被「起重」误判为起重机司机
        "起重司索工": "lifting_rigging",
        "锅炉作业（司炉工）": "boiler_operator",
        # 全/半角括号差异容错
        "锅炉作业(司炉工)": "boiler_operator",
        "特种设备安全管理（A证）": "special_equipment_management",
    }
    for name, category in expected.items():
        rule = match_sheet_rule(name)
        assert rule is not None, name
        assert rule.category == category, name
    # 带「人员」的原表名不等于 label，仍走关键词路径
    legacy = match_sheet_rule("特种设备管理人员（A证)")
    assert legacy is not None
    assert legacy.category == "special_equipment_management"


def test_normalize_department_rules() -> None:
    """车间名称归一化：数字简写补全/括号变体/机修统一/原样保留。"""
    cases: list[tuple[str | None, str | None, bool]] = [
        # 数字简写补全（含数字型单元格转成的文本）
        ("103", "103车间", True),
        ("101", "101车间", True),
        ("201一", "201一车间", True),
        ("201二", "201二车间", True),
        ("203", "203车间", True),
        # 代码式（equipment 车间编码风格）
        ("201-1", "201一车间", True),
        ("201—2", "201二车间", True),
        # 括号内容是车间区分标识，保留并补「车间」（括号统一全角）
        ("201二（多拉）", "201二车间（多拉）", True),
        ("201二(多拉)", "201二车间（多拉）", True),
        ("201二车间（多拉）", "201二车间（多拉）", False),
        # 机修前缀统一
        ("机修工", "机修", True),
        ("机修班长", "机修", True),
        ("机修班组", "机修", True),
        # 已是标准写法不变
        ("101车间", "101车间", False),
        ("101二车间", "101二车间", False),
        ("201一车间", "201一车间", False),
        ("201车间", "201车间", False),
        ("机修", "机修", False),
        # 非车间部门原样保留（仅去空白，不算变化）
        (" 动力科 ", "动力科", False),
        ("热动站", "热动站", False),
        ("QC", "QC", False),
        ("污水处理", "污水处理", False),
        ("102预混剂", "102预混剂", False),
        ("生产管理部", "生产管理部", False),
        # 空值
        (None, None, False),
        ("", None, False),
        (" ", None, False),
    ]
    for raw, expected, changed in cases:
        assert normalize_department(raw) == (expected, changed), raw


def test_parse_date_cell_variants() -> None:
    assert parse_date_cell("2025.11.26", month_end=True) == date(2025, 11, 26)
    assert parse_date_cell("2013.7.12", month_end=False) == date(2013, 7, 12)
    assert parse_date_cell("2022..09.02", month_end=False) == date(2022, 9, 2)
    assert parse_date_cell("2017.05.", month_end=False) == date(2017, 5, 1)
    # 月精度：issue 取月初、expiry 取月末
    assert parse_date_cell("2028.05", month_end=False) == date(2028, 5, 1)
    assert parse_date_cell("2028.05", month_end=True) == date(2028, 5, 31)
    assert parse_date_cell("2028.12", month_end=True) == date(2028, 12, 31)
    # 区间取截止端
    assert parse_date_cell("2025.11.26-2028.11.25", month_end=True) == date(
        2028, 11, 25
    )
    # Excel 串行数（41410 = 2013-05-01）
    assert parse_date_cell(41410, month_end=False) == (
        xlrd.xldate_as_datetime(41410, 0).date()
    )
    # 误存为小数的 "YYYY.MM"（源台账数字单元格），与串行日期以 10000 分界
    assert parse_date_cell(2022.08, month_end=False) == date(2022, 8, 1)
    assert parse_date_cell(2026.07, month_end=True) == date(2026, 7, 31)
    assert parse_date_cell(2017.0, month_end=False) == date(2017, 1, 1)
    assert parse_date_cell(2017.0, month_end=True) == date(2017, 12, 31)
    # openpyxl 真实日期单元格
    assert parse_date_cell(date(2029, 2, 12), month_end=True) == date(2029, 2, 12)
    # 空值与占位符
    assert parse_date_cell(None, month_end=True) is None
    assert parse_date_cell("-", month_end=True) is None
    assert parse_date_cell("abc", month_end=True) is None


def _ledger_sheets() -> dict[str, list[list[Any]]]:
    return {
        "电焊": [
            ["2026年焊接与热切割作业"],
            [
                "编号",
                "姓名",
                "车间",
                "岗位",
                "入职日期",
                "初领日期",
                "有效日期",
                "证书编号",
                "复审日期",
                "备注",
                "学历",
            ],
            [
                1,
                f"{_MARK}吴义龙",
                "101",
                "机修",
                "2013.07.12",
                "2019.12.09",
                "2029.02.12",
                "T640202197008161234",
                "2029.02",
                "公司",
                "高中",
            ],
            [
                2,
                f"{_MARK}丁金虎",
                "",
                "",
                "2013.07.12",
                "2020.01.17",
                "2032.02.11",
                "T640221198210232345",
                "2032.02",
                "公司",
                "高中",
            ],
            [3, None, "", "", "", "", "", "", "", "", ""],
            ["", "合计", "", "", "", "", "", "", "", "", ""],
        ],
        "电工（高）": [
            ["2026年高压电工操作证统计表"],
            [
                "序号",
                "姓名",
                "入职日期",
                "有效日期",
                "发证日期",
                "高压证书编号",
                "复审",
                "学历",
                "备注",
            ],
            [
                1,
                f"{_MARK}林宗伟",
                "2012.05.04",
                "2028.08.11",
                "2016.07.13",
                "T150102198310122345",
                "2028.08",
                "大专",
                "公司",
            ],
        ],
        "电工（低）": [
            ["2026年低压电工操作证统计表"],
            [
                "序号",
                "姓名",
                "入职日期",
                "有效日期",
                "发证日期",
                "低压证书编号",
                "复审",
                "备注",
                "学历",
            ],
            [
                1,
                f"{_MARK}林宗伟",
                "2012.05.04",
                "2030.01.09",
                "2016.08.20",
                "T150102198310122345",
                "2030.01",
                "公司",
                "大专",
            ],
        ],
        "管理人员": [
            ["2026年持证人员汇总表"],
            [
                "序号",
                "从业类别",
                "证件类型",
                "姓名",
                "学历",
                "职位",
                "领证日期",
                "复审日期",
                "有效期",
                "继续再教育时间",
                "电话",
                "身份证号",
                "专业",
            ],
            [
                1,
                "主要负责人",
                "危化生产",
                f"{_MARK}史润",
                "本科",
                "副总经理",
                "2025.11.26",
                "2028.11.25",
                "2025.11.26-2028.11.25",
                "2026.11.26",
                "133",
                "1426",
                "生物科学",
            ],
        ],
        "设备说明": [["这是一个无关子表"], ["内容"]],
    }


def test_parse_certificate_workbook_sheets() -> None:
    preview = parse_certificate_workbook(
        _xlsx_bytes(_ledger_sheets()), "2026年持证人员汇总表.xlsx"
    )
    by_sheet = {sheet["sheet"]: sheet for sheet in preview["sheets"]}
    # 未识别子表进入 skipped
    assert preview["skipped_sheets"] == [
        {"sheet": "设备说明", "reason": "未识别的子表"}
    ]
    assert by_sheet["电焊"]["certificate_category"] == "welding_cutting"
    assert by_sheet["电焊"]["row_count"] == 2  # 空行与合计行跳过
    assert by_sheet["管理人员"]["certificate_category"] == "hazmat_safety_manager"
    sample = by_sheet["管理人员"]["sample"][0]
    assert sample["person_name"] == f"{_MARK}史润"
    assert sample["expiry_date"] == "2028-11-25"
    assert sample["qualification_scope"] == "主要负责人 危化生产"


def test_parse_sheet_normalizes_department() -> None:
    """车间列归一化写入 department，原始写法变化时记入备注留痕。"""
    sheets = {
        "叉车": [
            ["2026年叉车作业操作证统计表"],
            ["编号", "姓名", "车间", "取证日期", "有效日期", "证书编号"],
            [1, f"{_MARK}马学忠", "201一（多拉）", "2021.12", "2029.11", "6402211"],
            [2, f"{_MARK}热动站工", " 热动站 ", "2021.12", "2029.11", "6402212"],
        ]
    }
    result = parse_sheet(
        _build_matrix("叉车", sheets["叉车"]), match_sheet_rule("叉车")
    )
    # 括号内容（多拉）是车间区分标识，保留
    assert result.records[0].department == "201一车间（多拉）"
    assert result.records[0].remark
    assert "车间原值201一（多拉）" in result.records[0].remark
    # 原样保留的部门：去空白即可，不记备注
    assert result.records[1].department == "热动站"
    assert not result.records[1].remark


def test_parse_sheet_expiry_error_row() -> None:
    sheets = {
        "叉车": [
            ["2026年叉车作业操作证统计表"],
            [
                "编号",
                "姓名",
                "车间",
                "技能证书",
                "入职日期",
                "取证日期",
                "有效日期",
                "聘用起止日期",
                "等级",
                "证书编号",
                "学历",
            ],
            [
                1,
                f"{_MARK}马学忠",
                "101车间",
                "叉车作业操作证",
                "2018.08.01",
                "2021.12",
                "2029.11",
                "2021.12.31-2029.11.30",
                "N1",
                "640221199107233456",
                "高中",
            ],
            [2, f"{_MARK}坏行", "", "", "", "2020.08", "未知日期", "", "", "", ""],
        ]
    }
    result = parse_sheet(
        _build_matrix("叉车", sheets["叉车"]), match_sheet_rule("叉车")
    )
    assert len(result.records) == 1
    record = result.records[0]
    assert record.qualification_scope == "叉车作业操作证、N1"
    assert record.expiry_date == date(2029, 11, 30)  # 月精度取月末
    assert result.errors == [{"row": 4, "reason": "有效日期无法解析：未知日期，已跳过"}]


def _build_matrix(name: str, rows: list[list[Any]]):  # noqa: ANN202
    from app.modules.safety.service.hazard_ledger_import import _build_matrix

    return _build_matrix(name, rows, [])


def test_merge_records_electrician_high_low() -> None:
    """高低压电工同证号合并：scope 并集、有效期取早、差异记备注。"""
    sheets = _ledger_sheets()
    high = parse_sheet(
        _build_matrix("电工（高）", sheets["电工（高）"]),
        match_sheet_rule("电工（高）"),
    )
    low = parse_sheet(
        _build_matrix("电工（低）", sheets["电工（低）"]),
        match_sheet_rule("电工（低）"),
    )
    merged = merge_records(high.records + low.records)
    assert len(merged) == 1
    record = merged[0]
    assert record.certificate_category == "electrician"
    assert record.qualification_scope == "高压电工作业、低压电工作业"
    assert record.expiry_date == date(2028, 8, 11)  # 取更早值
    assert record.remark and "2030-01-09" in record.remark  # 晚证号期记备注


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
    application.include_router(work_certificates_router, prefix="/api/v1/safety")
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
            select(SpecialWorkCertificate.id).where(
                SpecialWorkCertificate.person_name.like(f"{_MARK}%")
            )
        )
    )
    if ids:
        await db.execute(
            delete(SpecialWorkCertificate).where(SpecialWorkCertificate.id.in_(ids))
        )
    await db.commit()


async def test_import_parse_and_commit_flow(
    import_client: AsyncClient, db_session: AsyncSession
) -> None:
    try:
        content = _xlsx_bytes(_ledger_sheets())
        parse_res = await import_client.post(
            "/api/v1/safety/work-certificates/import/parse",
            files={
                "file": (
                    "2026年持证人员汇总表.xlsx",
                    content,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert parse_res.status_code == 200
        preview = parse_res.json()["data"]
        assert {sheet["sheet"] for sheet in preview["sheets"]} == {
            "电焊",
            "电工（高）",
            "电工（低）",
            "管理人员",
        }
        assert preview["skipped_sheets"] == [
            {"sheet": "设备说明", "reason": "未识别的子表"}
        ]

        import_res = await import_client.post(
            "/api/v1/safety/work-certificates/import",
            files={
                "file": (
                    "2026年持证人员汇总表.xlsx",
                    content,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            data={"sheets": "[]"},  # 空数组 = 导入全部可识别子表
        )
        assert import_res.status_code == 200
        result = import_res.json()["data"]
        # 电工高低合并 → 2(焊) + 1(合并电工) + 1(管理) = 4
        assert result["created"] == 4
        assert result["total_parsed"] == 4

        rows = list(
            await db_session.scalars(
                select(SpecialWorkCertificate).where(
                    SpecialWorkCertificate.person_name.like(f"{_MARK}%")
                )
            )
        )
        assert len(rows) == 4
        electrician = next(
            row for row in rows if row.certificate_category == "electrician"
        )
        assert electrician.certificate_no == "T150102198310122345"
        assert electrician.expiry_date == date(2028, 8, 11)

        # 重复导入同一文件：全部命中已有记录且无变化
        re_import = await import_client.post(
            "/api/v1/safety/work-certificates/import",
            files={
                "file": (
                    "2026年持证人员汇总表.xlsx",
                    content,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert re_import.status_code == 200
        re_result = re_import.json()["data"]
        assert re_result["created"] == 0
        assert re_result["unchanged"] == 4
    finally:
        await _cleanup_imported(db_session)


async def test_import_updates_changed_expiry(
    import_client: AsyncClient, db_session: AsyncSession
) -> None:
    try:
        sheets = _ledger_sheets()
        content = _xlsx_bytes(sheets)
        first = await import_client.post(
            "/api/v1/safety/work-certificates/import",
            files={"file": ("ledger.xlsx", content, "application/octet-stream")},
        )
        assert first.status_code == 200
        assert first.json()["data"]["created"] == 4

        # 台账复审换证：电焊第一条有效期延长 → 走更新而非新建
        sheets["电焊"][2][6] = "2033.02.12"
        updated_content = _xlsx_bytes(sheets)
        second = await import_client.post(
            "/api/v1/safety/work-certificates/import",
            files={
                "file": ("ledger.xlsx", updated_content, "application/octet-stream")
            },
        )
        assert second.status_code == 200
        result = second.json()["data"]
        assert result["created"] == 0
        assert result["updated"] == 1

        row = await db_session.scalar(
            select(SpecialWorkCertificate).where(
                SpecialWorkCertificate.certificate_no == "T640202197008161234"
            )
        )
        assert row is not None
        assert row.expiry_date == date(2033, 2, 12)
        assert row.status == "valid"
    finally:
        await _cleanup_imported(db_session)


async def test_create_conflict_only_within_category(
    import_client: AsyncClient, db_session: AsyncSession
) -> None:
    """同一证件号在不同类别下允许共存（复合唯一口径）。"""
    payload = {
        "person_name": f"{_MARK}跨类别{uuid4().hex[:6]}",
        "certificate_category": "electrician",
        "certificate_no": f"T{uuid4().hex[:12].upper()}",
    }
    try:
        first = await import_client.post(
            "/api/v1/safety/work-certificates", json=payload
        )
        assert first.status_code == 200

        same_category = await import_client.post(
            "/api/v1/safety/work-certificates",
            json={**payload, "person_name": f"{_MARK}同类别{uuid4().hex[:6]}"},
        )
        assert same_category.status_code == 409

        other_category = await import_client.post(
            "/api/v1/safety/work-certificates",
            json={
                **payload,
                "certificate_category": "welding_cutting",
                "person_name": f"{_MARK}异类别{uuid4().hex[:6]}",
            },
        )
        assert other_category.status_code == 200
    finally:
        await _cleanup_imported(db_session)


async def test_export_workbook_roundtrip(
    import_client: AsyncClient, db_session: AsyncSession
) -> None:
    """导出按类别分表（sheet 名=类别 label）→ 导出文件可直接再导入闭环。"""
    try:
        content = _xlsx_bytes(_ledger_sheets())
        import_res = await import_client.post(
            "/api/v1/safety/work-certificates/import",
            files={
                "file": (
                    "2026年持证人员汇总表.xlsx",
                    content,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert import_res.status_code == 200
        assert import_res.json()["data"]["created"] == 4

        export_res = await import_client.get("/api/v1/safety/work-certificates/export")
        assert export_res.status_code == 200
        assert export_res.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert "attachment" in export_res.headers.get("content-disposition", "")

        workbook = openpyxl.load_workbook(io.BytesIO(export_res.content))
        # 子表名 = 类别中文 label；断言按本测试数据过滤（全量导出
        # 可能同时含测试库中其他并存数据）
        sheetnames = set(workbook.sheetnames)
        assert {
            "焊接与热切割作业",
            "电工作业",
            "危化品安全管理人员",
        } <= sheetnames
        welding = workbook["焊接与热切割作业"]
        header = [cell.value for cell in welding[2]]
        assert header[:5] == ["姓名", "车间", "证书编号", "取证日期", "有效日期"]

        def _my_rows(sheet_name: str) -> list[Any]:
            return [
                row
                for row in workbook[sheet_name].iter_rows(min_row=3, values_only=True)
                if row[0] and str(row[0]).startswith(_MARK)
            ]

        welding_rows = _my_rows("焊接与热切割作业")
        assert len(welding_rows) == 2
        # 数字简写「101」导入时已归一，导出为标准车间名
        assert welding_rows[0][1] == "101车间"
        electrician_rows = _my_rows("电工作业")
        assert len(electrician_rows) == 1  # 高低压电工合并为一条

        # 回导：label 子表名精确命中类别，库内数据与导出一致不新建
        reimport = await import_client.post(
            "/api/v1/safety/work-certificates/import",
            files={
                "file": (
                    "持证人员汇总表_20260101.xlsx",
                    export_res.content,
                    "application/octet-stream",
                )
            },
        )
        assert reimport.status_code == 200
        result = reimport.json()["data"]
        assert result["created"] == 0
        assert result["updated"] == 0
        assert result["unchanged"] >= 4
        assert result["row_errors"] == []

        rows = list(
            await db_session.scalars(
                select(SpecialWorkCertificate).where(
                    SpecialWorkCertificate.person_name.like(f"{_MARK}%")
                )
            )
        )
        assert len(rows) == 4  # 回导未产生重复
    finally:
        await _cleanup_imported(db_session)
