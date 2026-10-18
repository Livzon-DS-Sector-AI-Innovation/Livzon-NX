"""隐患随手拍 → 公司隐患总台账汇总写入测试（飞书侧全程 mock）。"""

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.safety.models import HazardReport, SafetyPageFeishuConfig
from app.modules.safety.service import hazard_ledger_projection as projection

PAGE_KEY = projection.COMPANY_LEDGER_PAGE_KEY


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, binding, hazard):
        self._binding = binding
        self._hazard = hazard
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, *args, **kwargs):
        # 按 SQL 目标实体判别（同一会话会先后查配置行与隐患行）
        if "page_feishu_configs" in str(args[0]):
            return _FakeResult(self._binding)
        return _FakeResult(self._hazard)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class _FakeClient:
    def __init__(self, **kwargs):
        self.created: list[dict] = []
        self.updates: list[tuple[str, dict]] = []
        self.create_id = "recnew1"
        self.record_fields: dict = {}

    async def create_record(self, fields, table_id=None):
        self.created.append(fields)
        return self.create_id

    async def update_record_with_result(self, record_id, fields, table_id=None):
        self.updates.append((record_id, fields))
        return True, None

    async def get_record(self, record_id, table_id=None, **kwargs):
        return dict(self.record_fields)

    async def upload_media(self, file_bytes, file_name, parent_type="bitable_file"):
        return f"tok-{file_name}"


def _binding(**overrides) -> SafetyPageFeishuConfig:
    values = dict(
        page_key=PAGE_KEY,
        app_token="bascnLedger",
        table_id="tblLedger",
        is_enabled=True,
    )
    values.update(overrides)
    return SafetyPageFeishuConfig(**values)


def _hazard(**overrides) -> HazardReport:
    values = dict(
        id=uuid4(),
        hazard_no="HZ-20261015-001",
        description="配电箱门未上锁",
        department="201一车间",
        discovered_at=None,
        deadline=None,
        defect_photos=None,
        rectification_photos=None,
        rectification_reply=None,
        rectification_status="pending",
        status="open",
        feishu_record_id=None,
        ledger_record_id=None,
        rectification_responsible_person_name="韦静平",
    )
    values.update(overrides)
    return HazardReport(**values)


def _install(monkeypatch, client, session):
    monkeypatch.setattr(
        "app.modules.safety.service.hazard_ledger_projection.SafetyBitableClient",
        lambda **kwargs: client,
    )
    monkeypatch.setattr(
        "app.core.database.async_session_factory",
        lambda: _SessionCtx(session),
    )
    monkeypatch.setattr(
        projection, "_refresh_mirror", AsyncMock(return_value=None)
    )
    return client


class _SessionCtx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return None


async def test_project_creates_ledger_record_with_mapping(monkeypatch) -> None:
    hazard = _hazard()
    client = _install(
        monkeypatch, _FakeClient(), _FakeSession(_binding(), hazard)
    )

    await projection.project_hazard_to_company_ledger(hazard.id)

    assert len(client.created) == 1
    fields = client.created[0]
    assert fields["部门/车间"] == "201一车间"
    assert fields["隐患内容"] == "配电箱门未上锁"
    assert fields["关闭状态"] == "未关闭"
    assert fields["进度情况"] == "整改中"
    # 幂等锚点回存
    assert hazard.ledger_record_id == "recnew1"


async def test_project_skips_when_binding_disabled_or_missing(monkeypatch) -> None:
    client = _FakeClient()
    # 未配置
    _install(monkeypatch, client, _FakeSession(None, _hazard()))
    await projection.project_hazard_to_company_ledger(uuid4())
    # 停用
    _install(monkeypatch, client, _FakeSession(_binding(is_enabled=False), _hazard()))
    await projection.project_hazard_to_company_ledger(uuid4())
    # 绑定不完整
    _install(
        monkeypatch, client, _FakeSession(_binding(table_id=None), _hazard())
    )
    await projection.project_hazard_to_company_ledger(uuid4())
    assert client.created == []


async def test_project_skips_hazards_from_legacy_feishu_table(monkeypatch) -> None:
    """feishu_record_id 非空 = 旧隐患流程表来源，总台账另行维护避免重复。"""
    client = _install(
        monkeypatch,
        _FakeClient(),
        _FakeSession(_binding(), _hazard(feishu_record_id="recold1")),
    )

    await projection.project_hazard_to_company_ledger(uuid4())

    assert client.created == []


async def test_project_idempotent_routes_to_progress_sync(monkeypatch) -> None:
    """已写入过（ledger_record_id 非空）时走更新而不是重复建行。"""
    hazard = _hazard(ledger_record_id="recexist")
    client = _install(
        monkeypatch, _FakeClient(), _FakeSession(_binding(), hazard)
    )

    await projection.project_hazard_to_company_ledger(hazard.id)

    assert client.created == []
    assert len(client.updates) == 1
    assert client.updates[0][0] == "recexist"


async def test_project_uploads_defect_photos(monkeypatch, tmp_path) -> None:
    photo = tmp_path / "p1.png"
    photo.write_bytes(b"png-bytes")
    hazard = _hazard(defect_photos=json.dumps([str(photo)]))
    client = _install(
        monkeypatch, _FakeClient(), _FakeSession(_binding(), hazard)
    )

    await projection.project_hazard_to_company_ledger(hazard.id)

    fields = client.created[0]
    assert fields["隐患照片"] == [{"file_token": "tok-p1.png"}]


async def test_sync_updates_progress_and_close_status(monkeypatch) -> None:
    hazard = _hazard(
        ledger_record_id="recexist",
        rectification_status="closed",
        status="closed",
        rectification_reply="已更换锁具",
    )
    client = _install(
        monkeypatch, _FakeClient(), _FakeSession(_binding(), hazard)
    )

    await projection.sync_hazard_progress_to_company_ledger(hazard.id)

    record_id, fields = client.updates[0]
    assert record_id == "recexist"
    assert fields["进度情况"] == "已关闭"
    assert fields["关闭状态"] == "已关闭"
    assert fields["隐患整改措施"] == "已更换锁具"


async def test_sync_backfills_defect_photos_by_count(monkeypatch, tmp_path) -> None:
    """登记创建早于照片上传：进度同步按数量差补传隐患照片。"""
    p1, p2 = tmp_path / "p1.png", tmp_path / "p2.png"
    p1.write_bytes(b"a")
    p2.write_bytes(b"b")
    hazard = _hazard(
        ledger_record_id="recexist",
        rectification_status="replied",
        defect_photos=json.dumps([str(p1), str(p2)]),
    )
    client = _FakeClient()
    client.record_fields = {
        "隐患照片": [{"file_token": "tok-p1.png", "name": "p1.png"}]
    }
    _install(monkeypatch, client, _FakeSession(_binding(), hazard))

    await projection.sync_hazard_progress_to_company_ledger(hazard.id)

    _, fields = client.updates[0]
    assert fields["隐患照片"] == [
        {"file_token": "tok-p1.png"},
        {"file_token": "tok-p2.png"},
    ]


async def test_sync_appends_rectified_photos(monkeypatch, tmp_path) -> None:
    r1 = tmp_path / "r1.jpg"
    r1.write_bytes(b"c")
    hazard = _hazard(
        ledger_record_id="recexist",
        rectification_status="replied",
        rectification_photos=json.dumps([str(r1)]),
    )
    client = _FakeClient()
    client.record_fields = {
        "整改后照片": [{"file_token": "tok-old", "name": "old.jpg"}]
    }
    _install(monkeypatch, client, _FakeSession(_binding(), hazard))

    await projection.sync_hazard_progress_to_company_ledger(hazard.id)

    _, fields = client.updates[0]
    assert fields["整改后照片"] == [
        {"file_token": "tok-old"},
        {"file_token": "tok-r1.jpg"},
    ]


def test_progress_labels_cover_lifecycle() -> None:
    assert projection._progress_label("pending") == "整改中"
    assert projection._progress_label("replied") == "待复核"
    assert projection._progress_label("closed") == "已关闭"
    assert projection._progress_label(None) == "整改中"
    assert projection._progress_label("unknown") == "整改中"


def test_date_to_ms_uses_document_timezone() -> None:
    from datetime import UTC, datetime

    from app.modules.safety.feishu.field_codec import BITABLE_TIMEZONE

    def cn_midnight_ms(date_str: str) -> int:
        day = datetime.strptime(date_str, "%Y-%m-%d")
        return int(
            day.replace(tzinfo=BITABLE_TIMEZONE).timestamp() * 1000
        )

    # 任意时刻都归一到东八区当天零点（与 field_codec 日期口径一致）
    assert projection._date_to_ms(datetime(2026, 10, 15, 8, 0, tzinfo=UTC)) == (
        cn_midnight_ms("2026-10-15")
    )  # UTC 08:00 = 东八区 16:00，同一天
    assert projection._date_to_ms(datetime(2026, 10, 15, 23, 0, tzinfo=UTC)) == (
        cn_midnight_ms("2026-10-16")
    )  # UTC 23:00 = 东八区次日 07:00
    assert projection._date_to_ms(None) is None


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_progress_jobs_serialize_per_hazard(monkeypatch) -> None:
    """同一隐患的写入按提交顺序串行：后提交的关闭同步不被先提交的进度覆盖。"""
    import asyncio

    hazard = _hazard(
        ledger_record_id="recexist",
        rectification_status="closed",
        status="closed",
    )
    client = _FakeClient()
    client.record_fields = {}
    sessions: list[_FakeSession] = []

    def make_session():
        session = _FakeSession(_binding(), hazard)
        sessions.append(session)
        return session

    monkeypatch.setattr(
        "app.modules.safety.service.hazard_ledger_projection.SafetyBitableClient",
        lambda **kwargs: client,
    )
    monkeypatch.setattr(
        "app.core.database.async_session_factory",
        lambda: _SessionCtx(make_session()),
    )
    monkeypatch.setattr(projection, "_refresh_mirror", AsyncMock(return_value=None))

    # 并发触发两个同步：进度（先提交）与关闭（后提交）
    await asyncio.gather(
        projection.sync_hazard_progress_to_company_ledger(hazard.id),
        projection.sync_hazard_progress_to_company_ledger(hazard.id),
    )

    # 关闭语义最终一致（两个 job 读到的都是最新 closed 状态）
    assert all(
        fields["关闭状态"] == "已关闭" for _, fields in client.updates
    )
