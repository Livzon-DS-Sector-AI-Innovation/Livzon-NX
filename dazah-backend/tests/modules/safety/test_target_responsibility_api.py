"""责任书签订台账与责任制季度考核 API 路由测试（真实服务 + 独立测试库）。"""

import io
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.safety.api.targets import safety_targets_router
from app.modules.safety.models import (
    SafetyDutyAssessment,
    SafetyDutyAssessmentItem,
    SafetyTargetAgreement,
)
from app.platform.identity.models import User

_AGREEMENT_DEPT_PREFIX = "测试责任书部门-"
_ASSESSMENT_DEPT_PREFIX = "测试考核部门-"
_XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid4(), name=f"责任制测试{uuid4().hex[:8]}", role="user", status="active"
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def sub_app(test_user: User) -> FastAPI:
    application = FastAPI()
    application.include_router(safety_targets_router, prefix="/api/v1/safety")
    application.dependency_overrides[get_current_user] = lambda: test_user
    return application


@pytest.fixture
async def client(
    sub_app: FastAPI, db_session: AsyncSession
) -> AsyncIterator[AsyncClient]:
    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    sub_app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=sub_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    sub_app.dependency_overrides.pop(get_db, None)


async def _cleanup(db: AsyncSession) -> None:
    await db.execute(
        delete(SafetyDutyAssessmentItem).where(
            SafetyDutyAssessmentItem.assessment_id.in_(
                select(SafetyDutyAssessment.id).where(
                    SafetyDutyAssessment.department.like(
                        f"{_ASSESSMENT_DEPT_PREFIX}%"
                    )
                )
            )
        )
    )
    await db.execute(
        delete(SafetyDutyAssessment).where(
            SafetyDutyAssessment.department.like(f"{_ASSESSMENT_DEPT_PREFIX}%")
        )
    )
    await db.execute(
        delete(SafetyDutyAssessmentItem).where(
            SafetyDutyAssessmentItem.assessment_id.in_(
                select(SafetyDutyAssessment.id).where(
                    SafetyDutyAssessment.person_name.like("导入测试%")
                )
            )
        )
    )
    await db.execute(
        delete(SafetyDutyAssessment).where(
            SafetyDutyAssessment.person_name.like("导入测试%")
        )
    )
    await db.execute(
        delete(SafetyTargetAgreement).where(
            SafetyTargetAgreement.department.like(f"{_AGREEMENT_DEPT_PREFIX}%")
        )
    )
    await db.commit()


# ==================== 安全目标责任书 ====================


async def test_agreement_create_sign_and_stats_roundtrip(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    payload = {
        "year": 2026,
        "department": f"{_AGREEMENT_DEPT_PREFIX}安全部",
        "position": "负责人",
        "category": "部门/车间负责人",
        "goals_text": "不发生B级及以上事故\n隐患整改率100%",
    }
    create_res = await client.post(
        "/api/v1/safety/safety-target-agreements", json=payload
    )
    assert create_res.status_code == 200, create_res.text
    created = create_res.json()["data"]
    assert created["status"] == "unsigned"
    assert created["goals_text"].startswith("不发生B级及以上事故")

    duplicate = await client.post(
        "/api/v1/safety/safety-target-agreements", json=payload
    )
    assert duplicate.status_code == 409

    sign_res = await client.put(
        f"/api/v1/safety/safety-target-agreements/{created['id']}",
        json={
            "status": "signed",
            "signed_date": "2026-01-10",
            "expires_date": "2026-12-31",
            "party_a": "总经理/秦刚",
            "party_b": "张三",
        },
    )
    assert sign_res.status_code == 200, sign_res.text
    signed = sign_res.json()["data"]
    assert signed["status"] == "signed"
    assert signed["party_b"] == "张三"

    list_res = await client.get(
        "/api/v1/safety/safety-target-agreements",
        params={"year": 2026, "status": "signed", "keyword": "负责人"},
    )
    assert list_res.status_code == 200
    listed = list_res.json()["data"]
    assert listed["total"] >= 1
    assert any(item["id"] == created["id"] for item in listed["items"])

    stats_res = await client.get(
        "/api/v1/safety/safety-target-agreements/stats",
        params={"year": 2026},
    )
    assert stats_res.status_code == 200
    stats = stats_res.json()["data"]
    assert stats["total"] >= 1
    assert stats["signed"] >= 1
    assert 0 <= stats["sign_rate"] <= 100
    assert any(
        d["department"].startswith(_AGREEMENT_DEPT_PREFIX)
        for d in stats["departments"]
    )

    delete_res = await client.delete(
        f"/api/v1/safety/safety-target-agreements/{created['id']}"
    )
    assert delete_res.status_code == 200
    missing = await client.put(
        f"/api/v1/safety/safety-target-agreements/{created['id']}",
        json={"status": "unsigned"},
    )
    assert missing.status_code == 404


async def test_agreement_template_lookup(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    matched = await client.get(
        "/api/v1/safety/safety-duty-assessments/template",
        params={"department": "安全部负责人"},
    )
    assert matched.status_code == 200
    data = matched.json()["data"]
    assert data["matched"] is True
    assert data["name"] == "安全部"
    assert len(data["items"]) >= 5
    total = sum(item["standard_score"] for item in data["items"])
    assert total == 100

    unmatched = await client.get(
        "/api/v1/safety/safety-duty-assessments/template",
        params={"department": "不存在的部门XYZ"},
    )
    assert unmatched.status_code == 200
    assert unmatched.json()["data"]["matched"] is False


# ==================== 责任制季度考核 ====================


def _assessment_payload(department: str) -> dict:
    return {
        "year": 2026,
        "quarter": 1,
        "department": department,
        "person_name": "负责人",
        "assessor": "安全部",
        "assessment_date": "2026-01-20",
        "items": [
            {
                "content": "认真贯彻执行安全生产法律、法规",
                "rule": "未按要求执行，每项扣2分",
                "standard_score": 10,
                "deduction_score": 2,
            },
            {
                "content": "组织开展安全风险辨识及评估",
                "rule": "未按要求执行，每项扣2分",
                "standard_score": 10,
                "deduction_score": 0,
            },
        ],
        "remark": "",
    }


async def test_assessment_create_computes_total_and_grade(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    payload = _assessment_payload(f"{_ASSESSMENT_DEPT_PREFIX}安全部")
    create_res = await client.post(
        "/api/v1/safety/safety-duty-assessments", json=payload
    )
    assert create_res.status_code == 200, create_res.text
    created = create_res.json()["data"]
    # 明细不填 score 时按 标准分-扣减分 计算：8 + 10 = 18 …总分按满贯模板场景校验
    assert created["total_score"] == 18.0
    assert created["grade"] == "不合格"
    assert len(created["items"]) == 2
    assert created["items"][0]["score"] == 8.0

    duplicate = await client.post(
        "/api/v1/safety/safety-duty-assessments", json=payload
    )
    assert duplicate.status_code == 409

    # 更新评分明细：整体替换并重算总分/等级
    update_res = await client.put(
        f"/api/v1/safety/safety-duty-assessments/{created['id']}",
        json={
            "items": [
                {
                    "content": "认真贯彻执行安全生产法律、法规",
                    "standard_score": 100,
                    "deduction_score": 3,
                }
            ],
        },
    )
    assert update_res.status_code == 200, update_res.text
    updated = update_res.json()["data"]
    assert updated["total_score"] == 97.0
    assert updated["grade"] == "优秀"
    assert len(updated["items"]) == 1

    detail_res = await client.get(
        f"/api/v1/safety/safety-duty-assessments/{created['id']}"
    )
    assert detail_res.status_code == 200
    assert detail_res.json()["data"]["grade"] == "优秀"


async def test_assessment_list_filter_stats_and_delete(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    dept = f"{_ASSESSMENT_DEPT_PREFIX}动力部"
    create_res = await client.post(
        "/api/v1/safety/safety-duty-assessments",
        json=_assessment_payload(dept),
    )
    assert create_res.status_code == 200
    assessment_id = create_res.json()["data"]["id"]

    list_res = await client.get(
        "/api/v1/safety/safety-duty-assessments",
        params={"year": 2026, "quarter": 1, "keyword": "动力部"},
    )
    assert list_res.status_code == 200
    listed = list_res.json()["data"]
    assert any(item["id"] == assessment_id for item in listed["items"])

    stats_res = await client.get(
        "/api/v1/safety/safety-duty-assessments/stats", params={"year": 2026}
    )
    assert stats_res.status_code == 200
    stats = stats_res.json()["data"]
    assert stats["total"] >= 1
    assert stats["avg_score"] > 0
    grade_total = (
        stats["excellent"]
        + stats["good"]
        + stats["qualified"]
        + stats["unqualified"]
    )
    assert grade_total >= 1
    assert any(q["quarter"] == 1 for q in stats["quarters"])
    assert any(d["department"] == dept for d in stats["departments"])

    delete_res = await client.delete(
        f"/api/v1/safety/safety-duty-assessments/{assessment_id}"
    )
    assert delete_res.status_code == 200
    gone = await client.get(
        f"/api/v1/safety/safety-duty-assessments/{assessment_id}"
    )
    assert gone.status_code == 404

# ==================== Excel 批量导入 ====================


async def test_agreement_import_template_and_sign_import(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    create_res = await client.post(
        "/api/v1/safety/safety-target-agreements",
        json={
            "year": 2026,
            "department": f"{_AGREEMENT_DEPT_PREFIX}设备工程部",
            "position": "负责人",
            "category": "部门/车间负责人",
        },
    )
    assert create_res.status_code == 200

    template_res = await client.get(
        "/api/v1/safety/safety-target-agreements/import-template",
        params={"year": 2026},
    )
    assert template_res.status_code == 200
    assert template_res.headers["content-type"].startswith(
        "application/vnd.openxmlformats"
    )
    assert len(template_res.content) > 1000

    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(template_res.content))
    ws = wb.active
    headers = [cell.value for cell in ws[1]]
    assert headers[:3] == ["年度", "责任部门/单位", "岗位/角色"]

    target_row = None
    for row in ws.iter_rows(min_row=2):
        values = [cell.value for cell in row]
        if values[1] == f"{_AGREEMENT_DEPT_PREFIX}设备工程部":
            target_row = row
            break
    assert target_row is not None
    # 列：1年度 2部门 3岗位 4分类 5甲方 6乙方 7签订日期 8有效期 9备注
    ws.cell(row=target_row[0].row, column=5, value="总经理/秦刚")
    ws.cell(row=target_row[0].row, column=6, value="李四")
    ws.cell(row=target_row[0].row, column=7, value="2026-01-15")

    buffer = io.BytesIO()
    wb.save(buffer)
    import_res = await client.post(
        "/api/v1/safety/safety-target-agreements/import",
        files={"file": ("sign.xlsx", buffer.getvalue(), _XLSX_CONTENT_TYPE)},
    )
    assert import_res.status_code == 200, import_res.text
    result = import_res.json()["data"]
    assert result["updated"] >= 1
    assert result["created"] == 0
    assert result["errors"] == []

    list_res = await client.get(
        "/api/v1/safety/safety-target-agreements",
        params={"keyword": "设备工程部", "status": "signed"},
    )
    assert list_res.status_code == 200
    signed_items = [
        item
        for item in list_res.json()["data"]["items"]
        if item["department"] == f"{_AGREEMENT_DEPT_PREFIX}设备工程部"
    ]
    assert len(signed_items) == 1
    assert signed_items[0]["party_a"] == "总经理/秦刚"
    assert signed_items[0]["party_b"] == "李四"
    assert signed_items[0]["signed_date"] == "2026-01-15"


async def test_assessment_import_template_and_import_roundtrip(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    template_res = await client.get(
        "/api/v1/safety/safety-duty-assessments/import-template",
        params={"year": 2026, "quarter": 1},
    )
    assert template_res.status_code == 200

    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(template_res.content))
    assert "填写说明" in wb.sheetnames
    assert "安全部" in wb.sheetnames
    ws = wb["安全部"]
    ws["B2"] = "导入测试负责人"
    ws["E1"] = "安全部"
    ws["E2"] = "2026-01-20"
    # 第 4 行表头，第 5 行起为考核项；E 列=扣减分
    ws.cell(row=5, column=5, value=2)

    buffer = io.BytesIO()
    wb.save(buffer)
    import_res = await client.post(
        "/api/v1/safety/safety-duty-assessments/import",
        params={"year": 2026, "quarter": 1},
        files={"file": ("assess.xlsx", buffer.getvalue(), _XLSX_CONTENT_TYPE)},
    )
    assert import_res.status_code == 200, import_res.text
    result = import_res.json()["data"]
    assert result["imported"] == 1
    assert result["updated"] == 0
    # 其余 32 个模板 sheet 未填扣减分 → 全部跳过；填写说明为内置页不报告
    assert "安全部" not in result["skipped_sheets"]
    assert "填写说明" not in result["skipped_sheets"]
    assert len(result["skipped_sheets"]) >= 30
    assert result["errors"] == []

    list_res = await client.get(
        "/safety/safety-duty-assessments".replace("/safety", "/api/v1/safety", 1),
        params={"keyword": "导入测试负责人"},
    )
    assert list_res.status_code == 200
    items = list_res.json()["data"]["items"]
    assert len(items) == 1
    created = items[0]
    # 安全部模板 11 项合计 100 分，首项扣 2 分 → 98 分 = 优秀
    assert created["department"] == "安全部"
    assert created["person_name"] == "导入测试负责人"
    assert created["total_score"] == 98.0
    assert created["grade"] == "优秀"

    # 覆盖更新：同一年度/季度/部门/被考核人再次导入
    ws.cell(row=5, column=5, value=12)
    buffer2 = io.BytesIO()
    wb.save(buffer2)
    reimport_res = await client.post(
        "/api/v1/safety/safety-duty-assessments/import",
        params={"year": 2026, "quarter": 1},
        files={"file": ("assess2.xlsx", buffer2.getvalue(), _XLSX_CONTENT_TYPE)},
    )
    assert reimport_res.status_code == 200
    rerun = reimport_res.json()["data"]
    assert rerun["updated"] == 1
    assert rerun["imported"] == 0

    detail_res = await client.get(
        f"/api/v1/safety/safety-duty-assessments/{created['id']}"
    )
    assert detail_res.status_code == 200
    # 首项标准分 10、扣减 12 → 得分下限 0，总分 = 100 - 10 = 90
    assert detail_res.json()["data"]["total_score"] == 90.0
    assert detail_res.json()["data"]["grade"] == "良好"
