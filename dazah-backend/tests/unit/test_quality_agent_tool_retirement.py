"""质量飞书 CAPA 台账/同步 AI 工具退休后的注册面断言。"""

from __future__ import annotations

from app.modules.agent.tool_registration import ensure_agent_tools_registered
from app.modules.agent.tools import tool_registry


def test_retired_feishu_agent_tools_are_no_longer_registered() -> None:
    """本地台账化后，飞书 CAPA 台账/偏差/报告记录/CAPA 同步工具应从工具目录移除。"""
    ensure_agent_tools_registered()
    names = {spec.name for spec in tool_registry.list() if spec.module == "quality"}
    for retired in (
        "quality.sync_deviation_to_feishu",
        "quality.sync_deviation_report_record_to_feishu",
        "quality.sync_capa_to_feishu",
        "quality.list_feishu_capa_ledger",
        "quality.get_feishu_capa_ledger",
    ):
        assert retired not in names, f"{retired} 应已从质量 Agent 工具目录移除"
