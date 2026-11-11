"""应急预案模板/确定性校验/docx 导入导出单元测试（不依赖数据库）。"""

import io
from uuid import uuid4

from docx import Document

from app.modules.safety.schemas.emergency_plan_ai import (
    EmergencyPlanDocument,
    EmergencyPlanGenerateRequest,
    OrganizationPatch,
    OrgGroupPatch,
    PlanChapter,
)
from app.modules.safety.service.emergency_plan_checks import (
    apply_deterministic_fixes,
    cn_to_int,
    find_company_mentions,
    run_checks,
)
from app.modules.safety.service.emergency_plan_docx import build_plan_docx
from app.modules.safety.service.emergency_plan_import import parse_plan_docx
from app.modules.safety.service.emergency_plan_template import (
    build_skeleton,
    chinese_numeral,
    fill_standard_duties,
    merge_organization_patch,
    render_chapter_text,
)

# ---------- 构造测试文档 ----------


def _sample_params(**overrides) -> EmergencyPlanGenerateRequest:
    values: dict = {
        "level": "company",
        "accident_type": "leak_fire",
        "location": "危险品库",
        "substances": [],
        "company": "丽珠集团（宁夏）制药有限公司",
        "drill_date": "2026-11-17",
        "archive_department": "消保队",
        "participating_departments": ["仓储部"],
        "organization": {
            "commander": "史润",
            "deputy_commanders": ["田成"],
            "groups": [
                {"name": "应急处置组", "leader": "朱少军", "members": "仓储部人员"},
                {"name": "医疗救护组", "leader": "陈华"},
            ],
        },
    }
    values.update(overrides)
    return EmergencyPlanGenerateRequest(**values)


def _skeleton(**overrides) -> EmergencyPlanDocument:
    params = _sample_params(**overrides)
    return build_skeleton(params, "危险品库乙醇火灾事故综合应急演练方案")


def _docx_bytes(paragraphs: list[tuple[str, bool]]) -> bytes:
    doc = Document()
    for text, bold in paragraphs:
        paragraph = doc.add_paragraph()
        run = paragraph.add_run(text)
        run.bold = bold
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


# ---------- 模板 ----------


def test_skeleton_fills_fixed_chapters_and_titles() -> None:
    document = _skeleton(substances=[{"name": "乙醇"}])
    titles = {chapter.key: chapter.title for chapter in document.chapters}
    assert titles["properties"] == "乙醇的理化性质"
    assert titles["organization"] == "组织架构"
    guiding = document.chapter("guiding_thought")
    assert guiding is not None and "安全第一、预防为主" in guiding.content
    assert "危险化学品安全管理条例" in guiding.content
    preface = document.preface
    assert "丽珠集团（宁夏）制药有限公司" in preface
    assert "危险品库" in preface


def test_skeleton_without_substance_uses_generic_titles() -> None:
    document = _skeleton(accident_type="electric")
    titles = {chapter.key: chapter.title for chapter in document.chapters}
    assert titles["properties"] == "事故特性分析"
    assert titles["protection"] == "防护措施"


def test_render_chapter_uses_organization() -> None:
    document = _skeleton()
    org_chapter = document.chapter("organization")
    text = render_chapter_text(document, org_chapter)
    assert "总 指 挥：史润" in text
    assert "应急处置组" in text
    resp = document.chapter("responsibilities")
    resp_text = render_chapter_text(document, resp)
    assert "（三）指挥部人员职责分工" in resp_text
    assert "朱少军" not in resp_text  # 职责章不含人名，只有职责描述


def test_fill_standard_duties_only_fills_empty() -> None:
    document = _skeleton()
    org = document.organization
    custom = "现场专人负责堵漏。"
    org.groups[0].duties = custom
    filled = fill_standard_duties(org)
    assert filled.groups[0].duties == custom
    assert "灭火" in filled.groups[1].duties or filled.groups[1].duties


def test_merge_organization_patch() -> None:
    org = _skeleton().organization
    merged = merge_organization_patch(
        org,
        OrganizationPatch(
            commander="新总指挥",
            groups=[
                OrgGroupPatch(name="应急处置组", leader="新组长"),
                OrgGroupPatch(name="新增组", leader="某人"),
            ],
        ),
    )
    assert merged.commander == "新总指挥"
    assert merged.groups[0].leader == "新组长"
    assert merged.groups[0].members == "仓储部人员"  # 未指定的字段保留
    assert merged.groups[-1].name == "新增组"
    assert merged.deputy_commanders == ["田成"]


def test_chinese_numeral() -> None:
    assert [chinese_numeral(n) for n in (1, 4, 10, 11, 12, 20, 23)] == [
        "一",
        "四",
        "十",
        "十一",
        "十二",
        "二十",
        "二十三",
    ]
    assert cn_to_int("三") == 3
    assert cn_to_int("十二") == 12
    assert cn_to_int("二十三") == 23


# ---------- 确定性校验 ----------


def test_checks_company_full_name_and_leak_typo() -> None:
    document = _skeleton()
    scenario = document.chapter("scenario")
    scenario.content = (
        "（情景一）14时00分，现场发生泄漏。\n"
        "14时05分，公共关系与后勤组组长刘丽萍拨打119报警：“是119吗？"
        "我这里是平罗县的丽珠药业有限公司……”"
    )
    document = document.model_copy(
        update={
            "chapters": [
                scenario if item.key == "scenario" else item
                for item in document.chapters
            ]
        }
    )
    issues = run_checks(document, substances=["乙醇"])
    codes = {issue.code for issue in issues}
    assert "company_not_full_name" in codes
    fixed, fixes = apply_deterministic_fixes(document)
    assert "丽珠药业有限公司" not in (fixed.chapter("scenario").content)
    assert {fix.code for fix in fixes} >= {"company_not_full_name"}


def test_checks_timeline_backwards_and_missing_time() -> None:
    document = _skeleton()
    scenario = document.chapter("scenario")
    scenario.content = (
        "（情景一）14时10分，发现泄漏。\n"
        "（情景二）14时05分，警戒疏散组集合。\n"
        "（情景四）处置完成。"
    )
    document = document.model_copy(
        update={
            "chapters": [
                scenario if item.key == "scenario" else item
                for item in document.chapters
            ]
        }
    )
    issues = run_checks(document, substances=[])
    codes = {issue.code for issue in issues}
    assert "timeline_backwards" in codes
    assert "scene_missing_time" in codes
    assert "scene_numbering" in codes


def test_checks_foam_requires_alcohol_resistant() -> None:
    document = _skeleton()
    scenario = document.chapter("scenario")
    scenario.content = "消保队架设泡沫水枪对事故区进行灭火。"
    document = document.model_copy(
        update={
            "chapters": [
                scenario if item.key == "scenario" else item
                for item in document.chapters
            ]
        }
    )
    issues = run_checks(document, substances=["乙醇"])
    assert any(issue.code == "foam_not_alcohol_resistant" for issue in issues)
    # 非水溶性物质不报
    issues_oil = run_checks(document, substances=["柴油"])
    assert not any(issue.code == "foam_not_alcohol_resistant" for issue in issues_oil)


def test_checks_group_and_person_mismatch() -> None:
    document = _skeleton()
    scenario = document.chapter("scenario")
    scenario.content = (
        "应急处置组唐佳逸向指挥部汇报现场情况。\n"
        "应急处置组组长陈华组织灭火。\n"
        "应急处置组组长朱少军立即通知各组集合。"
    )
    document = document.model_copy(
        update={
            "chapters": [
                scenario if item.key == "scenario" else item
                for item in document.chapters
            ]
        }
    )
    issues = run_checks(document, substances=[])
    codes = {issue.code for issue in issues}
    assert "person_unknown" in codes
    assert "leader_mismatch" in codes


def test_checks_empty_chapters_flagged() -> None:
    document = _skeleton()
    document = document.model_copy(
        update={
            "chapters": [
                item.model_copy(update={"content": ""})
                if item.key == "scenario"
                else item
                for item in document.chapters
            ]
        }
    )
    issues = run_checks(document, substances=[])
    assert any(
        issue.code == "chapter_empty" and issue.section == "scenario"
        for issue in issues
    )


def test_find_company_mentions_with_parenthesis() -> None:
    text = "我这里是平罗县太沙工业园区（丽珠药业有限公司），请救援"
    assert find_company_mentions(text) == ["丽珠药业有限公司"]
    plain = "丽珠药业有限公司位于工业园区"
    assert find_company_mentions(plain) == ["丽珠药业有限公司"]


# ---------- docx 导入 ----------


def _template_docx_bytes() -> bytes:
    paragraphs = [
        ("", False),
        ("丽珠集团（宁夏）制药有限公司", True),
        ("危险品库乙醇火灾事故综合应急演练方案", True),
        ("(公司级)", True),
        ("", False),
        ("演练时间：2026年11月17日", True),
        ("建档时间： 2026年11月", True),
        ("建档部门：    消保队      ", True),
        ("丽珠集团（宁夏）制药有限公司", False),
        ("危险品库乙醇火灾事故综合应急演练方案", False),
        (
            "为验证我司针对危险化学品储存场所的突发事故、事件人员应急处置机制，"
            "特此组织演练，并制定本方案。",
            False,
        ),
        ("一、指导思想  ", True),
        ("本方案按照《安全生产法》等要求，坚持安全第一。", False),
        ("二、演练目的", True),
        ("评估公司应急准备状态，发现预案缺陷。", False),
        ("三、组织架构", True),
        ("总 指 挥：史润", False),
        ("副总指挥：田成", False),
        ("应急处置组", True),
        ("组长：朱少军", False),
        ("组员：仓储部全体人员", False),
        ("医疗救护组：", True),
        ("组长：陈华", False),
        ("四、职责分工", True),
        ("（一）指挥领导小组：", False),
        ("1、负责审核演练方案的制定、修订。", False),
        ("（三）指挥部人员职责分工 ", True),
        ("总指挥：负责人员、资源配置，应急队伍的调动。", True),
        ("应急处置组：负责事故现场灭火及人员搜救。", True),
        ("五、危险源分析", True),
        ("危险品库主要存放乙醇、丙酮等易燃液体。", False),
        ("六、乙醇的理化性质", True),
        ("闪点为13℃（闭杯），爆炸极限为3.3%～19%。", False),
        ("七、乙醇泄露的防护", True),
        ("佩戴防毒面具，穿防静电工作服。", False),
        ("八、乙醇泄露的处理", True),
        ("泄漏引发火灾使用抗溶性泡沫扑救。", False),
        ("九、车间应急组成员、组织机构", True),
        ("1、仓储部应急组成员：", False),
        ("应急处置组：", False),
        ("组长：", False),
        ("十、情景设置", True),
        ("（情景一）14时00分，发现乙醇泄漏。", False),
        ("（情景二）14时05分，现场处置完毕。", False),
        ("十一、演练讲评 ", True),
        ("1、总指挥宣布演练结束", False),
        ("十二、附件", True),
        ("1、应急响应流程", False),
        ("2、演练总结", False),
    ]
    return _docx_bytes(paragraphs)


def test_parse_template_docx_roundtrip() -> None:
    imported = parse_plan_docx(_template_docx_bytes())
    assert imported.is_template_like
    assert imported.template_headings == 12
    document = imported.document
    assert document.cover.company == "丽珠集团（宁夏）制药有限公司"
    assert document.cover.drill_date == "2026年11月17日"
    assert document.cover.archive_department == "消保队"
    assert document.cover.level == "公司级"
    assert document.organization.commander == "史润"
    assert document.organization.deputy_commanders == ["田成"]
    group = next(g for g in document.organization.groups if g.name == "应急处置组")
    assert group.leader == "朱少军"
    assert group.duties.startswith("负责事故现场灭火")
    workshop = document.workshop_organization
    assert workshop is not None and workshop.department == "仓储部"
    titles = {chapter.key: chapter.title for chapter in document.chapters}
    assert titles["properties"] == "乙醇的理化性质"
    assert "泄露" in titles["protection"]  # 原文错误保留，由校验/审核修正
    assert document.chapter("scenario").content.startswith("（情景一）")


def test_parse_plain_docx_not_template_like() -> None:
    content = _docx_bytes([("随便一个文档", False), ("没有章节结构", False)])
    imported = parse_plan_docx(content)
    assert not imported.is_template_like
    assert any("差异较大" in warning for warning in imported.warnings)


# ---------- docx 导出 ----------


def test_export_docx_roundtrip() -> None:
    imported = parse_plan_docx(_template_docx_bytes())
    document, _fixes = apply_deterministic_fixes(imported.document)
    data = build_plan_docx(document)
    result = Document(io.BytesIO(data))
    texts = [paragraph.text for paragraph in result.paragraphs]
    joined = "\n".join(texts)
    assert not any("{{" in text for text in texts)
    assert "丽珠集团（宁夏）制药有限公司" in texts
    assert "一、指导思想" in joined
    assert "七、乙醇泄漏的防护" in joined  # 标题已修正
    assert result.tables, "组织架构框图应为表格"
    assert "总指挥：史润" in result.tables[0].rows[0].cells[0].text
    fonts = {
        run.font.name
        for paragraph in result.paragraphs
        for run in paragraph.runs
        if run.font.name and len(paragraph.text) > 20
    }
    assert fonts == {"仿宋"}


def test_export_docx_sanitize_filename() -> None:
    from app.modules.safety.service.emergency_plan_docx import export_filename

    document = EmergencyPlanDocument(
        cover={
            "title": "预案A/B:测试*?",
            "level": "公司级",
        }
    )
    name = export_filename(document, "默认")
    assert "/" not in name and ":" not in name and "*" not in name
    assert name.endswith(".docx")
    assert uuid4().hex not in name
    empty = EmergencyPlanDocument()
    assert export_filename(empty, "兜底名称").endswith("兜底名称.docx")


def test_plan_chapter_key_validation() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PlanChapter(key="bad key!", title="x")
    with pytest.raises(ValidationError):
        EmergencyPlanDocument(
            chapters=[
                PlanChapter(key="scenario", title="a"),
                PlanChapter(key="scenario", title="b"),
            ]
        )
