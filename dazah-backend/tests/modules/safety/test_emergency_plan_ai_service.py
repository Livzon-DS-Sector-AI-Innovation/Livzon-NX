"""应急预案 AI 编排服务测试（monkeypatch llm_client，不连真实模型）。"""

import pytest

from app.core.llm.exceptions import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from app.modules.safety.schemas.emergency_plan_ai import (
    ChatEdit,
    EmergencyPlanDocument,
    EmergencyPlanGenerateRequest,
    ReviewIssue,
)
from app.modules.safety.service.emergency_plan_ai import (
    apply_chat_edits,
    chat_reply,
    generate_document,
    review_document,
    structure_document,
)
from tests.modules.safety.test_emergency_plan_workbench_unit import (
    _sample_params,
    _skeleton,
)


class _FakeLlm:
    """记录调用并按序返回预设 JSON（与真实客户端一致校验 expected_keys）。"""

    def __init__(self, responses: list[dict] | Exception):
        self.responses = list(responses) if isinstance(responses, list) else responses
        self.calls: list[dict] = []

    async def chat_json(self, messages, expected_keys=None, **kwargs):
        self.calls.append({"messages": messages, "expected_keys": expected_keys})
        if isinstance(self.responses, Exception):
            raise self.responses
        if not self.responses:
            raise LLMOutputError("no more responses")
        payload = self.responses.pop(0)
        if expected_keys and not all(key in payload for key in expected_keys):
            raise LLMOutputError(f"missing keys: {expected_keys}")
        return payload


def _params() -> EmergencyPlanGenerateRequest:
    return _sample_params()


def _context(substances: list[str] | None = None):
    from app.modules.safety.service.emergency_plan_context import (
        PlanGenerationContext,
        SubstanceContext,
    )

    return PlanGenerationContext(
        substances=[SubstanceContext(name=name) for name in substances or []]
    )


def _install(monkeypatch: pytest.MonkeyPatch, fake: _FakeLlm) -> None:
    async def _no_workflow_config(module_code: str):  # noqa: ARG001
        return None

    monkeypatch.setattr("app.modules.safety.service.emergency_plan_ai.llm_client", fake)
    monkeypatch.setattr(
        "app.modules.safety.service.emergency_plan_ai.SafetyRepository",
        lambda session: type(
            "_Repo",
            (),
            {"get_ai_workflow_config_by_module": staticmethod(_no_workflow_config)},
        )(),
    )


class _NullSession:
    """_get_workflow_config 只用到 repo 查询（已被替换为静态返回）。"""

    async def execute(self, *args, **kwargs):  # pragma: no cover
        return None


async def test_generate_document_fills_ai_chapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeLlm(
        [
            {
                "hazard_analysis": "库房存放乙醇。",
                "properties": "闪点 13℃。",
                "protection": "佩戴防毒面具。",
                "handling": "使用抗溶性泡沫。",
            },
            {"scenario": "（情景一）14时00分，发现泄漏。"},
        ]
    )
    _install(monkeypatch, fake)
    document = await generate_document(
        _NullSession(),
        params=_params(),
        plan_name="危险品库乙醇火灾事故综合应急演练方案",
        context=_context(["乙醇"]),
    )
    assert document.chapter("hazard_analysis").content == "库房存放乙醇。"
    assert document.chapter("scenario").content.startswith("（情景一）")
    assert document.chapter("guiding_thought").content  # 固定章节来自模板
    assert len(fake.calls) == 2
    # 提示词包含业务规则与 MSDS 约束
    first_prompt = fake.calls[0]["messages"][0]["content"]
    assert "抗溶性" in first_prompt
    assert "逐级" in first_prompt


async def test_generate_retries_on_partial_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeLlm(
        [
            {"hazard_analysis": "只有部分字段"},
            {
                "hazard_analysis": "完整",
                "properties": "p",
                "protection": "pr",
                "handling": "h",
            },
            {"scenario": "s"},
        ]
    )
    _install(monkeypatch, fake)
    document = await generate_document(
        _NullSession(),
        params=_params(),
        plan_name="预案",
        context=_context([]),
    )
    assert document.chapter("hazard_analysis").content == "完整"
    assert len(fake.calls) == 3


async def test_generate_error_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    for exc in (
        LLMConfigError("no config"),
        LLMRateLimitError("busy"),
        LLMOutputError("bad json"),
        LLMProviderError("down"),
    ):
        fake = _FakeLlm(exc)
        _install(monkeypatch, fake)
        with pytest.raises(type(exc)):
            await generate_document(
                _NullSession(), params=_params(), plan_name="预案", context=_context([])
            )


def _review_llm_payload() -> dict:
    return {
        "summary": "整体可用",
        "score": 88,
        "dimensions": [
            {"name": "一致性", "status": "warn", "note": "时间有倒退"},
            {"name": "专业性", "status": "ok", "note": ""},
        ],
        "issues": [
            {
                "section": "scenario",
                "quote": "泡沫水枪",
                "problem": "应使用抗溶性泡沫",
                "category": "technical",
                "severity": "high",
                "fix": "replace",
                "replacement": "抗溶性泡沫水枪",
            },
            {
                "section": "scenario",
                "quote": "",
                "problem": "缺应急电话，请人工补充",
                "category": "completeness",
                "severity": "medium",
                "fix": "none",
                "replacement": "",
            },
        ],
    }


async def test_review_applies_replacements_and_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _skeleton()
    scenario = document.chapter("scenario")
    scenario.content = "消保队架设泡沫水枪灭火。"
    document = document.model_copy(
        update={
            "chapters": [
                scenario if item.key == "scenario" else item
                for item in document.chapters
            ]
        }
    )
    consistency_only = {
        "issues": [
            {
                "section": "scenario",
                "quote": "泡沫水枪",
                "problem": "水溶性液体应用抗溶性泡沫",
                "category": "technical",
                "severity": "high",
                "fix": "replace",
                "replacement": "抗溶性泡沫水枪",
            }
        ]
    }
    fake = _FakeLlm([consistency_only, _review_llm_payload()])
    _install(monkeypatch, fake)
    new_document, report = await review_document(
        _NullSession(), document=document, context=_context(["乙醇"])
    )
    assert "抗溶性泡沫水枪" in new_document.chapter("scenario").content
    assert report.score == 88
    assert report.fixed_count >= 1
    fixed = [issue for issue in report.issues if issue.status == "fixed"]
    assert any(issue.after == "抗溶性泡沫水枪" for issue in fixed)
    needs = [issue for issue in report.issues if issue.status == "needs_human"]
    assert any("人工补充" in issue.problem for issue in needs)
    # 第一轮只查一致性、第二轮查专业性，均带规则校验结果
    assert len(fake.calls) == 2
    assert fake.calls[0]["expected_keys"] == ["issues"]
    assert "规则校验已发现" in fake.calls[0]["messages"][0]["content"]
    assert "MSDS 事实" in fake.calls[1]["messages"][0]["content"]


async def test_review_rewrite_chapter_length_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _skeleton()
    scenario = document.chapter("scenario")
    original = "原始内容。"
    scenario.content = original
    document = document.model_copy(
        update={
            "chapters": [
                scenario if item.key == "scenario" else item
                for item in document.chapters
            ]
        }
    )
    payload = _review_llm_payload()
    payload["issues"] = [
        {
            "section": "scenario",
            "quote": "",
            "problem": "本章多处问题需要重写",
            "category": "contradiction",
            "severity": "high",
            "fix": "rewrite",
            "replacement": "",
        }
    ]
    fake = _FakeLlm(
        [{"issues": []}, payload, {"content": "完全不同的一段超长重写内容，" * 60}]
    )
    _install(monkeypatch, fake)
    new_document, report = await review_document(
        _NullSession(), document=document, context=_context([])
    )
    assert new_document.chapter("scenario").content == original  # 长度保护生效
    assert any(
        issue.status == "needs_human" and issue.section == "scenario"
        for issue in report.issues
    )


async def test_chat_reply_and_apply_edits(monkeypatch: pytest.MonkeyPatch) -> None:
    document = _skeleton()
    fake = _FakeLlm(
        [
            {
                "reply": "已把情景一改为夜班发生。",
                "edits": [
                    {
                        "target": "chapter",
                        "chapter_key": "scenario",
                        "content": "（情景一）22时00分，发现泄漏。",
                        "summary": "改为夜班",
                    },
                    {
                        "target": "organization",
                        "organization_patch": {
                            "groups": [{"name": "应急处置组", "leader": "王五"}]
                        },
                        "summary": "更新组长",
                    },
                    {"target": "chapter", "chapter_key": "不存在", "content": "x"},
                    {"target": "chapter"},
                ],
            }
        ]
    )
    _install(monkeypatch, fake)
    reply, edits = await chat_reply(
        _NullSession(), document=document, history=[], message="改成夜班"
    )
    assert "夜班" in reply
    assert len(edits) == 2  # 非法补丁被丢弃
    new_document, sections = apply_chat_edits(document, edits)
    assert sections == ["scenario", "organization"]
    assert new_document.chapter("scenario").content.startswith("（情景一）22时00分")
    assert new_document.organization.groups[0].leader == "王五"
    assert new_document.organization.groups[0].members  # 未指定字段保留


async def test_structure_document_maps_chapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _skeleton()
    document = document.model_copy(
        update={
            "chapters": document.chapters
            + [
                type(document.chapters[0])(
                    key="custom_1", title="附页", content="一些零散内容"
                )
            ]
        }
    )
    fake = _FakeLlm(
        [{"chapters": {"scenario": "整理后的情景脚本。", "unknown_key": "忽略"}}]
    )
    _install(monkeypatch, fake)
    result = await structure_document(_NullSession(), document=document)
    assert result is not None
    assert result.chapter("scenario").content == "整理后的情景脚本。"
    assert result.chapter("custom_1").content == "一些零散内容"  # 自定义章保留


async def test_structure_document_invalid_output_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _skeleton()
    fake = _FakeLlm([{"chapters": "not-a-dict"}])
    _install(monkeypatch, fake)
    assert await structure_document(_NullSession(), document=document) is None


def test_organization_patch_schema_defaults() -> None:
    document = _skeleton()
    assert isinstance(document, EmergencyPlanDocument)
    issue = ReviewIssue(
        id="AI-01",
        source="ai",
        severity="high",
        category="typo",
        section="scenario",
        problem="x",
        status="fixed",
    )
    assert issue.quote == ""
    edit = ChatEdit(target="preface", content="新引言")
    assert edit.chapter_key is None


def test_plan_generation_context_facts_text_variants() -> None:
    """上下文纯逻辑：facts_text 的全字段/缺字段/空列表三形态。"""
    from app.modules.safety.service.emergency_plan_context import (
        PlanGenerationContext,
        SubstanceContext,
    )

    full = PlanGenerationContext(
        substances=[
            SubstanceContext(
                name="乙醇",
                cas_no="64-17-5",
                category="易燃液体",
                hazard_statements="高度易燃液体和蒸气",
                storage_requirements="远离火源",
                inventories=["库房 A 20 桶"],
                msds_text="MSDS 原文节选",
            )
        ],
        building_name="危险品库",
        building_category="warehouse",
    )
    facts = full.facts_text()
    assert "【事故场所】危险品库（warehouse）" in facts
    assert "CAS 号：64-17-5" in facts
    assert "车间库存：库房 A 20 桶" in facts
    assert "MSDS 原文节选" in facts

    # 无 MSDS 原文：提示不得自行编写
    sparse = PlanGenerationContext(
        substances=[SubstanceContext(name="丙酮")],
    )
    sparse_facts = sparse.facts_text()
    assert "MSDS 原文：未提供（理化数值不得自行编写）" in sparse_facts
    assert "【事故场所】" not in sparse_facts

    # 空上下文
    empty = PlanGenerationContext(substances=[])
    assert empty.facts_text() == "（未关联危化品档案）"
    assert empty.substance_names == []
    assert empty.msds_text == ""
