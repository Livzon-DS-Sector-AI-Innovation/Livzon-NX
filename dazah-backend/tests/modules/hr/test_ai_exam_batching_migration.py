"""AI 笔试出题分批与加权分配纯函数测试。

测试范围（对应 AI 笔试出题性能优化规格说明 Testing Decisions）：
- _weighted_alloc：最大余数法加权分配，总和恒等于请求数
- _split_files_into_batches：按文件分批、素材不跨批重复、题数加权、
  单批题数上限拆分、uploaded/manual 独立成批、0 题批跳过

全部为纯函数测试，无需 DB / Redis / LLM。
"""

from app.modules.hr.ai_exam_api import (
    _sanitize_questions,
    _split_files_into_batches,
    _weighted_alloc,
)

# ── _weighted_alloc 加权分配 ─────────────────────────────


def test_weighted_alloc_total_conserved():
    """分配结果总和必须恒等于请求题数（多组权重）。"""
    weights = [100, 300, 600]
    for total in (0, 1, 5, 10, 39):
        result = _weighted_alloc(total, weights)
        assert sum(result) == total
        assert len(result) == len(weights)


def test_weighted_alloc_proportional():
    """权重大的批次应分到更多题目。"""
    result = _weighted_alloc(10, [100, 300, 600])
    assert result == [1, 3, 6]


def test_weighted_alloc_zero_total():
    """请求题数为 0 时全部返回 0。"""
    assert _weighted_alloc(0, [100, 300, 600]) == [0, 0, 0]


def test_weighted_alloc_empty_weights():
    """权重列表为空时返回空列表。"""
    assert _weighted_alloc(10, []) == []


def test_weighted_alloc_zero_weight_batch():
    """无素材批次（权重 0）应分到 0 题，素材集中在有权重批次。"""
    result = _weighted_alloc(5, [0, 0, 1])
    assert result == [0, 0, 5]


def test_weighted_alloc_all_zero_weights():
    """全 0 权重兜底均分，不抛异常。"""
    result = _weighted_alloc(3, [0, 0, 0])
    assert sum(result) == 3


# ── _split_files_into_batches 按文件分批 ────────────────


def _file(name: str, chars: int) -> dict:
    return {"name": name, "code": None, "content": "x" * chars}


def test_split_no_content_files_returns_empty():
    """全部文件无有效内容时返回空批次列表。"""
    batches = _split_files_into_batches(
        [_file("A", 0), {"name": "B", "code": None, "content": "  "}],
        "",
        "",
        5,
        0,
        0,
        5,
    )
    assert batches == []


def test_split_single_file_single_quota():
    """单文件：仅一个批次，题数等于请求数。"""
    batches = _split_files_into_batches(
        [_file("A", 1000)],
        "",
        "",
        5,
        3,
        0,
        2,
        max_content_per_batch=20000,
        max_questions_per_batch=10,
    )
    assert len(batches) == 1
    b = batches[0]
    assert [f["name"] for f in b["files"]] == ["A"]
    assert (b["single"], b["multiple"], b["true_false"], b["fill"]) == (5, 3, 0, 2)


def test_split_small_files_merged_by_content_limit():
    """小文件应合并到同一批次，素材总量不超过单批上限。"""
    files = [_file("A", 10000), _file("B", 12000), _file("C", 1000)]
    batches = _split_files_into_batches(
        files,
        "",
        "",
        5,
        5,
        0,
        5,
        max_content_per_batch=15000,
        max_questions_per_batch=10,
    )
    # B(12000)+C(1000)=13000 ≤ 15000 合并；A(10000) 无法再并入 → 独立批
    names_per_batch = [[f["name"] for f in b["files"]] for b in batches]
    assert names_per_batch == [["B", "C"], ["A"]]


def test_split_file_content_not_repeated_across_batches():
    """每个文件只能出现在一个批次中（素材不跨批重复）。"""
    files = [_file("A", 10000), _file("B", 12000), _file("C", 1000)]
    batches = _split_files_into_batches(
        files,
        "",
        "",
        5,
        5,
        0,
        5,
        max_content_per_batch=15000,
        max_questions_per_batch=10,
    )
    all_names = [f["name"] for b in batches for f in b["files"]]
    for n in ("A", "B", "C"):
        assert all_names.count(n) == 1


def test_split_questions_weighted_by_content():
    """题数应按各批素材长度加权分配，且各题型总量守恒。"""
    files = [_file("A", 10000), _file("B", 20000)]
    batches = _split_files_into_batches(
        files,
        "",
        "",
        5,
        0,
        0,
        5,
        max_content_per_batch=20000,
        max_questions_per_batch=10,
    )
    assert len(batches) == 2  # A、B 各自成批（各 10 题 ≤ 单批上限）
    total_single = sum(b["single"] for b in batches)
    total_fill = sum(b["fill"] for b in batches)
    assert total_single == 5
    assert total_fill == 5
    # 分组按内容长度降序：batches[0] 是更重的 B，应分到更多或相等的题
    assert batches[0]["single"] >= batches[1]["single"]


def test_split_questions_per_batch_capped():
    """单批题数不得超过上限：超上限时拆成多个子批（素材相同，题量分拆）。"""
    # 单文件 40 题 → 4 个子批，每批 ≤ 10 题
    batches = _split_files_into_batches(
        [_file("A", 30000)],
        "",
        "",
        20,
        0,
        0,
        20,
        max_content_per_batch=20000,
        max_questions_per_batch=10,
    )
    assert len(batches) == 4
    for b in batches:
        total = b["single"] + b["multiple"] + b["true_false"] + b["fill"]
        assert total <= 10
    total_single = sum(b["single"] for b in batches)
    total_fill = sum(b["fill"] for b in batches)
    assert total_single == 20
    assert total_fill == 20


def test_split_uploaded_and_manual_own_batches():
    """上传内容与手动内容应各自独立成批，与文件批次分离。"""
    # 三份素材长度相当，确保三批都能加权分到题目
    batches = _split_files_into_batches(
        [_file("A", 1000)],
        "上传内容示例：" + "a" * 1000,
        "手动补充示例：" + "b" * 1000,
        3,
        0,
        0,
        3,
        max_content_per_batch=20000,
        max_questions_per_batch=10,
    )
    assert len(batches) == 3
    # 文件批、上传批、手动批各一份
    file_batch = next(b for b in batches if b["files"])
    upload_batch = next(b for b in batches if b["uploaded"])
    manual_batch = next(b for b in batches if b["manual"])
    assert file_batch["uploaded"] == "" and file_batch["manual"] == ""
    assert upload_batch["files"] == [] and upload_batch["manual"] == ""
    assert manual_batch["files"] == [] and manual_batch["uploaded"] == ""
    # 各题型总量守恒
    total = sum(
        b["single"] + b["multiple"] + b["true_false"] + b["fill"] for b in batches
    )
    assert total == 6


def test_split_zero_quota_batches_skipped():
    """分配到 0 题的批次应被跳过（不创建无谓的 LLM 调用）。"""
    # 大批素材但只请求 1 题：只有权重最大批分到这 1 题，其余批跳过
    files = [_file("A", 5000), _file("B", 5001), _file("C", 5002)]
    batches = _split_files_into_batches(
        files,
        "",
        "",
        1,
        0,
        0,
        0,
        max_content_per_batch=20000,
        max_questions_per_batch=10,
    )
    assert len(batches) == 1
    total = batches[0]["single"] + batches[0]["multiple"]
    assert total == 1


def test_split_mixed_question_types_allocated():
    """四种题型同时存在时应全部加权分配且各自守恒。"""
    files = [_file("A", 1000), _file("B", 2000)]
    batches = _split_files_into_batches(
        files,
        "",
        "",
        3,
        4,
        5,
        6,
        max_content_per_batch=20000,
        max_questions_per_batch=10,
    )
    assert sum(b["single"] for b in batches) == 3
    assert sum(b["multiple"] for b in batches) == 4
    assert sum(b["true_false"] for b in batches) == 5
    assert sum(b["fill"] for b in batches) == 6


def test_split_large_uploaded_content_split_across_subbatches():
    """大段上传内容拆子批时应按题数占比切分，不得整份复制（避免输入放大）。"""
    uploaded = "y" * 120000
    batches = _split_files_into_batches(
        [],
        uploaded,
        "",
        10,
        0,
        0,
        10,
        max_content_per_batch=20000,
        max_questions_per_batch=10,
    )
    # 20 题 → 2 个子批，各 10 题
    assert len(batches) == 2
    total_input = sum(len(b["uploaded"]) for b in batches)
    # 内容分摊后总和 = 原内容长度（不放大、不丢失）
    assert total_input == len(uploaded)
    # 各子批内容互不重叠，拼接后还原全量
    assert "".join(b["uploaded"] for b in batches) == uploaded


def test_split_large_uploaded_with_files_no_repetition():
    """15 份文件 + 12 万字上传内容：uploaded 内容只出现一次，不跨子批重复。"""
    files = [_file(f"F{i}", 5000) for i in range(15)]
    uploaded = "y" * 120000
    batches = _split_files_into_batches(
        files,
        uploaded,
        "",
        20,
        0,
        0,
        20,
        max_content_per_batch=20000,
        max_questions_per_batch=10,
    )
    total_uploaded = sum(len(b["uploaded"]) for b in batches)
    assert total_uploaded == len(uploaded)
    # 题型守恒
    assert sum(b["single"] for b in batches) == 20
    assert sum(b["fill"] for b in batches) == 20


# ── _sanitize_questions LLM 输出容错归类 ──────────────


def _valid_choice(question: str = "选择题", answer: str = "A") -> dict:
    return {
        "question": question,
        "options": [
            {"label": "A", "text": "a"},
            {"label": "B", "text": "b"},
            {"label": "C", "text": "c"},
            {"label": "D", "text": "d"},
        ],
        "answer": answer,
    }


def test_sanitize_moves_tf_questions_from_choices():
    """LLM 误放入 choice_questions 的判断题应归回 true_false。"""
    choices = [
        _valid_choice(),
        {"question": "判断一", "answer": "√"},
        {"question": "判断二", "answer": "×"},
    ]
    true_falses = [{"question": "原有判断", "answer": "√"}]
    fills: list[dict] = []

    c, tf, f = _sanitize_questions(choices, true_falses, fills)
    assert len(c) == 1  # 只保留有效选择题
    assert len(tf) == 3  # 2 个误入归回 + 1 个原有
    assert tf[1]["question"] == "判断一" and tf[1]["answer"] == "√"
    assert f == []


def test_sanitize_drops_junk_rows():
    """无题干 / 无答案 / 非 dict / 无 options 且非判断答案的脏数据应丢弃。"""
    choices = [
        _valid_choice(),
        {
            "question": "",
            "answer": "A",
            "options": [{"label": "A", "text": "a"}],
        },  # 无题干
        {"question": "无options无判断答案", "answer": "X"},  # 无法归类
        "not-a-dict",
    ]
    true_falses = [
        {"question": "", "answer": "√"},
        {"question": "无答案", "answer": ""},
    ]
    fills = [
        {"question": "", "answer": "答案"},
        {"question": "有效填空______", "answer": "答"},
    ]

    c, tf, f = _sanitize_questions(choices, true_falses, fills)
    assert len(c) == 1
    assert len(tf) == 0  # 无题干/无答案的判断题全被丢弃
    assert len(f) == 1
    assert f[0]["question"] == "有效填空______"


# ── _sanitize_questions 逐题 Schema 校验（M2 加固） ────────


def test_sanitize_drops_choice_with_broken_options():
    """options 元素缺 label/text 的选择题应被逐题校验丢弃（M2）。"""
    choices = [
        _valid_choice(),
        {
            "question": "选项残缺的选择题",
            "options": ["A. 字符串选项", "B. 无法通过校验"],
            "answer": "A",
        },
        {
            "question": "选项缺 text",
            "options": [{"label": "A"}],
            "answer": "A",
        },
    ]
    true_falses: list[dict] = []
    fills: list[dict] = []

    c, tf, f = _sanitize_questions(choices, true_falses, fills)
    assert len(c) == 1  # 只保留有效选择题
    assert c[0]["question"] == "选择题"
    assert tf == []
    assert f == []


def test_sanitize_drops_choice_without_answer():
    """有 options 但缺 answer 的选择题应被丢弃（M2）。"""
    choices = [
        {
            "question": "缺答案的选择题",
            "options": [{"label": "A", "text": "a"}, {"label": "B", "text": "b"}],
        },
    ]
    c, tf, f = _sanitize_questions(choices, [], [])
    assert c == []
    assert tf == []
    assert f == []


def test_sanitize_keeps_tf_with_mark_and_drops_broken_tf():
    """判断题缺题干/缺答案/非 dict 应被丢弃（M2）；字符串答案合法保留。"""
    true_falses = [
        {"question": "正常判断", "answer": "√"},
        {"question": "答案为说明文字", "answer": "以上说法正确"},
        {"question": "", "answer": "√"},
        {"question": "无答案", "answer": ""},
        "not-a-dict",
    ]
    c, tf, f = _sanitize_questions([], true_falses, [])
    assert len(tf) == 2
    assert tf[0]["question"] == "正常判断"
    assert tf[1]["question"] == "答案为说明文字"


def test_sanitize_drops_fill_without_question():
    """填空题缺题干应被丢弃（M2）。"""
    fills = [
        {"question": "有效填空______", "answer": "答"},
        {"answer": "无题干填空"},
    ]
    c, tf, f = _sanitize_questions([], [], fills)
    assert len(f) == 1
    assert f[0]["question"] == "有效填空______"


# ── A1：文件批拆子批时文件内容按题数占比切分（防输入放大） ──


def _split_batches(files, uploaded="", manual="", **kwargs):
    """便捷调用 _split_files_into_batches。"""
    return _split_files_into_batches(
        files,
        uploaded,
        manual,
        kwargs.get("single", 0),
        kwargs.get("multiple", 0),
        kwargs.get("true_false", 0),
        kwargs.get("fill", 0),
        max_content_per_batch=kwargs.get("max_content_per_batch", 20000),
        max_questions_per_batch=kwargs.get("max_questions_per_batch", 10),
    )


def test_split_file_subbatches_slice_content_not_duplicated():
    """超大文件批拆子批时，文件内容按子批题数占比切片，不整份重复（A1）。"""
    big_content = "材" * 1000
    files = [{"name": "big.md", "code": None, "content": big_content}]
    # 15 道题超过单批 10 题上限 → 拆 2 个子批
    batches = _split_batches(files, single=15, max_questions_per_batch=10)
    assert len(batches) == 2
    # 两个子批的内容总长 = 原文件长（不放大）
    total = sum(len(b["files"][0]["content"]) for b in batches)
    assert total == 1000
    # 子批内容不重叠且是原内容的切片
    first = batches[0]["files"][0]["content"]
    second = batches[1]["files"][0]["content"]
    assert first + second == big_content


def test_split_file_subbatches_single_batch_keeps_full_content():
    """文件批不拆子批时保留整份内容（不切片）。"""
    content = "材" * 500
    files = [{"name": "a.md", "code": None, "content": content}]
    batches = _split_batches(files, single=3)
    assert len(batches) == 1
    assert batches[0]["files"][0]["content"] == content
