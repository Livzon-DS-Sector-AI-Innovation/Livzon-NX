"""Validated task plans and deterministic, evidence-backed business replies."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.business_reply import answer_focus, render_business_data

TaskKind = Literal["capability", "read", "knowledge", "write", "analysis", "draft", "verify", "general"]
StepState = Literal["completed", "awaiting_confirmation", "execution_unknown", "verification_pending", "blocked", "failed", "not_started"]


class VerificationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_step_id: str
    source_pointer: str = Field(pattern=r"^(?:/.*)?$", max_length=200)
    result_pointer: str = Field(pattern=r"^(?:/.*)?$", max_length=200)


class AgentTaskStep(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    kind: TaskKind
    goal: str = Field(min_length=1, max_length=240)
    search_query: str = Field(default="", max_length=200)
    depends_on: list[str] = Field(default_factory=list, max_length=8)
    missing_inputs: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(default_factory=list, max_length=8)
    verification_checks: list[VerificationCheck] = Field(default_factory=list, max_length=10)


class AgentTaskPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    steps: list[AgentTaskStep] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def ordered_dependencies(self) -> AgentTaskPlan:
        seen: set[str] = set()
        kinds: dict[str, TaskKind] = {}
        for step in self.steps:
            if step.id in seen or any(dep not in seen for dep in step.depends_on):
                raise ValueError("step IDs must be unique and dependencies must precede their consumers")
            if step.kind == "draft" and not step.depends_on:
                raise ValueError("business drafts need source tasks")
            if any(check.source_step_id not in step.depends_on or kinds.get(check.source_step_id) != "write"
                   for check in step.verification_checks) or (step.verification_checks and step.kind != "verify"):
                raise ValueError("verification checks must reference preceding write dependencies")
            seen.add(step.id)
            kinds[step.id] = step.kind
        return self


class TaskEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str
    step_id: str
    action: Literal["search", "describe", "execute", "analysis", "draft"]
    operation: str | None = None
    ok: bool
    occurred_at: str
    filters: dict[str, Any] = Field(default_factory=dict)
    data: Any = None
    write: bool | None = None
    result_kind: Literal["records", "statistics", "knowledge_index", "knowledge"] | None = None
    output_hint: str | None = Field(default=None, max_length=800)
    confirmation_id: str | None = None
    error_code: str | None = None
    error_fields: list[str] = Field(default_factory=list, max_length=10)


class TaskStepOutcome(BaseModel):
    id: str
    kind: TaskKind
    state: StepState
    evidence_ids: list[str] = Field(default_factory=list)


def _pointer_value(value: Any, pointer: str) -> tuple[bool, Any]:
    for component in pointer.split("/")[1:]:
        key = component.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and key.isdigit() and int(key) < len(value):
            value = value[int(key)]
        else:
            return False, None
    return True, value


def evaluate_plan(plan: AgentTaskPlan, evidence: list[TaskEvidence]) -> list[TaskStepOutcome]:
    outcomes: list[TaskStepOutcome] = []
    states: dict[str, StepState] = {}
    for step in plan.steps:
        items = [item for item in evidence if item.step_id == step.id]
        valid = [item for item in items if item.ok]
        state: StepState = "not_started"
        if step.missing_inputs or any(states[dep] != "completed" for dep in step.depends_on):
            state = "blocked"
        elif step.kind == "capability":
            if any(item.action == "search" and isinstance(item.data, list) for item in valid):
                state = "completed"
        elif step.kind in {"read", "knowledge"}:
            if any(item.action == "execute" and item.write is False and item.data is not None
                   and item.confirmation_id is None
                   and (step.kind != "knowledge" or item.result_kind != "knowledge_index") for item in valid):
                state = "completed"
        elif step.kind == "analysis":
            if any(item.action == "analysis" and item.data is not None for item in valid):
                state = "completed"
        elif step.kind == "draft":
            if any(item.action == "draft" and item.data is not None for item in valid):
                state = "completed"
        elif step.kind == "verify":
            reads = [item for item in valid if item.action == "execute" and item.write is False
                     and item.data is not None and not item.confirmation_id]
            if reads:
                state = "verification_pending"
                if step.verification_checks:
                    matches = []
                    for check in step.verification_checks:
                        sources = [item for item in evidence if item.step_id == check.source_step_id
                                   and item.ok and item.action == "execute" and item.write is True
                                   and not item.confirmation_id and item.data is not None]
                        found, expected = _pointer_value(sources[-1].data, check.source_pointer) if sources else (False, None)
                        exists, actual = _pointer_value(reads[-1].data, check.result_pointer)
                        matches.append(found and exists and expected is not None and type(expected) is type(actual) and expected == actual)
                    state = "completed" if all(matches) else "failed"
        elif step.kind == "write":
            writes = [item for item in valid if item.action == "execute" and item.write is True]
            if any(item.confirmation_id for item in writes):
                state = "awaiting_confirmation"
            elif any(item.data is not None for item in writes):
                state = "completed"
            elif any(not item.ok and item.write is True and item.error_code in {
                "timeout", "connection_failed", "http_500", "http_502", "http_503", "http_504",
                "invalid_response", "write_execution_unknown",
            } for item in items):
                state = "execution_unknown"
        if state == "not_started" and items and any(not item.ok for item in items):
            state = "failed"
        states[step.id] = state
        outcomes.append(TaskStepOutcome(id=step.id, kind=step.kind, state=state,
                                        evidence_ids=[item.id for item in valid]))
    return outcomes


def build_draft_evidence(plan: AgentTaskPlan, evidence: list[TaskEvidence]) -> list[TaskEvidence]:
    """Build review previews from cited facts; never submit a business write."""
    additions: list[TaskEvidence] = []
    for step in plan.steps:
        if step.kind != "draft" or step.missing_inputs or any(item.step_id == step.id and item.action == "draft" for item in evidence + additions):
            continue
        states = {item.id: item.state for item in evaluate_plan(plan, evidence + additions)}
        if any(states[dependency] != "completed" for dependency in step.depends_on):
            continue
        sources = [item for item in evidence + additions if item.step_id in step.depends_on
                   and item.ok and item.action in {"execute", "analysis", "draft"} and item.data is not None]
        if not sources:
            continue
        additions.append(TaskEvidence(
            id=uuid.uuid4().hex, step_id=step.id, action="draft", ok=True, write=False,
            occurred_at=sources[-1].occurred_at,
            data={"标题": step.goal, "状态": "仅供审核，未写入业务系统",
                  "正文": [{"来源": item.operation or item.action, "内容": item.data} for item in sources],
                  "限制": "仅基于本轮返回范围；截断或分页数据不代表全量，辅助分析需人工复核。",
                  "依据": [{"evidence_id": item.id, "operation": item.operation,
                            "occurred_at": item.occurred_at, "filters": item.filters} for item in sources]},
        ))
    return additions


_PRIVATE_KEYS = {"authorization", "cookie", "password", "passwd", "secret", "token", "api_key",
                 "access_token", "refresh_token", "raw_response", "prompt"}


def safe_business_value(value: Any, depth: int = 0) -> Any:
    """Bound and strip secret-bearing fields before retaining tool facts."""
    if depth > 6:
        return "[内容过深，未展示]"
    if isinstance(value, dict):
        result = {str(key): safe_business_value(item, depth + 1) for key, item in list(value.items())[:30]
                  if str(key).lower() not in _PRIVATE_KEYS
                  and not str(key).lower().endswith(("_token", "_secret", "_password", "_api_key"))}
        if len(value) > 30:
            result["展示范围"] = "仅展示前 30 个字段"
        return result
    if isinstance(value, list):
        rows = [safe_business_value(item, depth + 1) for item in value[:3]]
        if len(value) > 3:
            rows.append({"展示范围": f"仅展示前 3 条，本次结果共 {len(value)} 条"})
        return rows
    if isinstance(value, str):
        if value.lower().startswith("bearer "):
            return "[已隐藏凭据]"
        return value[:1000] + ("[文本已截断]" if len(value) > 1000 else "")
    return value


def _reply_business_data(value: Any) -> Any:
    """Project generated analysis/drafts without their internal citation records."""
    if isinstance(value, dict) and isinstance(value.get("分析"), list) and "性质" in value:
        return {**value, "分析": [
            {key: finding[key] for key in ("辅助解释", "原始事实") if key in finding}
            for finding in value["分析"] if isinstance(finding, dict)
        ]}
    if isinstance(value, dict) and "依据" in value and isinstance(value.get("正文"), list):
        return {key: (
            [_reply_business_data(part.get("内容")) for part in item if isinstance(part, dict)]
            if key == "正文" else item
        ) for key, item in value.items() if key != "依据"}
    return value


def render_task_reply(plan: AgentTaskPlan, evidence: list[TaskEvidence], *, request: str = "") -> str:
    outcomes = evaluate_plan(plan, evidence)
    lines: list[str] = []
    labels = {"completed": "已完成", "awaiting_confirmation": "待确认，尚未执行",
              "execution_unknown": "执行结果未知，禁止重复提交", "verification_pending": "已取得核对数据，核对条件待明确",
              "blocked": "需补充条件或等待前置任务", "failed": "调用失败", "not_started": "尚未完成"}
    for step, outcome in zip(plan.steps, outcomes, strict=True):
        if outcome.state != "completed":
            lines.append(f"{step.goal}：{labels[outcome.state]}")
        if step.missing_inputs:
            lines.append("请补充：" + "、".join(step.missing_inputs))
        if outcome.state == "blocked" and step.depends_on:
            lines.append("需先完成相关操作。")
        items = [item for item in evidence if item.step_id == step.id and item.ok]
        if step.kind == "capability" and outcome.state == "completed":
            entries = {entry["operation"]: entry for item in items if item.action == "search"
                       for entry in item.data if isinstance(entry, dict) and entry.get("operation")}
            if not entries:
                lines.append("授权目录中未找到匹配能力；可补充页面或业务名称。")
            for operation, entry in entries.items():
                suffix = "（写入需确认）" if entry.get("confirmation_required") else ""
                lines.append(f"- {entry.get('summary') or operation}{suffix}：`{operation}`")
        if outcome.state in {"completed", "verification_pending"} and step.kind in {"read", "knowledge", "analysis", "write", "draft", "verify"}:
            for item in items:
                if item.action in {"execute", "analysis", "draft"} and item.confirmation_id is None and item.data is not None:
                    label = "辅助分析（需人工复核）：\n" if item.action == "analysis" else "审核报告草稿：\n" if item.action == "draft" else ""
                    focus = answer_focus(request or step.goal) if item.action == "execute" and step.kind == "read" else "details"
                    lines.append(label + render_business_data(_reply_business_data(item.data), focus=focus))
        if outcome.state in {"failed", "not_started"}:
            if step.kind == "knowledge" and any(
                item.action == "execute" and item.ok and item.result_kind == "knowledge_index" for item in items
            ):
                lines.append("仅取得资料目录，尚未读取正文；需继续检索正文或其他授权业务依据。")
            failures = [item.error_code for item in evidence if item.step_id == step.id and not item.ok]
            reasons = {"http_403": "页面授权或授权同步校验未通过", "http_401": "身份校验未通过",
                       "http_422": "工具参数未通过校验", "timeout": "工具服务超时",
                       "connection_failed": "工具服务连接失败", "execution_rejected": "平台拒绝执行",
                       "tool_not_configured": "工具服务未配置", "invalid_response": "工具响应格式无效",
                       "run_cancelled": "本轮任务已取消", "repair_budget_exhausted": "只读修复次数已用尽",
                       "repair_read_only": "修复链路只允许只读操作",
                       "step_operation_kind_mismatch": "工具类型与本项任务不一致",
                       "analysis_unavailable": "辅助分析未生成或引用校验未通过，已保留查询事实"}
            lines.append("检查结果：" + ("、".join(reasons.get(code, "工具调用未完成") for code in failures if code)
                                         or "缺少匹配的本轮执行证据"))
            if step.kind == "verify" and any(item.action == "execute" for item in items):
                lines.append("核对未通过：返回字段缺失或与写入回执不一致；请核查业务记录。")
        from services.task_recovery import recovery_decision

        step_evidence = [item for item in evidence if item.step_id == step.id]
        decision = recovery_decision(step_evidence)
        executions = [item for item in step_evidence if item.action == "execute"]
        parameters_corrected = (
            outcome.state == "awaiting_confirmation" and decision.category == "parameters"
            and bool(executions) and executions[-1].ok and bool(executions[-1].confirmation_id)
        )
        if decision.category != "discover" and not parameters_corrected and (outcome.state != "completed" or decision.category == "ask_user"):
            lines.append("下一步：" + decision.instruction)
        fields = list(dict.fromkeys(field for item in evidence if item.step_id == step.id for field in item.error_fields))
        if fields and outcome.state != "completed" and not parameters_corrected:
            lines.append("需检查字段：" + "、".join(fields))
    return "\n\n".join(lines)
