from copy import deepcopy

import pytest

from app.modules.research import ich_service
from app.modules.research.q3c_report_gen import generate_q3c_report
from app.modules.research.q3c_solvent_match import (
    analyze_steps,
    build_solvent_index,
    classify_solvents,
    load_synonyms,
)


def test_process_parsing_and_solvent_name_normalization() -> None:
    assert ich_service.parse_process_steps("步骤1：投料\n步骤2：浓缩") == [
        {"step_number": 1, "content": "投料"},
        {"step_number": 2, "content": "浓缩"},
    ]
    assert ich_service.parse_process_steps("1. Mixing\n2. Drying") == [
        {"step_number": 1, "content": "Mixing"},
        {"step_number": 2, "content": "Drying"},
    ]
    assert ich_service.parse_process_steps("(1)反应\n(2)过滤")[1]["content"] == "过滤"
    assert ich_service.parse_process_steps("未编号的单步操作") == [
        {"step_number": 1, "content": "未编号的单步操作"}
    ]
    assert ich_service.remove_concentration_prefix("95% 乙醇") == "乙醇"
    assert ich_service.remove_concentration_prefix("无水乙醇") == "乙醇"
    assert ich_service.remove_concentration_prefix("Absolute ethanol") == "ethanol"


def test_q3d_rule_engine_and_markdown_report_cover_all_classes(monkeypatch) -> None:
    sample_data = {
        "classes": {
            "Class 1": {
                "elements": {
                    "As": {
                        "oral_pde": 15,
                        "parenteral_pde": 15,
                        "inhalation_pde": 2,
                        "cutaneous_pde": 30,
                    }
                }
            },
            "Class 2A": {
                "elements": {
                    "Co": {
                        "oral_pde": 50,
                        "parenteral_pde": 5,
                        "inhalation_pde": 3,
                        "cutaneous_pde": 50,
                        "ctcl": 35,
                    }
                }
            },
            "Class 2B": {
                "elements": {
                    "Ag": {
                        "oral_pde": 150,
                        "parenteral_pde": 10,
                        "inhalation_pde": 7,
                    }
                }
            },
            "Class 3": {
                "elements": {
                    "Li": {
                        "oral_pde": 550,
                        "parenteral_pde": 250,
                        "inhalation_pde": 25,
                        "parenteral_assess": True,
                        "inhalation_assess": False,
                    }
                }
            },
            "Other": {
                "elements": {
                    "Fe": {
                        "oral_pde": None,
                        "notes": "逐案评价",
                    }
                }
            },
        },
        "option_1_concentrations": {
            "elements": {
                "As": {"oral": 1.5, "parenteral": 1.5, "inhalation": 0.2},
                "Co": {"oral": 5, "parenteral": 0.5, "inhalation": 0.3},
            }
        },
    }
    monkeypatch.setattr(ich_service, "Q3D_DATA", sample_data)

    elements = ich_service.identify_elements(
        {
            "elements": [
                {"symbol": "As", "source": "原料", "intentionally_added": False},
                {"symbol": "Ag", "source": "催化剂", "intentionally_added": True},
                {"symbol": "Fe", "source": "设备", "intentionally_added": True},
                {"symbol": "Xx", "source": "未知试剂", "intentionally_added": True},
                {"symbol": "", "source": "忽略"},
            ]
        }
    )

    assert set(elements) == {"As", "Co", "Li", "Fe", "Xx"}
    assert elements["As"]["source"] == "原料"
    assert elements["Xx"]["notes"].startswith("该元素不在ICH Q3D范围内")
    assert ich_service.get_element_data("Co")["class"] == "Class 2A"
    assert ich_service.get_element_data("missing") == {}
    assert ich_service.get_option1_concentrations("As")["oral"] == 1.5

    elements["Ag"] = {
        "source": "催化剂",
        "intentionally_added": True,
        "assessment_required": True,
        "q3d_class": "Class 2B",
        "oral_pde": 150,
        "parenteral_pde": 10,
        "inhalation_pde": 7,
        "cutaneous_pde": None,
        "ctcl": None,
        "notes": "",
    }
    display = ich_service._add_frontend_fields(
        deepcopy(elements),
        {"elements": [{"symbol": "As"}, {"symbol": "Ag"}, {"symbol": "Fe"}]},
    )
    assert display["As"]["found_in_text"] is True
    assert display["Co"]["needs_assessment"] is True
    assert display["Ag"]["needs_assessment"] is True
    assert display["Li"]["needs_assessment"] is True
    assert display["Fe"]["needs_assessment"] is True

    report = ich_service.generate_report("投料并反应", display)
    assert "# 元素杂质评估报告" in report
    assert "2B类元素有意添加，需要评估" in report
    assert "该元素不在ICH Q3D范围内" in report
    assert "皮肤毒性浓度限度（CTCL）" in report


@pytest.mark.anyio
async def test_q3d_analysis_orchestrates_extraction_rules_and_report(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        ich_service,
        "extract_text_from_docx",
        lambda _: "步骤1：加入砷催化剂\n步骤2：过滤",
    )

    async def fake_extract_elements(text: str) -> list[dict]:
        assert "砷催化剂" in text
        return [{"symbol": "As", "source": "催化剂", "intentionally_added": True}]

    from app.modules.research import llm_service

    monkeypatch.setattr(llm_service, "extract_elements_with_llm", fake_extract_elements)

    result = await ich_service.analyze_ich_q3d_with_llm(b"not-used")

    assert result["type"] == "Q3D"
    assert result["steps_count"] == 2
    assert result["llm_elements_count"] == 1
    assert any(
        element["symbol"] == "As" and element["found_in_text"]
        for element in result["elements_found"]
    )
    assert "# 元素杂质评估报告" in result["report"]


def test_q3c_matching_classifies_known_unknown_and_step_aggregates() -> None:
    synonyms = load_synonyms()
    index = build_solvent_index(ich_service.Q3C_DATA, synonyms)
    classified = classify_solvents(
        [
            {
                "solvent": "ethanol",
                "original_name": "95%乙醇",
                "purpose": "清洗",
            },
            {
                "solvent": "definitely-not-listed",
                "original_name": "未知溶剂",
                "purpose": "反应",
            },
        ],
        index,
    )

    assert len(classified) == 2
    assert classified[0]["original_name"] == "95%乙醇"
    assert classified[1]["class"] == "unknown"

    analysis = analyze_steps(
        {
            "step_analysis": [
                {
                    "step_number": 1,
                    "step_title": "反应",
                    "solvents": [{"solvent": "ethanol", "purpose": "反应介质"}],
                },
                {
                    "step_number": 2,
                    "step_title": "洗涤",
                    "solvents": [{"solvent": "ethanol", "purpose": "洗涤"}],
                },
            ]
        },
        index,
    )
    assert analysis["total_unique_solvents"] == 1
    only_solvent = next(iter(analysis["all_solvents"].values()))
    assert only_solvent["steps_used"] == [1, 2]

    report = generate_q3c_report(
        analysis,
        flag_class1=True,
        ich_data_source="测试数据库",
    )
    assert "溶剂残留" in report
    assert "测试数据库" in report


@pytest.mark.anyio
async def test_q3c_analysis_orchestrates_llm_matching_and_reporting(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        ich_service,
        "extract_text_from_docx",
        lambda _: "步骤1：使用 ethanol 反应\n步骤2：使用未知溶剂洗涤",
    )

    async def fake_extract_solvents(steps: list[dict]) -> dict:
        assert len(steps) == 2
        return {
            "steps": [
                {
                    "step_number": 1,
                    "step_title": "反应",
                    "solvents": [
                        {
                            "matched_name": "ethanol",
                            "original_name": "ethanol",
                            "ich_class": "Class 3",
                            "purpose": "反应介质",
                            "amount": "10 L",
                        },
                        {"matched_name": "", "original_name": ""},
                    ],
                },
                {
                    "step_number": 2,
                    "step_title": "洗涤",
                    "solvents": [
                        {
                            "matched_name": "methanol",
                            "original_name": "methanol",
                            "ich_class": "Class 2",
                            "purpose": "洗涤",
                        }
                    ],
                },
            ]
        }

    from app.modules.research import llm_service

    monkeypatch.setattr(llm_service, "extract_solvents_with_llm", fake_extract_solvents)

    result = await ich_service.analyze_ich_q3c_with_llm(b"not-used")

    assert result["type"] == "Q3C"
    assert result["steps_count"] == 2
    assert result["total_solvents"] == 2
    assert result["summary"]["class_3"] == 1
    assert result["summary"]["class_2"] == 1
    assert result["summary"]["unknown"] == 0
    assert "溶剂残留" in result["report"]
