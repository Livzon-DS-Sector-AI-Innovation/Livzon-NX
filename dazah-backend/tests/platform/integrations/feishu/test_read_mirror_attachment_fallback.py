"""镜像附件回退通道的纯逻辑测试（tmp_url 定位与合法性判定）。

应用无云盘下载权限时 medias/download 返回无体 400，read_mirror 需从记录
原始字段定位该附件项自带的 tmp_url 换签名直链；这里覆盖定位与边界。
"""

from typing import Any

from app.platform.integrations.feishu.read_mirror import ModuleFeishuReadMirrorService

ATTACHMENT = {
    "url": "https://open.feishu.cn/open-apis/drive/v1/medias/tok1/download",
    "name": "photo.JPEG",
    "type": "image/jpeg",
    "file_token": "tok1",
    "tmp_url": (
        "https://open.feishu.cn/open-apis/drive/v1/medias/"
        "batch_get_tmp_download_url?file_tokens=tok1&extra=%7B%7D"
    ),
}


def test_attachment_tmp_url_finds_matching_item() -> None:
    value = [ATTACHMENT]
    assert (
        ModuleFeishuReadMirrorService._attachment_tmp_url(value, "tok1")
        == ATTACHMENT["tmp_url"]
    )


def test_attachment_tmp_url_rejects_mismatched_token() -> None:
    locate = ModuleFeishuReadMirrorService._attachment_tmp_url
    assert locate([ATTACHMENT], "tok2") is None


def test_attachment_tmp_url_rejects_non_open_api_url() -> None:
    forged = {
        **ATTACHMENT,
        "tmp_url": "https://evil.example.com/download?file_tokens=tok1",
    }
    assert ModuleFeishuReadMirrorService._attachment_tmp_url([forged], "tok1") is None


def test_attachment_tmp_url_handles_nested_structures() -> None:
    nested = {"分段": [{"子表": [[ATTACHMENT]]}]}
    assert (
        ModuleFeishuReadMirrorService._attachment_tmp_url(nested, "tok1")
        == ATTACHMENT["tmp_url"]
    )


def test_attachment_tmp_url_missing_returns_none() -> None:
    locate = ModuleFeishuReadMirrorService._attachment_tmp_url
    without_tmp = {k: v for k, v in ATTACHMENT.items() if k != "tmp_url"}
    assert locate([without_tmp], "tok1") is None
    assert locate(None, "tok1") is None


def _fake_record_columns() -> Any:
    """真实 JSONB 列：record_model.raw_fields[...] 需要列集合语义。"""
    import sqlalchemy as sa
    from sqlalchemy.dialects.postgresql import JSONB

    metadata = sa.MetaData()
    table = sa.Table("mirror_record", metadata, sa.Column("raw_fields", JSONB))
    return table.c


def test_record_order_expression_numeric_desc_nulls_last() -> None:
    """日期/数值字段按数值倒序，空值排最后（镜像日期是毫秒时间戳）。"""
    from app.platform.integrations.feishu.read_mirror import (
        _record_order_expression,
    )

    columns = _fake_record_columns()
    expr = _record_order_expression(columns, "用印日期", 5, "desc")
    compiled = str(expr).upper()
    assert "DESC" in compiled
    assert "NULLS LAST" in compiled
    assert "NUMERIC" in compiled


def test_record_order_expression_text_asc_nulls_last() -> None:
    """升序同样空值垫底（镜像存在 raw_fields 全空的记录，nulls_first 会顶满整页）。"""
    from app.platform.integrations.feishu.read_mirror import (
        _record_order_expression,
    )

    columns = _fake_record_columns()
    expr = _record_order_expression(columns, "申请人", 1, "asc")
    compiled = str(expr).upper()
    assert "ASC" in compiled
    assert "NULLS LAST" in compiled
    assert "NUMERIC" not in compiled


def test_record_filter_contains_escapes_like_wildcards() -> None:
    import sqlalchemy as sa
    from sqlalchemy.dialects.postgresql import JSONB

    from app.platform.integrations.feishu.read_mirror import (
        _record_filter_expression,
    )

    metadata = sa.MetaData()
    table = sa.Table("mirror_record", metadata, sa.Column("raw_fields", JSONB))
    expr = _record_filter_expression(table.c, "报废物资名称", 1, "contains", "废铁%_")
    compiled = str(expr).lower()
    assert " like " in compiled
    # LIKE 通配符必须被转义（转义后的值是绑定参数，不出现在 SQL 文本里）
    right_value = getattr(expr.right, "value", None)
    assert right_value == r"%废铁\%\_%"


def test_record_filter_numeric_eq_casts_to_numeric() -> None:
    import sqlalchemy as sa
    from sqlalchemy.dialects.postgresql import JSONB

    from app.platform.integrations.feishu.read_mirror import (
        _record_filter_expression,
    )

    metadata = sa.MetaData()
    table = sa.Table("mirror_record", metadata, sa.Column("raw_fields", JSONB))
    expr = _record_filter_expression(table.c, "数量", 2, "gte", "12")
    compiled = str(expr).upper()
    assert "NUMERIC" in compiled
    assert ">=" in compiled


def test_record_filter_numeric_rejects_non_numeric_value() -> None:
    import sqlalchemy as sa
    from sqlalchemy.dialects.postgresql import JSONB

    from app.core.exceptions import AppException
    from app.platform.integrations.feishu.read_mirror import (
        _record_filter_expression,
    )

    metadata = sa.MetaData()
    table = sa.Table("mirror_record", metadata, sa.Column("raw_fields", JSONB))
    try:
        _record_filter_expression(table.c, "用印日期", 5, "gte", "abc")
    except AppException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("expected AppException for non-numeric value")


def test_record_filter_rejects_unknown_operator() -> None:
    import sqlalchemy as sa
    from sqlalchemy.dialects.postgresql import JSONB

    from app.core.exceptions import AppException
    from app.platform.integrations.feishu.read_mirror import (
        _record_filter_expression,
    )

    metadata = sa.MetaData()
    table = sa.Table("mirror_record", metadata, sa.Column("raw_fields", JSONB))
    try:
        _record_filter_expression(table.c, "申请人", 1, "regex", "x")
    except AppException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("expected AppException for unknown operator")
