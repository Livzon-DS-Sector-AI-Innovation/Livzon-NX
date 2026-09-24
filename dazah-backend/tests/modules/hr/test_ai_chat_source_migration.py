"""HR AI 聊天服务测试。

测试范围：
- 系统提示词构建
- 工具 Schema 合法性
- 工具查询函数（mock DB）
- 写工具执行
"""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.hr.ai_chat_service import build_hr_system_prompt, build_welcome_message
from app.modules.hr.ai_tools import (
    ALL_TOOL_SCHEMAS,
    TOOL_EXECUTORS,
    hr_count_by_field,
    hr_create_offboarding_record,
    hr_create_training_record,
    hr_list_contracts,
    hr_query_contract_expiring,
    hr_query_employee,
    hr_query_offboarding,
    hr_query_position_transfers,
    hr_update_employee_basic,
)

# ── Helper ────────────────────────────────────────────


def _mock_session(return_rows: list = None):
    """创建带链式 mock 的 AsyncSession。"""
    session = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = return_rows or []
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)
    return session


# ── System Prompt Tests ──────────────────────────────────


def test_build_system_prompt_no_context():
    """无页面上下文时系统提示词应包含基本角色设定。"""
    prompt = build_hr_system_prompt(None)
    assert prompt["role"] == "system"
    assert "小H" in prompt["content"]
    assert "hr_query_employee" in prompt["content"]
    assert "hr_count_by_field" in prompt["content"]


def test_build_system_prompt_with_page():
    """有页面上下文时应包含页面名称。"""
    prompt = build_hr_system_prompt({"page": "profile"})
    assert "员工档案" in prompt["content"]


def test_build_welcome_message():
    """欢迎消息应包含可用功能列表。"""
    msg = build_welcome_message()
    assert "小H" in msg


# ── Tool Schema Tests ────────────────────────────────────


def test_all_tool_schemas_count():
    """应有 16 个工具 Schema。"""
    assert len(ALL_TOOL_SCHEMAS) == 17  # 新增 hr_query_onboarding


def test_all_tool_executors_match():
    """Schema 数量和 executor 数量应一致。"""
    assert len(ALL_TOOL_SCHEMAS) == len(TOOL_EXECUTORS)


def test_each_schema_has_name():
    """每个 Schema 应有 function.name。"""
    for schema in ALL_TOOL_SCHEMAS:
        assert schema["type"] == "function"
        assert "name" in schema["function"]
        assert "description" in schema["function"]


def test_write_tools_have_required_params():
    """写工具的 required 参数应符合预期。"""
    write_expected = {
        "hr_create_training_record": [
            "employee_number",
            "training_date",
            "training_subject",
        ],
        "hr_create_offboarding_record": [
            "employee_number",
            "offboarding_date",
            "offboarding_type",
            "reason",
        ],
        "hr_update_employee_basic": ["employee_number"],
    }
    for schema in ALL_TOOL_SCHEMAS:
        name = schema["function"]["name"]
        if name in write_expected:
            required = schema["function"]["parameters"].get("required", [])
            assert required == write_expected[name], (
                f"{name}: expected {write_expected[name]}, got {required}"
            )


# ── Tool Execution Tests ─────────────────────────────────


@pytest.mark.asyncio
async def test_hr_query_employee_empty():
    """查询不存在的员工应返回空列表。"""
    session = _mock_session(return_rows=[])
    result = await hr_query_employee(session, "不存在的员工")
    assert result == []


@pytest.mark.asyncio
async def test_hr_count_by_field_total():
    """不传 field 应返回总人数。"""
    session = AsyncMock()
    with patch("app.modules.hr.ai_tools.group_count_employees", return_value=[]):
        with patch("app.modules.hr.ai_tools.query_employees", return_value=([], 68)):
            result = await hr_count_by_field(session, field=None)
            assert result["总人数"] == 68


@pytest.mark.asyncio
async def test_hr_query_offboarding_no_keyword():
    """不传 keyword 应查询全部离职记录。"""
    session = _mock_session(return_rows=[])
    result = await hr_query_offboarding(session, keyword=None)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_hr_query_position_transfers_no_keyword():
    """不传 keyword 应查询全部调动记录。"""
    session = _mock_session(return_rows=[])
    result = await hr_query_position_transfers(session, keyword=None)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_hr_list_contracts_with_filters():
    """合同查询应支持部门筛选。"""
    session = _mock_session(return_rows=[])
    result = await hr_list_contracts(session, department="生产管理部")
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_hr_query_contract_expiring_skips_renewed_and_uses_current_end():
    """合同到期查询返回当前合同到期日；已续签（无固定期限/下期未填到期日）不返回。"""
    employee_active = SimpleNamespace(
        employee_number="E001",
        name="张三",
        department="质量部",
        position="QA",
        contract_type="固定期限",
        hire_date=date(2023, 8, 21),
        contract_start_date=date(2023, 8, 21),
        contract_end_date=date(2026, 8, 20),
        contract_start_2=None,
        contract_end_2=None,
        contract_start_3=None,
        contract_end_3=None,
        contract_start_4=None,
        contract_end_4=None,
        contract_start_5=None,
        contract_end_5=None,
        contract_start_6=None,
        contract_end_6=None,
    )
    employee_renewed = SimpleNamespace(
        employee_number="E002",
        name="李四",
        department="101二车间",
        position="机修工",
        contract_type="",
        hire_date=date(2023, 7, 4),
        contract_start_date=date(2023, 7, 4),
        contract_end_date=date(2026, 7, 3),
        contract_start_2=date(2026, 7, 4),
        contract_end_2=None,
        contract_start_3=None,
        contract_end_3=None,
        contract_start_4=None,
        contract_end_4=None,
        contract_start_5=None,
        contract_end_5=None,
        contract_start_6=None,
        contract_end_6=None,
    )
    ledger_renewed = SimpleNamespace(
        employee_number="E003",
        name="王五",
        dept_level1="103车间",
        position="值班员工",
        contract_start_1=date(2020, 7, 17),
        contract_end_1=date(2026, 7, 16),
        contract_start_2=date(2026, 7, 17),
        contract_end_2="无固定期限",
        contract_start_3=None,
        contract_end_3=None,
        contract_start_4=None,
        contract_end_4=None,
        contract_start_5=None,
        contract_end_5=None,
        contract_start_6=None,
        contract_end_6=None,
    )
    # 无工号：合并时跳过（not key 分支）
    employee_no_number = SimpleNamespace(
        employee_number=None,
        name="赵六",
        department="质量部",
        position="QC",
        contract_type="固定期限",
        hire_date=date(2023, 1, 1),
        contract_start_date=date(2023, 1, 1),
        contract_end_date=date(2026, 8, 10),
        contract_start_2=None,
        contract_end_2=None,
        contract_start_3=None,
        contract_end_3=None,
        contract_start_4=None,
        contract_end_4=None,
        contract_start_5=None,
        contract_end_5=None,
        contract_start_6=None,
        contract_end_6=None,
    )
    # 当前合同到期日在窗口外：跳过（不在窗口分支）
    employee_out_of_window = SimpleNamespace(
        employee_number="E004",
        name="钱七",
        department="生产部",
        position="操作工",
        contract_type="固定期限",
        hire_date=date(2023, 2, 1),
        contract_start_date=date(2023, 2, 1),
        contract_end_date=date(2026, 12, 31),
        contract_start_2=None,
        contract_end_2=None,
        contract_start_3=None,
        contract_end_3=None,
        contract_start_4=None,
        contract_end_4=None,
        contract_start_5=None,
        contract_end_5=None,
        contract_start_6=None,
        contract_end_6=None,
    )
    # 合同管理表：工号与员工表重复（key in seen 分支）
    ledger_duplicate = SimpleNamespace(
        employee_number="E001",
        name="张三（台账重复）",
        dept_level1="质量部",
        position="QA",
        contract_start_1=date(2023, 8, 21),
        contract_end_1=date(2026, 8, 20),
        contract_start_2=None,
        contract_end_2=None,
        contract_start_3=None,
        contract_end_3=None,
        contract_start_4=None,
        contract_end_4=None,
        contract_start_5=None,
        contract_end_5=None,
        contract_start_6=None,
        contract_end_6=None,
    )
    # 合同管理表独有工号且当期在窗口内：并入结果
    ledger_unique = SimpleNamespace(
        employee_number="E009",
        name="孙八",
        dept_level1="103车间",
        position="值班员工",
        contract_start_1=date(2023, 8, 15),
        contract_end_1=date(2026, 8, 15),
        contract_start_2=None,
        contract_end_2=None,
        contract_start_3=None,
        contract_end_3=None,
        contract_start_4=None,
        contract_end_4=None,
        contract_start_5=None,
        contract_end_5=None,
        contract_start_6=None,
        contract_end_6=None,
    )
    session = AsyncMock()
    emp_result = MagicMock()
    emp_result.scalars.return_value.all.return_value = [
        employee_active,
        employee_renewed,
        employee_no_number,
        employee_out_of_window,
    ]
    cm_result = MagicMock()
    cm_result.scalars.return_value.all.return_value = [
        ledger_renewed,
        ledger_duplicate,
        ledger_unique,
    ]
    session.execute = AsyncMock(side_effect=[emp_result, cm_result])

    result = await hr_query_contract_expiring(session, "2026-07-01", "2026-09-30")

    assert [item["工号"] for item in result] == ["E001", "E009"]
    assert result[0]["合同到期日"] == "2026-08-20"
    assert result[0]["数据来源"] == "员工档案"
    assert result[1]["合同到期日"] == "2026-08-15"
    assert result[1]["数据来源"] == "合同管理表"

    # 员工查询的在职过滤按“非离职/待审批”，兼容飞书“正式”等取值
    emp_stmt = session.execute.call_args_list[0][0][0]
    sql = str(emp_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "NOT IN" in sql.upper()
    assert "离职" in sql


# ── Write Tool Tests ─────────────────────────────────────


@pytest.mark.asyncio
async def test_hr_create_training_record_mocked():
    """创建培训记录应返回 success。"""
    session = AsyncMock()
    mock_record = MagicMock()
    mock_record.id = "test-id"

    with patch(
        "app.modules.hr.service.TrainingLedgerService.create_record",
        new=AsyncMock(return_value=mock_record),
    ):
        result = await hr_create_training_record(
            session,
            employee_number="10001",
            training_date="2026-07-30",
            training_subject="安全培训",
        )
        assert result["success"] is True
        assert result["id"] == "test-id"


@pytest.mark.asyncio
async def test_hr_create_offboarding_record_mocked():
    """创建离职记录应返回 success。"""
    session = AsyncMock()
    mock_record = MagicMock()
    mock_record.id = "test-id"

    with patch(
        "app.modules.hr.service.OffboardingRecordService.create_record",
        new=AsyncMock(return_value=mock_record),
    ):
        result = await hr_create_offboarding_record(
            session,
            employee_number="10001",
            offboarding_date="2026-07-30",
            offboarding_type="辞职",
            reason="个人原因",
        )
        assert result["success"] is True


@pytest.mark.asyncio
async def test_hr_update_employee_not_found():
    """更新不存在的员工应返回错误。"""
    session = _mock_session(return_rows=[])
    # scalar_one_or_none 返回 None
    session.execute.return_value.scalar_one_or_none.return_value = None

    result = await hr_update_employee_basic(
        session, employee_number="99999", phone="13800000000"
    )
    assert result["success"] is False
    assert "未找到" in result["error"]
