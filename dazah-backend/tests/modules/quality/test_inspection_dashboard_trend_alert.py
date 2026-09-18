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
from sqlalchemy import select, text
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

    ai, status, verdicts = await calc._process_product_trend(
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
    assert verdicts == {}  # AI 未完成前无裁决数据
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
    _ai2, status2, _v2 = await calc._process_product_trend(db_session, **kwargs)
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

    ai, status, verdicts = await calc._process_product_trend(
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
    assert verdicts == {}
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
                "trend_reading": "含量当月持续上升；有关物质经复核属正常波动。",
                "signals": [
                    {
                        "metric_index": 1,
                        "batch_no": "MC260807",
                        "rule_type": "month_slope",
                        "severity": "high",
                        "note": "含量：连续上行",
                    }
                ],
                "outlook": {"direction": "up", "batches_to_limit": 5, "risk": "或越限"},
                "recommendation": "加严监测并结合偏差评估",
                "confidence": "medium",
                # AI 终审：指标1 真异常、指标2 判正常（不标红/不出图/不进卡）
                "metric_findings": [
                    {
                        "metric_index": 1,
                        "metric_label": "含量（干品）",
                        "verdict": "abnormal",
                        "summary": "持续上升，逼近上限",
                    },
                    {
                        "metric_index": 2,
                        "metric_label": "有关物质",
                        "verdict": "normal",
                        "summary": "较历史抬升但仍在波动带内，风险可控",
                    },
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
    # AI 裁决回填：abnormal/normal + 复核计数
    assert fetched.ai_summary is not None
    verdicts = fetched.ai_summary["metric_verdicts"]
    assert verdicts["含量（干品）:97.0%-103.0%"]["verdict"] == "abnormal"
    assert verdicts["含量（干品）:97.0%-103.0%"]["batches"] == ["MC260807"]
    assert verdicts["有关物质:%<=0.2%"]["verdict"] == "normal"
    assert fetched.ai_summary["review_counts"]["abnormal"] == 1
    assert fetched.ai_summary["review_counts"]["normal"] == 1
    assert fetched.model_name == "q-test"
    # 只有 AI 判定异常的指标出图/进卡
    assert upload.await_count == 1
    assert fetched.feishu_image_key == "img_v3_key"
    sent_kwargs = card.await_args.kwargs
    assert [label for label, _key in sent_kwargs["chart_images"]] == ["含量（干品）"]
    # 只发一张合并卡
    card.assert_awaited_once()
    assert fetched.notification_status == "sent"
    assert fetched.feishu_message_id == "om_prod"


@pytest.mark.anyio
async def test_execute_product_trend_job_no_send_when_all_normal(
    db_session: AsyncSession, monkeypatch
) -> None:
    """AI 终审全判正常/改善：结论留页面回看，不推卡、不出图（正常不打扰）。"""
    await _ensure_table(db_session)
    await _purge(db_session)
    record = _product_record()
    db_session.add(record)
    await db_session.commit()

    monkeypatch.setattr(
        calc,
        "run_product_trend_ai_analysis",
        AsyncMock(
            return_value={
                "status": "completed",
                "model_name": "q-test",
                "ai_summary": {
                    "summary": "整体平稳，风险可控",
                    "trend_reading": "两项判据经复核均属正常波动/改善。",
                    "signals": [],
                    "outlook": {
                        "direction": "flat",
                        "batches_to_limit": None,
                        "risk": "",
                    },
                    "recommendation": "维持常规监测",
                    "confidence": "medium",
                    "metric_findings": [
                        {
                            "metric_index": 1,
                            "metric_label": "含量（干品）",
                            "verdict": "improved",
                            "summary": "下降属改善",
                        },
                        {
                            "metric_index": 2,
                            "metric_label": "有关物质",
                            "verdict": "normal",
                            "summary": "正常波动",
                        },
                    ],
                },
            }
        ),
    )
    render = AsyncMock(return_value=b"PNGDATA")
    monkeypatch.setattr(calc, "render_trend_chart_png", render)
    upload = AsyncMock(return_value="img_v3_key")
    monkeypatch.setattr(calc, "upload_image", upload)
    monkeypatch.setattr(
        calc, "load_inspection_trend_alert_config", AsyncMock(return_value=_config())
    )
    card = AsyncMock()
    monkeypatch.setattr(calc, "_send_trend_ai_card", card)

    await calc._execute_trend_ai_job(
        db_session, record, record.payload, sender_user_open_id="ou_sender"
    )
    await db_session.commit()

    fetched = await db_session.get(FinishedTrendAIAnalysis, record.id)
    assert fetched is not None
    assert fetched.notification_status == "completed"
    assert fetched.feishu_message_id is None
    assert fetched.notified_at is None
    card.assert_not_awaited()
    render.assert_not_awaited()  # 无异常指标 → 不渲染图
    upload.assert_not_awaited()


@pytest.mark.anyio
async def test_execute_product_trend_job_marks_ai_failed_for_retry(
    db_session: AsyncSession, monkeypatch
) -> None:
    """AI 未完成（无配置/限流等）：标记 ai_failed 可重试，不推送。"""
    await _ensure_table(db_session)
    await _purge(db_session)
    record = _product_record()
    db_session.add(record)
    await db_session.commit()

    monkeypatch.setattr(
        calc,
        "run_product_trend_ai_analysis",
        AsyncMock(
            return_value={
                "status": "failed",
                "error": "no_config",
                "model_name": None,
                "ai_summary": None,
            }
        ),
    )
    monkeypatch.setattr(
        calc, "load_inspection_trend_alert_config", AsyncMock(return_value=_config())
    )
    card = AsyncMock()
    monkeypatch.setattr(calc, "_send_trend_ai_card", card)

    await calc._execute_trend_ai_job(
        db_session, record, record.payload, sender_user_open_id="ou_sender"
    )
    await db_session.commit()

    fetched = await db_session.get(FinishedTrendAIAnalysis, record.id)
    assert fetched is not None
    assert fetched.notification_status == "ai_failed"
    assert fetched.ai_summary is None
    card.assert_not_awaited()


def test_build_metric_verdicts_unreviewed_and_signal_sanitize() -> None:
    """未裁决兜底：缺条目按 unreviewed（不标红）；信号只留异常指标且批次白名单。"""
    metrics = [
        {"metric_key": "m1", "anomalies": [{"affected_batches": ["B1", "B2"]}]},
        {"metric_key": "m2", "anomalies": [{"affected_batches": ["B3"]}]},
        {"metric_key": "m3", "anomalies": [{"affected_batches": ["B4"]}]},
    ]
    verdicts, approved, counts = calc._build_metric_verdicts(
        metrics,
        [
            {"metric_index": 1, "verdict": "abnormal", "summary": "x"},
            {"metric_index": 2, "verdict": "normal", "summary": "y"},
            # 指标 3 缺裁决条目 → unreviewed
        ],
    )
    assert verdicts["m1"] == {"verdict": "abnormal", "batches": ["B1", "B2"]}
    assert verdicts["m2"] == {"verdict": "normal", "batches": []}
    assert verdicts["m3"] == {"verdict": "unreviewed", "batches": []}
    assert [m["metric_key"] for m in approved] == ["m1"]
    assert counts == {
        "candidates": 3,
        "abnormal": 1,
        "normal": 1,
        "improved": 0,
        "unreviewed": 1,
    }
    signals = calc._sanitize_product_signals(
        [
            {"metric_index": 1, "batch_no": "B1", "rule_type": "month_level"},
            {"metric_index": 1, "batch_no": "B9", "rule_type": "month_level"},
            {"metric_index": 2, "batch_no": "B3", "rule_type": "month_level"},
            {"batch_no": "B4", "rule_type": "month_level"},  # 无序号 → 丢
            {"metric_index": "bad", "batch_no": "B5", "rule_type": "month_level"},
        ],
        metrics,
        verdicts,
    )
    assert [s.get("batch_no") for s in signals] == ["B1", ""]
    assert [s.get("metric_index") for s in signals] == [1, 1]


def test_build_metric_verdicts_falls_back_to_metric_label() -> None:
    """模型只回指标名（或序号非数字被清洗）时，按名称兜底回填裁决。"""
    metrics = [
        {"metric_key": "m1", "metric_label": "水分：≤3.0%", "anomalies": []},
        {"metric_key": "m2", "metric_label": "炽灼残渣：≤0.5%", "anomalies": []},
    ]
    verdicts, approved, counts = calc._build_metric_verdicts(
        metrics,
        [
            # 序号写成中文描述 → 清洗为 None，但名称可匹配
            {
                "metric_index": None,
                "metric_label": "水分：≤3.0%",
                "verdict": "abnormal",
                "summary": "抬升",
            },
            {
                "metric_index": None,
                "metric_label": "炽灼残渣：≤0.5%",
                "verdict": "normal",
                "summary": "正常",
            },
        ],
    )
    assert verdicts["m1"]["verdict"] == "abnormal"
    assert verdicts["m2"]["verdict"] == "normal"
    assert counts == {
        "candidates": 2,
        "abnormal": 1,
        "normal": 1,
        "improved": 0,
        "unreviewed": 0,
    }


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


@pytest.mark.anyio
async def test_process_product_trend_retries_when_previous_failed(
    db_session: AsyncSession, monkeypatch
) -> None:
    """上轮任务 failed（如连接池超时）且无结论：打开页面自动重试。"""
    await _ensure_table(db_session)
    await _purge(db_session)
    record = _product_record()
    record.notification_status = "failed"
    record.ai_summary = None
    db_session.add(record)
    await db_session.commit()

    submit = AsyncMock(return_value="job-2")
    monkeypatch.setattr(calc, "submit_job", submit)

    _ai, status, _verdicts = await calc._process_product_trend(
        db_session,
        sender_user_open_id="ou_sender",
        source_label="霉酚酸（内控）",
        entity_code="qc_finished_internal",
        frontend_group="mpa",
        metric_ctxs=_product_ctxs(),
        period="2026-09",
    )
    assert status == "pending"
    submit.assert_awaited_once()
    rows = (
        await db_session.execute(FinishedTrendAIAnalysis.__table__.select())
    ).all()
    assert len(rows) == 1  # 复用在档行重试，不新建


@pytest.mark.anyio
async def test_process_product_trend_does_not_retry_terminal_rows(
    db_session: AsyncSession, monkeypatch
) -> None:
    """已交付（sent）的行再次打开不重跑、不重发。"""
    await _ensure_table(db_session)
    await _purge(db_session)
    record = _product_record()
    record.notification_status = "sent"
    record.ai_summary = {"summary": "已交付", "metric_verdicts": {}}
    db_session.add(record)
    await db_session.commit()

    submit = AsyncMock(return_value="job-3")
    monkeypatch.setattr(calc, "submit_job", submit)

    _ai, status, _verdicts = await calc._process_product_trend(
        db_session,
        sender_user_open_id="ou_sender",
        source_label="霉酚酸（内控）",
        entity_code="qc_finished_internal",
        frontend_group="mpa",
        metric_ctxs=_product_ctxs(),
        period="2026-09",
    )
    submit.assert_not_awaited()
    assert status == "completed"


def test_trend_ai_job_semaphore_is_per_event_loop() -> None:
    """并发闸门按事件循环隔离：跨 loop 复用会报 bound to a different loop。"""
    import asyncio as _a

    async def _get():
        return calc._trend_ai_job_semaphore()

    first = _a.run(_get())
    second = _a.run(_get())
    assert first is not second
    assert first._value == calc._TREND_AI_JOB_CONCURRENCY  # type: ignore[attr-defined]


def test_product_content_signature_ignores_jsonb_int_float_drift() -> None:
    """内容签名对 JSONB 整数/浮点往返稳定；数据变化必须改变签名。"""
    metrics = [
        {
            "metric_key": "含量（干品）:97.0%-103.0%",
            "points": [{"batch_no": "MC260801", "value": 90.0}],
            "spec_lines": [{"label": "标准上限", "value": 103.0}],
        }
    ]
    stored = [
        {
            "metric_key": "含量（干品）:97.0%-103.0%",
            "points": [{"batch_no": "MC260801", "value": 90}],
            "spec_lines": [{"label": "标准上限", "value": 103}],
        }
    ]
    assert calc._product_content_signature(metrics) == (
        calc._product_content_signature(stored)
    )
    changed = [dict(metrics[0], points=[{"batch_no": "MC260801", "value": 90.5}])]
    assert calc._product_content_signature(metrics) != (
        calc._product_content_signature(changed)
    )


async def _seed_prior_period_analysis(
    db_session: AsyncSession,
    monkeypatch,
    period: str = "2026-08",
) -> AsyncMock:
    """造一条已完成推送的历史月度分析行（payload 由真实入口构建）。"""
    await _ensure_table(db_session)
    await _purge(db_session)
    submit = AsyncMock(return_value="job-1")
    monkeypatch.setattr(calc, "submit_job", submit)
    await calc._process_product_trend(
        db_session,
        sender_user_open_id="ou_sender",
        source_label="霉酚酸（内控）",
        entity_code="qc_finished_internal",
        frontend_group="mpa",
        metric_ctxs=_product_ctxs(),
        period=period,
    )
    record = (
        (await db_session.execute(select(FinishedTrendAIAnalysis)))
        .scalars()
        .one()
    )
    record.ai_summary = {
        "summary": "8 月结论",
        "metric_verdicts": {
            "含量（干品）:97.0%-103.0%": {
                "verdict": "abnormal",
                "batches": ["MC260807"],
            }
        },
    }
    record.notification_status = "sent"
    await db_session.commit()
    return submit


@pytest.mark.anyio
async def test_process_product_trend_reuses_prior_analysis_for_unchanged_content(
    db_session: AsyncSession, monkeypatch
) -> None:
    """数据内容未变（跨周期）：不重复自动分析，直接复用最近一次结论。"""
    submit = await _seed_prior_period_analysis(db_session, monkeypatch)

    ai, status, verdicts = await calc._process_product_trend(
        db_session,
        sender_user_open_id="ou_sender",
        source_label="霉酚酸（内控）",
        entity_code="qc_finished_internal",
        frontend_group="mpa",
        metric_ctxs=_product_ctxs(),
        period="2026-09",
    )

    assert status == "completed"
    assert ai is not None
    assert ai.period == "2026-08"  # 沿用上期结论，页面展示其分析周期
    assert verdicts["含量（干品）:97.0%-103.0%"]["verdict"] == "abnormal"
    submit.assert_awaited_once()  # 只在 8 月提交过，9 月未再提交
    rows = (
        (await db_session.execute(select(FinishedTrendAIAnalysis))).scalars().all()
    )
    assert len(rows) == 1  # 未新建 9 月行


@pytest.mark.anyio
async def test_process_product_trend_analyzes_when_content_changed(
    db_session: AsyncSession, monkeypatch
) -> None:
    """数据有更新（限度线变化导致签名不同）：不命中去重，正常建行分析。"""
    submit = await _seed_prior_period_analysis(db_session, monkeypatch)

    changed_ctxs = _product_ctxs()
    changed_ctxs[0] = _hit_ctx(spec_lines=[{"label": "标准上限", "value": 101.0}])
    _ai, status, _verdicts = await calc._process_product_trend(
        db_session,
        sender_user_open_id="ou_sender",
        source_label="霉酚酸（内控）",
        entity_code="qc_finished_internal",
        frontend_group="mpa",
        metric_ctxs=changed_ctxs,
        period="2026-09",
    )

    assert status == "pending"
    assert submit.await_count == 2
    rows = (
        (await db_session.execute(select(FinishedTrendAIAnalysis))).scalars().all()
    )
    assert len(rows) == 2


@pytest.mark.anyio
async def test_process_product_trend_manual_rerun_bypasses_reuse(
    db_session: AsyncSession, monkeypatch
) -> None:
    """手动「重新分析」不受跨周期去重限制：同内容也强制重跑。"""
    submit = await _seed_prior_period_analysis(db_session, monkeypatch)

    _ai, status, _verdicts = await calc._process_product_trend(
        db_session,
        sender_user_open_id="ou_sender",
        source_label="霉酚酸（内控）",
        entity_code="qc_finished_internal",
        frontend_group="mpa",
        metric_ctxs=_product_ctxs(),
        period="2026-09",
        manual_rerun=True,
    )

    assert status == "pending"
    assert submit.await_count == 2
    rows = (
        (await db_session.execute(select(FinishedTrendAIAnalysis))).scalars().all()
    )
    assert len(rows) == 2


@pytest.mark.anyio
async def test_reanalyze_runs_manual_even_without_current_period_row(
    db_session: AsyncSession, monkeypatch
) -> None:
    """当月无记录（如同内容被跨月去重跳过）时手动重分析仍可用。"""
    await _ensure_table(db_session)
    await _purge(db_session)

    async def fake_entry(db, **kwargs):
        assert kwargs.get("manual_rerun") is True
        assert kwargs.get("enable_trend_ai") is True
        return {"configured": True, "charts": [], "summary": {}}

    monkeypatch.setattr(
        "app.modules.quality.service.inspection_dashboard_entry"
        ".get_mpa_dashboard_data",
        fake_entry,
    )
    monkeypatch.setattr(
        calc,
        "load_inspection_trend_alert_config",
        AsyncMock(
            return_value=SimpleNamespace(
                manual_rerun_send=True, is_enabled=True, lines={}
            )
        ),
    )

    result = await calc.reanalyze_trend_ai(
        db_session,
        entity_code="qc_finished_internal",
        sender_user_open_id="ou_sender",
    )
    assert result["period"] == calc._trend_period()
    assert result["job_id"] == ""
