"""偏差根因归类（人机料法环）与部门推导测试。"""

from types import SimpleNamespace

import pytest

from app.modules.quality.service import deviation_cause_analysis as service


def test_keyword_category_prefers_root_cause_sentence_over_direct_cause() -> None:
    text = (
        "直接原因：检验员赵双运行序列时，肢体与台面非预期的触碰，导致序列中断。\n"
        "根本原因：键盘与操作区域处于同一操作平面，且操作软件不具备防错机制。"
    )
    assert service.keyword_category(text) == "设施/设备"


def test_keyword_category_covers_five_categories_and_fallback() -> None:
    assert service.keyword_category("根本原因：文件中未对滤芯更换做出规定。") == "文件"
    assert service.keyword_category("根本原因：人员未经培训导致误操作。") == "人员"
    assert service.keyword_category("根本原因：进样针夹层堵塞导致负压。") == "设施/设备"
    assert service.keyword_category("根本原因：物料杂质含量异常。") == "产品/物料"
    assert service.keyword_category("根本原因：环境的温度超出规定范围。") == "环境"
    assert service.keyword_category(None) is None
    assert service.keyword_category("根本原因：原因不明。") == "其它"


def test_keyword_department_extracts_workshop_and_qa() -> None:
    assert service.keyword_department("201二车间工艺员巡检发现。") == "201二车间"
    assert service.keyword_department("检验员在QC中控中心液相室发现。") == "QC"
    assert service.keyword_department("QA人员上传入库扫描数据时发现。") == "QA"
    assert service.keyword_department("仓库管理员收货时发现。") == "仓库"
    assert service.keyword_department("陈芳") is None


def _record(code: str, **kwargs: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "deviation_code": code,
        "description": "描述",
        "root_cause_analysis": "根本原因：设备故障。",
        "root_cause_category": None,
        "department": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class _FakeDB:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
async def test_fill_missing_analysis_uses_llm_result_and_skips_filled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filled = _record("PC-1", root_cause_category="文件", department="QA")
    blank_llm = _record("PC-2")
    blank_llm_fail = _record("PC-3")
    db = _FakeDB()

    async def fake_analyze(records):
        return {
            "PC-2": {"category": "人员", "department": "QC"},
            "PC-3": {"category": "", "department": ""},
        }

    monkeypatch.setattr(service, "analyze_records", fake_analyze)
    await service.fill_missing_analysis(
        db, [filled, blank_llm, blank_llm_fail], include_department=True
    )

    assert filled.root_cause_category == "文件"
    assert filled.department == "QA"
    assert blank_llm.root_cause_category == "人员"
    assert blank_llm.department == "QC"
    assert blank_llm_fail.root_cause_category == "设施/设备"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_fill_missing_analysis_falls_back_to_keywords_on_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.llm import LLMConfigError

    async def raise_config_error(self, _messages, **_kwargs):
        raise LLMConfigError("no config")

    # 单例方法统一 patch 类型，避免实例属性污染后续用例
    monkeypatch.setattr(
        type(service.llm_client), "chat_json", raise_config_error
    )
    record = _record(
        "PC-9",
        description="检验员在QC液相室发现异常。",
        root_cause_analysis="根本原因：文件中未规定清洁要求。",
    )
    db = _FakeDB()
    await service.fill_missing_analysis(db, [record], include_department=True)
    assert record.root_cause_category == "文件"
    assert record.department == "QC"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_fill_missing_analysis_skips_when_nothing_missing() -> None:
    record = _record("PC-4", root_cause_category="人员", department="QC")
    db = _FakeDB()
    await service.fill_missing_analysis(db, [record])
    assert db.commits == 0
