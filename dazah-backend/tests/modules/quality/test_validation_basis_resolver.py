"""验证基准匹配（validation_basis_resolver）单元测试。

覆盖：编号归一化/修订拆分、设备位号与批号噪音过滤、Word 空格修订容错、
目录反查（命中/缺失/版本不一致/噪音忽略）。
"""

from __future__ import annotations

import uuid

from app.modules.quality.service.validation_basis_resolver import (
    BasisEntry,
    DocumentBasis,
    _compact,
    _split_revision,
    extract_document_number,
    extract_reference_codes,
    infer_doc_kind,
    resolve_references,
)


def _entry(code: str | None, name: str = "") -> BasisEntry:
    return BasisEntry(
        id=uuid.uuid4(),
        code=code,
        name=name,
        effective_date=None,
        updated_at=None,
    )


def _basis(*entries: BasisEntry) -> DocumentBasis:
    return DocumentBasis(
        entries=list(entries),
        prefixes={
            "SMP",
            "SOP",
            "STP",
            "KP",
            "VP",
            "VR",
            "MS",
            "QS",
            "PS",
            "EQ",
            "QC",
            "RA",
        },
    )


class TestCompactAndSplit:
    def test_compact_removes_separators(self) -> None:
        assert _compact("SMP-QA-105 / 03") == "SMPQA10503"
        assert _compact("smp-qa-105/03") == "SMPQA10503"

    def test_split_revision(self) -> None:
        assert _split_revision("SMP-QA-105/03") == ("SMP-QA-105", "03")
        # -NN 结尾是文档序号（非修订），不拆分
        assert _split_revision("VR-QC-M1731-01") == ("VR-QC-M1731-01", None)
        assert _split_revision("STP-QS-MC-001") == ("STP-QS-MC-001", None)


class TestDocKindAndNumber:
    def test_infer_doc_kind(self) -> None:
        assert infer_doc_kind("VP-FT3-CV1902-01 清洁验证方案.doc") == "plan"
        assert infer_doc_kind("VR-FT3-CV1902-01 清洁验证报告.doc") == "report"
        assert infer_doc_kind("没有前缀的文档.docx") == "plan"

    def test_extract_document_number(self) -> None:
        assert (
            extract_document_number("VP-FT3-CV1902-01 清洁验证方案.doc")
            == "VP-FT3-CV1902-01"
        )
        assert (
            extract_document_number("VR-MC-PV1902-01霉酚酸提炼生产验证报告.doc")
            == "VR-MC-PV1902-01"
        )
        assert extract_document_number("随便一个文件.docx") is None


class TestExtractReferenceCodes:
    def test_extract_plain_codes(self) -> None:
        text = (
            "依据《清洁验证管理程序》（SMP-QA-105/03）"
            "和《偏差管理程序》（SMP-QA-011/02）执行。"
        )
        assert extract_reference_codes(text) == ["SMP-QA-105/03", "SMP-QA-011/02"]

    def test_extract_from_table_row(self) -> None:
        text = "| SMP-QA-100/03 | 验证管理程序 | 最新版本并生效 | 符合 |"
        assert extract_reference_codes(text) == ["SMP-QA-100/03"]

    def test_word_space_revision_tolerated(self) -> None:
        text = "引用《清洁验证管理程序》（SMP-QA-105 / 03）执行"
        assert extract_reference_codes(text) == ["SMP-QA-105/03"]

    def test_equipment_noise_filtered(self) -> None:
        text = (
            "设备位号 FT3-1-1-077、FT3-2-1-422 与仪表 FT3FP-071 均正常，"
            "批号 USMC-A-G1904001 取样完成。"
        )
        assert extract_reference_codes(text) == []

    def test_mixed_noise_and_refs(self) -> None:
        text = (
            "钠化罐 FT3-1-1-077 清洁依据《清洁验证管理程序》（SMP-QA-105/03），"
            "检测限引用 VR-QC-M1731-01。"
        )
        assert extract_reference_codes(text) == ["SMP-QA-105/03", "VR-QC-M1731-01"]


class TestResolveReferences:
    def test_exact_match(self) -> None:
        basis = _basis(
            _entry("SMP-QA-105/03", "清洁验证管理程序"),
            _entry("SOP-FT3-201/03", "钠化罐清洁标准操作规程"),
        )
        items = resolve_references(basis, "依据（SMP-QA-105/03）执行")
        assert len(items) == 1
        item = items[0]
        assert item.matched is True
        assert item.match_type == "exact"
        assert item.issue == "none"
        assert item.current_revision == "03"

    def test_version_mismatch(self) -> None:
        basis = _basis(_entry("SMP-QA-105/03", "清洁验证管理程序"))
        items = resolve_references(basis, "依据（SMP-QA-105/02）执行")
        assert len(items) == 1
        item = items[0]
        assert item.revision == "02"
        assert item.current_revision == "03"
        assert item.issue == "version_mismatch"
        assert item.match_type == "related"

    def test_missing_reference(self) -> None:
        basis = _basis(_entry("SMP-QA-100/03", "验证管理程序"))
        items = resolve_references(basis, "依据（SMP-QA-999/01）执行")
        assert len(items) == 1
        item = items[0]
        assert item.matched is False
        assert item.match_type == "missing"
        assert item.issue == "missing"

    def test_unknown_prefix_treated_as_noise(self) -> None:
        basis = _basis(_entry("SMP-QA-100/03", "验证管理程序"))
        # 前缀 XYZ 不在目录前缀集合，视为噪音忽略
        items = resolve_references(basis, "依据（XYZ-AB-123/01）执行")
        assert len(items) == 1
        assert items[0].match_type == "noise"
        assert items[0].issue == "none"

    def test_latest_version_selected(self) -> None:
        basis = _basis(
            _entry("SMP-QA-105/02", "清洁验证管理程序（旧版）"),
            _entry("SMP-QA-105/03", "清洁验证管理程序（现行版）"),
        )
        items = resolve_references(basis, "依据（SMP-QA-105/02）执行")
        assert items[0].current_revision == "03"
        assert items[0].issue == "version_mismatch"
        assert items[0].entry_name == "清洁验证管理程序（现行版）"

    def test_empty_text_no_items(self) -> None:
        assert resolve_references(_basis(), "") == []

    def test_to_dict_shape(self) -> None:
        basis = _basis(_entry("SMP-QA-105/03", "清洁验证管理程序"))
        items = resolve_references(basis, "依据（SMP-QA-105/03）执行")
        data = items[0].to_dict()
        assert data["code"] == "SMP-QA-105/03"
        assert data["matched"] is True
        assert data["entry_code"] == "SMP-QA-105/03"
        assert data["entry_id"] is not None
