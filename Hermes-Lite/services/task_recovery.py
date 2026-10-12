"""Recovery decisions derived from trusted current-turn evidence."""

from dataclasses import dataclass
import re
from typing import Any, Literal

from services.agent_task_contract import TaskEvidence


def validation_fields(payload: Any) -> list[str]:
    """Keep field locations only; backend messages can contain sensitive values."""
    if not isinstance(payload, dict):
        return []
    detail = payload.get("detail")
    if isinstance(detail, str):
        match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_.]{0,100}):", detail)
        return [match[1]] if match else []
    if isinstance(detail, list):
        return list(dict.fromkeys(".".join(str(part) for part in item.get("loc", [])
                                          if part not in {"body", "params", "query"})
                                 for item in detail[:10] if isinstance(item, dict) and item.get("loc")))
    return []


def empty_result(data: Any) -> bool:
    if isinstance(data, list):
        return not data
    return isinstance(data, dict) and any(data.get(key) == [] for key in ("items", "rows", "records", "results"))


@dataclass(frozen=True)
class RecoveryDecision:
    category: Literal["discover", "parameters", "transient", "stop", "ask_user", "check_receipt"]
    instruction: str


def recovery_decision(items: list[TaskEvidence]) -> RecoveryDecision:
    if any(item.error_code in {"http_401", "http_403", "subject_unavailable", "run_cancelled"} for item in items):
        return RecoveryDecision("stop", "身份、权限拒绝或已取消；停止调用，不能换工具绕过。")
    if any(item.write is True and not item.ok and item.error_code in {
        "timeout", "connection_failed", "http_500", "http_502", "http_503", "http_504", "invalid_response", "write_execution_unknown",
    } for item in items):
        return RecoveryDecision("check_receipt", "写入结果未知；禁止重发，需按 Trace ID 核查平台执行回执。")
    successful = [item for item in items if item.ok and item.action == "execute"]
    if successful and empty_result(successful[-1].data):
        return RecoveryDecision("ask_user", "查询已完成但结果为空；保留原条件，询问是否调整日期或筛选条件。")
    failures = [item for item in items if not item.ok]
    if not failures:
        return RecoveryDecision("discover", "搜索授权目录，按实时Schema描述并执行所需只读能力。")
    code = failures[-1].error_code
    if code == "analysis_unavailable":
        return RecoveryDecision("stop", "辅助分析或引用校验未完成；保留已核实事实，说明能确认和不能确认的内容。")
    if code in {"http_400", "http_422"}:
        return RecoveryDecision("parameters", "重新describe获取字段要求，只修正已报告的参数错误；缺失业务值需具体追问，不得猜测。")
    if code in {"timeout", "connection_failed", "http_429", "http_500", "http_502", "http_503", "http_504"}:
        return RecoveryDecision("transient", "同条件只读重试已用尽；停止本轮重试，保留失败原因供稍后恢复。")
    return RecoveryDecision("stop", "能力停用、对象不存在或业务规则拒绝；保留原因，不能替换对象或放宽条件重试。")
