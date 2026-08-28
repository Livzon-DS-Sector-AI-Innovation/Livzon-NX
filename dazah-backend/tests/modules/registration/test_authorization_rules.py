import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace as _SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from app.modules.registration.service import authorization as service

SimpleNamespace: Any = _SimpleNamespace


def _word_table(*rows: list[str], prefix: str = "", trailing: str = "") -> str:
    body = "".join("\n\x07".join(row) + "\n\x07\n" for row in rows)
    return f"{prefix}{body}{trailing}"


def _ledger_entry(**overrides: object) -> SimpleNamespace:
    now = datetime(2026, 8, 20, tzinfo=UTC)
    values: dict[str, object] = {
        "id": uuid4(),
        "product_name": " 阿魏酸钠 ",
        "market_name": " 国内 ",
        "source_sequence": " 1 ",
        "authorization_file_name": " 授权书A ",
        "quality_standard": " USP ",
        "company_name": " 客户A ",
        "country": " 中国 ",
        "customer_code": " C001 ",
        "purpose": " 注册 ",
        "authorization_date": "2026-08-20",
        "handler": " 张三 ",
        "status": " 已递交 ",
        "remarks": " 首次递交 ",
        "created_at": now,
        "updated_at": now,
        "created_by": uuid4(),
        "updated_by": uuid4(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  A\x07  B\n C ", "A B C"),
        ("", ""),
        ("  单行  ", "单行"),
    ],
)
def test_normalize_inline_text(value: str, expected: str) -> None:
    assert service._normalize_inline_text(value) == expected


def test_line_row_and_remark_normalization() -> None:
    assert service._normalize_lines(" 第一行 \n\n 第二行 ") == ["第一行", "第二行"]
    assert service._fit_row(["A", "B", "C", "D"], 3) == ["A", "B", "C D"]
    assert service._fit_row(["A"], 3) == ["A", "", ""]
    assert service._merge_remark(None, "新增说明") == "新增说明"
    assert service._merge_remark("—", "新增说明") == "新增说明"
    assert service._merge_remark("已有", "") == "已有"
    assert service._merge_remark("已有", "新增") == "已有 新增"
    assert service._is_generic_trailing_note("注明：收回授权时需归档") is True


@pytest.mark.parametrize(
    ("remarks", "expected"),
    [
        (None, "待确认"),
        ("授权已收回", "已收回"),
        ("暂未向官方递交", "未递交"),
        ("资料待更新", "待更新"),
        ("已经递交", "已递交"),
        ("人工核查", "待确认"),
    ],
)
def test_derive_ledger_status(remarks: str | None, expected: str) -> None:
    assert service._derive_ledger_status(remarks) == expected


def test_authorization_date_sort_key_orders_dates_before_text_and_blanks() -> None:
    values = [None, "待确认", "2026/08/20 更新", "2025-01-02"]

    assert sorted(values, key=service._authorization_date_sort_key) == [
        "2025-01-02",
        "2026/08/20 更新",
        "待确认",
        None,
    ]


def test_ledger_keys_signatures_and_sanitized_values() -> None:
    first = _ledger_entry()
    last = _ledger_entry(updated_at=datetime(2026, 8, 21, tzinfo=UTC))

    key = service._build_legacy_ledger_main_key(first)
    signature = service._build_legacy_update_signature(first)
    main_values = service._build_sanitized_main_values(first, last)
    update_values = service._build_sanitized_update_values(first)

    assert key[0] == "阿魏酸钠"
    assert key[-1] == "已递交"
    assert signature == ("2026-08-20", "张三", "首次递交")
    assert main_values["updated_at"] == last.updated_at
    assert main_values["country"] == "中国"
    assert update_values["handler"] == "张三"
    assert service._sanitize_optional_ledger_text("  ") is None


def test_normalize_sort_and_group_legacy_entries() -> None:
    later = _ledger_entry(authorization_date="2026-08-20")
    earlier = _ledger_entry(authorization_date="2026-01-01")
    separate = _ledger_entry(product_name="  阿立哌唑 ", authorization_date=None)

    service._normalize_legacy_entry_in_place(separate)
    grouped = service._group_legacy_ledger_entries([later, separate, earlier])

    assert separate.product_name == "阿立哌唑"
    assert len(grouped) == 2
    matching_group = next(items for items in grouped.values() if len(items) == 2)
    assert [item.authorization_date for item in matching_group] == [
        "2026-01-01",
        "2026-08-20",
    ]


@pytest.mark.parametrize(
    ("relative", "product", "market", "category"),
    [
        (
            "阿魏酸钠-list-of-authorized-parties-to-incorporate-by-reference.docx",
            "阿魏酸钠",
            "FDA",
            "FDA 引用授权名单",
        ),
        ("授权书台帐-艾普拉唑-欧盟.docx", "艾普拉唑", "欧盟", "授权书台账"),
        (
            "盐酸伊托必利授权客户明细/客户-登记-日本.docx",
            "盐酸伊托必利",
            "日本",
            "授权客户明细",
        ),
        ("普通产品/资料.docx", "普通产品", None, "产品授权资料"),
    ],
)
def test_extract_material_metadata(
    tmp_path: Path,
    relative: str,
    product: str,
    market: str | None,
    category: str,
) -> None:
    source_root = tmp_path / "授权资料"
    file_path = source_root / relative

    assert service._extract_product_name(file_path, source_root) == product
    assert service._extract_market_name(file_path) == market
    assert service._extract_category(file_path) == category
    assert service._should_skip_source_file(file_path.with_name("~$temp.docx")) is True
    assert len(service._slugify_material_id(relative)) == 32
    assert service._powershell_quote("a'b") == "a''b"


def test_parse_word_table_preserves_prefix_rows_and_trailing_lines() -> None:
    raw = _word_table(
        ["序号", "公司", "日期"],
        ["1", "客户A", "2026-08-20"],
        prefix="授权名单\n",
        trailing="备注说明",
    )

    prefix, rows, trailing = service._parse_word_table(raw)

    assert prefix == ["授权名单"]
    assert rows == [["序号", "公司", "日期"], ["1", "客户A", "2026-08-20"]]
    assert trailing == ["备注说明"]


def test_parse_fda_records_inherits_merged_cells_and_filters_generic_note() -> None:
    raw = _word_table(
        ["No.", "Company", "Address", "Reference", "LOA", "Submission", "Sections"],
        ["1", "客户A", "地址A", "REF-1", "2026-01-01", "2026-01-02", "3.2.S"],
        ["2", " ", " ", " ", "2026-02-01", "2026-02-02", "3.2.P"],
        trailing="注明：收回授权时需归档\n有效备注",
    )

    records, note = service._parse_fda_records(raw)

    assert len(records) == 2
    assert records[1].company_name == "客户A"
    assert records[1].reference_number == "REF-1"
    assert records[1].referenced_sections == "3.2.P"
    assert note == "有效备注"


def test_parse_fda_records_handles_empty_and_short_merged_rows() -> None:
    assert service._parse_fda_records("无表格") == ([], None)
    raw = _word_table(
        ["Company", "Address", "Reference", "LOA", "Submission", "Sections"],
        ["客户A", "地址A", "REF-1", "2026-01-01", "2026-01-02", "3.2.S"],
        [" ", "2026-02-01", "2026-02-02", "3.2.P"],
        [" ", "REF-2", "2026-03-01", "2026-03-02", "3.2.A"],
    )

    records, _ = service._parse_fda_records(raw)

    assert len(records) == 3
    assert records[-1].reference_number == "REF-2"


def test_parse_ledger_records_splits_country_and_merges_explanation_rows() -> None:
    raw = _word_table(
        [
            "序号",
            "授权文件",
            "标准",
            "公司/国家",
            "客户编码",
            "用途",
            "日期",
            "经办人",
            "备注",
        ],
        [
            "1",
            "授权书A",
            "USP",
            "客户A / 中国",
            "C001",
            "注册",
            "2026-01-01",
            "张三",
            "首次递交",
        ],
        ["更新日期", "2026-02-01"],
        trailing="附加说明\n注明：收回授权时需归档",
    )

    records, note = service._parse_ledger_records(raw)

    assert len(records) == 1
    assert records[0].company_name == "客户A"
    assert records[0].country == "中国"
    assert records[0].remarks == "首次递交 更新日期 2026-02-01"
    assert note == "附加说明"
    assert service._split_company_and_country("") == (None, None)
    assert service._split_company_and_country("仅公司") == ("仅公司", None)


def test_scan_materials_builds_stable_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "授权资料"
    source_root.mkdir()
    fda = source_root / f"阿魏酸钠{service.FDA_SUFFIX}.docx"
    ledger = source_root / "授权书台帐-阿魏酸钠-欧盟.docx"
    skipped = source_root / "~$temp.docx"
    for path in (fda, ledger, skipped):
        path.write_bytes(b"doc")
    monkeypatch.setattr(service, "_get_authorization_source_dir", lambda: source_root)

    materials, summary = service._scan_authorization_materials()

    assert [item.file_name for item in materials] == [fda.name, ledger.name]
    assert summary.total_products == 1
    assert summary.total_files == 2
    assert summary.fda_products == 1
    assert summary.fda_files == 1


def test_build_content_index_combines_fda_and_market_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "授权资料"
    source_root.mkdir()
    fda = source_root / f"阿魏酸钠{service.FDA_SUFFIX}.docx"
    ledger = source_root / "授权书台帐-阿魏酸钠-欧盟.docx"
    failed = source_root / "普通产品" / "损坏.docx"
    failed.parent.mkdir()
    for path in (fda, ledger, failed):
        path.write_bytes(b"doc")

    fda_text = _word_table(
        ["Company", "Address", "Reference", "LOA", "Submission", "Sections"],
        ["客户A", "地址A", "REF-1", "2026-01-01", "2026-01-02", "3.2.S"],
    )
    ledger_text = _word_table(
        [
            "序号",
            "授权文件",
            "标准",
            "公司/国家",
            "客户编码",
            "用途",
            "日期",
            "经办人",
            "备注",
        ],
        [
            "1",
            "授权书A",
            "USP",
            "客户B/德国",
            "C002",
            "注册",
            "2026-02-01",
            "李四",
            "已递交",
        ],
        trailing="补充备注",
    )

    def read_content(path: Path) -> str:
        if path == failed:
            raise RuntimeError("broken document")
        return fda_text if path == fda else ledger_text

    monkeypatch.setattr(service, "_get_authorization_source_dir", lambda: source_root)
    monkeypatch.setattr(service, "_read_word_content", read_content)
    service._build_authorization_content_cached.cache_clear()

    overview, products, details = service._build_authorization_content_cached(
        "snapshot"
    )

    assert overview.total_products == 2
    assert overview.total_files == 3
    assert overview.fda_records == 1
    assert products[0].product_name == "阿魏酸钠"
    assert details["阿魏酸钠"].ledger_records[0].market_name == "欧盟"
    assert "补充备注" in details["阿魏酸钠"].ledger_records[0].remarks  # type: ignore[operator]
    service._build_authorization_content_cached.cache_clear()


def test_build_content_and_scan_return_empty_when_source_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing"
    monkeypatch.setattr(service, "_get_authorization_source_dir", lambda: missing)
    service._build_authorization_content_cached.cache_clear()

    overview, products, details = service._build_authorization_content_cached("missing")
    materials, summary = service._scan_authorization_materials()

    assert overview.total_files == 0
    assert products == []
    assert details == {}
    assert materials == []
    assert summary.total_files == 0
    service._build_authorization_content_cached.cache_clear()


def test_generate_authorization_letter_replaces_docx_xml_and_binary_templates() -> None:
    source = io.BytesIO()
    with zipfile.ZipFile(source, "w") as zipped:
        zipped.writestr("word/document.xml", "<w:t>旧客户</w:t>")
        zipped.writestr("other.txt", b"unchanged")

    rendered = service.generate_authorization_letter_bytes(
        source.getvalue(), [("旧客户", "新客户"), ("不存在", "忽略")]
    )
    with zipfile.ZipFile(io.BytesIO(rendered)) as zipped:
        assert "新客户" in zipped.read("word/document.xml").decode("utf-8")
        assert zipped.read("other.txt") == b"unchanged"

    binary = "客户A".encode("utf-16le")
    assert service.generate_authorization_letter_bytes(
        binary, [("客户A", "客户B")]
    ) == "客户B".encode("utf-16le")
    with pytest.raises(ValueError, match="长度不匹配"):
        service.generate_authorization_letter_bytes(binary, [("客户A", "长客户B")])


def test_docx_replace_rejects_non_utf8_document_xml() -> None:
    source = io.BytesIO()
    with zipfile.ZipFile(source, "w") as zipped:
        zipped.writestr("word/document.xml", b"\xff\xfe")

    with pytest.raises(ValueError, match="UTF-8"):
        service.generate_authorization_letter_bytes(source.getvalue(), [("A", "B")])
