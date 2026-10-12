"""FA 排产校验器测试：规则逐条 + 约束/检修存取。

排产表构造沿用 test_fermentation_block_period_handoff 的 FA 块格式；
稳态基线模拟「每日一放一移」的三罐轮转（302A→303A→304A），各规则
测试在其上做定向变异后断言问题清单。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pytest

from app.modules.production import fermentation_board_service as board
from app.modules.production import schedule_validation_service as svc
from app.modules.production.tank_maintenance_models import TankMaintenance

NOW = datetime(2026, 12, 10, 12, 0)
BLOCK_TITLE = "2026年11月27日～2026年12月26日103车间FA450T罐排产"
PREV_TITLE = "2026年10月27日～2026年11月26日103车间FA450T罐排产"
TANKS = ["302A", "303A", "304A"]
CONSTRAINTS = {
    "standard_cycle_hours": 61.0,
    "cycle_tolerance_hours": 4.0,
    "max_cycle_hours": 72.0,
    "turnaround_hours": 8.0,
    "monthly_dump_target": 26,
}


# ═══════════════════ 测试排产表构造 ═══════════════════


def _steady_days() -> dict[date, dict[str, Any]]:
    """稳态基线：Nov 28 起每日移种，种子在前一日，放罐在移种后第 3 天。

    放罐批次数 26（Dec 1～Dec 26），与 CONSTRAINTS 的月目标一致；
    Dec 24～26 移种的批次放罐落在下一份表（覆盖范围外，不报）。
    """
    days: dict[date, dict[str, Any]] = {}

    def ensure(day: date) -> dict[str, Any]:
        return days.setdefault(
            day, {"seed": None, "ferm": None, "dump": None, "note": ""}
        )

    for idx in range(29):  # Nov 28 .. Dec 26
        ferm_day = date(2026, 11, 28) + timedelta(days=idx)
        batch = f"FA263{idx + 1:02d}"
        tank = TANKS[idx % 3]
        ensure(ferm_day - timedelta(days=1))["seed"] = batch
        ensure(ferm_day)["ferm"] = (batch, tank)
        dump_day = ferm_day + timedelta(days=3)
        if dump_day <= date(2026, 12, 26):
            ensure(dump_day)["dump"] = (batch, tank)
    return days


def _fa_block_rows(
    title: str, days: dict[date, dict[str, Any]]
) -> list[list[Any]]:
    dates = sorted(days)
    columns = []
    for day in dates:
        entry = days[day]
        seed = entry["seed"]
        ferm = entry["ferm"]
        dump = entry["dump"]
        columns.append(
            {
                "day": day.day,
                "seed": seed or "",
                "seed_tank": entry.get("seed_tank") or "",
                "seed_time": "20:00" if seed else "",
                "ferm": ferm[0] if ferm else "",
                "tank": ferm[1] if ferm else "",
                "ferm_time": "21:00" if ferm else "",
                "dump": dump[0] if dump else "",
                "dump_tank": dump[1] if dump else "",
                "dump_time": "10:00" if dump else "",
                "note": entry.get("note", ""),
            }
        )
    width = len(columns) + 2
    return [
        [title] + [""] * (width - 1),
        ["", "日期"] + [c["day"] for c in columns],
        ["时间", "罐号"] + [""] * len(columns),
        ["种子罐", ""] + [c["seed"] for c in columns],
        ["罐号", ""] + [c["seed_tank"] for c in columns],
        ["接种时间", ""] + [c["seed_time"] for c in columns],
        ["发酵罐", ""] + [c["ferm"] for c in columns],
        ["罐号", ""] + [c["tank"] for c in columns],
        ["移种时间", ""] + [c["ferm_time"] for c in columns],
        ["放罐", ""] + [c["dump"] for c in columns],
        ["罐号", ""] + [c["dump_tank"] for c in columns],
        ["放罐时间", ""] + [c["dump_time"] for c in columns],
        ["备注", ""] + [c["note"] for c in columns],
        [""] * width,
    ]


def _copy_days(days: dict[date, dict[str, Any]]) -> dict[date, dict[str, Any]]:
    return {
        day: {
            "seed": entry["seed"],
            "ferm": entry["ferm"],
            "dump": entry["dump"],
            "note": entry.get("note", ""),
        }
        for day, entry in days.items()
    }


def _validate(
    days: dict[date, dict[str, Any]],
    *,
    title: str = BLOCK_TITLE,
    previous_rows: list[list[Any]] | None = None,
    constraints: dict[str, Any] | None = CONSTRAINTS,
    maintenance: list[dict[str, Any]] | None = None,
    now: datetime = NOW,
) -> dict[str, Any]:
    return svc.validate_schedule_rows(
        _fa_block_rows(title, days),
        previous_rows=previous_rows,
        constraints=constraints,
        maintenance=maintenance,
        now=now,
    )


def _rules(report: dict[str, Any]) -> list[str]:
    return [issue["rule"] for issue in report["issues"]]


# ═══════════════════ 稳态与范围 ═══════════════════


def test_steady_schedule_clean() -> None:
    report = _validate(_steady_days())
    assert report["issues"] == []
    assert report["summary"] == {"warn": 0, "info": 0}
    assert report["scope"]["from"] == "2026-12-10"
    assert report["coverage"] == {"start": "2026-11-27", "end": "2026-12-26"}


def test_no_constraints_reports_skipped_checks() -> None:
    report = _validate(_steady_days(), constraints=None)
    assert report["summary"]["warn"] == 0
    assert "constraint_missing" in _rules(report)
    text = next(
        i["text"] for i in report["issues"] if i["rule"] == "constraint_missing"
    )
    assert "未配置" in text


def test_issues_before_scope_are_ignored() -> None:
    days = _copy_days(_steady_days())
    # Dec 1 的移种时间损坏：早于校验起点（Dec 10），不报
    days[date(2026, 12, 1)]["ferm"] = ("FA26304", "302A")
    days[date(2026, 12, 1)]["note"] = ""
    rows = _fa_block_rows(BLOCK_TITLE, days)
    for row in rows:
        if row and row[0] == "移种时间":
            row[2 + 4] = "21:00:00"  # Dec 1 列（第 5 列）真实时间类型串
    report = svc.validate_schedule_rows(
        rows, constraints=CONSTRAINTS, now=NOW
    )
    assert "time_cell" not in _rules(report)


def test_no_blocks_returns_message() -> None:
    report = svc.validate_schedule_rows(
        [["无关内容"]], constraints=CONSTRAINTS, now=NOW
    )
    assert report["issues"] == []
    assert "无法校验" in (report.get("message") or "")


# ═══════════════════ A 类硬错误 ═══════════════════


def test_time_cell_unparsed_and_missing() -> None:
    days = _copy_days(_steady_days())
    rows = _fa_block_rows(BLOCK_TITLE, days)
    dates = sorted(days)
    dec12_index = dates.index(date(2026, 12, 12))
    dec13_index = dates.index(date(2026, 12, 13))
    for row in rows:
        if row and row[0] == "移种时间":
            row[2 + dec12_index] = "21:00:00"  # Excel 真实时间类型串，无法识别
        if row and row[0] == "放罐时间":
            row[2 + dec13_index] = ""  # 缺失
    report = svc.validate_schedule_rows(
        rows, constraints=CONSTRAINTS, now=NOW
    )
    time_issues = [i for i in report["issues"] if i["rule"] == "time_cell"]
    assert len(time_issues) == 2
    assert any("无法识别" in i["text"] for i in time_issues)
    assert any("时间为空" in i["text"] for i in time_issues)


def test_tank_invalid() -> None:
    days = _copy_days(_steady_days())
    ferm_day = date(2026, 12, 12)
    dump_day = date(2026, 12, 15)
    batch, _tank = days[ferm_day]["ferm"]
    days[ferm_day]["ferm"] = (batch, "302B")
    days[dump_day]["dump"] = (batch, "302B")
    report = _validate(days)
    tank_issues = [i for i in report["issues"] if i["rule"] == "tank_invalid"]
    assert len(tank_issues) == 2  # 发酵罐行 + 放罐行
    assert all(i["level"] == "warn" for i in tank_issues)


def test_tank_missing() -> None:
    days = _copy_days(_steady_days())
    ferm_day = date(2026, 12, 12)
    batch, _tank = days[ferm_day]["ferm"]
    days[ferm_day]["ferm"] = (batch, "")
    report = _validate(days)
    assert "tank_invalid" in _rules(report)


def test_tank_overlap() -> None:
    days = _copy_days(_steady_days())
    # Dec 14（303A 槽位）改排 302A：与 Dec 13 的 302A 批次
    # （Dec 16 才放罐）重叠
    batch, _tank = days[date(2026, 12, 14)]["ferm"]
    days[date(2026, 12, 14)]["ferm"] = (batch, "302A")
    dump_batch, _dump_tank = days[date(2026, 12, 17)]["dump"]
    days[date(2026, 12, 17)]["dump"] = (dump_batch, "302A")
    report = _validate(days)
    assert "tank_overlap" in _rules(report)
    overlap = next(i for i in report["issues"] if i["rule"] == "tank_overlap")
    assert overlap["tank_no"] == "302A"
    assert overlap["level"] == "warn"


def test_turnaround_short() -> None:
    constraints = {**CONSTRAINTS, "turnaround_hours": 10.0}  # 实际间隔 9h
    report = _validate(_steady_days(), constraints=constraints)
    assert "turnaround_short" in _rules(report)
    assert "tank_overlap" not in _rules(report)


def test_dump_before_inoculate() -> None:
    days = _copy_days(_steady_days())
    # 把 Dec 16 的放罐（Dec 13 移种批次的）挪到 Dec 8 → 日期倒挂
    moved = days[date(2026, 12, 16)]["dump"]
    days[date(2026, 12, 16)]["dump"] = days[date(2026, 12, 8)]["dump"]
    days[date(2026, 12, 8)]["dump"] = moved
    report = _validate(days)
    assert "dump_before_inoculate" in _rules(report)


def test_dump_tank_mismatch() -> None:
    days = _copy_days(_steady_days())
    batch, tank = days[date(2026, 12, 15)]["dump"]
    other = "303A" if tank != "303A" else "304A"
    days[date(2026, 12, 15)]["dump"] = (batch, other)
    report = _validate(days)
    assert "dump_tank_mismatch" in _rules(report)


def test_ferm_without_dump() -> None:
    days = _copy_days(_steady_days())
    days[date(2026, 12, 16)]["dump"] = None  # Dec 13 移种批次的放罐
    report = _validate(days)
    assert "ferm_without_dump" in _rules(report)
    issue = next(i for i in report["issues"] if i["rule"] == "ferm_without_dump")
    assert issue["batch_no"] == "FA26316"


def test_orphan_dump() -> None:
    days = _copy_days(_steady_days())
    _batch, tank = days[date(2026, 12, 15)]["dump"]
    days[date(2026, 12, 15)]["dump"] = ("FA26999", tank)
    report = _validate(days)
    assert "orphan_dump" in _rules(report)


def test_ferm_without_seed_in_current_file() -> None:
    days = _copy_days(_steady_days())
    days[date(2026, 12, 14)]["seed"] = None  # Dec 15 移种批次的种子
    report = _validate(days)
    assert "ferm_without_seed" in _rules(report)


def test_seed_transfer_gap_overage() -> None:
    days = _copy_days(_steady_days())
    # 把 Dec 9 的种子挪到 Dec 8：FA26313（Dec 10 移种）菌龄 2 天超龄
    days[date(2026, 12, 8)]["seed"] = days[date(2026, 12, 9)]["seed"]
    days[date(2026, 12, 9)]["seed"] = None
    report = _validate(days)
    assert "seed_transfer_gap" in _rules(report)
    issue = next(
        i for i in report["issues"] if i["rule"] == "seed_transfer_gap"
    )
    assert issue["batch_no"] == "FA26313"
    assert "超龄" in issue["text"]


def test_duplicate_inoculation() -> None:
    days = _copy_days(_steady_days())
    batch, tank = days[date(2026, 12, 17)]["ferm"]
    days[date(2026, 12, 17)]["ferm"] = ("FA26314", tank)  # 已于 Dec 11 移种
    report = _validate(days)
    assert "duplicate_inoculation" in _rules(report)
    issue = next(
        i for i in report["issues"] if i["rule"] == "duplicate_inoculation"
    )
    assert issue["batch_no"] == "FA26314"


def test_date_column_duplicate() -> None:
    days = _copy_days(_steady_days())
    rows = _fa_block_rows(BLOCK_TITLE, days)
    # 日期行标签在第二格（["", "日期", ...]），直接定位第一块的日期行
    dates = sorted(days)
    rows[1][2 + dates.index(date(2026, 12, 13))] = 12  # 与前一日重复
    report = svc.validate_schedule_rows(
        rows, constraints=CONSTRAINTS, now=NOW
    )
    assert "date_column_anomaly" in _rules(report)
    issue = next(
        i for i in report["issues"] if i["rule"] == "date_column_anomaly"
    )
    assert "重复" in issue["text"]


def test_date_column_missing() -> None:
    days = _copy_days(_steady_days())
    del days[date(2026, 12, 14)]  # 整列缺失
    report = _validate(days)
    assert "date_column_anomaly" in _rules(report)
    issue = next(
        i for i in report["issues"] if i["rule"] == "date_column_anomaly"
    )
    assert any(k in issue["text"] for k in ("缺少", "重复", "无法识别"))


def test_date_column_bad_value() -> None:
    days = _copy_days(_steady_days())
    rows = _fa_block_rows(BLOCK_TITLE, days)
    dates = sorted(days)
    rows[1][2 + dates.index(date(2026, 12, 15))] = "X"  # 无法识别的日期值
    report = svc.validate_schedule_rows(
        rows, constraints=CONSTRAINTS, now=NOW
    )
    assert "date_column_anomaly" in _rules(report)
    texts = [
        i["text"] for i in report["issues"] if i["rule"] == "date_column_anomaly"
    ]
    assert any("无法识别" in t for t in texts)  # 坏值列同时报缺列，属预期


# ═══════════════════ 检修联动 ═══════════════════


def test_maintenance_conflict_without_recovery_date() -> None:
    maintenance = [
        {
            "tank_no": "302A",
            "reason": "染菌检查",
            "started_at": "2026-12-10T08:00:00",
            "expected_recovery_date": None,
        }
    ]
    report = _validate(_steady_days(), maintenance=maintenance)
    conflicts = [i for i in report["issues"] if i["rule"] == "maintenance_conflict"]
    assert conflicts  # Dec 13/16/19/22/25 的 302A 移种均提醒补填恢复日期
    assert all("补填" in i["text"] for i in conflicts)


def test_maintenance_conflict_only_within_window() -> None:
    maintenance = [
        {
            "tank_no": "302A",
            "reason": "染菌检查",
            "started_at": "2026-12-10T08:00:00",
            "expected_recovery_date": "2026-12-12",
        }
    ]
    report = _validate(_steady_days(), maintenance=maintenance)
    conflicts = [i for i in report["issues"] if i["rule"] == "maintenance_conflict"]
    # 仅 Dec 10 的 302A 移种落在窗口内（Dec 13 起已晚于恢复日）
    assert len(conflicts) == 1
    assert conflicts[0]["date"] == "2026-12-10"
    assert "窗口内" in conflicts[0]["text"]


def test_disruption_hole_is_legal_with_maintenance() -> None:
    """染菌停罐一天的扰动形态：废种留痕 + 无放罐日，检修窗口内不误报。"""
    days = _copy_days(_steady_days())
    # Dec 12（304A 槽位）不进罐：种子 Dec 11 留在表上（废种留痕）
    days[date(2026, 12, 12)]["ferm"] = None
    days[date(2026, 12, 15)]["dump"] = None  # 该批次的放罐随移种一并取消
    window = [
        {
            "tank_no": "304A",
            "reason": "染菌检查",
            "started_at": "2026-12-12T08:00:00",
            "expected_recovery_date": "2026-12-13",
        }
    ]
    report = _validate(days, maintenance=window)
    assert report["summary"]["warn"] == 0  # 扰动合法，无硬错误
    assert "seed_discarded" not in _rules(report)  # 检修窗口内静默
    assert "no_dump_day" not in _rules(report)  # 洞的成因（Dec 12 少一次移种）已知


def test_disruption_hole_reported_without_maintenance() -> None:
    """无检修标注时：废种留痕以 info 提示确认，不判错。

    洞（无放罐日）的成因是废种时不再重复提示；若种子一并未排
    （成因不可见），改为以无放罐日提示。
    """
    days = _copy_days(_steady_days())
    days[date(2026, 12, 12)]["ferm"] = None
    days[date(2026, 12, 15)]["dump"] = None
    report = _validate(days, maintenance=None)
    assert report["summary"]["warn"] == 0
    rules = _rules(report)
    assert "seed_discarded" in rules
    assert "no_dump_day" not in rules  # 洞的成因（废种）已有提示
    discarded = next(i for i in report["issues"] if i["rule"] == "seed_discarded")
    assert discarded["level"] == "info"
    assert discarded["batch_no"] == "FA26315"

    days2 = _copy_days(days)
    days2[date(2026, 12, 11)]["seed"] = None  # 种子一并未排
    report2 = _validate(days2, maintenance=None)
    rules2 = _rules(report2)
    assert "seed_discarded" not in rules2
    assert "no_dump_day" in rules2
    hole = next(i for i in report2["issues"] if i["rule"] == "no_dump_day")
    assert hole["level"] == "info"
    assert hole["date"] == "2026-12-15"


# ═══════════════════ 跨周期衔接 ═══════════════════


def _prev_rows_with_inflight() -> list[list[Any]]:
    """上一份表：Nov 24 移种 302A，放罐预计 Nov 27（落在本表覆盖内）。"""
    days: dict[date, dict[str, Any]] = {
        date(2026, 11, 23): {"seed": "FA26298", "ferm": None, "dump": None, "note": ""},
        date(2026, 11, 24): {
            "seed": None,
            "ferm": ("FA26298", "302A"),
            "dump": None,
            "note": "",
        },
    }
    return _fa_block_rows(PREV_TITLE, days)


def test_inflight_continuity_missing_dump() -> None:
    report = _validate(_steady_days(), previous_rows=_prev_rows_with_inflight())
    assert "inflight_continuity" in _rules(report)
    issue = next(
        i for i in report["issues"] if i["rule"] == "inflight_continuity"
    )
    assert issue["batch_no"] == "FA26298"


def test_inflight_continuity_satisfied_by_current_dump() -> None:
    days = _copy_days(_steady_days())
    days[date(2026, 11, 27)]["dump"] = ("FA26298", "302A")
    report = _validate(days, previous_rows=_prev_rows_with_inflight())
    assert "inflight_continuity" not in _rules(report)
    # 放罐批号的移种在上一份表：不算孤儿
    assert "orphan_dump" not in _rules(report)


# ═══════════════════ B 类约束判定 ═══════════════════


def test_cycle_over_limit_is_warn() -> None:
    days = _copy_days(_steady_days())
    rows = _fa_block_rows(BLOCK_TITLE, days)
    dec13_index = sorted(days).index(date(2026, 12, 13))
    for row in rows:
        if row and row[0] == "放罐时间":
            row[2 + dec13_index] = "23:00"  # 周期 74h > 上限 72h
    report = svc.validate_schedule_rows(
        rows, constraints=CONSTRAINTS, now=NOW
    )
    assert "cycle_over_limit" in _rules(report)
    assert "cycle_deviation" not in _rules(report)


def test_cycle_deviation_within_limit_is_info() -> None:
    constraints = {**CONSTRAINTS, "cycle_tolerance_hours": 2.0}
    days = _copy_days(_steady_days())
    rows = _fa_block_rows(BLOCK_TITLE, days)
    dec13_index = sorted(days).index(date(2026, 12, 13))
    for row in rows:
        if row and row[0] == "放罐时间":
            row[2 + dec13_index] = "13:00"  # 延长培养 3h：64h，超容差但在上限内
    report = svc.validate_schedule_rows(
        rows, constraints=constraints, now=NOW
    )
    assert "cycle_deviation" in _rules(report)
    assert "cycle_over_limit" not in _rules(report)
    issue = next(i for i in report["issues"] if i["rule"] == "cycle_deviation")
    assert issue["level"] == "info"


def test_dump_target_deviation_is_info() -> None:
    constraints = {**CONSTRAINTS, "monthly_dump_target": 20}
    report = _validate(_steady_days(), constraints=constraints)
    assert "dump_target_deviation" in _rules(report)
    issue = next(
        i for i in report["issues"] if i["rule"] == "dump_target_deviation"
    )
    assert issue["level"] == "info"


# ═══════════════════ C 类提示 ═══════════════════


def test_nonstandard_time_is_info() -> None:
    days = _copy_days(_steady_days())
    rows = _fa_block_rows(BLOCK_TITLE, days)
    dec12_index = sorted(days).index(date(2026, 12, 12))
    for row in rows:
        if row and row[0] == "移种时间":
            row[2 + dec12_index] = "20:30"
    report = svc.validate_schedule_rows(
        rows, constraints=CONSTRAINTS, now=NOW
    )
    assert "nonstandard_time" in _rules(report)
    issue = next(i for i in report["issues"] if i["rule"] == "nonstandard_time")
    assert issue["level"] == "info"


def test_batch_format_is_info() -> None:
    days = _copy_days(_steady_days())
    ferm_day = date(2026, 12, 12)
    dump_day = date(2026, 12, 15)
    _tank = days[ferm_day]["ferm"][1]
    days[date(2026, 12, 11)]["seed"] = "FA-26315"
    days[ferm_day]["ferm"] = ("FA-26315", _tank)
    days[dump_day]["dump"] = ("FA-26315", _tank)
    report = _validate(days)
    assert "batch_format" in _rules(report)
    issue = next(i for i in report["issues"] if i["rule"] == "batch_format")
    assert issue["level"] == "info"


def test_empty_column_is_info() -> None:
    days = _copy_days(_steady_days())
    days[date(2026, 12, 14)] = {
        "seed": None,
        "ferm": None,
        "dump": None,
        "note": "",
    }
    report = _validate(days)
    assert "empty_column" in _rules(report)
    issue = next(i for i in report["issues"] if i["rule"] == "empty_column")
    assert issue["level"] == "info"


# ═══════════════════ 约束配置与检修存取 ═══════════════════


@pytest.mark.asyncio
async def test_upsert_and_get_constraint_setting(db_session) -> None:
    item = await svc.upsert_constraint_setting(
        db_session,
        product_code="FA",
        standard_cycle_hours=61.0,
        cycle_tolerance_hours=4.0,
        max_cycle_hours=72.0,
        turnaround_hours=8.0,
        monthly_dump_target=26,
    )
    assert svc.serialize_constraint_setting(item)["standard_cycle_hours"] == 61.0
    # 更新同产品记录而非新增
    again = await svc.upsert_constraint_setting(
        db_session,
        product_code="FA",
        standard_cycle_hours=63.0,
        cycle_tolerance_hours=4.0,
        max_cycle_hours=72.0,
        turnaround_hours=8.0,
        monthly_dump_target=None,
    )
    assert again.id == item.id
    fetched = await svc.get_constraint_setting(db_session, "FA")
    assert fetched is not None
    assert fetched.standard_cycle_hours == 63.0
    assert fetched.monthly_dump_target is None
    await db_session.delete(fetched)
    await db_session.commit()


@pytest.mark.asyncio
async def test_upsert_constraint_rejects_max_below_standard(db_session) -> None:
    with pytest.raises(ValueError, match="不能小于"):
        await svc.upsert_constraint_setting(
            db_session,
            product_code="FA",
            standard_cycle_hours=61.0,
            cycle_tolerance_hours=4.0,
            max_cycle_hours=50.0,
            turnaround_hours=8.0,
            monthly_dump_target=26,
        )


def test_maintenance_note_includes_recovery() -> None:
    assert (
        board.maintenance_note(
            {"tank_no": "302A", "reason": "染菌", "expected_recovery_date": None}
        )
        == "检修：染菌"
    )
    assert board.maintenance_note(
        {
            "tank_no": "302A",
            "reason": "染菌",
            "expected_recovery_date": "2026-12-13",
        }
    ) == "检修：染菌，预计12-13恢复"


@pytest.mark.asyncio
async def test_serialize_maintenance_includes_recovery(db_session) -> None:
    item = TankMaintenance(
        tank_no="302A",
        reason="染菌检查",
        expected_recovery_date=date(2026, 12, 13),
    )
    db_session.add(item)
    await db_session.flush()
    data = board.serialize_maintenance(item)
    assert data["expected_recovery_date"] == "2026-12-13"
    await db_session.delete(item)
    await db_session.commit()
