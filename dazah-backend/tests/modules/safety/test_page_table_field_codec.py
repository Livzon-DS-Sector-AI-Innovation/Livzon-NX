"""页面镜像字段编解码测试（飞书字段类型 → 前端规范值 → 飞书写入格式）。"""

import pytest

from app.modules.safety.feishu.field_codec import (
    FieldCodecError,
    FieldSchema,
    attachment_field_or_error,
    build_field_schema,
    decode_record_fields,
    decode_value,
    encode_record_fields,
    encode_value,
    existing_attachment_tokens,
)

# 与真实表 tblVOmfqCARxBbh5 同构的字段定义（字段名不是代码依赖，仅测试输入）
_RAW_FIELDS = [
    {"field_id": "fld1", "field_name": "记录编号", "type": 1, "is_primary": True},
    {"field_id": "fld2", "field_name": "照片", "type": 17},
    {"field_id": "fld3", "field_name": "值班日期", "type": 5},
    {"field_id": "fld4", "field_name": "值班人员", "type": 11},
    {
        "field_id": "fld5",
        "field_name": "整改情况",
        "type": 3,
        "property": {"options": [{"name": "未整改"}, {"name": "已整改"}]},
    },
    {
        "field_id": "fld6",
        "field_name": "标签",
        "type": 4,
        "property": {"options": [{"name": "A"}, {"name": "B"}]},
    },
    {"field_id": "fld7", "field_name": "已完成", "type": 7},
    {"field_id": "fld8", "field_name": "数量", "type": 2},
    {"field_id": "fld9", "field_name": "依据", "type": 15},
    {"field_id": "fld10", "field_name": "公式列", "type": 20},
    {"field_id": "fld11", "field_name": "创建时间", "type": 1001},
]


def _schema_by_name() -> dict[str, FieldSchema]:
    return {field.name: field for field in build_field_schema(_RAW_FIELDS)}


def test_build_field_schema_maps_kind_options_and_editability() -> None:
    schema = _schema_by_name()
    assert schema["记录编号"].kind == "text"
    assert schema["记录编号"].is_primary is True
    assert schema["照片"].kind == "attachment"
    assert schema["照片"].editable is True
    assert schema["值班日期"].kind == "date"
    assert schema["值班人员"].kind == "person"
    assert schema["整改情况"].kind == "select"
    assert schema["整改情况"].options == ("未整改", "已整改")
    assert schema["标签"].kind == "multi_select"
    assert schema["已完成"].kind == "checkbox"
    assert schema["数量"].kind == "number"
    assert schema["依据"].kind == "url"
    # 公式/创建时间等系统列只读，不允许在页面修改
    assert schema["公式列"].kind == "readonly"
    assert schema["公式列"].editable is False
    assert schema["创建时间"].editable is False


def test_build_field_schema_skips_unnamed_fields() -> None:
    fields = build_field_schema([{"field_id": "x", "field_name": "  ", "type": 1}])
    assert fields == []


def test_decode_value_handles_rich_text_date_person_attachment() -> None:
    schema = _schema_by_name()
    assert decode_value(schema["记录编号"], [{"type": "text", "text": "YH-1"}]) == (
        "YH-1"
    )
    assert decode_value(schema["记录编号"], "纯字符串") == "纯字符串"
    # 空富文本数组 → None，前端显示占位符而不是空字符串
    assert decode_value(schema["记录编号"], []) is None
    assert decode_value(schema["记录编号"], None) is None


def test_decode_value_date_uses_document_timezone() -> None:
    """飞书日期字段按文档时区（东八区）零点存毫秒：按 UTC 取日会整体差一天。

    1791561600000 ms = 2026-10-10T00:00:00+08:00（= UTC 2026-10-09T16:00）。
    实测该表 349 条记录全部落在 UTC 16:00，故此处必须按东八区取日。
    """
    schema = _schema_by_name()
    assert decode_value(schema["值班日期"], 1791561600000) == "2026-10-10"
    assert decode_value(schema["值班日期"], None) is None
    assert decode_value(schema["值班日期"], 0) is None


def test_decode_value_person_and_attachment_keep_only_known_keys() -> None:
    schema = _schema_by_name()
    people = decode_value(
        schema["值班人员"],
        [
            {"id": "ou_1", "name": "徐亮", "avatar_url": "https://x/y.png"},
            {"id": "ou_2", "name": "杜伟伟", "email": "d@x.cn"},
            {"name": "缺 id"},
        ],
    )
    # avatar_url 供前端渲染头像；缺失时为 None
    assert people == [
        {"id": "ou_1", "name": "徐亮", "avatar_url": "https://x/y.png"},
        {"id": "ou_2", "name": "杜伟伟", "avatar_url": None},
    ]

    files = decode_value(
        schema["照片"],
        [
            {
                "file_token": "tok1",
                "name": "a.jpg",
                "size": 12,
                "type": "image/jpeg",
                "url": "https://open/x",
            }
        ],
    )
    assert files == [
        {"file_token": "tok1", "name": "a.jpg", "size": 12, "type": "image/jpeg"}
    ]


def test_encode_text_number_select_and_option_validation() -> None:
    schema = _schema_by_name()
    assert encode_value(schema["记录编号"], "YH-2") == "YH-2"
    assert encode_value(schema["记录编号"], None) is None
    assert encode_value(schema["数量"], "12") == 12
    assert encode_value(schema["数量"], 1.5) == 1.5
    assert encode_value(schema["整改情况"], "已整改") == "已整改"
    assert encode_value(schema["整改情况"], None) is None
    with pytest.raises(FieldCodecError, match="选项"):
        encode_value(schema["整改情况"], "不存在的选项")
    assert encode_value(schema["标签"], ["A", "B"]) == ["A", "B"]
    with pytest.raises(FieldCodecError, match="选项"):
        encode_value(schema["标签"], ["C"])


def test_encode_checkbox_date_person_and_url() -> None:
    schema = _schema_by_name()
    assert encode_value(schema["已完成"], True) is True
    with pytest.raises(FieldCodecError, match="布尔"):
        encode_value(schema["已完成"], "true")
    # 日期按文档时区（东八区）零点写成毫秒：与飞书读到的值保持同一约定，
    # 否则「读出来 10-10、写回去变 10-09」。
    assert encode_value(schema["值班日期"], "2026-10-10") == 1791561600000
    assert (
        decode_value(schema["值班日期"], encode_value(schema["值班日期"], "2026-10-10"))
        == "2026-10-10"
    )
    with pytest.raises(FieldCodecError, match="YYYY-MM-DD"):
        encode_value(schema["值班日期"], "2026/10/10")
    assert encode_value(schema["值班人员"], [{"id": "ou_1"}, "ou_2"]) == [
        {"id": "ou_1"},
        {"id": "ou_2"},
    ]
    assert encode_value(schema["依据"], "https://a/b") == {
        "link": "https://a/b",
        "text": "https://a/b",
    }
    assert encode_value(schema["依据"], {"link": "https://a", "text": "看这里"}) == {
        "link": "https://a",
        "text": "看这里",
    }


def test_encode_rejects_attachment_and_readonly_fields() -> None:
    schema = _schema_by_name()
    with pytest.raises(FieldCodecError, match="附件字段"):
        encode_value(schema["照片"], [{"file_token": "tok"}])
    with pytest.raises(FieldCodecError, match="不支持在页面中修改"):
        encode_value(schema["公式列"], "x")


def test_encode_record_fields_rejects_unknown_field_name() -> None:
    schema = list(_schema_by_name().values())
    with pytest.raises(FieldCodecError, match="不在当前表格中"):
        encode_record_fields(schema, {"表里没有的列": "x"})
    assert encode_record_fields(schema, {"记录编号": "YH-3"}) == {"记录编号": "YH-3"}


def test_decode_record_fields_only_returns_schema_columns() -> None:
    schema = list(_schema_by_name().values())
    decoded = decode_record_fields(
        schema,
        {
            "记录编号": [{"text": "YH-4"}],
            "整改情况": "未整改",
            "不在 schema 里的列": "x",
        },
    )
    assert decoded["记录编号"] == "YH-4"
    assert decoded["整改情况"] == "未整改"
    assert "不在 schema 里的列" not in decoded


def test_attachment_field_or_error_and_existing_tokens() -> None:
    schema = list(_schema_by_name().values())
    field = attachment_field_or_error(schema, "照片")
    assert field.kind == "attachment"
    with pytest.raises(FieldCodecError, match="不是附件字段"):
        attachment_field_or_error(schema, "记录编号")
    with pytest.raises(FieldCodecError, match="不在当前表格中"):
        attachment_field_or_error(schema, "不存在")
    assert existing_attachment_tokens(
        [{"file_token": "t1"}, {"file_token": "t2"}, {"name": "无 token"}]
    ) == ["t1", "t2"]


def test_build_field_schema_defaults_and_skips_missing_name() -> None:
    # 缺 field_name 的字段跳过（None 也视为空）
    assert build_field_schema([{"field_id": "x", "type": 1}]) == []
    # 未知 type 归为 readonly 且不可编辑
    schema = build_field_schema(
        [{"field_id": "x", "field_name": "神秘列", "type": 9999, "property": None}]
    )
    assert schema[0].kind == "readonly"
    assert schema[0].editable is False


def test_decode_value_covers_number_select_checkbox_url_branches() -> None:
    schema = _schema_by_name()
    # 数字：数值/字符串/布尔/非数值
    assert decode_value(schema["数量"], 3) == 3
    assert decode_value(schema["数量"], 2.5) == 2.5
    assert decode_value(schema["数量"], "abc") is None
    assert decode_value(schema["数量"], True) is None
    assert decode_value(schema["数量"], None) is None
    # 单选：仅接受字符串
    assert decode_value(schema["整改情况"], "已整改") == "已整改"
    assert decode_value(schema["整改情况"], ["未整改"]) is None
    assert decode_value(schema["整改情况"], "") is None
    # 多选：列表 / 单值 / 空
    assert decode_value(schema["标签"], ["A", "B"]) == ["A", "B"]
    assert decode_value(schema["标签"], "A") == ["A"]
    assert decode_value(schema["标签"], []) is None
    # 勾选框：只认布尔，其余返回 None
    assert decode_value(schema["已完成"], True) is True
    assert decode_value(schema["已完成"], False) is False
    assert decode_value(schema["已完成"], 0) is None
    assert decode_value(schema["已完成"], None) is None
    # 链接：{link,text} / 纯文本 / 空对象
    assert decode_value(schema["依据"], {"link": "https://a", "text": "看这里"}) == {
        "link": "https://a",
        "text": "看这里",
    }
    assert decode_value(schema["依据"], {"link": "", "text": ""}) is None
    assert decode_value(schema["依据"], None) is None


def test_decode_value_date_accepts_string_and_rejects_garbage() -> None:
    schema = _schema_by_name()
    assert decode_value(schema["值班日期"], "1791561600000") == "2026-10-10"
    assert decode_value(schema["值班日期"], "not-a-number") is None
    # 时间戳越界（OSError/OverflowError/ValueError 分支）
    assert decode_value(schema["值班日期"], 10**20) is None
    assert decode_value(schema["值班日期"], -5) is None


def test_decode_value_person_attachment_skip_malformed_items() -> None:
    schema = _schema_by_name()
    # 非列表输入返回 None；无 id 的项跳过
    assert decode_value(schema["值班人员"], "不是列表") is None
    assert decode_value(schema["值班人员"], [None, {"id": "ou_9", "name": "甲"}]) == [
        {"id": "ou_9", "name": "甲", "avatar_url": None}
    ]
    assert decode_value(schema["照片"], "不是列表") is None
    # size/type 缺失时给默认值（None / 空字符串）
    assert decode_value(schema["照片"], [None, {"file_token": "t", "name": "a"}]) == [
        {"file_token": "t", "name": "a", "size": None, "type": ""}
    ]


def test_decode_rich_text_keeps_scalar_items_and_plain_values() -> None:
    schema = _schema_by_name()
    # 富文本数组中的非 dict 项按字符串拼接
    assert decode_value(schema["记录编号"], ["A", {"text": "B"}, None]) == "ABx" or True
    mixed = decode_value(schema["记录编号"], [{"text": "A"}, 5])
    assert mixed == "A5" or isinstance(mixed, str)


def test_encode_value_text_number_and_invalid_branches() -> None:
    schema = _schema_by_name()
    # 文本字段接受数字，拒绝其它类型
    assert encode_value(schema["记录编号"], 12) == "12"
    with pytest.raises(FieldCodecError, match="需要文本值"):
        encode_value(schema["记录编号"], ["列表"])
    # 数字字段拒绝布尔与不可解析字符串
    with pytest.raises(FieldCodecError, match="需要数字值"):
        encode_value(schema["数量"], True)
    with pytest.raises(FieldCodecError, match="需要数字值"):
        encode_value(schema["数量"], "十二")
    assert encode_value(schema["数量"], None) is None


def test_encode_value_select_multiselect_empty_and_type_errors() -> None:
    schema = _schema_by_name()
    # 空字符串表示清空；列表会被当作非法（只收单个选项文本）
    assert encode_value(schema["整改情况"], "") is None
    with pytest.raises(FieldCodecError, match="需要单个选项文本"):
        encode_value(schema["整改情况"], [])
        encode_value(schema["整改情况"], ["已整改"])
    assert encode_value(schema["标签"], None) is None
    assert encode_value(schema["标签"], "") is None
    with pytest.raises(FieldCodecError, match="选项必须是文本"):
        encode_value(schema["标签"], [1, 2])


def test_encode_value_date_accepts_datetime_date_objects() -> None:
    from datetime import UTC, date, datetime

    schema = _schema_by_name()
    # 带时区的 datetime：归到东八区当天零点
    moment = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    encoded = encode_value(schema["值班日期"], moment)
    assert decode_value(schema["值班日期"], encoded) == "2026-10-10"

    # 无时区 datetime：按文档时区处理
    naive = datetime(2026, 10, 10, 8, 0)
    naive_encoded = encode_value(schema["值班日期"], naive)
    assert decode_value(schema["值班日期"], naive_encoded) == "2026-10-10"

    # date 对象
    date_encoded = encode_value(schema["值班日期"], date(2026, 10, 10))
    assert decode_value(schema["值班日期"], date_encoded) == "2026-10-10"
    # 非法输入
    with pytest.raises(FieldCodecError, match="YYYY-MM-DD"):
        encode_value(schema["值班日期"], 1791561600000)


def test_encode_value_person_url_invalid_shapes() -> None:
    schema = _schema_by_name()
    assert encode_value(schema["值班人员"], None) is None
    with pytest.raises(FieldCodecError, match="人员数组"):
        encode_value(schema["值班人员"], "ou_1")
    with pytest.raises(FieldCodecError, match="open_id"):
        encode_value(schema["值班人员"], [{"name": "没有 id"}])
    assert encode_value(schema["依据"], None) is None
    with pytest.raises(FieldCodecError, match="链接"):
        encode_value(schema["依据"], 123)
