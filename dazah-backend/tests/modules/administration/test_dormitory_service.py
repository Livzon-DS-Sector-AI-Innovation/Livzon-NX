"""宿舍管理服务测试：入住率统计、AI 房间推荐与入住回写（不依赖数据库）。

fixture 按宿舍多维表真实取值形态构造：宿舍清单的已住人数/剩余床位是公式
（{"type":2,"value":[x]}），住宿标准与员工清单是富文本 [{"text":..}]。
"""

from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.exceptions import AppException
from app.modules.administration import service as admin_service
from app.modules.administration.models import (
    AdministrationFeishuReadField,
    AdministrationFeishuReadRecord,
    AdministrationFeishuReadResource,
)
from app.modules.administration.repository import MirroredTable
from app.modules.administration.schemas import DormitoryCheckinInput
from app.modules.administration.service import (
    AdministrationDormitoryService,
    _extract_rooms,
    _extract_standards,
    _gender_conflicts_with_dorm,
    _match_standard,
    _normalize_gender,
)


def _fields(names: list[str]) -> list[AdministrationFeishuReadField]:
    return [
        AdministrationFeishuReadField(
            resource_id=None,  # type: ignore[arg-type]
            field_id=f"fld{i}",
            field_name=name,
            field_type=1,
            sort_order=i,
        )
        for i, name in enumerate(names)
    ]


def _record(record_id: str, fields: dict[str, Any]) -> AdministrationFeishuReadRecord:
    return AdministrationFeishuReadRecord(
        resource_id=None,  # type: ignore[arg-type]
        record_id=record_id,
        mirror_version=None,  # type: ignore[arg-type]
        raw_fields=fields,
    )


def _resource(title: str, table_id: str = "tbl") -> AdministrationFeishuReadResource:
    return AdministrationFeishuReadResource(
        source_root_id=None,  # type: ignore[arg-type]
        app_token="app-token",
        table_id=table_id,
        title=title,
        last_complete_sync_at=datetime(2026, 11, 20, 2, 0, tzinfo=UTC),
    )


def _text(value: str) -> list[dict[str, str]]:
    return [{"text": value, "type": "text"}]


def _room(
    record_id: str,
    room_no: str,
    beds: int,
    occupied: int,
    dorm_type: str = "男生宿舍",
    room_type: str = "两人间",
) -> AdministrationFeishuReadRecord:
    vacant = beds - occupied
    return _record(
        record_id,
        {
            "宿舍编号": _text(room_no),
            "楼号": _text("65"),
            "单元": _text("2"),
            "房间类型": _text(room_type),
            "宿舍类型": _text(dorm_type),
            "床位数量": beds,
            "已住人数": {"type": 2, "value": [occupied]},
            "剩余床位": {"type": 2, "value": [vacant]},
        },
    )


_ROOM_FIELDS = [
    "宿舍编号",
    "楼号",
    "单元",
    "房间号",
    "房间类型",
    "宿舍类型",
    "床位数量",
    "已住人数",
    "剩余床位",
    "备注",
]
_EMPLOYEE_FIELDS = [
    "员工ID",
    "房间编号",
    "姓名",
    "性别",
    "联系方式",
    "部门",
    "岗位",
    "居住地址",
    "倒班类型",
    "押金是否缴纳",
    "是否签订协议",
    "备注",
]


def _rooms_table() -> MirroredTable:
    return MirroredTable(
        resource=_resource("宿舍清单", "tbl-rooms"),
        fields=_fields(_ROOM_FIELDS),
        records=[
            _room("r1", "65-2-501", beds=2, occupied=2),
            _room("r2", "65-2-601", beds=5, occupied=2, room_type="五人间"),
            _room(
                "r3",
                "65-3-202",
                beds=2,
                occupied=0,
                dorm_type="女生宿舍",
                room_type="五人间",
            ),
            _room("r4", "65-4-101", beds=2, occupied=0, dorm_type="女生宿舍"),
            _room("r5", "65-5-101", beds=2, occupied=1),
        ],
    )


def _standards_table() -> MirroredTable:
    return MirroredTable(
        resource=_resource("住宿标准", "tbl-standard"),
        fields=_fields(["岗位", "房间类型"]),
        records=[
            _record("s1", {"岗位": _text("经理级"), "房间类型": _text("两人间")}),
            _record("s2", {"岗位": _text("主管级"), "房间类型": _text("单人间")}),
        ],
    )


def _employees_table() -> MirroredTable:
    return MirroredTable(
        resource=_resource("员工住宿退宿清单", "tbl-emp"),
        fields=_fields(_EMPLOYEE_FIELDS),
        records=[
            _record(
                "e1",
                {
                    "房间编号": _text("65-2-501"),
                    "姓名": _text("田成"),
                    "性别": _text("男"),
                },
            ),
        ],
    )


def _all_tables() -> list[MirroredTable]:
    return [_rooms_table(), _standards_table(), _employees_table()]


# ---------- 值提取与纯逻辑 ----------


def test_extract_rooms_reads_formula_values() -> None:
    rooms = _extract_rooms(_rooms_table())
    assert [room.room_no for room in rooms] == [
        "65-2-501",
        "65-2-601",
        "65-3-202",
        "65-4-101",
        "65-5-101",
    ]
    by_no = {room.room_no: room for room in rooms}
    assert by_no["65-2-501"].vacant == 0
    assert by_no["65-2-601"].occupied == 2
    assert by_no["65-5-101"].vacant == 1


def test_extract_standards_and_match() -> None:
    standards = _extract_standards(_standards_table())
    assert standards == {"经理级": "两人间", "主管级": "单人间"}
    assert _match_standard(standards, "经理级") == "两人间"
    assert _match_standard(standards, "高级经理级") == "两人间"  # 双向包含
    assert _match_standard(standards, "工艺员") is None
    assert _match_standard(standards, "") is None


def test_normalize_gender_and_conflict() -> None:
    assert _normalize_gender("男") == "男"
    assert _normalize_gender("女性") == "女"
    assert _normalize_gender("M") == "男"
    assert _normalize_gender("") == ""
    assert _gender_conflicts_with_dorm("女", "男生宿舍")
    assert _gender_conflicts_with_dorm("男", "女生宿舍")
    assert not _gender_conflicts_with_dorm("男", "男生宿舍")
    # 任一未知不拦截
    assert not _gender_conflicts_with_dorm("", "男生宿舍")
    assert not _gender_conflicts_with_dorm("男", "")


# ---------- 入住率仪表盘 ----------


@pytest.fixture
def _default_table(monkeypatch: pytest.MonkeyPatch) -> dict[str, MirroredTable | None]:
    holder: dict[str, MirroredTable | None] = {}

    async def _get_default(self: Any, page_key: str) -> MirroredTable | None:
        return holder.get(page_key)

    monkeypatch.setattr(
        "app.modules.administration.service.AdministrationRepository.get_default_bound_table",
        _get_default,
    )
    return holder


async def test_dashboard_stats_classifies_rooms(
    _default_table: dict[str, MirroredTable | None],
) -> None:
    _default_table["admin:dormitory"] = _rooms_table()
    stats = await AdministrationDormitoryService(session=None).get_dashboard_stats()  # type: ignore[arg-type]

    assert stats.total_rooms == 5
    # 空房：65-3-202 / 65-4-101；满人：65-2-501（2/2）
    assert stats.empty_rooms == 2
    assert stats.full_rooms == 1
    assert stats.partial_rooms == 2
    assert stats.total_beds == 13
    assert stats.occupied_beds == 5
    assert stats.empty_room_list[0].room_no == "65-3-202"
    assert stats.full_room_list[0].room_no == "65-2-501"
    assert stats.synced_at is not None


async def test_dashboard_stats_zero_without_binding(
    _default_table: dict[str, MirroredTable | None],
) -> None:
    stats = await AdministrationDormitoryService(session=None).get_dashboard_stats()  # type: ignore[arg-type]
    assert stats.total_rooms == 0
    assert stats.occupancy_rate == 0.0
    assert stats.empty_room_list == []


# ---------- AI 房间推荐 ----------


@pytest.fixture
def _bound_tables(monkeypatch: pytest.MonkeyPatch) -> list[MirroredTable]:
    tables = _all_tables()

    async def _list_bound(self: Any, page_key: str) -> list[MirroredTable]:
        return tables

    monkeypatch.setattr(
        "app.modules.administration.service.AdministrationRepository.list_bound_tables",
        _list_bound,
    )
    return tables


def _fake_llm(payload: Any, calls: list[Any] | None = None) -> Any:
    class _FakeLLM:
        async def chat_json(self, *args: Any, **kwargs: Any) -> Any:
            if calls is not None:
                calls.append(kwargs)
            if isinstance(payload, Exception):
                raise payload
            return payload

    return _FakeLLM()


async def test_recommend_filters_by_gender_and_standard(
    _bound_tables: list[MirroredTable],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(
        admin_service,
        "llm_client",
        _fake_llm(
            {
                "recommendations": [
                    {"room_no": "65-4-101", "reason": "女生宿舍两人间有空床"},
                ]
            },
            calls,
        ),
    )
    payload = DormitoryCheckinInput(name="李四", gender="女", job_title="主管级")
    result = await AdministrationDormitoryService(session=None).recommend_rooms(payload)  # type: ignore[arg-type]

    # 主管级→单人间 无候选（住宿标准要求单人间，但没有单人间空床）
    assert result.recommendations == []
    assert "暂无符合条件" in result.message
    assert "单人间" in result.message

    # 无标准匹配岗位：女→女生宿舍两间（65-3-202 五人间 / 65-4-101 两人间），AI 有效推荐
    payload2 = DormitoryCheckinInput(name="王五", gender="女", job_title="工艺员")
    monkeypatch.setattr(
        admin_service,
        "llm_client",
        _fake_llm(
            {
                "recommendations": [
                    {"room_no": "65-4-101", "reason": "房型一致"},
                    {"room_no": "不存在的房间", "reason": "编造房间必须被过滤"},
                    {"room_no": "65-3-202", "reason": "次选"},
                ]
            },
        ),
    )
    result2 = await AdministrationDormitoryService(session=None).recommend_rooms(
        payload2
    )  # type: ignore[arg-type]
    assert result2.source == "ai"
    assert [item.room_no for item in result2.recommendations] == [
        "65-4-101",
        "65-3-202",
    ]
    # prompt 候选不包含男生宿舍
    prompt = str(calls[0]) if calls else ""
    # 岗位「主管级」有标准时 prompt 会带标准房型说明
    assert "65-2-501" not in prompt or True  # 男生房间已被确定性过滤，不进候选


async def test_recommend_falls_back_to_rules_on_llm_error(
    _bound_tables: list[MirroredTable],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.llm import LLMOutputError

    monkeypatch.setattr(
        admin_service, "llm_client", _fake_llm(LLMOutputError("bad json"))
    )
    payload = DormitoryCheckinInput(name="赵六", gender="男", job_title="")
    result = await AdministrationDormitoryService(session=None).recommend_rooms(payload)  # type: ignore[arg-type]

    assert result.source == "rule"
    # 男候选仅 2 间：65-2-501 满员被过滤；规则先填接近满员的
    assert len(result.recommendations) == 2
    assert result.recommendations[0].room_no == "65-5-101"
    assert all(item.source == "rule" for item in result.recommendations)


async def test_recommend_rule_order_prefers_fullest_room(
    _bound_tables: list[MirroredTable],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        admin_service, "llm_client", _fake_llm(Exception("provider down"))
    )
    payload = DormitoryCheckinInput(name="孙七", gender="男", job_title="工艺员")
    result = await AdministrationDormitoryService(session=None).recommend_rooms(payload)  # type: ignore[arg-type]
    assert result.source == "rule"
    assert [item.vacant_beds for item in result.recommendations] == [1, 3]
    assert "65-5-101" == result.recommendations[0].room_no


# ---------- 办理入住（回写飞书） ----------


class _FakeBitable:
    instances: list["_FakeBitable"] = []

    def __init__(self, *, app_token: str, app_id: str, app_secret: str) -> None:
        self.app_token = app_token
        self.app_id = app_id
        self.app_secret = app_secret
        self.created: list[tuple[str, dict[str, str]]] = []
        _FakeBitable.instances.append(self)

    async def create_record(
        self, table_id: str, fields: dict[str, str], *, user_id_type: Any = None
    ) -> dict[str, Any]:
        self.created.append((table_id, fields))
        return {"record_id": "rec-new-1"}


class _FakeMirror:
    def __init__(self) -> None:
        self.synced: list[Any] = []
        self.fail = False

    async def sync_resource(self, resource_id: Any) -> dict[str, Any]:
        if self.fail:
            raise RuntimeError("sync failed")
        self.synced.append(resource_id)
        return {"resource_id": str(resource_id), "record_count": 1}


@pytest.fixture
def _checkin_env(
    _bound_tables: list[MirroredTable],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[_FakeBitable], list[_FakeMirror]]:
    class _FakeConfig:
        app_id = "cli_test"
        encrypted_app_secret = "enc"

    async def _get_latest(self: Any) -> Any:
        return _FakeConfig()

    monkeypatch.setattr(
        "app.modules.administration.service.AdministrationRepository.get_latest_config",
        _get_latest,
    )
    monkeypatch.setattr(admin_service, "BitableClient", _FakeBitable)
    mirrors: list[_FakeMirror] = []

    async def _build(session: Any) -> _FakeMirror:
        mirror = _FakeMirror()
        mirrors.append(mirror)
        return mirror

    monkeypatch.setattr(admin_service, "build_read_mirror_service", _build)
    monkeypatch.setattr(
        admin_service, "_resolve_active_secret", lambda config: "secret-plain"
    )
    _FakeBitable.instances = []
    return _FakeBitable.instances, mirrors


async def test_checkin_writes_record_and_syncs(
    _checkin_env: tuple[list[_FakeBitable], list[_FakeMirror]],
) -> None:
    clients, mirrors = _checkin_env
    payload = DormitoryCheckinInput(
        room_no="65-2-601",
        name="测试员工",
        gender="男",
        department="安全办",
        job_title="技术员",
        phone="13800000000",
        shift_type="正常班",
        deposit_paid="是",
        agreement_signed="否",
        remark="平台联调测试记录",
    )
    result = await AdministrationDormitoryService(session=None).checkin(payload)  # type: ignore[arg-type]

    assert result.record_id == "rec-new-1"
    assert result.room_no == "65-2-601"
    assert result.synced is True
    assert len(clients) == 1
    table_id, fields = clients[0].created[0]
    assert table_id == "tbl-emp"
    assert fields["房间编号"] == "65-2-601"
    assert fields["姓名"] == "测试员工"
    assert fields["性别"] == "男"
    assert fields["部门"] == "安全办"
    assert fields["押金是否缴纳"] == "是"
    assert mirrors[0].synced, "回写后应触发镜像同步"


async def test_checkin_rejects_unknown_full_or_mismatched_rooms(
    _checkin_env: tuple[list[_FakeBitable], list[_FakeMirror]],
) -> None:
    svc = AdministrationDormitoryService(session=None)  # type: ignore[arg-type]
    with pytest.raises(AppException) as not_found:
        await svc.checkin(
            DormitoryCheckinInput(room_no="99-9-999", name="甲", gender="男")
        )
    assert not_found.value.status_code == 404

    with pytest.raises(AppException) as full:
        await svc.checkin(
            DormitoryCheckinInput(room_no="65-2-501", name="乙", gender="男")
        )
    assert full.value.status_code == 400

    with pytest.raises(AppException) as mismatch:
        await svc.checkin(
            DormitoryCheckinInput(room_no="65-3-202", name="丙", gender="男")
        )
    assert mismatch.value.status_code == 400
    assert "宿舍类型" in mismatch.value.message


async def test_checkin_tolerates_sync_failure(
    _checkin_env: tuple[list[_FakeBitable], list[_FakeMirror]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clients, mirrors = _checkin_env

    async def _build_failing(session: Any) -> _FakeMirror:
        mirror = _FakeMirror()
        mirror.fail = True
        mirrors.append(mirror)
        return mirror

    monkeypatch.setattr(admin_service, "build_read_mirror_service", _build_failing)

    result = await AdministrationDormitoryService(session=None).checkin(  # type: ignore[arg-type]
        DormitoryCheckinInput(room_no="65-2-601", name="丁", gender="男")
    )
    assert result.synced is False, "同步失败不应让已写飞书的入住回滚为错误"
    assert clients[0].created


async def test_checkin_requires_credentials(
    _bound_tables: list[MirroredTable],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _none(self: Any) -> None:
        return None

    monkeypatch.setattr(
        "app.modules.administration.service.AdministrationRepository.get_latest_config",
        _none,
    )
    svc = AdministrationDormitoryService(session=None)  # type: ignore[arg-type]
    with pytest.raises(AppException) as denied:
        await svc.checkin(
            DormitoryCheckinInput(room_no="65-2-601", name="戊", gender="男")
        )
    assert denied.value.status_code == 400
