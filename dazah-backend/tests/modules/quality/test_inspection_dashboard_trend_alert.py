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


def _product_record() -> FinishedTrendAIAnalysis:
    """产品级月度AI行：metric_key=哨兵，payload.metrics=两个命中指标。"""
    metrics = [
        {
            "metric_key": "含量（干品）:97.0%-103.0%",
            "metric_label": "含量（干品）",
            "points": _rising_points(),
            "categories": [p["batch_no"] for p in _rising_points()],
            "actual_series": [float(p["value"]) for p in _rising_points()],
            "mean": 95.25,
            "std_dev": 3.24,
            "upper_control_limit": 105.0,
            "lower_control_limit": 85.5,
            "spec_lines": [{"label": "标准上限", "value": 103.0}],
            "anomalies": [
                {
                    "rule_type": "month_slope",
                    "severity": "high",
                    "start_batch": "MC260800",
                    "end_batch": "MC260807",
                    "description": "当月持续上升",
                    "evidence": {"slope": 1.5},
                    "affected_batches": ["MC260807"],
                }
            ],
        },
        {
            "metric_key": "有关物质:%<=0.2%",
            "metric_label": "有关物质",
            "points": _rising_points(),
            "categories": [p["batch_no"] for p in _rising_points()],
            "actual_series": [float(p["value"]) for p in _rising_points()],
            "mean": 0.12,
            "std_dev": 0.02,
            "upper_control_limit": 0.18,
            "lower_control_limit": 0.06,
            "spec_lines": [{"label": "标准上限", "value": 0.2}],
            "anomalies": [
                {
                    "rule_type": "month_level",
                    "severity": "medium",
                    "start_batch": "MC260800",
                    "end_batch": "MC260807",
                    "description": "当月较历史抬升",
                    "evidence": {"delta": 0.03},
                    "affected_batches": ["MC260807"],
                }
            ],
        },
    ]
    return FinishedTrendAIAnalysis(
        id=uuid.uuid4(),
        entity_code="qc_finished_internal",
        source_label="霉酚酸（内控）",
        frontend_group="mpa",
        metric_key="__product__",
        metric_label="全部指标",
        rule_type="monthly_overall",
        severity="high",
        trend_start_batch="MC260701",
        trend_end_batch="2026-09",
        description="月度整体趋势分析（2026-09，2 项指标命中）",
        evidence={"period": "2026-09"},
        payload={
            "source_label": "霉酚酸（内控）",
            "frontend_group": "mpa",
            "metrics": metrics,
        },
        affected_batches=["MC260807"],
        notification_status="pending",
    )


def _config(enabled: bool = True) -> InspectionTrendAlertConfig:
    return SimpleNamespace(
        is_enabled=enabled,
        lines={"qc_finished_internal": {"enabled": enabled, "recipients": []}},
    )


def _hit_ctx(**overrides) -> dict:
    """一个命中判据的指标上下文（供产品级月度AI）。"""
    ctx = {
        "metric_key": "含量（干品）:97.0%-103.0%",
        "metric_label": "含量（干品）",
        "points": _rising_points(),
        "categories": [p["batch_no"] for p in _rising_points()],
        "actual_series": [float(p["value"]) for p in _rising_points()],
        "mean": 95.25,
        "std_dev": 3.24,
        "upper_control_limit": 105.0,
        "lower_control_limit": 85.5,
        "spec_lines": [{"label": "标准上限", "value": 103.0}],
        "serialized_anomalies": [
            {
                "rule_type": "month_slope",
                "severity": "medium",
                "start_batch": "MC260800",
                "end_batch": "MC260807",
                "description": "当月持续上升",
                "evidence": {"slope": 1.5},
                "affected_batches": ["MC260806", "MC260807"],
            }
        ],
    }
    ctx.update(overrides)
    return ctx


def _product_ctxs() -> list[dict]:
    """两个指标：一个命中、一个未命中（未命中的不应进入 AI 输入）。"""
    return [
        _hit_ctx(),
        _hit_ctx(
            metric_key="干燥失重:%<=0.5%",
            metric_label="干燥失重",
            serialized_anomalies=[],
        ),
    ]


@pytest.mark.anyio
async def test_process_product_trend_creates_pending_and_submits_once(
    db_session: AsyncSession, monkeypatch
) -> None:
    await _ensure_table(db_session)
    await _purge(db_session)
    submit = AsyncMock(return_value="job-1")
    monkeypatch.setattr(calc, "submit_job", submit)

    ai, status = await calc._process_product_trend(
        db_session,
        sender_user_open_id="ou_sender",
        source_label="霉酚酸（内控）",
        entity_code="qc_finished_internal",
        frontend_group="mpa",
        metric_ctxs=_product_ctxs(),
        period="2026-09",
    )

    assert ai is None
    assert status == "pending"
    submit.assert_awaited_once()
    rows = (
        await db_session.execute(FinishedTrendAIAnalysis.__table__.select())
    ).all()
    assert len(rows) == 1
    # 产品级行：一个产品一行，指标为哨兵键，payload 只含命中指标
    assert rows[0].metric_key == calc.TREND_PRODUCT_METRIC_KEY
    payload = rows[0].payload
    assert [m["metric_label"] for m in payload["metrics"]] == ["含量（干品）"]


@pytest.mark.anyio
async def test_process_product_trend_dedups_on_reopen(
    db_session: AsyncSession, monkeypatch
) -> None:
    await _ensure_table(db_session)
    await _purge(db_session)
    submit = AsyncMock(return_value="job-1")
    monkeypatch.setattr(calc, "submit_job", submit)

    kwargs = dict(
        sender_user_open_id="ou_sender",
        source_label="霉酚酸（内控）",
        entity_code="qc_finished_internal",
        frontend_group="mpa",
        metric_ctxs=_product_ctxs(),
        period="2026-09",
    )
    await calc._process_product_trend(db_session, **kwargs)
    # 第二次打开同一仪表盘：唯一键命中，不再提交 job
    _ai2, status2 = await calc._process_product_trend(db_session, **kwargs)
    assert submit.await_count == 1
    assert status2 == "pending"


@pytest.mark.anyio
async def test_process_product_trend_skips_when_no_metric_hits(
    db_session: AsyncSession, monkeypatch
) -> None:
    await _ensure_table(db_session)
    await _purge(db_session)
    submit = AsyncMock(return_value="job-1")
    monkeypatch.setattr(calc, "submit_job", submit)

    ai, status = await calc._process_product_trend(
        db_session,
        sender_user_open_id="ou_sender",
        source_label="霉酚酸（内控）",
        entity_code="qc_finished_internal",
        frontend_group="mpa",
        metric_ctxs=[_hit_ctx(serialized_anomalies=[])],
        period="2026-09",
    )
    assert ai is None
    assert status == "none"
    submit.assert_not_awaited()
    rows = (
        await db_session.execute(FinishedTrendAIAnalysis.__table__.select())
    ).all()
    assert not rows


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
async def test_execute_product_trend_job_sends_one_merged_card(
    db_session: AsyncSession, monkeypatch
) -> None:
    """产品级月度AI：一次模型调用、一张合并卡（硬编码防飞书限流）。"""
    await _ensure_table(db_session)
    await _purge(db_session)
    record = _product_record()
    db_session.add(record)
    await db_session.commit()

    product_ai = AsyncMock(
        return_value={
            "status": "completed",
            "model_name": "q-test",
            "ai_summary": {
                "summary": "含量上行主导，整体风险偏高",
                "trend_reading": "含量当月持续上升；有关物质较历史抬升。",
                "signals": [
                    {
                        "batch_no": "MC260807",
                        "rule_type": "month_slope",
                        "severity": "high",
                        "note": "含量：连续上行",
                    }
                ],
                "outlook": {"direction": "up", "batches_to_limit": 5, "risk": "或越限"},
                "recommendation": "加严监测并结合偏差评估",
                "confidence": "medium",
                "metric_findings": [
                    {"metric_label": "含量（干品）", "summary": "持续上升，逼近上限"},
                    {"metric_label": "有关物质", "summary": "较历史抬升，需关注"},
                ],
            },
        }
    )
    monkeypatch.setattr(calc, "run_product_trend_ai_analysis", product_ai)
    monkeypatch.setattr(calc, "render_trend_chart_png", lambda **kw: b"PNGDATA")
    upload = AsyncMock(return_value="img_v3_key")
    monkeypatch.setattr(calc, "upload_image", upload)
    monkeypatch.setattr(
        calc, "load_inspection_trend_alert_config", AsyncMock(return_value=_config())
    )
    card = AsyncMock(
        return_value={"status": "sent", "message_id": "om_prod", "error": None}
    )
    monkeypatch.setattr(calc, "_send_trend_ai_card", card)

    await calc._execute_trend_ai_job(
        db_session, record, record.payload, sender_user_open_id="ou_sender"
    )
    await db_session.commit()

    fetched = await db_session.get(FinishedTrendAIAnalysis, record.id)
    assert fetched is not None
    # 一次模型调用（不逐指标）
    product_ai.assert_awaited_once()
    assert product_ai.await_args.kwargs["period"] == "2026-09"
    assert len(product_ai.await_args.kwargs["metrics"]) == 2
    # AI 结论含逐指标 findings 并回写
    assert fetched.ai_summary is not None
    assert len(fetched.ai_summary["metric_findings"]) == 2
    assert fetched.model_name == "q-test"
    # 两个命中指标各渲染+上传一张图，全部并入同一张卡
    assert upload.await_count == 2
    assert fetched.feishu_image_key == "img_v3_key"
    sent_kwargs = card.await_args.kwargs
    assert [label for label, _key in sent_kwargs["chart_images"]] == [
        "含量（干品）",
        "有关物质",
    ]
    # 只发一张合并卡
    card.assert_awaited_once()
    assert fetched.notification_status == "sent"
    assert fetched.feishu_message_id == "om_prod"


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
