"""设备巡检飞书镜像同步测试。"""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.equipment.models.inspection_feishu_config import (
    EquipmentInspectionFeishuConfig,
)
from app.modules.equipment.models.inspection_feishu_mirror import (
    EquipmentInspectionFeishuDevice,
    EquipmentInspectionFeishuRecord,
)
from app.modules.equipment.service import inspection_feishu_config as feishu_config
from app.modules.equipment.service import inspection_feishu_mirror as mirror


@pytest.fixture(autouse=True)
async def _clear_config_rows(db_session: AsyncSession) -> None:
    """清空配置与镜像表，保证环境变量回退路径和行数断言不被残留数据干扰。"""
    await db_session.execute(delete(EquipmentInspectionFeishuConfig))
    await db_session.execute(delete(EquipmentInspectionFeishuRecord))
    await db_session.execute(delete(EquipmentInspectionFeishuDevice))
    await db_session.commit()


def _fields(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "日期": 1791475200000,  # 2026-10-09 (北京时间)
        "设备名称": [{"text": "方锥混合机", "type": "text"}],
        "设备编号": [{"text": "XT1-1-1-129", "type": "text"}],
        "上午清洁": "√",
        "下午清洁": "√",
        "其他异常情况（具体描述，可另附页）": "无",
        "处理状态": "有效记录",
    }
    base.update(overrides)
    return base


# ---------- 字段规范化 ----------


def test_normalize_extracts_common_fields() -> None:
    values = mirror.normalize_record_fields(_fields())
    assert values["record_date"] == date(2026, 10, 9)
    assert values["equipment_name"] == "方锥混合机"
    assert values["equipment_no"] == "XT1-1-1-129"
    assert values["anomaly_note"] == "无"
    assert values["process_status"] == "有效记录"
    assert values["am_clean"] == "√"
    assert values["pm_clean"] == "√"
    assert values["has_abnormal"] is False


def test_normalize_matches_typo_column_and_abnormal() -> None:
    # 今日巡检表的错别字列「外表吴克坚变色…」也能按关键字识别为外表面项
    values = mirror.normalize_record_fields(
        _fields(**{"下午设备外表吴克坚变色痕迹及污渍": "×"})
    )
    assert values["pm_surface"] == "×"
    assert values["has_abnormal"] is True


def test_normalize_treats_unknown_option_id_as_empty() -> None:
    values = mirror.normalize_record_fields(_fields(**{"上午密封": "optQYbBdcd"}))
    assert values["am_sealing"] is None
    assert values["has_abnormal"] is False


def test_normalize_unmatched_columns_kept_in_raw() -> None:
    values = mirror.normalize_record_fields(
        _fields(**{"自定义新列": [{"text": "备注", "type": "text"}]})
    )
    assert "自定义新列" not in values


# ---------- 同步执行（mock 飞书拉取） ----------


class _FakeRecord(dict):
    pass


def _item(record_id: str, fields: dict[str, Any], modified_ms: int) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "fields": fields,
        "last_modified_time": modified_ms,
    }


async def _patch_fetch(monkeypatch: pytest.MonkeyPatch, items: list[dict[str, Any]]):
    async def fake_fetch(client: Any, table_id: str, **kwargs: Any):
        return items

    monkeypatch.setattr(mirror, "_fetch_pages", fake_fetch)


async def _enable_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(feishu_config.settings, "EQUIPMENT_FEISHU_APP_ID", "cli_test")
    monkeypatch.setattr(
        feishu_config.settings, "EQUIPMENT_FEISHU_APP_SECRET", "secret"
    )
    monkeypatch.setattr(
        feishu_config.settings, "EQUIPMENT_FEISHU_BITABLE_APP_TOKEN", "test_token"
    )
    monkeypatch.setattr(
        feishu_config.settings, "EQUIPMENT_FEISHU_BITABLE_TODAY_TABLE_ID", "tbl_today"
    )
    monkeypatch.setattr(
        feishu_config.settings,
        "EQUIPMENT_FEISHU_BITABLE_HISTORY_TABLE_ID",
        "tbl_history",
    )
    monkeypatch.setattr(
        feishu_config.settings,
        "EQUIPMENT_FEISHU_BITABLE_DEVICE_TABLE_ID",
        "tbl_devices",
    )


async def test_sync_all_persists_three_sources(db_session, monkeypatch) -> None:
    await _enable_config(monkeypatch)
    modified = int(
        datetime(2026, 10, 10, 10, 0, tzinfo=UTC).timestamp() * 1000
    )

    async def fake_fetch(client: Any, table_id: str, **kwargs: Any):
        if table_id == "tbl_today":
            return [_item("rec_today_1", _fields(), modified)]
        if table_id == "tbl_history":
            return [
                _item("rec_hist_1", _fields(**{"处理状态": "已拆分"}), modified),
                _item("rec_hist_2", _fields(), modified),
            ]
        return [
            _item(f"rec_dev_{i}", {
                "设备名称": [{"text": f"设备{i}", "type": "text"}],
                "设备编号": [{"text": f"XT1-1-1-{i:03d}", "type": "text"}],
            }, modified)
            for i in range(3)
        ]

    monkeypatch.setattr(mirror, "_fetch_pages", fake_fetch)
    results = await mirror.sync_all(db_session, incremental=False)
    assert results["today"] == {"synced": 1, "total": 1}
    assert results["history"] == {"synced": 2, "total": 2}
    assert results["devices"] == {"synced": 3, "total": 3}


async def test_full_sync_reconciles_only_same_source(
    db_session, monkeypatch
) -> None:
    """历史表全量对账不得删除今日表的行（回归：跨 source 误删）。"""
    await _enable_config(monkeypatch)
    modified = int(
        datetime(2026, 10, 10, 11, 0, tzinfo=UTC).timestamp() * 1000
    )

    async def fetch_with_today(client: Any, table_id: str, **kwargs: Any):
        if table_id == "tbl_today":
            return [_item("rec_today_1", _fields(), modified)]
        if table_id == "tbl_history":
            return [_item("rec_hist_1", _fields(), modified)]
        return []

    monkeypatch.setattr(mirror, "_fetch_pages", fetch_with_today)
    await mirror.sync_all(db_session, incremental=False)

    # 第二轮：今日巡检的行在飞书消失（被拆分），历史表仍在
    async def fetch_history_only(client: Any, table_id: str, **kwargs: Any):
        if table_id == "tbl_history":
            return [_item("rec_hist_1", _fields(), modified)]
        return []

    monkeypatch.setattr(mirror, "_fetch_pages", fetch_history_only)
    await mirror.sync_all(db_session, incremental=False)

    from sqlalchemy import select

    from app.modules.equipment.models.inspection_feishu_mirror import (
        EquipmentInspectionFeishuRecord,
    )

    rows = (
        await db_session.execute(
            select(
                EquipmentInspectionFeishuRecord.source,
                EquipmentInspectionFeishuRecord.record_id,
            ).where(EquipmentInspectionFeishuRecord.is_deleted == False)  # noqa: E712
        )
    ).all()
    # 今日行被对账删除（飞书侧已无），历史行保留
    assert set(rows) == {("history", "rec_hist_1")}


async def test_incremental_uses_watermark_state(db_session, monkeypatch) -> None:
    """增量同步后水位写入 sync_state。"""
    await _enable_config(monkeypatch)
    modified = int(
        datetime(2026, 10, 10, 12, 0, tzinfo=UTC).timestamp() * 1000
    )
    await _patch_fetch(
        monkeypatch, [_item("rec_hist_9", _fields(), modified)]
    )
    await mirror.sync_table(db_session, "history", incremental=True)
    state = await mirror._get_state(db_session, "history")
    assert state.last_status == "success"
    assert state.total_rows == 1
    assert state.last_synced_at is not None


async def test_sync_truncates_overlong_text_to_column_width(
    db_session, monkeypatch
) -> None:
    """飞书自由文本超过镜像列宽时截断入库，不得让同步整体失败。"""
    await _enable_config(monkeypatch)
    long_name = "超" * 250
    long_status = "状" * 40
    modified = int(
        datetime(2026, 10, 10, 13, 0, tzinfo=UTC).timestamp() * 1000
    )
    await _patch_fetch(
        monkeypatch,
        [_item("rec_long_1", _fields(**{
            "设备名称": [{"text": long_name, "type": "text"}],
            "处理状态": long_status,
        }), modified)],
    )
    results = await mirror.sync_all(db_session, incremental=True)
    assert results["history"].get("error") is None

    from sqlalchemy import select

    from app.modules.equipment.models.inspection_feishu_mirror import (
        EquipmentInspectionFeishuRecord,
    )

    row = (
        await db_session.execute(
            select(EquipmentInspectionFeishuRecord).where(
                EquipmentInspectionFeishuRecord.record_id == "rec_long_1",
                EquipmentInspectionFeishuRecord.source == "history",
            )
        )
    ).scalar_one()
    assert len(row.equipment_name) == 200
    assert len(row.process_status) == 20
    # 原文保留在 raw_fields
    assert row.raw_fields["处理状态"] == long_status


async def test_sync_all_records_failure_on_unexpected_db_error(
    db_session, monkeypatch
) -> None:
    """数据库级异常中止事务时：回滚整轮、三表统一记失败，不向上抛 500。"""
    await _enable_config(monkeypatch)
    modified = int(
        datetime(2026, 10, 10, 14, 0, tzinfo=UTC).timestamp() * 1000
    )
    await _patch_fetch(
        monkeypatch, [_item("rec_any", _fields(), modified)]
    )

    async def broken_upsert(db: Any, source: str, item: dict[str, Any]) -> None:
        raise RuntimeError("value too long for type character varying(200)")

    monkeypatch.setattr(mirror, "_upsert_record", broken_upsert)

    results = await mirror.sync_all(db_session, incremental=True)
    for key in ("today", "history", "devices"):
        assert "error" in results[key]
        assert "同步中断已回滚" in results[key]["error"]
        state = await mirror._get_state(db_session, key)
        assert state.last_status == "failed"
        assert "同步中断已回滚" in (state.last_message or "")


# ---------- 字段规范化分支 ----------


def test_text_value_variants() -> None:
    assert mirror._text_value(None) is None
    assert mirror._text_value("") is None
    assert mirror._text_value("  ") is None
    rich = [{"text": "混合", "type": "text"}, {"text": "机"}]
    assert mirror._text_value(rich) == "混合机"
    assert mirror._text_value(["纯", "文本段"]) == "纯文本段"
    assert mirror._text_value(123) == "123"
    assert mirror._text_value([{"text": "  ", "type": "text"}]) is None


def test_date_value_variants() -> None:
    from datetime import date

    assert mirror._date_value(None) is None
    # 毫秒时间戳（北京时间 2026-10-09）
    assert mirror._date_value(1791475200000) == date(2026, 10, 9)
    # ISO 字符串（含 Z 与 +00:00 两种写法）
    assert mirror._date_value("2026-10-08") == date(2026, 10, 8)
    assert mirror._date_value("2026-10-08T16:00:00Z") == date(2026, 10, 8)
    assert mirror._date_value("2026-10-08T16:00:00+00:00") == date(2026, 10, 8)
    # 无效与空值
    assert mirror._date_value("") is None
    assert mirror._date_value("不是日期") is None


def test_datetime_value_variants() -> None:
    from datetime import datetime

    value = mirror._datetime_value(1791475200000)
    assert value is not None and value.year == 2026
    assert mirror._datetime_value("2026-10-08T16:00:00Z") == datetime(
        2026, 10, 8, 16, 0, tzinfo=mirror.UTC
    )
    assert mirror._datetime_value(None) is None
    assert mirror._datetime_value("垃圾") is None
    assert mirror._datetime_value("") is None


def test_normalize_covers_date_note_and_status() -> None:
    values = mirror.normalize_record_fields(
        _fields(
            **{
                "日期": "2026-09-30",
                "其他异常情况": "渗漏",
                "处理状态": "已拆分",
            }
        )
    )
    assert values["record_date"] is not None
    assert values["anomaly_note"] == "渗漏"
    assert values["process_status"] == "已拆分"


def test_normalize_empty_fields_dict() -> None:
    assert mirror.normalize_record_fields({})["has_abnormal"] is False
