from datetime import UTC, datetime
from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.modules.safety.feishu import bitable_handler as handler

SimpleNamespace: Any = _SimpleNamespace


def test_person_select_attachment_and_time_value_extractors() -> None:
    assert handler._extract_person_info(None) == {"name": "", "id": "", "email": ""}
    assert handler._extract_person_info(
        {
            "users": [
                {
                    "userId": "u_1",
                    "name": " 张三 ",
                    "email": " zhang@example.com ",
                }
            ]
        }
    ) == {"name": "张三", "id": "u_1", "email": "zhang@example.com"}
    assert handler._extract_person_info({"users": []})["name"] == ""
    assert (
        handler._extract_person_info(
            [{"id": "ou_1", "name": "李四", "email": "li@example.com"}]
        )["id"]
        == "ou_1"
    )
    assert handler._extract_person_info("王五")["name"] == "王五"
    assert handler._extract_person_info([42])["name"] == "42"
    assert handler._is_open_id_like("ou_abc") is True
    assert handler._is_open_id_like("张三") is False

    assert handler._extract_select_values(["生产部", "", "质量部"]) == "生产部, 质量部"
    assert handler._extract_select_values("生产部") == "生产部"
    assert handler._extract_select_values(1) == ""
    assert handler._extract_attachments(
        [{"file_token": "f1", "name": "a.jpg"}, "ignored"]
    ) == [{"file_token": "f1", "name": "a.jpg"}]
    assert handler._extract_attachments("bad") == []
    assert (
        handler._extract_rich_text([{"type": "text", "text": "阀门"}, "泄漏"])
        == "阀门泄漏"
    )
    assert handler._extract_rich_text(7) == "7"

    moment = datetime(2026, 7, 27, tzinfo=UTC)
    milliseconds = handler._datetime_to_ms(moment)
    assert handler._ms_to_datetime(milliseconds) == moment
    assert handler._ms_to_datetime(str(milliseconds)) == moment
    assert handler._ms_to_datetime("bad") is None
    assert handler._datetime_to_ms(None) == ""


def test_bitable_fields_map_to_valid_hazard_values() -> None:
    moment_ms = 1785081600000
    mapped = handler._map_bitable_fields(
        {
            "检查日期": moment_ms,
            "检查人员": [{"id": "ou_1", "name": "张三"}],
            "检查人员.部门": ["生产部", "安全部"],
            "检查类别": ["日常检查"],
            "隐患描述": [{"type": "text", "text": "阀门泄漏"}],
            "责任部门": "生产部",
            "整改责任人": {"users": [{"userId": "u_2"}]},
            "隐患分类（AI）": "物的不安全状态",
            "隐患类别（AI）": "设备设施",
            "隐患级别（AI）": "重大隐患",
            "缺陷图片": [{"file_token": "f1", "name": "leak.jpg"}],
            "整改后图片": [],
            "整改期限": str(moment_ms),
            "部门负责人复核": "已同意",
            "分管领导复核": "未同意",
            "检查人员复核": "",
            "整改建议（AI）": "更换阀门",
            "未知字段": "忽略",
        }
    )

    assert mapped["discovered_by_name"] == "张三"
    assert mapped["rectification_responsible_person_name"] == "u_2"
    assert mapped["inspector_department"] == "生产部, 安全部"
    assert mapped["description"] == "阀门泄漏"
    assert "hazard_type" not in mapped
    assert "hazard_category" not in mapped
    assert "hazard_level" not in mapped
    assert mapped["verify_level_1_status"] == "approved"
    assert mapped["verify_level_2_status"] == "rejected"
    assert "verify_level_3_status" not in mapped
    assert mapped["deadline"].tzinfo == UTC
    assert '"file_token": "f1"' in mapped["defect_photos"]
    assert mapped["rectification_photos"] is None


def test_hazard_model_maps_back_to_bitable_with_field_types(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        handler,
        "_field_type_cache",
        {
            "隐患分类（AI）": 3,
            "隐患类别（AI）": 4,
            "隐患级别（AI）": 3,
        },
    )
    moment = datetime(2026, 7, 27, tzinfo=UTC)
    hazard: Any = SimpleNamespace(
        hazard_no="HZ-001",
        discovered_at=moment,
        discovered_by_name="张三",
        inspector_department="生产部",
        inspection_category="日常检查",
        description="阀门泄漏",
        department="生产部",
        rectification_responsible_person_name="李四",
        hazard_type="unsafe_condition",
        hazard_category="equipment",
        hazard_level="major",
        key_defect="密封失效",
        major_hazard_basis="可能导致泄漏",
        defect_photos=None,
        rectification_photos=None,
        rectification_reply="已更换",
        deadline=moment,
        actual_completion_date=None,
        verify_level_1_status="approved",
        verify_level_2_status="pending",
        verify_level_3_status="rejected",
        corrective_preventive_measures="定期点检",
    )

    mapped = handler._map_model_to_bitable(hazard)

    assert "隐患编号" not in mapped
    assert mapped["隐患分类（AI）"] == "物的不安全状态"
    assert mapped["隐患类别（AI）"] == ["设备设施"]
    assert mapped["隐患级别（AI）"] == "重大隐患"
    assert mapped["部门负责人复核"] == "已同意"
    assert mapped["检查人员复核"] == "未同意"
    assert mapped["检查日期"] == handler._datetime_to_ms(moment)


@pytest.mark.parametrize(
    ("level_one", "level_two", "level_three", "hazard_level", "expected"),
    [
        ("rejected", None, None, "general", "rejected"),
        ("approved", None, "approved", "general", "closed"),
        ("approved", None, None, "general", "level2_approved"),
        ("approved", "approved", None, "major", "level2_approved"),
        ("approved", None, None, "major", "level1_approved"),
        (None, None, None, "major", None),
    ],
)
def test_rectification_status_derivation(
    level_one: Any,
    level_two: Any,
    level_three: Any,
    hazard_level: Any,
    expected: Any,
) -> None:
    assert (
        handler._compute_rectification_status(
            level_one,
            level_two,
            level_three,
            hazard_level,
        )
        == expected
    )


def test_action_values_resolve_field_names_json_and_option_ids(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        handler,
        "_option_map_cache",
        {
            "隐患级别（AI）": {"opt_major": "重大隐患"},
            "检查类别": {"daily": "日常检查", "special": "专项检查"},
        },
    )
    monkeypatch.setattr(
        handler,
        "_field_type_cache",
        {"隐患级别（AI）": 3, "检查类别": 4, "缺陷图片": 17},
    )
    fields = handler._convert_after_value_to_fields(
        [
            {"field_id": "f1", "field_value": "opt_major"},
            {"field_id": "f2", "field_value": '["daily", "special", "missing"]'},
            {
                "field_id": "f3",
                "field_value": '[{"file_token":"token","name":"a.jpg"}]',
            },
            {"field_id": "unknown", "field_value": "ignored"},
        ],
        {"f1": "隐患级别（AI）", "f2": "检查类别", "f3": "缺陷图片"},
    )

    assert fields["隐患级别（AI）"] == "重大隐患"
    assert fields["检查类别"] == ["日常检查", "专项检查", "missing"]
    assert fields["缺陷图片"][0]["file_token"] == "token"
    assert handler._resolve_option_ids("raw", {}, 3) == "raw"
    assert handler._resolve_option_ids("unknown", {"known": "名称"}, 3) == "unknown"
    assert handler._match_target(handler._TARGET_FILE_TOKEN, handler._TARGET_TABLE_ID)
    assert not handler._match_target("wrong", handler._TARGET_TABLE_ID)


@pytest.mark.anyio
async def test_person_resolution_uses_identity_then_safe_fallbacks(
    monkeypatch: Any,
) -> None:
    class FakeResolver:
        def __init__(self: Any, session: Any) -> None:
            pass

        async def _find_user_by_user_id(self: Any, user_id: Any) -> Any:
            if user_id == "u_known":
                return SimpleNamespace(
                    id="db-id",
                    feishu_open_id="ou_global",
                    name="张三",
                )
            return None

        async def _find_user_by_email(self: Any, email: Any) -> Any:
            return None

        async def _find_user_by_name(self: Any, name: Any) -> Any:
            return None

    from app.modules.safety.feishu import identity_resolver

    monkeypatch.setattr(identity_resolver, "IdentityResolver", FakeResolver)

    assert await handler._resolve_person(
        object(),
        {"users": [{"userId": "u_known", "name": "张三"}]},
    ) == ("db-id", "ou_global", "张三")
    assert await handler._resolve_person(
        object(),
        {"users": [{"userId": "u_missing", "name": "李四"}]},
    ) == (None, "u_missing", "李四")
    assert await handler._resolve_person(
        object(),
        {"users": [{"userId": "u_missing", "name": "ou_display"}]},
    ) == (None, "u_missing", "u_missing")
    assert await handler._resolve_person(
        object(),
        None,
        existing_name="已有姓名",
    ) == (None, "", "已有姓名")
    assert await handler._resolve_person(object(), None) == (None, "", "飞书用户")


@pytest.mark.anyio
async def test_event_deduplication_and_field_fallback_are_resilient(
    monkeypatch: Any,
) -> None:
    redis: Any = SimpleNamespace(set=AsyncMock(return_value=True))
    monkeypatch.setattr(handler, "redis_client", redis)
    assert await handler._is_duplicate("changed", "rec1") is False
    redis.set.return_value = False
    assert await handler._is_duplicate("changed", "rec1") is True
    redis.set.side_effect = RuntimeError("redis unavailable")
    assert await handler._is_duplicate("changed", "rec1") is False

    bitable: Any = SimpleNamespace(
        get_record=AsyncMock(return_value={"隐患描述": "API值"})
    )
    assert await handler._get_fields_fallback(
        bitable,
        "rec1",
        {"隐患描述": "事件值"},
    ) == {"隐患描述": "事件值"}
    assert await handler._get_fields_fallback(bitable, "rec1", {}) == {
        "隐患描述": "API值"
    }
