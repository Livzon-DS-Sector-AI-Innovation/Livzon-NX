"""特殊作业关键作业自动判定规则测试（逐类覆盖 8 类作业）。"""

import pytest

from app.modules.safety.service.special_operation_critical import (
    CRITICAL_LEVELS_BY_TYPE,
    TYPE_LABELS,
    evaluate_critical,
    evaluate_from_notes,
    is_hazardous_confined_level,
)

ALL_TYPES = [
    "hot_work",
    "height_work",
    "lifting",
    "confined_space",
    "blind_plate",
    "excavation",
    "road_breaking",
    "temporary_electricity",
]


def test_rule_table_covers_all_eight_types() -> None:
    """8 类特殊作业都必须显式登记关键作业级别，避免漏掉高处/吊装等类型。"""
    assert set(CRITICAL_LEVELS_BY_TYPE) == set(ALL_TYPES)
    assert set(TYPE_LABELS) == set(ALL_TYPES)


@pytest.mark.parametrize("operation_type", ALL_TYPES)
@pytest.mark.parametrize("level", ["special", "grade1"])
def test_special_and_grade1_are_critical_for_every_type(
    operation_type: str, level: str
) -> None:
    """特级/一级在任意作业类型下都是关键作业（动火、高处、吊装、受限空间…）。"""
    decision = evaluate_critical(
        operation_type=operation_type, operation_level=level
    )
    assert decision.is_critical is True
    assert decision.reason
    assert TYPE_LABELS[operation_type] in decision.reason


@pytest.mark.parametrize("operation_type", ALL_TYPES)
@pytest.mark.parametrize("level", ["grade2", "not_applicable"])
def test_lower_levels_are_not_critical_by_level_alone(
    operation_type: str, level: str
) -> None:
    decision = evaluate_critical(
        operation_type=operation_type, operation_level=level
    )
    assert decision.is_critical is False
    assert decision.reason is None


def test_reason_text_names_type_and_level() -> None:
    assert (
        evaluate_critical(
            operation_type="height_work", operation_level="grade1"
        ).reason
        == "一级高处作业"
    )
    assert (
        evaluate_critical(operation_type="lifting", operation_level="special").reason
        == "特级吊装作业"
    )


def test_environment_and_upgrade_flags_force_critical() -> None:
    explosion = evaluate_critical(
        operation_type="hot_work",
        operation_level="grade2",
        explosion_proof=True,
    )
    assert explosion.is_critical is True
    assert explosion.reason == "涉及防爆区"

    upgraded = evaluate_critical(
        operation_type="lifting",
        operation_level="grade2",
        upgraded=True,
    )
    assert upgraded.is_critical is True
    assert upgraded.reason == "作业提级管理"


def test_hazardous_confined_space_is_critical() -> None:
    decision = evaluate_critical(
        operation_type="confined_space",
        operation_level="not_applicable",
        hazardous_confined=True,
    )
    assert decision.is_critical is True
    assert "受限空间" in (decision.reason or "")


def test_reasons_combine_for_multiple_hits() -> None:
    decision = evaluate_critical(
        operation_type="hot_work",
        operation_level="grade1",
        explosion_proof=True,
        upgraded=True,
    )
    assert decision.is_critical is True
    assert decision.reason == "一级动火作业、涉及防爆区、作业提级管理"


def test_evaluate_from_notes_parses_feishu_marks() -> None:
    notes = "施工单位：机修；是否提级管理：是；是否周六日节假日：否；是否防爆区：是"
    decision = evaluate_from_notes(
        operation_type="hot_work", operation_level="grade2", notes=notes
    )
    assert decision.is_critical is True
    assert "涉及防爆区" in (decision.reason or "")
    assert "作业提级管理" in (decision.reason or "")

    plain = evaluate_from_notes(
        operation_type="hot_work",
        operation_level="grade2",
        notes="施工单位：机修；是否提级管理：否；是否防爆区：否",
    )
    assert plain.is_critical is False


def test_is_hazardous_confined_level_matches_source_text() -> None:
    assert is_hazardous_confined_level("涉及有毒有害、易燃、易爆（受限空间）")
    assert not is_hazardous_confined_level("不涉及有毒有害、易燃、易爆（受限空间）")
    assert not is_hazardous_confined_level(None)
