"""隐患到期提醒测试（节点制）：节点判定、去重推送、设置与调度开关。

飞书发送与台账取数全部 mock，不访问真实多维表格。
"""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.core.exceptions import AppException
from app.modules.safety.models import (
    HazardDueNotificationLog,
    SafetyFeishuAppSettings,
)
from app.modules.safety.scheduled import SafetyHazardDueReminderGenerator
from app.modules.safety.service import hazard_due_reminder, page_table

PAGE_KEY = hazard_due_reminder.LEDGER_PAGE_KEY

_DUE_FIELDS = [
    {"field_id": "fld1", "field_name": "隐患内容", "type": 1},
    {"field_id": "fld2", "field_name": "目标完成日期", "type": 5},
    {
        "field_id": "fld3",
        "field_name": "关闭状态",
        "type": 3,
        "property": {"options": [{"name": "已关闭"}, {"name": "未关闭"}]},
    },
]


def _fields_schema() -> list:
    from app.modules.safety.feishu.field_codec import build_field_schema

    return build_field_schema(_DUE_FIELDS)


def _settings(**overrides: object) -> SafetyFeishuAppSettings:
    values: dict[str, object] = {
        "app_id": "cli_x",
        "app_secret": "enc",
        "hazard_due_notify_enabled": True,
        "hazard_due_notify_milestones": [30, 15, 7],
        "hazard_due_notify_chat_ids": ["oc_chat1"],
        "hazard_due_notify_user_ids": ["ou_user1"],
    }
    values.update(overrides)
    return SafetyFeishuAppSettings(**values)


def _record(
    rid: str,
    days: int | None,
    close: str | list | None = "未关闭",
) -> dict:
    today = date.today()
    due = "" if days is None else (today + timedelta(days=days)).isoformat()
    return {
        "_record_id": rid,
        "隐患内容": f"隐患{rid}",
        "目标完成日期": due,
        "关闭状态": close,
    }


class _FakeScalars:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def all(self) -> list[object]:
        return list(self._values)


class _FakeResult:
    def __init__(self, value: object = None, list_value: list | None = None) -> None:
        self._value = value
        self._list = (
            list_value if list_value is not None else ([value] if value else [])
        )

    def scalar_one_or_none(self) -> object:
        return self._value

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._list)


class _FakeSession:
    """带内存推送记录存储的假会话：按查询对象区分返回设置或推送记录。"""

    def __init__(self, settings: SafetyFeishuAppSettings | None) -> None:
        self.settings = settings
        self.logs: list[HazardDueNotificationLog] = []
        self.commits = 0

    async def execute(self, *args: object, **kwargs: object) -> _FakeResult:
        statement = str(args[0]) if args else ""
        if "hazard_due_notification_log" in statement:
            return _FakeResult(None, list_value=list(self.logs))
        return _FakeResult(self.settings)

    def add(self, obj: object) -> None:
        if isinstance(obj, HazardDueNotificationLog):
            self.logs.append(obj)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None


class _FakeClient:
    async def list_fields(self, table_id: str | None = None) -> list[dict]:
        return _DUE_FIELDS

    async def search_records_with_result(self, **kwargs: object):
        return [], None


def _install_ledger(monkeypatch, records: list[dict]) -> None:
    """把台账取数链路（配置/绑定/取数）替换为固定记录集（单主表）。"""

    async def fake_collect(db, model, app_token, bound, **kwargs):
        return records, _fields_schema()

    config = SimpleNamespace(
        page_key=PAGE_KEY, app_token="bascnX", table_id="tblMain", is_mirrored=False
    )

    async def fake_load(db, page_key):
        return (SimpleNamespace(page_key=PAGE_KEY), config, "bascnX", "tblMain")

    monkeypatch.setattr(page_table, "_collect_table_records", fake_collect)
    monkeypatch.setattr(page_table, "_load_config_or_raise", fake_load)
    monkeypatch.setattr(
        page_table,
        "_bound_tables",
        lambda definition, model: [
            SimpleNamespace(table_id="tblMain", tab_name="主表")
        ],
    )
    monkeypatch.setattr(page_table, "SafetyBitableClient", lambda **kw: _FakeClient())


def _install_senders(monkeypatch) -> tuple[list[str], list[str]]:
    sent_group: list[str] = []
    sent_user: list[str] = []

    async def fake_group(chat_id, title, content, **kwargs):
        sent_group.append(f"{title}\n{content}")
        return True

    async def fake_user(open_id, title, content, **kwargs):
        sent_user.append(f"{title}\n{content}")
        return True

    monkeypatch.setattr(hazard_due_reminder, "send_group_card", fake_group)
    monkeypatch.setattr(hazard_due_reminder, "send_user_card", fake_user)
    return sent_group, sent_user


# ── 节点判定 ──


def test_milestone_for_picks_outermost_entered() -> None:
    m = [30, 15, 7]
    assert hazard_due_reminder.milestone_for(40, m) is None  # 未进入任何节点
    assert hazard_due_reminder.milestone_for(25, m) == 30  # 一个月节点
    assert hazard_due_reminder.milestone_for(10, m) == 15  # 半个月节点
    assert hazard_due_reminder.milestone_for(3, m) == 7  # 一周节点
    assert hazard_due_reminder.milestone_for(-2, m) == 0  # 逾期节点


def test_summarize_due_buckets_by_window() -> None:
    today = date.today()
    records = [
        {"目标完成日期": (today - timedelta(days=3)).isoformat(), "关闭状态": "未关闭"},
        {"目标完成日期": (today + timedelta(days=5)).isoformat(), "关闭状态": ""},
        {
            "目标完成日期": (today + timedelta(days=12)).isoformat(),
            "关闭状态": "未关闭",
        },
        {
            "目标完成日期": (today + timedelta(days=25)).isoformat(),
            "关闭状态": None,
        },
        {"目标完成日期": (today - timedelta(days=9)).isoformat(), "关闭状态": "已关闭"},
        # 多选关闭状态（2024 表结构）：含「已关闭」即视为闭环
        {
            "目标完成日期": (today - timedelta(days=9)).isoformat(),
            "关闭状态": ["已关闭"],
        },
        {"目标完成日期": None, "关闭状态": "未关闭"},
    ]
    summary = hazard_due_reminder.summarize_due(records)
    assert summary["overdue"] == 1
    assert summary["within_7"] == 1
    assert summary["within_15"] == 2
    assert summary["within_30"] == 3


# ── 节点推送与去重 ──


async def test_pushes_once_per_milestone_and_skips_when_nothing_new(
    monkeypatch,
) -> None:
    sent_group, sent_user = _install_senders(monkeypatch)
    # rec-25 剩 25 天（命中 30 节点）；rec-over 已逾期（命中 0 节点）；
    # rec-far 剩 60 天（未进入任何节点）；rec-closed 已关闭
    _install_ledger(
        monkeypatch,
        [
            _record("rec-25", 25),
            _record("rec-over", -3),
            _record("rec-far", 60),
            _record("rec-closed", -1, close="已关闭"),
        ],
    )

    db = _FakeSession(_settings())
    sent, errors = await hazard_due_reminder.send_hazard_due_notifications(db)
    assert sent == 2 and errors == []
    # 只推 2 条（30 节点 + 逾期节点），标题汇总 2 项
    assert sent_group and "2 项进入提醒节点" in sent_group[0]
    # 推送记录：两个节点各一条
    assert sorted(log.milestone_days for log in db.logs) == [0, 30]

    # 同样的数据再跑一轮：无新节点 → 静默跳过，不重复推送
    sent2, errors2 = await hazard_due_reminder.send_hazard_due_notifications(db)
    assert (sent2, errors2) == (0, None)
    assert len(sent_group) == 1

    # rec-25 进入 15 节点（剩 10 天）：只推这一个新节点
    _install_ledger(monkeypatch, [_record("rec-25", 10), _record("rec-over", -3)])
    db2 = _FakeSession(_settings())
    db2.logs = list(db.logs)
    sent3, _ = await hazard_due_reminder.send_hazard_due_notifications(db2)
    assert sent3 == 2
    assert "半个月" in sent_group[-1]
    assert sorted(log.milestone_days for log in db2.logs) == [0, 15, 30]


async def test_push_respects_switch_and_targets(monkeypatch) -> None:
    _install_senders(monkeypatch)

    # 关闭开关 → 静默跳过
    _install_ledger(monkeypatch, [_record("rec-25", 25)])
    sent, errors = await hazard_due_reminder.send_hazard_due_notifications(
        _FakeSession(_settings(hazard_due_notify_enabled=False))
    )
    assert (sent, errors) == (0, None)

    # 未配置目标 → 静默跳过
    sent, errors = await hazard_due_reminder.send_hazard_due_notifications(
        _FakeSession(
            _settings(hazard_due_notify_chat_ids=[], hazard_due_notify_user_ids=[])
        )
    )
    assert (sent, errors) == (0, None)

    # 未配置节点 → 静默跳过
    sent, errors = await hazard_due_reminder.send_hazard_due_notifications(
        _FakeSession(_settings(hazard_due_notify_milestones=[]))
    )
    assert (sent, errors) == (0, None)

    # 全部记录都在节点之外 → 静默跳过
    _install_ledger(monkeypatch, [_record("rec-far", 90)])
    sent, errors = await hazard_due_reminder.send_hazard_due_notifications(
        _FakeSession(_settings())
    )
    assert (sent, errors) == (0, None)


async def test_send_test_notification_reports_missing_targets() -> None:
    db = _FakeSession(
        _settings(hazard_due_notify_chat_ids=[], hazard_due_notify_user_ids=[])
    )
    with pytest.raises(AppException) as excinfo:
        await hazard_due_reminder.send_test_notification(db)
    assert "未配置提醒目标" in excinfo.value.message


# ── 调度开关 ──


class _SettingsSession:
    """调度器 find_due 用的会话替身：任何查询都返回设置行。"""

    def __init__(self, settings: SafetyFeishuAppSettings | None) -> None:
        self._settings = settings

    async def execute(self, *args: object, **kwargs: object) -> _FakeResult:
        return _FakeResult(self._settings)


async def test_daily_generator_respects_enabled_switch() -> None:
    generator = SafetyHazardDueReminderGenerator()

    disabled = await generator.find_due(
        _SettingsSession(_settings(hazard_due_notify_enabled=False))
    )
    assert disabled == []

    enabled = await generator.find_due(_SettingsSession(_settings()))
    assert enabled == [True]


async def test_all_targets_failed_writes_no_log(monkeypatch) -> None:
    """全部发送失败时不写推送记录：明晚重试，不因故障漏推。"""

    async def fail_send(target, title, content, **kwargs):
        return False

    monkeypatch.setattr(hazard_due_reminder, "send_group_card", fail_send)
    monkeypatch.setattr(hazard_due_reminder, "send_user_card", fail_send)
    _install_ledger(monkeypatch, [_record("rec-25", 25)])

    db = _FakeSession(_settings())
    sent, errors = await hazard_due_reminder.send_hazard_due_notifications(db)
    assert sent == 0 and errors  # 发送失败
    assert db.logs == []  # 但推送记录未写 → 明晚会重试
    assert db.commits == 0
