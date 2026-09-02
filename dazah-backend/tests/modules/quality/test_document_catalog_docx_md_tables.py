"""docx→MD 表格结构函数综合测试（伪造 python-docx 对象，不读真实文件）。"""

from types import SimpleNamespace
from typing import Any

from app.modules.quality.service.document_catalog_docx_md import (
    ExtractedImage,
    _extract_effective_date,
    _extract_images,
    _find_column_groups,
    _find_content_start_row,
    _find_main_content_table,
    _find_seq_column,
    _is_data_table_header_row,
    _is_inline_small_header_table,
    _is_small_header_table,
    _merge_column_group_contents,
    _nested_table_to_md,
    _table_to_2d_list,
)


def _cell(text: str, paragraphs: list[str] | None = None, rids: list[str] | None = None) -> Any:  # noqa: E501
    paras = paragraphs if paragraphs is not None else ([text] if text else [])
    cell = SimpleNamespace(
        text=text,
        paragraphs=[SimpleNamespace(text=p) for p in paras],
        _element=_FakeElement(rids or []),
    )
    return cell


class _FakeElement:
    """findall 按本地名匹配（qn() 展开为命名空间 URI，比较尾段）。"""

    def __init__(self, rids: list[str]) -> None:
        self._rids = rids

    def findall(self, xpath: str) -> list[Any]:
        local = xpath.rsplit("}", 1)[-1].rsplit("/", 1)[-1]
        if local.endswith("blip") and self._rids:
            return [_FakeBlip(rid) for rid in self._rids]
        return []


class _FakeBlip:
    def __init__(self, rid: str) -> None:
        self._rid = rid

    def get(self, key: str, default: Any = None) -> Any:
        return self._rid


def _row(cells: list[Any]) -> Any:
    return SimpleNamespace(cells=cells)


def _table(rows: list[list[Any]]) -> Any:
    return SimpleNamespace(rows=[_row(cells) for cells in rows])


def _cell_img(rids: list[str]) -> Any:
    return _cell("", rids=rids)


# ── 序号列 / 起始行 ─────────────────────────────────────


def test_find_seq_column_and_content_start_row() -> None:
    assert _find_seq_column(_table([])) == -1
    table = _table([
        [_cell("标题"), _cell("内容")],
        [_cell("1"), _cell("第一条")],
        [_cell("2"), _cell("第二条")],
        [_cell("3"), _cell("第三条")],
    ])
    assert _find_seq_column(table) == 0
    assert _find_content_start_row(table) == 1
    # 无序号 → -1 / 起始 0
    no_seq = _table([[_cell("a"), _cell("b")], [_cell("c"), _cell("d")]])
    assert _find_seq_column(no_seq) == -1
    assert _find_content_start_row(no_seq) == 0


def test_is_small_header_table() -> None:
    # 命中关键词 + 无序号 → True
    header = _table([
        [_cell("生效日期"), _cell("2024-01-01")],
        [_cell("审核间隔"), _cell("2年")],
    ])
    assert _is_small_header_table(header) is True
    # 有序号列 → False（主内容表）
    main = _table([
        [_cell("1"), _cell("内容")],
        [_cell("2"), _cell("内容2")],
    ])
    assert _is_small_header_table(main) is False
    # 空表 → False
    assert _is_small_header_table(_table([])) is False
    # >10 行 → False
    big = _table([[_cell("生效日期"), _cell("x")]] + [[_cell("a"), _cell("b")]] * 11)
    assert _is_small_header_table(big) is False


def test_find_main_content_table_scoring() -> None:
    # 只有小表（<3行）→ None
    assert _find_main_content_table(SimpleNamespace(tables=[_table([[_cell("x")]])])) is None  # noqa: E501
    # 序号列加分胜出
    small = _table([[_cell("生效日期"), _cell("2024")], [_cell("a"), _cell("b")]])
    main = _table(
        [[_cell("序"), _cell("内容")]]
        + [[_cell(str(i)), _cell("内容" * 20)] for i in range(1, 6)]
    )
    doc = SimpleNamespace(tables=[small, main])
    assert _find_main_content_table(doc) is main


def test_extract_images_various_rels() -> None:
    ok_rel = SimpleNamespace(
        reltype=".../image",
        target_part=SimpleNamespace(blob=b"png", partname="/tmp/pic.PNG"),
    )
    bad_rel = SimpleNamespace(reltype=".../image", target_part=None)
    bad_rel.target_part = None  # type: ignore[assignment]
    doc = SimpleNamespace(part=SimpleNamespace(rels={"rId1": ok_rel, "rId2": bad_rel, "rId3": SimpleNamespace(reltype=".../styles")}))  # noqa: E501
    image_map = _extract_images(doc)
    assert "rId1" in image_map
    assert image_map["rId1"].name.endswith(".png") or image_map["rId1"].name.endswith(".PNG".lower())  # noqa: E501
    assert len(image_map) == 1  # 坏关系被吞掉，非图片关系被跳过


# ── 嵌套表格 → MD ───────────────────────────────────────


def test_nested_table_to_md_with_images_and_dedupe() -> None:
    assert _nested_table_to_md(_table([]), {}) == ""
    image_map = {"rId9": ExtractedImage(name="img_000.png", data=b"x", content_type="image/png")}  # noqa: E501
    table = _table([
        [_cell_img(["rId9"]), _cell("同"), _cell("同")],
        [_cell("A"), _cell("B"), _cell("B")],
    ])
    md = _nested_table_to_md(table, image_map)
    assert "![image](img_000.png)" in md
    assert "| A | B |" in md
    assert "同" in md
    # 重复列被去重：B 只出现一次/行
    assert md.count("| A | B |") == 1


# ── 数据表表头 / 列组 ───────────────────────────────────


def test_is_data_table_header_row() -> None:
    row = _row([_cell("序号"), _cell("版本"), _cell("日期")])
    assert _is_data_table_header_row(row, seq_col=0) is True
    numbered = _row([_cell("1"), _cell("x"), _cell("y")])
    assert _is_data_table_header_row(numbered, seq_col=0) is False
    only_one = _row([_cell(""), _cell("唯一")])
    assert _is_data_table_header_row(only_one, seq_col=0) is False


def test_find_column_groups_dedupes_identical() -> None:
    table = _table([
        [_cell("序"), _cell("内容"), _cell("内容"), _cell("备注")],
        [_cell("1"), _cell("A"), _cell("A"), _cell("n1")],
        [_cell("2"), _cell("B"), _cell("B"), _cell("n2")],
    ])
    reps = _find_column_groups(table, seq_col=0)
    assert 1 in reps and 2 not in reps and 3 in reps
    # 无内容列 → []
    single = _table([[_cell("序")], [_cell("1")]])
    assert _find_column_groups(single, seq_col=0) == []


def test_merge_column_group_contents_branches() -> None:
    assert _merge_column_group_contents(_row([]), []) == ""
    # 全空 → ""
    empty_cells = _row([_cell(""), _cell("")])
    assert _merge_column_group_contents(empty_cells, [0, 1]) == ""
    # 单列组 → 原样
    single = _row([_cell("a", paragraphs=["a1", "a2"]), _cell("")])
    assert _merge_column_group_contents(single, [0]) == "a1\na2"
    # 完全相同 → 一份
    same = _row([_cell("x", paragraphs=["p1", "p2"]), _cell("x", paragraphs=["p1", "p2"])])  # noqa: E501
    assert _merge_column_group_contents(same, [0, 1]) == "p1\np2"
    # 段落数相近（2列）→ "名称（编号）" 配对
    paired = _row([
        _cell("n", paragraphs=["规程A", "规程B"]),
        _cell("c", paragraphs=["SOP-1", "SOP-2"]),
    ])
    out = _merge_column_group_contents(paired, [0, 1])
    assert "规程A（SOP-1）" in out
    # 段落数差异大 → 去重拼接
    varied = _row([
        _cell("n", paragraphs=["A", "B", "C", "D", "E"]),
        _cell("c", paragraphs=["A", "X"]),
    ])
    out2 = _merge_column_group_contents(varied, [0, 1])
    assert "A" in out2 and "X" in out2


# ── 生效日期 ────────────────────────────────────────────


def test_extract_effective_date() -> None:
    assert _extract_effective_date(SimpleNamespace(tables=[])) == ""
    doc = SimpleNamespace(tables=[
        _table([
            [_cell("文件编号"), _cell("ABC-1")],
            [_cell("生效日期"), _cell("2024-06-01")],
        ])
    ])
    assert _extract_effective_date(doc) == "2024-06-01"
    # 右侧为空 → 继续；找不到 → ""
    doc2 = SimpleNamespace(tables=[_table([[_cell("生效日期"), _cell("")], [_cell("x"), _cell("y")]])])  # noqa: E501
    assert _extract_effective_date(doc2) == ""


def test_table_to_2d_list() -> None:
    table = _table([[_cell(" a\nb "), _cell("c")]])
    assert _table_to_2d_list(table) == [["a b", "c"]]


# ── XML 级首页小表判断 ─────────────────────────────────


class _XmlText:
    def __init__(self, text: str) -> None:
        self.text = text


def _local(xpath: str) -> str:
    return xpath.rsplit("}", 1)[-1].rsplit("/", 1)[-1]


class _XmlCell:
    def __init__(self, texts: list[str]) -> None:
        self._texts = [_XmlText(t) for t in texts]

    def findall(self, xpath: str) -> list[Any]:
        if _local(xpath).endswith("t"):
            return self._texts
        return []


class _XmlRow:
    def __init__(self, cells_text: list[str]) -> None:
        self._cells = [_XmlCell([t]) for t in cells_text]

    def findall(self, xpath: str) -> list[Any]:
        if _local(xpath).endswith("tc"):
            return self._cells
        return []


def test_is_inline_small_header_table() -> None:
    assert _is_inline_small_header_table([]) is False
    header_row = _XmlRow(["生效日期", "2024-01-01"])
    plain = _XmlRow(["a", "b"])
    # 命中关键词且无序号 → True
    assert _is_inline_small_header_table([header_row, plain]) is True
    # 带序号行 → False
    numbered = _XmlRow(["1", "内容内容"])
    assert _is_inline_small_header_table([header_row, numbered]) is False
    # 无关键词 → False
    assert _is_inline_small_header_table([plain]) is False
