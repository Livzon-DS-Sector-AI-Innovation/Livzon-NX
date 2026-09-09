"""成品检测趋势编排接线测试：规则→去重落库→后台 job 渲染/上传/推送富化。

覆盖：新异常建 pending 行并提交 job；重复打开命中唯一键不再重复提交；
后台 job 成功路径写入 AI 摘要并以「图 + 深链按钮 + AI 摘要」发送；LLM 失败
降级为 ai_failed 不发送；去重记录直接返回已完成状态。
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality.models.finished_trend_ai_analysis import (
    FinishedTrendAIAnalysis,
)
from app.modules.quality.service import inspection_dashboard_calc as calc
from app.modules.quality.service.quality_notification_settings import (
    InspectionTrendAlertConfig,
)


async def _ensure_table(db: AsyncSession) -> None:
    await db.run_sync(
        lambda _sd: FinishedTrendAIAnalysis.__table__.create(
            _sd.connection(), checkfirst=True
        )
    )


async def _purge(db: AsyncSession) -> None:
    await db.execute(
        text("DELETE FROM quality.quality_finished_trend_ai_analyses")
    )


def _rising_points(n: int = 8) -> list[dict]:
    # 跨两个月（2607 四批 + 2608 其余），v3 口径需要历史/本月两段才能对比
    return [
        {"batch_no": f"MC2607{i + 1:03d}", "value": 90.0 + i * 1.5}
        for i in range(4)
    ] + [
        {"batch_no": f"MC2608{i + 1:03d}", "value": 90.0 + (i + 4) * 1.5}
        for i in range(n - 4)
    ]


def _base_kwargs(**overrides) -> dict:
    args = {
        "sender_user_open_id": "ou_sender",
        "source_label": "霉酚酸（内控）",
        "entity_code": "qc_finished_internal",
        "frontend_group": "mpa",
        "metric_key": "含量（干品）:97.0%-103.0%",
        "metric_label": "含量（干品）",
        "points": _rising_points(),
        "mean": 95.25,
        "std_dev": 3.24,
        "upper_control_limit": 105.0,
        "lower_control_limit": 85.5,
        "spec_lines": [{"label": "标准上限", "value": 103.0}],
    }
    args.update(overrides)
    return args


def _config(enabled: bool = True) -> InspectionTrendAlertConfig:
    return SimpleNamespace(
        is_enabled=enabled,
        lines={"qc_finished_internal": {"enabled": enabled, "recipients": []}},
    )


@pytest.mark.anyio
async def test_process_metric_trend_creates_pending_and_submits_once(
    db_session: AsyncSession, monkeypatch
) -> None:
    await _ensure_table(db_session)
    await _purge(db_session)
    submit = AsyncMock(return_value="job-1")
    monkeypatch.setattr(calc, "submit_job", submit)

    serialized, ai, status = await calc._process_metric_trend(
        db_session, **_base_kwargs()
    )

    assert serialized  # 至少一条趋势异常事实
    assert ai is None
    assert status == "pending"
    submit.assert_awaited_once()
    rows = (
        await db_session.execute(
            FinishedTrendAIAnalysis.__table__.select()
        )
    ).all()
    assert len(rows) == 1


@pytest.mark.anyio
async def test_process_metric_trend_dedups_on_reopen(
    db_session: AsyncSession, monkeypatch
) -> None:
    await _ensure_table(db_session)
    await _purge(db_session)
    submit = AsyncMock(return_value="job-1")
    monkeypatch.setattr(calc, "submit_job", submit)

    await calc._process_metric_trend(db_session, **_base_kwargs())
    # 第二次打开同一仪表盘：唯一键命中，不再提交 job
    _s2, _ai2, status2 = await calc._process_metric_trend(
        db_session, **_base_kwargs()
    )
    assert submit.await_count == 1
    assert status2 == "pending"


@pytest.mark.anyio
async def test_execute_trend_ai_job_sends_card_with_image_and_link(
    db_session: AsyncSession, monkeypatch
) -> None:
    await _ensure_table(db_session)
    await _purge(db_session)

    record = FinishedTrendAIAnalysis(
        id=uuid.uuid4(),
        entity_code="qc_finished_internal",
        source_label="霉酚酸（内控）",
        frontend_group="mpa",
        metric_key="含量（干品）:97.0%-103.0%",
        metric_label="含量（干品）",
        rule_type="continuous_move",
        severity="medium",
        trend_start_batch="MC260800",
        trend_end_batch="MC260807",
        description="连续 8 批上升",
        evidence={"direction": "up", "run_points": 8},
        payload={
            "points": _rising_points(),
            "categories": [f"MC2608{i:02d}" for i in range(8)],
            "actual_series": [90.0 + i * 1.5 for i in range(8)],
            "mean": 95.25,
            "std_dev": 3.24,
            "upper_control_limit": 105.0,
            "lower_control_limit": 85.5,
            "spec_lines": [{"label": "标准上限", "value": 103.0}],
            "source_label": "霉酚酸（内控）",
            "frontend_group": "mpa",
        },
        affected_batches=["MC260804", "MC260805", "MC260806", "MC260807"],
        notification_status="pending",
    )
    db_session.add(record)
    await db_session.commit()

    monkeypatch.setattr(
        calc,
        "run_trend_ai_analysis",
        AsyncMock(
            return_value={
                "status": "completed",
                "model_name": "q-test",
                "ai_summary": {
                    "summary": "含量持续上行，逼近上限",
                    "trend_reading": "近 8 批单调上升，斜率约 1.5/批。",
                    "signals": [
                        {
                            "batch_no": "MC260807",
                            "rule_type": "continuous_move",
                            "severity": "high",
                            "note": "连续上升",
                        }
                    ],
                    "outlook": {
                        "direction": "up",
                        "batches_to_limit": 6,
                        "risk": "或越 OOT",
                    },
                    "recommendation": "建议加严监测",
                    "confidence": "medium",
                },
            }
        ),
    )
    monkeypatch.setattr(calc, "render_trend_chart_png", lambda **kw: b"PNGDATA")
    monkeypatch.setattr(calc, "upload_image", AsyncMock(return_value="img_v3_key"))
    monkeypatch.setattr(
        calc, "load_inspection_trend_alert_config", AsyncMock(return_value=_config())
    )
    card = AsyncMock(
        return_value={"status": "sent", "message_id": "om_1", "error": None}
    )
    monkeypatch.setattr(calc, "_send_trend_ai_card", card)

    await calc._execute_trend_ai_job(
        db_session, record, record.payload, sender_user_open_id="ou_sender"
    )
    await db_session.commit()

    fetched = await db_session.get(FinishedTrendAIAnalysis, record.id)
    assert fetched is not None
    assert fetched.ai_summary is not None
    assert fetched.ai_summary["affected_batches"] == [
        "MC260804",
        "MC260805",
        "MC260806",
        "MC260807",
    ]
    assert fetched.model_name == "q-test"
    assert fetched.feishu_image_key == "img_v3_key"
    assert fetched.notification_status == "sent"
    assert fetched.feishu_message_id == "om_1"
    assert fetched.notified_at is not None
    card.assert_awaited_once()


@pytest.mark.anyio
async def test_execute_trend_ai_job_skips_send_when_paused(
    db_session: AsyncSession, monkeypatch
) -> None:
    await _ensure_table(db_session)
    await _purge(db_session)
    record = FinishedTrendAIAnalysis(
        id=uuid.uuid4(),
        entity_code="qc_finished_internal",
        source_label="霉酚酸（内控）",
        frontend_group="mpa",
        metric_key="k",
        metric_label="含量",
        rule_type="mean_shift",
        severity="medium",
        trend_start_batch="A",
        trend_end_batch="B",
        description="均值偏移",
        evidence={},
        payload={"points": [], "categories": [], "actual_series": [], "spec_lines": []},
        affected_batches=[],
        notification_status="pending",
    )
    db_session.add(record)
    await db_session.commit()

    monkeypatch.setattr(
        calc,
        "run_trend_ai_analysis",
        AsyncMock(
            return_value={
                "status": "completed",
                "model_name": "m",
                "ai_summary": {"summary": "s", "confidence": "low", "signals": []},
            }
        ),
    )
    monkeypatch.setattr(
        calc,
        "load_inspection_trend_alert_config",
        AsyncMock(return_value=_config(enabled=False)),
    )
    card = AsyncMock()
    monkeypatch.setattr(calc, "_send_trend_ai_card", card)

    await calc._execute_trend_ai_job(
        db_session, record, record.payload, sender_user_open_id=None
    )
    await db_session.commit()
    fetched = await db_session.get(FinishedTrendAIAnalysis, record.id)
    assert fetched is not None
    assert fetched.notification_status == "paused"
    # AI 仍已生成（供页面回看），但停用不发送
    assert fetched.ai_summary is not None
    card.assert_not_awaited()


@pytest.mark.anyio
async def test_run_trend_ai_job_idempotent_terminal_status(
    db_session: AsyncSession, monkeypatch
) -> None:
    await _ensure_table(db_session)
    await _purge(db_session)
    record = FinishedTrendAIAnalysis(
        id=uuid.uuid4(),
        entity_code="qc_finished_internal",
        source_label="霉酚酸（内控）",
        frontend_group="mpa",
        metric_key="k",
        metric_label="含量",
        rule_type="continuous_move",
        severity="high",
        trend_start_batch="A",
        trend_end_batch="B",
        description="已推送",
        evidence={},
        payload={"points": [], "spec_lines": []},
        affected_batches=[],
        notification_status="sent",
    )
    db_session.add(record)
    await db_session.commit()

    run = AsyncMock()
    monkeypatch.setattr(calc, "run_trend_ai_analysis", run)
    monkeypatch.setattr(
        calc,
        "async_session_factory",
        _make_factory(db_session),
    )
    result = await calc._run_trend_ai_job(
        analysis_id=record.id, sender_user_open_id=None
    )
    assert result == {"status": "already"}
    run.assert_not_awaited()


def _make_factory(session: AsyncSession):
    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return False

    return lambda: _Ctx()
