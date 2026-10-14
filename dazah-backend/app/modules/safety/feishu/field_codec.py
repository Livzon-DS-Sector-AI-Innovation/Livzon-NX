"""飞书多维表格字段编解码。

镜像页的列完全由飞书实时 schema 决定（见 ``page_tables.py`` 的页面注册表
与 ``safety.page_feishu_configs`` 的表格绑定），因此本模块内不出现任何具体
字段名。它负责三件事：

1. 把 Bitable 字段定义翻译成前端可渲染的列定义（类型 → 控件、选项、可写性）；
2. 把 Bitable 原始值解码成前端规范值（日期统一 ``YYYY-MM-DD``，人员与附件
   统一为对象数组）；
3. 把前端提交的规范值编码回 Bitable 写入格式，并校验类型与选项。

附件字段的写入不经过 :func:`encode_value`：新增附件走专用上传端点
（先 ``upload_media`` 再追加 ``file_token``），避免整列覆盖导致已有附件被清空。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

# 飞书多维表格的日期字段存的是「文档时区当天零点」的毫秒时间戳。本租户为
# Asia/Shanghai：实测 349 条记录全部落在 UTC 16:00（= 东八区 00:00），若按 UTC
# 取日会整体差一天。写入时也必须用同一时区回推，否则日期会前后偏移。
BITABLE_TIMEZONE = ZoneInfo("Asia/Shanghai")

# ── Bitable 字段类型 ──
FIELD_TYPE_TEXT = 1
FIELD_TYPE_NUMBER = 2
FIELD_TYPE_SINGLE_SELECT = 3
FIELD_TYPE_MULTI_SELECT = 4
FIELD_TYPE_DATE = 5
FIELD_TYPE_CHECKBOX = 7
FIELD_TYPE_PERSON = 11
FIELD_TYPE_PHONE = 13
FIELD_TYPE_URL = 15
FIELD_TYPE_ATTACHMENT = 17
FIELD_TYPE_SINGLE_LINK = 18
FIELD_TYPE_LOOKUP = 19
FIELD_TYPE_FORMULA = 20
FIELD_TYPE_DUPLEX_LINK = 21
FIELD_TYPE_LOCATION = 22
FIELD_TYPE_GROUP_CHAT = 23
FIELD_TYPE_CREATED_TIME = 1001
FIELD_TYPE_MODIFIED_TIME = 1002
FIELD_TYPE_CREATED_USER = 1003
FIELD_TYPE_MODIFIED_USER = 1004
FIELD_TYPE_AUTO_NUMBER = 1005

# 前端渲染用的控件类型
KIND_TEXT = "text"
KIND_NUMBER = "number"
KIND_SELECT = "select"
KIND_MULTI_SELECT = "multi_select"
KIND_DATE = "date"
KIND_CHECKBOX = "checkbox"
KIND_PERSON = "person"
KIND_PHONE = "phone"
KIND_URL = "url"
KIND_ATTACHMENT = "attachment"
KIND_READONLY = "readonly"

_KIND_BY_TYPE: dict[int, str] = {
    FIELD_TYPE_TEXT: KIND_TEXT,
    FIELD_TYPE_NUMBER: KIND_NUMBER,
    FIELD_TYPE_SINGLE_SELECT: KIND_SELECT,
    FIELD_TYPE_MULTI_SELECT: KIND_MULTI_SELECT,
    FIELD_TYPE_DATE: KIND_DATE,
    FIELD_TYPE_CHECKBOX: KIND_CHECKBOX,
    FIELD_TYPE_PERSON: KIND_PERSON,
    FIELD_TYPE_PHONE: KIND_PHONE,
    FIELD_TYPE_URL: KIND_URL,
    FIELD_TYPE_ATTACHMENT: KIND_ATTACHMENT,
}

# 可通过「记录字段更新」写入的类型；附件另走上传端点，故不在此列。
_WRITABLE_TYPES: frozenset[int] = frozenset(
    {
        FIELD_TYPE_TEXT,
        FIELD_TYPE_NUMBER,
        FIELD_TYPE_SINGLE_SELECT,
        FIELD_TYPE_MULTI_SELECT,
        FIELD_TYPE_DATE,
        FIELD_TYPE_CHECKBOX,
        FIELD_TYPE_PERSON,
        FIELD_TYPE_PHONE,
        FIELD_TYPE_URL,
    }
)

# 附件字段虽然可改，但只能通过附件上传端点追加。
_EDITABLE_TYPES: frozenset[int] = _WRITABLE_TYPES | {FIELD_TYPE_ATTACHMENT}

_DATE_FORMAT = "%Y-%m-%d"


class FieldCodecError(ValueError):
    """字段值不符合飞书字段类型或选项约束。"""


@dataclass(frozen=True, slots=True)
class FieldSchema:
    """单个字段的列定义。"""

    field_id: str
    name: str
    type: int
    kind: str
    is_primary: bool
    options: tuple[str, ...]
    editable: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id,
            "name": self.name,
            "type": self.type,
            "kind": self.kind,
            "is_primary": self.is_primary,
            "options": list(self.options),
            "editable": self.editable,
        }


def build_field_schema(raw_fields: list[dict[str, Any]]) -> list[FieldSchema]:
    """把 ``list_fields`` 的原始返回翻译成列定义（保持飞书返回顺序）。"""
    schema: list[FieldSchema] = []
    for raw in raw_fields:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("field_name") or "").strip()
        if not name:
            continue
        field_type = raw.get("type")
        if not isinstance(field_type, int):
            field_type = 0
        property_ = raw.get("property")
        options: tuple[str, ...] = ()
        if isinstance(property_, dict):
            raw_options = property_.get("options")
            if isinstance(raw_options, list):
                options = tuple(
                    str(item.get("name"))
                    for item in raw_options
                    if isinstance(item, dict) and item.get("name") is not None
                )
        schema.append(
            FieldSchema(
                field_id=str(raw.get("field_id") or ""),
                name=name,
                type=field_type,
                kind=_KIND_BY_TYPE.get(field_type, KIND_READONLY),
                is_primary=bool(raw.get("is_primary")),
                options=options,
                editable=field_type in _EDITABLE_TYPES,
            )
        )
    return schema


def _join_rich_text(value: Any) -> str:
    """Bitable 文本字段返回富文本段落数组，拼接为纯文本。"""
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text")
                if text is not None:
                    parts.append(str(text))
            elif item is not None:
                parts.append(str(item))
        return "".join(parts)
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _decode_date(value: Any) -> str | None:
    """毫秒时间戳 → ``YYYY-MM-DD``（按文档时区取日，避免整体差一天）。"""
    millis: float | None = None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        millis = float(value)
    elif isinstance(value, str) and value.strip():
        try:
            millis = float(value.strip())
        except ValueError:
            return None
    if millis is None or millis <= 0:
        return None
    try:
        moment = datetime.fromtimestamp(millis / 1000, tz=BITABLE_TIMEZONE)
        return moment.date().isoformat()
    except (OSError, OverflowError, ValueError):
        return None


def _decode_person(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    people: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        person_id = item.get("id")
        if not person_id:
            continue
        # avatar_url 供前端渲染头像（与质量管理 QC 验证一致）；写回时只取 id
        avatar_url = item.get("avatar_url")
        people.append(
            {
                "id": str(person_id),
                "name": str(item.get("name") or ""),
                "avatar_url": str(avatar_url) if avatar_url else None,
            }
        )
    return people


def _decode_attachments(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    files: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        token = item.get("file_token")
        if not token:
            continue
        files.append(
            {
                "file_token": str(token),
                "name": str(item.get("name") or ""),
                "size": item.get("size") if isinstance(item.get("size"), int) else None,
                "type": str(item.get("type") or ""),
            }
        )
    return files


def _decode_url(value: Any) -> dict[str, str] | None:
    if isinstance(value, dict):
        link = value.get("link")
        text = value.get("text")
        if not link and not text:
            return None
        return {"link": str(link or ""), "text": str(text or link or "")}
    if isinstance(value, str) and value.strip():
        return {"link": value.strip(), "text": value.strip()}
    return None


def decode_value(field: FieldSchema, raw: Any) -> Any:
    """把 Bitable 原始字段值解码为前端规范值。"""
    if raw is None:
        return None
    if field.kind == KIND_TEXT:
        text = _join_rich_text(raw)
        return text or None
    if field.kind == KIND_NUMBER:
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        return raw
    if field.kind == KIND_SELECT:
        return str(raw) if isinstance(raw, str) and raw else None
    if field.kind == KIND_MULTI_SELECT:
        if isinstance(raw, list):
            values = [str(item) for item in raw if isinstance(item, str) and item]
            return values or None
        if isinstance(raw, str) and raw:
            return [raw]
        return None
    if field.kind == KIND_DATE:
        return _decode_date(raw)
    if field.kind == KIND_CHECKBOX:
        return bool(raw) if isinstance(raw, bool) else None
    if field.kind == KIND_PERSON:
        people = _decode_person(raw)
        return people or None
    if field.kind == KIND_PHONE:
        text = _join_rich_text(raw)
        return text or None
    if field.kind == KIND_URL:
        return _decode_url(raw)
    if field.kind == KIND_ATTACHMENT:
        files = _decode_attachments(raw)
        return files or None
    # 只读类型：尽力给出可展示的文本，避免前端出现空白列
    text = _join_rich_text(raw)
    return text or None


def _encode_text(field: FieldSchema, value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    raise FieldCodecError(f"字段「{field.name}」需要文本值")


def _encode_number(field: FieldSchema, value: Any) -> float | int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise FieldCodecError(f"字段「{field.name}」需要数字值")
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError as exc:
            raise FieldCodecError(f"字段「{field.name}」需要数字值") from exc
        return int(number) if number.is_integer() else number
    raise FieldCodecError(f"字段「{field.name}」需要数字值")


def _check_option(field: FieldSchema, option: str) -> None:
    if field.options and option not in field.options:
        raise FieldCodecError(
            f"字段「{field.name}」的选项「{option}」不存在，"
            f"可选：{'、'.join(field.options)}"
        )


def _encode_single_select(field: FieldSchema, value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise FieldCodecError(f"字段「{field.name}」需要单个选项文本")
    _check_option(field, value)
    return value


def _encode_multi_select(field: FieldSchema, value: Any) -> list[str] | None:
    if value is None or value == "":
        return None
    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in values:
        if not isinstance(item, str):
            raise FieldCodecError(f"字段「{field.name}」的选项必须是文本")
        _check_option(field, item)
        result.append(item)
    return result or None


def _encode_date(field: FieldSchema, value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=BITABLE_TIMEZONE)
        # 日期字段只保留日期：统一归到文档时区的当天零点
        local_date = moment.astimezone(BITABLE_TIMEZONE).date()
        return int(
            datetime.combine(local_date, time.min, tzinfo=BITABLE_TIMEZONE).timestamp()
            * 1000
        )
    if isinstance(value, date):
        return int(
            datetime.combine(value, time.min, tzinfo=BITABLE_TIMEZONE).timestamp()
            * 1000
        )
    if isinstance(value, str):
        try:
            parsed = datetime.strptime(value.strip(), _DATE_FORMAT).date()
        except ValueError as exc:
            raise FieldCodecError(
                f"字段「{field.name}」需要 YYYY-MM-DD 格式的日期"
            ) from exc
        return int(
            datetime.combine(parsed, time.min, tzinfo=BITABLE_TIMEZONE).timestamp()
            * 1000
        )
    raise FieldCodecError(f"字段「{field.name}」需要 YYYY-MM-DD 格式的日期")


def _encode_checkbox(field: FieldSchema, value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise FieldCodecError(f"字段「{field.name}」需要布尔值")


def _encode_person(field: FieldSchema, value: Any) -> list[dict[str, str]] | None:
    if value is None or value == "":
        return None
    if not isinstance(value, list):
        raise FieldCodecError(f"字段「{field.name}」需要人员数组")
    people: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            people.append({"id": item.strip()})
        elif isinstance(item, dict) and item.get("id"):
            people.append({"id": str(item["id"])})
        else:
            raise FieldCodecError(
                f"字段「{field.name}」的人员项需要 open_id（形如 ou_...）"
            )
    return people or None


def _encode_url(field: FieldSchema, value: Any) -> dict[str, str] | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        link = value.strip()
        return {"link": link, "text": link} if link else None
    if isinstance(value, dict):
        link = str(value.get("link") or "").strip()
        if not link:
            return None
        text = str(value.get("text") or "").strip() or link
        return {"link": link, "text": text}
    raise FieldCodecError(f"字段「{field.name}」需要链接文本或 {{link, text}}")


def encode_value(field: FieldSchema, value: Any) -> Any:
    """把前端规范值编码为 Bitable 写入格式。

    只接受可写类型；附件字段请改用附件上传端点。
    """
    if field.kind == KIND_ATTACHMENT:
        raise FieldCodecError(
            f"字段「{field.name}」是附件字段，请使用附件上传功能修改"
        )
    if field.type not in _WRITABLE_TYPES:
        raise FieldCodecError(f"字段「{field.name}」不支持在页面中修改")
    if field.kind == KIND_TEXT:
        return _encode_text(field, value)
    if field.kind == KIND_NUMBER:
        return _encode_number(field, value)
    if field.kind == KIND_SELECT:
        return _encode_single_select(field, value)
    if field.kind == KIND_MULTI_SELECT:
        return _encode_multi_select(field, value)
    if field.kind == KIND_DATE:
        return _encode_date(field, value)
    if field.kind == KIND_CHECKBOX:
        return _encode_checkbox(field, value)
    if field.kind == KIND_PERSON:
        return _encode_person(field, value)
    if field.kind == KIND_PHONE:
        return _encode_text(field, value)
    if field.kind == KIND_URL:
        return _encode_url(field, value)
    raise FieldCodecError(f"字段「{field.name}」不支持在页面中修改")


def encode_record_fields(
    schema: list[FieldSchema],
    values: dict[str, Any],
) -> dict[str, Any]:
    """把前端提交的 ``{字段名: 规范值}`` 批量编码为 Bitable 写入字段。

    未在 schema 中出现的字段名一律拒绝，避免把任意字段写进飞书表。
    """
    by_name = {field.name: field for field in schema}
    encoded: dict[str, Any] = {}
    for name, value in values.items():
        field = by_name.get(name)
        if field is None:
            raise FieldCodecError(f"字段「{name}」不在当前表格中")
        encoded[name] = encode_value(field, value)
    return encoded


def decode_record_fields(
    schema: list[FieldSchema],
    raw_fields: dict[str, Any],
) -> dict[str, Any]:
    """把一条记录的原始字段解码为前端规范值（只输出 schema 内的字段）。"""
    decoded: dict[str, Any] = {}
    for field in schema:
        if field.name in raw_fields:
            decoded[field.name] = decode_value(field, raw_fields[field.name])
    return decoded


def attachment_field_or_error(
    schema: list[FieldSchema], field_name: str
) -> FieldSchema:
    """取附件字段定义；不是附件字段或不存在时报错。"""
    field = next((item for item in schema if item.name == field_name), None)
    if field is None:
        raise FieldCodecError(f"字段「{field_name}」不在当前表格中")
    if field.kind != KIND_ATTACHMENT:
        raise FieldCodecError(f"字段「{field_name}」不是附件字段")
    return field


def existing_attachment_tokens(raw_value: Any) -> list[str]:
    """取附件字段现有 file_token（用于上传后追加，避免覆盖已有附件）。"""
    return [item["file_token"] for item in _decode_attachments(raw_value)]
