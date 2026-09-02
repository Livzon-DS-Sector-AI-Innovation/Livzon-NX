"""离职管理 飞书同步 回归测试。

覆盖三个曾出问题的点：
1. 读取字段名对齐飞书离职表真实名称（域账户 / 职位/岗位），不再读成空。
2. 在职状态按飞书在职状态推导：在职状态=离职 → 本地在职状态=离职。
3. 空值不覆盖本地已有值（避免清掉本地手动维护的在职/域账号/职务）。
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.hr.feishu.bitable import BitableClient
from app.modules.hr.models import HrFeishuEntitySetting, OffboardingRecord
from app.modules.hr.service import (
    OffboardingRecordService,
)

# 模拟飞书离职表原始记录（字段名与真实表一致）
RAW_RECORDS = [
    {
        "record_id": "rec_departed",
        "fields": {
            "姓名": "张三",
            "工号": 1001,
            "域账户": "zhangsan",
            "职位/岗位": "工程师",
            "职级": "P3",
            "在职状态": "离职",
            "最后工作日": 1700000000000,
            "离职原因": "正常离职",
            "离职类型": "正常离职",
            "一级部门": "生产管理部",
            "二级部门": "生产管理",
        },
    },
    {
        # 在职状态为空：不应覆盖本地已有交接/在职状态
        "record_id": "rec_empty",
        "fields": {
            "姓名": "李四",
            "工号": 1002,
            "在职状态": "",
            "最后工作日": 1700000000000,
        },
    },
]


async def _seed_entity_setting(session: AsyncSession) -> None:
    from sqlalchemy import select

    row = (
        await session.execute(
            select(HrFeishuEntitySetting).where(
                HrFeishuEntitySetting.entity_code == "offboarding_record"
            )
        )
    ).scalar_one_or_none()
    if row is None:
        session.add(
            HrFeishuEntitySetting(
                entity_code="offboarding_record",
                entity_name="离职管理",
                entity_group="人事台账",
                app_token="test_app_token",
                base_table_id="tbl_off",
                is_enabled=True,
            )
        )
    else:
        row.app_token = "test_app_token"
        row.base_table_id = "tbl_off"
        row.is_enabled = True
    await session.flush()


@pytest.fixture
def mock_feishu(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search_records(self, table_id: str, **kwargs):
        return RAW_RECORDS

    monkeypatch.setattr(BitableClient, "search_records", fake_search_records)
    monkeypatch.setattr(
        "app.modules.hr.service.get_hr_feishu_app_credentials",
        AsyncMock(return_value=("app_id", "app_secret")),
    )



@pytest.fixture(autouse=True)
def _safe_commit(db_session, monkeypatch):
    """同步类 service 内部会 session.commit()；测试内降级为 flush 保持隔离。"""
    monkeypatch.setattr(db_session, "commit", db_session.flush, raising=False)

@pytest.mark.asyncio
async def test_sync_creates_record_with_correct_fields(
    db_session: AsyncSession, mock_feishu,
) -> None:
    """新记录：域账户/职位/岗位按正确字段名解析；在职=离职 → 本地在职状态=离职。"""
    await _seed_entity_setting(db_session)
    svc = OffboardingRecordService(db_session)
    stats = await svc.sync_from_feishu()
    assert stats["created"] == 2
    rec = await svc.repo.get_by_feishu_record_id("rec_departed")
    assert rec is not None
    assert rec.domain_account == "zhangsan"   # 来自「域账户」字段
    assert rec.position == "工程师"           # 来自「职位/岗位」字段
    assert rec.level == "P3"
    assert rec.status == "离职"


@pytest.mark.asyncio
async def test_sync_empty_does_not_overwrite_local(
    db_session: AsyncSession, mock_feishu,
) -> None:
    """在职状态为空的飞书记录：不覆盖本地已有的在职/域账号/职务。"""
    await _seed_entity_setting(db_session)
    local = OffboardingRecord(
        feishu_record_id="rec_empty",
        name="李四",
        employee_number="1002",
        domain_account="lisi_old",
        position="QA",
        status="离职",
        offboarding_date=date(2023, 1, 1),
    )
    db_session.add(local)
    await db_session.flush()

    svc = OffboardingRecordService(db_session)
    stats = await svc.sync_from_feishu()
    assert stats["created"] == 1  # rec_departed 新建
    assert stats["updated"] == 1  # rec_empty 更新
    rec = await svc.repo.get_by_feishu_record_id("rec_empty")
    assert rec is not None
    # 空值不覆盖本地已有值
    assert rec.status == "离职"
    assert rec.domain_account == "lisi_old"
    assert rec.position == "QA"


@pytest.mark.asyncio
async def test_update_status_departed_snapshots_employee(
    db_session: AsyncSession,
) -> None:
    """在职状态→离职时，把员工档案对应信息整体转抄进离职台账（含软删员工）。"""
    from app.modules.hr.models import Employee
    from app.modules.hr.schemas import OffboardingRecordUpdate

    emp = Employee(
        name="转抄甲",
        employee_number="ZS001",
        domain_account="zhuanchaojia",
        department="质量部",
        sub_department="QA",
        position="质量监督员",
        level="P3",
        gender="男",
        ethnic_group="汉族",
        id_card="110101199001011234",
        education="本科",
        school="测试大学",
        phone="13800000000",
        email="a@test.com",
        hire_date=date(2019, 3, 1),
        work_years=5,
        # Employee 为 Date、OffboardingRecord 为 String 的合同字段（验证类型转换）
        contract_end_2=date(2024, 1, 1),
        contract_start_3=date(2024, 2, 1),
        status="在职",
    )
    db_session.add(emp)
    await db_session.flush()
    rec = OffboardingRecord(
        name="转抄甲",
        employee_number="ZS001",
        employee_id=emp.id,
        status="在职",
        offboarding_date=date(2023, 1, 1),
    )
    db_session.add(rec)
    await db_session.flush()
    # 模拟自动转离职后的软删员工
    emp.is_deleted = True
    await db_session.flush()

    svc = OffboardingRecordService(db_session)
    updated = await svc.update_record(
        rec.id, OffboardingRecordUpdate(status="离职")
    )
    assert updated.status == "离职"
    # 员工档案字段被转抄进离职台账
    assert updated.domain_account == "zhuanchaojia"
    assert updated.position == "质量监督员"
    assert updated.level == "P3"
    assert updated.gender == "男"
    assert updated.ethnic_group == "汉族"
    assert updated.id_card == "110101199001011234"
    assert updated.education == "本科"
    assert updated.school == "测试大学"
    assert updated.phone == "13800000000"
    assert updated.email == "a@test.com"
    assert updated.sub_department == "QA"
    # work_years 类型：Employee Integer → OffboardingRecord String
    assert updated.work_years == "5"
    # 合同日期字段：Employee Date → OffboardingRecord String，转成 YYYY-MM-DD
    assert updated.contract_end_2 == "2024-01-01"
    assert updated.contract_start_3 == "2024-02-01"


@pytest.mark.asyncio
async def test_create_record_snapshots_employee(
    db_session: AsyncSession,
) -> None:
    """创建离职台账时，自动把员工档案对应信息转抄进来。"""
    from app.modules.hr.models import Employee
    from app.modules.hr.schemas import OffboardingRecordCreate

    emp = Employee(
        name="转抄乙",
        employee_number="ZS002",
        domain_account="zhuanchao_yi",
        department="生产部",
        position="班长",
        id_card="110101199202022345",
        education="大专",
        hire_date=date(2020, 1, 1),
        status="在职",
    )
    db_session.add(emp)
    await db_session.flush()

    svc = OffboardingRecordService(db_session)
    created = await svc.create_record(
        OffboardingRecordCreate(
            employee_id=emp.id,
            employee_number="ZS002",
            name="转抄乙",
            offboarding_type="辞职",
            offboarding_date=date(2023, 1, 1),
            status="离职",
        )
    )
    assert created.employee_id == emp.id
    assert created.status == "离职"
    # 已离职创建：员工档案字段被转抄
    assert created.domain_account == "zhuanchao_yi"
    assert created.position == "班长"
    assert created.department == "生产部"
    assert created.id_card == "110101199202022345"
    assert created.education == "大专"
    # 员工在职状态同步为离职 + 员工档案被软删（已离职创建联动）
    refreshed = await db_session.get(Employee, emp.id)
    assert refreshed.status == "离职"
    assert refreshed.is_deleted is True


@pytest.mark.asyncio
async def test_upsert_by_employee_number_skips_departed(
    db_session: AsyncSession,
) -> None:
    """飞书同步 upsert：已离职/已软删的员工跳过不复活，保持离职状态。"""
    from app.modules.hr.models import Employee
    from app.modules.hr.repository import EmployeeRepository

    emp = Employee(
        employee_number="RS001",
        name="离职甲",
        department="生产部",
        position="班长",
        hire_date=date(2020, 1, 1),
        status="离职",
        is_deleted=True,
    )
    db_session.add(emp)
    await db_session.flush()

    repo = EmployeeRepository(db_session)
    data = {
        "employee_number": "RS001",
        "name": "离职甲",
        "department": "生产部",
        "position": "副班长",
        "status": "在职",
        "hire_date": date(2020, 1, 1),
    }
    result = await repo.upsert_by_employee_number(data)
    assert result is None  # 跳过，不复活
    refreshed = await db_session.get(Employee, emp.id)
    assert refreshed.is_deleted is True  # 保持软删
    assert refreshed.status == "离职"  # 保持离职
    assert refreshed.position == "班长"  # 未被飞书数据覆盖


@pytest.mark.asyncio
async def test_update_feishu_failure_does_not_block_local_update(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """飞书同步失败时，本地更新不被打断、不因飞书异常回滚（与创建时行为一致）。

    回归场景：云端离职管理把在职状态改为「离职」时报
    「An error occurred in the Server Components render」——
    update_record 里 _sync_to_feishu 裸调用，飞书多维表格异常直接 500。
    """
    from unittest.mock import AsyncMock

    from app.modules.hr.models import Employee
    from app.modules.hr.schemas import OffboardingRecordUpdate

    emp = Employee(
        name="飞书失败甲",
        employee_number="FS001",
        department="QA",
        position="QA",
        hire_date=date(2020, 1, 1),
        status="在职",
    )
    db_session.add(emp)
    await db_session.flush()
    rec = OffboardingRecord(
        name="飞书失败甲",
        employee_id=emp.id,
        status="在职",
        offboarding_date=date(2023, 1, 1),
    )
    db_session.add(rec)
    await db_session.flush()

    async def fake_pair(self):
        client = AsyncMock()
        client.update_record = AsyncMock(side_effect=RuntimeError("飞书表字段不匹配"))
        client.create_record = AsyncMock(side_effect=RuntimeError("飞书表字段不匹配"))
        return client, "tbl_off"

    monkeypatch.setattr(
        OffboardingRecordService, "_get_offboarding_bitable", fake_pair
    )

    svc = OffboardingRecordService(db_session)
    updated = await svc.update_record(
        rec.id, OffboardingRecordUpdate(status="离职")
    )
    assert updated.status == "离职"
    refreshed = await db_session.get(Employee, emp.id)
    assert refreshed.status == "离职"  # 员工档案联动仍提交


@pytest.mark.asyncio
async def test_sync_to_feishu_text_fields_coerced_to_str(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """年龄等数值列写给飞书 Text 字段时必须转字符串。

    回归：离职台账 age 为 Integer，原 `_s(v)=v if v else ""` 会把 int 原样传给
    飞书「年龄」文本字段，触发 TextFieldConvFail（code=1254060），
    导致云端离职管理「在职→离职」时飞书同步异常。
    """
    from unittest.mock import AsyncMock

    from app.modules.hr.models import OffboardingRecord

    rec = OffboardingRecord(
        name="年龄甲",
        employee_number="AGE001",
        age=51,
        status="离职",
        offboarding_date=date(2023, 1, 1),
    )
    db_session.add(rec)
    await db_session.flush()

    client = AsyncMock()
    client.create_record = AsyncMock(return_value={"record_id": "rec_new"})
    client.update_record = AsyncMock()

    async def fake_pair(self):
        return client, "tbl_off"

    monkeypatch.setattr(
        OffboardingRecordService, "_get_offboarding_bitable", fake_pair
    )

    svc = OffboardingRecordService(db_session)
    await svc._sync_to_feishu(rec, is_create=True)

    created_fields = client.create_record.call_args.args[1]
    assert isinstance(created_fields["年龄"], str)
    assert created_fields["年龄"] == "51"
    assert isinstance(created_fields["姓名"], str)
    assert created_fields["姓名"] == "年龄甲"
    assert isinstance(created_fields["在职状态"], str)


@pytest.mark.asyncio
async def test_sync_from_feishu_fills_birth_age_from_employee(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """飞书拉取时，离职表未维护出生年月/年龄，回退到员工档案补全。

    回归：云端离职管理的出生年月/年龄本地有值、飞书多维表格却为空——
    同步方向错误/缺失导致字段丢失，需从员工档案（权威来源）回退。
    """
    from app.modules.hr.models import Employee

    emp = Employee(
        name="回退甲",
        employee_number="HB001",
        department="QA",
        position="QA",
        hire_date=date(2020, 1, 1),
        birth_year=1980,
        birth_month=4,
        birth_day=23,
        age=46,
        status="在职",
    )
    db_session.add(emp)
    await db_session.flush()

    async def fake_search_records(self, table_id: str, **kwargs):
        return [
            {
                "record_id": "rec_birth_fallback",
                "fields": {
                    "姓名": "回退甲",
                    "工号": "HB001",
                    "在职状态": "离职",
                    "最后工作日": 1700000000000,
                    # 出生年月/年龄 缺失（飞书离职表未维护）
                },
            }
        ]

    monkeypatch.setattr(BitableClient, "search_records", fake_search_records)
    monkeypatch.setattr(
        "app.modules.hr.service.get_hr_feishu_app_credentials",
        AsyncMock(return_value=("app_id", "app_secret")),
    )
    await _seed_entity_setting(db_session)

    svc = OffboardingRecordService(db_session)
    stats = await svc.sync_from_feishu()
    assert stats["created"] == 1
    rec = await svc.repo.get_by_feishu_record_id("rec_birth_fallback")
    assert rec is not None
    assert rec.birth_year == 1980
    assert rec.birth_month == 4
    assert rec.birth_day == 23
    assert rec.age == 46


