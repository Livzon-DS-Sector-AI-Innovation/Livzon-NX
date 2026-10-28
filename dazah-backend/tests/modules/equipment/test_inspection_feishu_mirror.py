"""设备巡检飞书镜像同步测试。"""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

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


@pytest.mark.parametrize("sorted_search", [False, True])
async def test_page_fetch_preserves_pagination_and_incremental_watermark(
    sorted_search: bool,
) -> None:
    first = {"record_id": "first", "last_modified_time": 200}
    second = {"record_id": "second", "last_modified_time": 150}
    older = {"record_id": "older", "last_modified_time": 80}
    fetch = AsyncMock(
        side_effect=[
            {"items": [first], "has_more": True, "page_token": "page-2", "total": 3},
            {
                "items": [second, older],
                "has_more": True,
                "page_token": "page-3",
                "total": 3,
            },
        ]
    )
    client = SimpleNamespace(
        app_token="test-base",
        client=SimpleNamespace(request=fetch),
        search_records_page=fetch,
    )
    result = await mirror._fetch_pages(
        client, "test-table", sort_by_modified=sorted_search, stop_before_ms=100
    )
    assert result == [first, second]
    assert fetch.await_count == 2
    kwargs = fetch.await_args_list[1].kwargs
    assert (kwargs["params"] if sorted_search else kwargs)["page_token"] == "page-2"


async def test_device_without_number_keeps_pending_status(
    db_session: AsyncSession,
) -> None:
    record_id = f"empty-{uuid4().hex}"
    db_session.add(
        EquipmentInspectionFeishuDevice(
            record_id=record_id, equipment_name="尚未编号的设备", equipment_no=None
        )
    )
    await db_session.flush()
    rows = await mirror.list_devices(db_session, "201-1")
    record = next(row for row in rows["items"] if row["record_id"] == record_id)
    assert record["equipment_no"] is None
    assert record["today_status"] == "pending"
    assert record["in_ledger"] is False


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
    results = await mirror.sync_all(db_session, "201-1", incremental=False)
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
    await mirror.sync_all(db_session, "201-1", incremental=False)

    # 第二轮：今日巡检的行在飞书消失（被拆分），历史表仍在
    async def fetch_history_only(client: Any, table_id: str, **kwargs: Any):
        if table_id == "tbl_history":
            return [_item("rec_hist_1", _fields(), modified)]
        return []

    monkeypatch.setattr(mirror, "_fetch_pages", fetch_history_only)
    await mirror.sync_all(db_session, "201-1", incremental=False)

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
    await mirror.sync_table(db_session, "201-1", "history", incremental=True)
    state = await mirror._get_state(db_session, "201-1", "history")
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
    results = await mirror.sync_all(db_session, "201-1", incremental=True)
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

    results = await mirror.sync_all(db_session, "201-1", incremental=True)
    for key in ("today", "history", "devices"):
        assert "error" in results[key]
        assert "同步中断已回滚" in results[key]["error"]
        state = await mirror._get_state(db_session, "201-1", key)
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


async def test_sync_wrong_table_id_error_hints_view_id(
    db_session, monkeypatch
) -> None:
    """WrongTableId 失败信息附带视图 ID 提示，便于定位 Table ID 配置错误。"""
    await _enable_config(monkeypatch)

    async def fake_fetch(client: Any, table_id: str, **kwargs: Any):
        raise RuntimeError(
            "Feishu API error: code=1254004, msg=WrongTableId, "
            "path=/bitable/v1/apps/app/tables/vewihhse0W/records/search"
        )

    monkeypatch.setattr(mirror, "_fetch_pages", fake_fetch)
    results = await mirror.sync_all(db_session, "201-1", incremental=False)
    assert "视图 ID" in (results["today"]["error"] or "")


# ---------- 今日口径（北京时间） ----------


def test_cst_today_resolves_utc_cst_boundary() -> None:
    """UTC 与北京日期不同的窗口（CST 00:00–08:00），“今日”按 CST 取。"""
    # UTC 2026-10-11 19:00 = CST 2026-10-12 03:00（UTC 容器 date.today() 为 10-11）
    assert mirror._cst_today(datetime(2026, 10, 11, 19, 0, tzinfo=UTC)) == date(
        2026, 10, 12
    )
    # UTC 2026-10-12 01:00 = CST 10:00，同日
    assert mirror._cst_today(datetime(2026, 10, 12, 1, 0, tzinfo=UTC)) == date(
        2026, 10, 12
    )
    # UTC 2026-10-12 15:59 = CST 23:59；再过一分钟 CST 跨日
    assert mirror._cst_today(datetime(2026, 10, 12, 15, 59, tzinfo=UTC)) == date(
        2026, 10, 12
    )
    assert mirror._cst_today(datetime(2026, 10, 12, 16, 0, tzinfo=UTC)) == date(
        2026, 10, 13
    )


async def test_today_summary_uses_cst_today(db_session, monkeypatch) -> None:
    """今日进度按北京时间口径统计（回归：容器 UTC 在 CST 凌晨取错日期）。"""
    monkeypatch.setattr(mirror, "_cst_today", lambda: date(2026, 10, 12))
    db_session.add(
        EquipmentInspectionFeishuDevice(
            record_id="dev_a", equipment_name="方锥混合机", equipment_no="XT-A"
        )
    )
    db_session.add(
        EquipmentInspectionFeishuDevice(
            record_id="dev_b", equipment_name="摇摆颗粒机", equipment_no="XT-B"
        )
    )
    db_session.add(
        EquipmentInspectionFeishuRecord(
            source="today",
            record_id="rec_today_a",
            record_date=date(2026, 10, 12),
            equipment_no="XT-A",
            has_abnormal=True,
        )
    )
    db_session.add(
        EquipmentInspectionFeishuRecord(
            source="today",
            record_id="rec_today_b",
            record_date=date(2026, 10, 11),
            equipment_no="XT-B",
            has_abnormal=True,
        )
    )
    await db_session.flush()

    summary = await mirror.today_summary(db_session, "201-1")
    assert summary == {
        "date": date(2026, 10, 12),
        "total_devices": 2,
        "inspected": 1,
        "abnormal": 1,
        "am_inspected": 0,
        "pm_inspected": 0,
    }


async def test_list_devices_today_status_uses_cst_today(
    db_session, monkeypatch
) -> None:
    """设备清单今日状态按北京时间口径（回归：容器 UTC 在 CST 凌晨取错日期）。"""
    monkeypatch.setattr(mirror, "_cst_today", lambda: date(2026, 10, 12))
    db_session.add(
        EquipmentInspectionFeishuDevice(
            record_id="dev_a", equipment_name="方锥混合机", equipment_no="XT-A"
        )
    )
    db_session.add(
        EquipmentInspectionFeishuDevice(
            record_id="dev_b", equipment_name="摇摆颗粒机", equipment_no="XT-B"
        )
    )
    db_session.add(
        EquipmentInspectionFeishuRecord(
            source="today",
            record_id="rec_today_a",
            record_date=date(2026, 10, 12),
            equipment_no="XT-A",
            has_abnormal=False,
        )
    )
    db_session.add(
        EquipmentInspectionFeishuRecord(
            source="today",
            record_id="rec_today_b",
            record_date=date(2026, 10, 11),
            equipment_no="XT-B",
            has_abnormal=True,
        )
    )
    await db_session.flush()

    result = await mirror.list_devices(db_session, "201-1")
    assert result["date"] == date(2026, 10, 12)
    devices = {d["equipment_no"]: d for d in result["items"]}
    assert devices["XT-A"]["today_status"] == "inspected"
    # 昨日的记录（即使异常）不计入今日状态
    assert devices["XT-B"]["today_status"] == "pending"
    # 最近巡检日期：今日已巡取当天，未巡取最近一次
    assert devices["XT-A"]["last_inspected_date"] == date(2026, 10, 12)
    assert devices["XT-B"]["last_inspected_date"] == date(2026, 10, 11)


async def test_today_status_matches_unnumbered_devices_by_name(
    db_session, monkeypatch
) -> None:
    """无编号设备按名称匹配今日记录；飞书名称粘连的汇总行不产生误匹配。"""
    monkeypatch.setattr(mirror, "_cst_today", lambda: date(2026, 10, 12))
    db_session.add(
        EquipmentInspectionFeishuDevice(
            record_id="dev_nonum", equipment_name="尾气塔", equipment_no=None
        )
    )
    db_session.add(
        EquipmentInspectionFeishuDevice(
            record_id="dev_num", equipment_name="方锥混合机", equipment_no="XT-A"
        )
    )
    # 无编号设备的今日记录（同样没有编号，只有名称）
    db_session.add(
        EquipmentInspectionFeishuRecord(
            source="today",
            record_id="rec_nonum",
            record_date=date(2026, 10, 12),
            equipment_name="尾气塔",
            equipment_no=None,
            has_abnormal=True,
        )
    )
    # 名称粘连的汇总行：匹配不到任何设备，不得计入
    db_session.add(
        EquipmentInspectionFeishuRecord(
            source="today",
            record_id="rec_garbage",
            record_date=date(2026, 10, 12),
            equipment_name="A101A102尾气塔泵类",
            equipment_no=None,
        )
    )
    await db_session.flush()

    summary = await mirror.today_summary(db_session, "201-1")
    assert summary == {
        "date": date(2026, 10, 12),
        "total_devices": 2,
        "inspected": 1,
        "abnormal": 1,
        "am_inspected": 0,
        "pm_inspected": 0,
    }

    devices = {
        d["equipment_name"]: d
        for d in (await mirror.list_devices(db_session, "201-1"))["items"]
    }
    assert devices["尾气塔"]["today_status"] == "abnormal"
    assert devices["方锥混合机"]["today_status"] == "pending"
    # 无编号设备同样带最近巡检日期；从未出现的设备为空
    assert devices["尾气塔"]["last_inspected_date"] == date(2026, 10, 12)
    assert devices["方锥混合机"]["last_inspected_date"] is None


async def test_today_summary_counts_am_pm_completion(
    db_session, monkeypatch
) -> None:
    """上午/下午完成数：对应时段任一检查项有值即计入；基于有效记录行。"""
    monkeypatch.setattr(mirror, "_cst_today", lambda: date(2026, 10, 12))
    db_session.add(
        EquipmentInspectionFeishuDevice(record_id="dev_am", equipment_no="XT-AM")
    )
    db_session.add(
        EquipmentInspectionFeishuDevice(record_id="dev_pm", equipment_no="XT-PM")
    )
    db_session.add(
        EquipmentInspectionFeishuRecord(
            source="today",
            record_id="rec_am",
            record_date=date(2026, 10, 12),
            equipment_no="XT-AM",
            am_clean="√",
            process_status="有效记录",
        )
    )
    db_session.add(
        EquipmentInspectionFeishuRecord(
            source="today",
            record_id="rec_pm",
            record_date=date(2026, 10, 12),
            equipment_no="XT-PM",
            pm_clean="√",
            process_status="有效记录",
        )
    )
    await db_session.flush()

    summary = await mirror.today_summary(db_session, "201-1")
    assert summary["inspected"] == 2
    assert summary["am_inspected"] == 1
    assert summary["pm_inspected"] == 1


async def test_list_records_today_keeps_latest_valid_row_per_device(
    db_session, monkeypatch
) -> None:
    """今日列表：排除关联行，同设备多条有效提交只保留最新一条。"""
    monkeypatch.setattr(mirror, "_cst_today", lambda: date(2026, 10, 12))
    common = {
        "source": "today",
        "record_date": date(2026, 10, 12),
        "equipment_no": "XT-D",
    }
    # 飞书分组/引用产生的关联行（无处理状态），修改时间最新也不得展示
    db_session.add(
        EquipmentInspectionFeishuRecord(
            record_id="rec_link",
            last_modified_at=datetime(2026, 10, 12, 12, 0, tzinfo=UTC),
            **common,
        )
    )
    db_session.add(
        EquipmentInspectionFeishuRecord(
            record_id="rec_valid_old",
            process_status="有效记录",
            last_modified_at=datetime(2026, 10, 12, 10, 0, tzinfo=UTC),
            **common,
        )
    )
    db_session.add(
        EquipmentInspectionFeishuRecord(
            record_id="rec_valid_new",
            process_status="有效记录",
            last_modified_at=datetime(2026, 10, 12, 11, 0, tzinfo=UTC),
            **common,
        )
    )
    await db_session.flush()

    rows, total = await mirror.list_records(
        db_session, workshop_code="201-1", source="today"
    )
    assert total == 1
    assert [r.record_id for r in rows] == ["rec_valid_new"]


async def test_list_records_today_falls_back_without_process_status(
    db_session, monkeypatch
) -> None:
    """表未启用“处理状态”字段时全部行有效，仍按设备保留最新一条。"""
    monkeypatch.setattr(mirror, "_cst_today", lambda: date(2026, 10, 12))
    for record_id, hour in (("rec_e_old", 8), ("rec_e_new", 12)):
        db_session.add(
            EquipmentInspectionFeishuRecord(
                source="today",
                record_id=record_id,
                record_date=date(2026, 10, 12),
                equipment_no="XT-E",
                last_modified_at=datetime(2026, 10, 12, hour, 0, tzinfo=UTC),
            )
        )
    # 无编号行（含名称粘连的汇总行）排在有编号设备之后
    db_session.add(
        EquipmentInspectionFeishuRecord(
            source="today",
            record_id="rec_garbage",
            record_date=date(2026, 10, 12),
            equipment_name="A101A102尾气塔泵类",
            last_modified_at=datetime(2026, 10, 12, 7, 0, tzinfo=UTC),
        )
    )
    await db_session.flush()

    rows, total = await mirror.list_records(
        db_session, workshop_code="201-1", source="today"
    )
    assert total == 2
    assert [r.record_id for r in rows] == ["rec_e_new", "rec_garbage"]


async def test_list_records_today_excludes_split_merged_rows(
    db_session, monkeypatch
) -> None:
    """多设备合并填写的原始行（处理状态=已拆分）不进入今日列表。

    飞书侧把粘连多设备的合并行拆成逐设备有效行后，原始行标记为已拆分；
    当天只剩已拆分行时同样不得回退把合并行当有效行展示。
    """
    monkeypatch.setattr(mirror, "_cst_today", lambda: date(2026, 10, 12))
    common = {"source": "history", "record_date": date(2026, 10, 12)}
    for record_id, no in (("rec_dev_a", "XT-A"), ("rec_dev_b", "XT-B")):
        db_session.add(
            EquipmentInspectionFeishuRecord(
                record_id=record_id,
                equipment_no=no,
                process_status="有效记录",
                **common,
            )
        )
    db_session.add(
        EquipmentInspectionFeishuRecord(
            record_id="rec_merged_split",
            equipment_name="A101A102A103A104A",
            process_status="已拆分",
            **common,
        )
    )
    # 当天只有已拆分原始行的车间：回退逻辑不得把合并行当有效行展示
    db_session.add(
        EquipmentInspectionFeishuRecord(
            workshop_code="103",
            record_id="rec_only_split",
            equipment_name="酸化罐 1酸化罐 2",
            process_status="已拆分",
            **common,
        )
    )
    await db_session.flush()

    rows, total = await mirror.list_records(
        db_session, workshop_code="201-1", source="today"
    )
    assert [r.record_id for r in rows] == ["rec_dev_a", "rec_dev_b"]
    assert total == 2

    only_split_rows, only_split_total = await mirror.list_records(
        db_session, workshop_code="103", source="today"
    )
    assert only_split_rows == []
    assert only_split_total == 0


async def test_list_records_today_source_only_returns_cst_today_rows(
    db_session, monkeypatch
) -> None:
    """「今日巡检」只返回当天（CST）有效记录：今日表滞留的旧日期行、
    被拆分的合并原始行都不出现。"""
    monkeypatch.setattr(mirror, "_cst_today", lambda: date(2026, 10, 12))
    db_session.add(
        EquipmentInspectionFeishuRecord(
            source="today",
            record_id="rec_today_cur",
            record_date=date(2026, 10, 12),
            equipment_no="XT-A",
            process_status="有效记录",
        )
    )
    db_session.add(
        EquipmentInspectionFeishuRecord(
            source="today",
            record_id="rec_today_stale",
            record_date=date(2026, 10, 11),
            equipment_no="XT-B",
            process_status="有效记录",
        )
    )
    db_session.add(
        EquipmentInspectionFeishuRecord(
            source="history",
            record_id="rec_history_cur",
            record_date=date(2026, 10, 12),
            equipment_no="XT-C",
            process_status="有效记录",
        )
    )
    # 多设备合并填写后被拆分的原始行：日期仍为当天、名称粘连，不得进入今日列表
    db_session.add(
        EquipmentInspectionFeishuRecord(
            source="history",
            record_id="rec_history_split",
            record_date=date(2026, 10, 12),
            equipment_name="酸化罐 1酸化罐 2酸化罐 3",
            process_status="已拆分",
        )
    )
    await db_session.flush()

    # 今日口径按日期取数：当天有效记录无论落在今日表还是历史表都展示，
    # 已拆分的合并原始行被排除
    rows, total = await mirror.list_records(
        db_session, workshop_code="201-1", source="today"
    )
    assert [r.record_id for r in rows] == ["rec_today_cur", "rec_history_cur"]
    assert total == 2

    # history 来源不套用今日口径，但已拆分的合并原始行同样不展示
    # （回归：历史列表出现 199 字符合并行撑宽表格）
    history_rows, history_total = await mirror.list_records(
        db_session, workshop_code="201-1", source="history"
    )
    assert [r.record_id for r in history_rows] == ["rec_history_cur"]
    assert history_total == 1

    # 缺省 source 不受今日口径限制（设备详情抽屉按设备聚合全部记录）
    _, all_total = await mirror.list_records(db_session, workshop_code="201-1")
    assert all_total == 3


# ---------- 车间隔离 ----------


async def test_sync_scopes_records_by_workshop(db_session, monkeypatch) -> None:
    """各车间各自配置各自同步：镜像行、设备清单与今日进度互不串台。"""
    from app.modules.equipment.schemas.inspection import (
        EquipmentInspectionFeishuConfigUpdateRequest,
    )

    await feishu_config.update_config(
        db_session,
        "101-1",
        EquipmentInspectionFeishuConfigUpdateRequest(
            app_id="cli_ws",
            app_secret="secret_ws",
            app_token="bascn_ws101",
            today_table_id="tbl_ws_today",
            history_table_id="tbl_ws_history",
            device_table_id="tbl_ws_devices",
        ),
    )
    modified = int(
        datetime(2026, 10, 12, 9, 0, tzinfo=UTC).timestamp() * 1000
    )

    async def fake_fetch(client: Any, table_id: str, **kwargs: Any):
        if table_id == "tbl_ws_devices":
            return [
                _item(
                    "rec_ws_dev_1",
                    {
                        "设备名称": [{"text": "压滤机", "type": "text"}],
                        "设备编号": [{"text": "XT2-1-1-001", "type": "text"}],
                    },
                    modified,
                )
            ]
        return [_item("rec_ws_today_1", _fields(), modified)]

    monkeypatch.setattr(mirror, "_fetch_pages", fake_fetch)
    results = await mirror.sync_all(db_session, "101-1", incremental=False)
    assert results["today"] == {"synced": 1, "total": 1}
    assert results["devices"] == {"synced": 1, "total": 1}

    summary_101 = await mirror.today_summary(db_session, "101-1")
    summary_201 = await mirror.today_summary(db_session, "201-1")
    assert summary_101["total_devices"] == 1
    assert summary_201["total_devices"] == 0

    devices_101 = await mirror.list_devices(db_session, "101-1")
    assert [d["equipment_no"] for d in devices_101["items"]] == ["XT2-1-1-001"]

    # 环境变量回退仅作用于默认车间：未配置车间视为未启用
    assert await feishu_config.is_mirror_enabled(db_session, "101-1") is True
    with pytest.MonkeyPatch.context() as env_patch:
        for key in (
            "EQUIPMENT_FEISHU_APP_ID",
            "EQUIPMENT_FEISHU_APP_SECRET",
            "EQUIPMENT_FEISHU_BITABLE_APP_TOKEN",
        ):
            env_patch.setattr(feishu_config.settings, key, "")
        assert await feishu_config.is_mirror_enabled(db_session, "203") is False


async def test_list_records_excludes_split_raw_rows(db_session) -> None:
    """巡检记录/聚合口径不展示多设备合并填写的原始行（处理状态=已拆分）。

    回归：通用列表仅今日口径过滤已拆分行，历史 Tab 会显示 199 字符的
    合并原始行并撑宽表格；未启用该字段的表（NULL）不受影响。
    """
    for record_id, status, name in (
        ("rec_normal", "有效记录", "糖化罐2#"),
        ("rec_split", "已拆分", "A101A102A103"),
        ("rec_legacy", None, "legacy 设备"),
    ):
        db_session.add(
            EquipmentInspectionFeishuRecord(
                workshop_code="201-1",
                source="history",
                record_id=record_id,
                record_date=date(2026, 10, 13),
                equipment_name=name,
                process_status=status,
            )
        )
    await db_session.flush()

    items, total = await mirror.list_records(
        db_session, workshop_code="201-1", source="history"
    )
    assert total == 2
    assert {item.record_id for item in items} == {"rec_normal", "rec_legacy"}

    # 显式按状态筛选时仍可查到原始行（保留审计口径）
    explicit, explicit_total = await mirror.list_records(
        db_session, workshop_code="201-1", source="history", process_status="已拆分"
    )
    assert explicit_total == 1
    assert [item.record_id for item in explicit] == ["rec_split"]


# ---------- 设备自动注册进台账（出码/报修依据） ----------


async def test_sync_devices_auto_registers_ledger_equipment(
    db_session, monkeypatch
) -> None:
    """镜像同步的设备应自动注册进设备台账（幂等，按编号去重）。"""
    from sqlalchemy import select as sa_select

    from app.modules.equipment.models.equipment import Equipment

    await _enable_config(monkeypatch)
    modified = int(datetime(2026, 10, 28, 10, 0, tzinfo=UTC).timestamp() * 1000)

    async def fake_fetch(client: Any, table_id: str, **kwargs: Any):
        return [
            _item(
                f"rec_dev_{i}",
                {
                    "设备名称": [{"text": f"离心机{i}", "type": "text"}],
                    "设备编号": [{"text": f"XT9-9-9-{i:03d}", "type": "text"}],
                },
                modified,
            )
            for i in range(3)
        ]

    monkeypatch.setattr(mirror, "_fetch_pages", fake_fetch)

    results = await mirror.sync_all(db_session, "201-1", incremental=False)
    assert results["devices"]["synced"] == 3

    ledger = (
        (
            await db_session.execute(
                sa_select(Equipment).where(Equipment.workshop_code == "201-1")
            )
        )
        .scalars()
        .all()
    )
    assert {(e.name, e.equipment_no) for e in ledger} >= {
        ("离心机0", "XT9-9-9-000"),
        ("离心机1", "XT9-9-9-001"),
        ("离心机2", "XT9-9-9-002"),
    }

    # 再同步一次：编号去重，台账不重复增长
    await mirror.sync_all(db_session, "201-1", incremental=False)
    ledger_again = (
        (
            await db_session.execute(
                sa_select(Equipment).where(Equipment.workshop_code == "201-1")
            )
        )
        .scalars()
        .all()
    )
    assert len(ledger_again) == len(ledger)
