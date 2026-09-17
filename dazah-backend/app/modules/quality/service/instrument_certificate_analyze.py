"""校准证书 AI 识别 + QC 设备目录实时反查（外部校准检定新增辅助）。

流程：上传证书（图片/PDF）→ AI 提取关键字段 → 实时反查 QC 设备目录
（使用地点 / 检定周期，目录数据频繁变化，每次识别都现查、不走镜像）
→ 按目录周期推算下次检定日期（与飞书公式 EDATE(检定日期, 周期)-1 同口径）
→ 映射为外部校准表可写字段。本服务只做识别与预填，不直接写飞书记录；
写入由人工确认后的通用新增接口完成。
"""

from __future__ import annotations

import asyncio
import base64
import calendar
import io
import logging
import os
import re
from datetime import date, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
    llm_client,
)
from app.modules.quality.schemas.instrument_certificate import (
    CertificateExtractedFields,
    CertificateRematchRequest,
    DeviceDirectoryMatch,
)
from app.modules.quality.service.inspection_feishu_crud import (
    _entity_table_id,
    upload_inspection_feishu_attachment,
)
from app.modules.quality.service.quality_feishu_pages import _resolve_runtime_entity
from app.modules.quality.service.quality_feishu_sync import (
    _escape_feishu_filter_value,
    _normalize_text,
)
from app.platform.integrations.feishu.bitable import BitableClient

logger = logging.getLogger(__name__)

CERTIFICATE_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
CERTIFICATE_MAX_BYTES = 20 * 1024 * 1024  # 与飞书附件上传上限一致

_PDF_MIN_TEXT_CHARS = 200
_PDF_MAX_RENDER_PAGES = 3
_PDF_RENDER_DPI = 150

_CAL_EXTERNAL_ENTITY_CODE = "qc_instr_cal_external"
_DIRECTORY_ENTITY_CODE = "qc_instr_device_directory"

EXTRACTED_FIELD_KEYS = [
    "instrument_name",
    "model",
    "serial_no",
    "calibration_date",
    "next_calibration_date_stated",
    "certificate_no",
    "calibration_agency",
    "conclusion",
]

_CERTIFICATE_EXTRACT_PROMPT = (
    "你是药厂 QC 计量管理助手。请从这份仪器校准/检定证书中提取以下信息，"
    '只输出一个 JSON 对象：{"instrument_name": "仪器/器具名称", '
    '"model": "型号/规格", '
    '"serial_no": "出厂编号/器具编号/设备编号，必须完整抄录证书该栏的全部内容'
    "（含括号内的手写备注），不要遗漏或只取一部分，"
    '例如 H29465 (QCPD-007) 须原样完整返回", '
    '"calibration_date": "检定或校准日期 YYYY-MM-DD", '
    '"next_calibration_date_stated": "证书载明的下次检定日期或有效期至 '
    'YYYY-MM-DD，没有则 null", '
    '"certificate_no": "证书编号", "calibration_agency": "检定/校准机构", '
    '"conclusion": "结论（如 合格）"}。\n'
    "要求：读不清或证书上没有的字段用 null；日期必须是 YYYY-MM-DD 格式；"
    "不得猜测或编造证书上不存在的内容。"
)

# 目录列名候选（全半角括号/空格差异在匹配时归一）
_DIRECTORY_CODE_COLUMNS = ("器具编号", "出厂编号", "设备编号", "仪器编号")
_DIRECTORY_GAUGE_COLUMNS = ("仪表编号", "设备仪表编号")
_DIRECTORY_NAME_COLUMNS = ("器具名称", "设备名称", "仪器名称")
_DIRECTORY_LOCATION_COLUMNS = ("使用地点", "设备安装地点", "安装地点", "存放地点")
_DIRECTORY_PERIOD_COLUMNS = (
    "检定周期（月）",
    "检定周期(月)",
    "校准周期（月）",
    "校验周期（月）",
    "检验周期（月）",
    "检定周期",
    "校准周期",
    "校验周期",
    "检验周期",
)

_DATE_ISO_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NUM_TEXT_PATTERN = re.compile(r"^\d+(\.\d+)?$")
_NONE_TEXT = {"", "null", "none", "无", "未知", "没有", "不适用", "n/a", "-"}


# ── 上传校验 ─────────────────────────────────────────────────────────


def _validate_certificate_file(file_name: str, content: bytes) -> str:
    extension = os.path.splitext(file_name or "")[1].lower()
    if extension not in CERTIFICATE_ALLOWED_EXTENSIONS:
        allowed = "、".join(sorted(CERTIFICATE_ALLOWED_EXTENSIONS))
        raise AppException(message=f"校准证书仅支持 {allowed} 文件", status_code=400)
    if not content:
        raise AppException(message="上传文件内容为空", status_code=400)
    if len(content) > CERTIFICATE_MAX_BYTES:
        raise AppException(message="证书文件超过 20MB 限制", status_code=400)
    return extension


# ── AI 提取 ──────────────────────────────────────────────────────────


def _image_data_uri(content: bytes, content_type: str) -> str:
    mime = content_type or "image/png"
    if not mime.startswith("image/"):
        mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


def _extract_pdf_text(content: bytes) -> str:
    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            parts.append(text)
            if sum(len(part) for part in parts) >= _PDF_MIN_TEXT_CHARS:
                break
    return "\n".join(parts)


def _render_pdf_pages(content: bytes) -> list[str]:
    """扫描版 PDF → 前几页 JPEG data URI（在线程池外调用，内部已同步）。"""
    import fitz  # type: ignore[import-untyped]  # PyMuPDF exposes runtime module without stubs

    document = fitz.open(stream=content, filetype="pdf")
    try:
        uris: list[str] = []
        for page in document.pages(0, _PDF_MAX_RENDER_PAGES):
            pix = page.get_pixmap(dpi=_PDF_RENDER_DPI)
            jpeg = pix.tobytes("jpeg")
            uris.append(
                f"data:image/jpeg;base64,{base64.b64encode(jpeg).decode('ascii')}"
            )
        return uris
    finally:
        document.close()


async def _call_llm_json(
    *,
    prompt: str,
    text: str | None = None,
    image_urls: list[str] | None = None,
) -> dict[str, Any]:
    """按文本/视觉两条路径调用统一 LLM 客户端，异常映射为业务错误。"""
    try:
        if image_urls is not None:
            return await llm_client.chat_vision_json(
                prompt, image_urls, expected_keys=EXTRACTED_FIELD_KEYS
            )
        return await llm_client.chat_json(
            [{"role": "user", "content": prompt}], expected_keys=EXTRACTED_FIELD_KEYS
        )
    except LLMConfigError as exc:
        raise AppException(
            message="AI 识别功能未配置，请联系管理员在系统中配置模型", status_code=503
        ) from exc
    except LLMRateLimitError as exc:
        raise AppException(
            message="AI 识别请求过于频繁，请稍后重试", status_code=429
        ) from exc
    except LLMOutputError as exc:
        raise AppException(
            message="AI 返回内容无法解析，请重试或手工填写记录", status_code=502
        ) from exc
    except LLMProviderError as exc:
        logger.warning("certificate analyze LLM provider error: %s", exc)
        raise AppException(
            message="AI 服务暂不可用，请稍后重试或手工填写记录", status_code=502
        ) from exc


def _clean_text(value: Any) -> str | None:
    text = str(value or "").strip()
    if text.lower() in _NONE_TEXT:
        return None
    return text or None


def _clean_date(value: Any) -> str | None:
    text = _clean_text(value)
    if text is None or not _DATE_ISO_PATTERN.match(text):
        return None
    try:
        date.fromisoformat(text)
    except ValueError:
        return None
    return text


def _clean_extracted(raw: dict[str, Any]) -> CertificateExtractedFields:
    return CertificateExtractedFields(
        instrument_name=_clean_text(raw.get("instrument_name")),
        model=_clean_text(raw.get("model")),
        serial_no=_clean_text(raw.get("serial_no")),
        calibration_date=_clean_date(raw.get("calibration_date")),
        next_calibration_date_stated=_clean_date(
            raw.get("next_calibration_date_stated")
        ),
        certificate_no=_clean_text(raw.get("certificate_no")),
        calibration_agency=_clean_text(raw.get("calibration_agency")),
        conclusion=_clean_text(raw.get("conclusion")),
    )


# ── QC 设备目录实时反查 ──────────────────────────────────────────────


def _normalize_field_name(name: Any) -> str:
    return (
        re.sub(r"\s+", "", str(name or ""))
        .replace("（", "(")
        .replace("）", ")")
        .lower()
    )


def _find_directory_column(
    field_names: list[str], candidates: tuple[str, ...], *, keyword: str
) -> str | None:
    normalized = {_normalize_field_name(name): name for name in field_names}
    for candidate in candidates:
        hit = normalized.get(_normalize_field_name(candidate))
        if hit:
            return hit
    for name in field_names:
        if keyword in _normalize_field_name(name):
            return name
    return None


def _parse_period_months(value: Any) -> int | None:
    """周期原文 → 月数：支持 12 / 12个月 / 12 月 / 1年 / 2年 等写法。"""
    text = _normalize_text(value)
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(年|个月|月)?", text)
    if not match:
        return None
    number = float(match.group(1))
    if match.group(2) == "年":
        months = number * 12
    else:
        months = number
    if months <= 0 or months > 600:
        return None
    return int(months)


def _serial_candidates(serial_no: str) -> list[str]:
    """出厂编号候选：完整值优先，其次括号外主体、括号内手写备注。

    证书出厂编号栏常写成「H29465 (QCPD-007)」（打印编号 + 手写内部编号），
    设备目录可能只存其中之一，因此拆出各部分逐个尝试。
    """
    text = str(serial_no).strip()
    candidates: list[str] = [text]
    outer = re.sub(r"[（(][^（）()]*[）)]", "", text).strip()
    if outer and outer not in candidates:
        candidates.append(outer)
    for match in re.findall(r"[（(]([^（）()]+)[）)]", text):
        inner = match.strip()
        if inner and inner not in candidates:
            candidates.append(inner)
    return candidates


def _cell_matches_any(
    fields: dict[str, Any], code_columns: list[str], candidates: list[str]
) -> bool:
    normalized_candidates = {_normalize_field_name(c) for c in candidates}
    for column in code_columns:
        cell = _normalize_field_name(_normalize_text(fields.get(column)))
        if cell and cell in normalized_candidates:
            return True
    return False


async def _search_directory_by_code(
    client: BitableClient,
    table_id: str,
    *,
    code_columns: list[str],
    location_column: str | None,
    field_names: list[str],
    candidates: list[str],
) -> tuple[list[dict[str, Any]], str | None]:
    """编号列精确检索 → 使用地点包含匹配 → 首屏全量兜底比对。

    返回 (命中记录, 实际命中的列名)；未命中返回 ([], None)。
    """
    for column in code_columns:
        for candidate in candidates:
            filter_str = (
                f'CurrentValue.[{column}] = "{_escape_feishu_filter_value(candidate)}"'
            )
            try:
                records = await client.search_records(
                    table_id,
                    filter_str=filter_str,
                    field_names=field_names,
                    page_size=20,
                )
            except Exception as exc:  # noqa: BLE001 - 单次检索失败降级继续尝试
                logger.warning(
                    "directory filter search failed (%s=%s): %s",
                    column,
                    candidate,
                    exc,
                )
                records = []
            if records:
                return records, column
    # 使用地点部分记录会带仪器编号（如「滴定间2 QCPD-007」）：包含匹配兜底
    records = await client.search_records(
        table_id, field_names=field_names, page_size=500
    )
    for record in records:
        fields = record.get("fields") or {}
        if _cell_matches_any(fields, code_columns, candidates):
            return [record], code_columns[0]
        if location_column:
            location_text = _normalize_field_name(
                _normalize_text(fields.get(location_column))
            )
            if location_text and any(
                len(_normalize_field_name(c)) >= 4
                and _normalize_field_name(c) in location_text
                for c in candidates
            ):
                return [record], location_column
    return [], None


async def _lookup_device_directory(
    db: AsyncSession,
    extracted: CertificateExtractedFields,
    warnings: list[str],
) -> DeviceDirectoryMatch:
    """实时反查 QC 设备目录（使用地点/检定周期）；查不到不阻断识别流程。"""
    serial_no = extracted.serial_no
    if not serial_no:
        warnings.append(
            "证书中未识别到出厂编号，未反查设备目录，请手工核对使用地点与检定周期"
        )
        return DeviceDirectoryMatch(matched=False)
    try:
        runtime, entity = await _resolve_runtime_entity(
            db, _DIRECTORY_ENTITY_CODE, direction="pull"
        )
        client = BitableClient(
            app_token=entity.app_token,
            app_id=runtime.app_id,
            app_secret=runtime.app_secret,
        )
        table_id = _entity_table_id(entity)
        field_names = [
            str(item.get("field_name") or "")
            for item in await client.list_fields(table_id)
            if item.get("field_name")
        ]
        code_column = _find_directory_column(
            field_names, _DIRECTORY_CODE_COLUMNS, keyword="编号"
        )
        if code_column is None:
            warnings.append("设备目录表未找到编号列，请检查目录表结构")
            return DeviceDirectoryMatch(matched=False)
        # 内部仪表编号（如 QCPD-007）与器具编号可能是不同编号体系，都参与匹配
        gauge_column = _find_directory_column(
            field_names, _DIRECTORY_GAUGE_COLUMNS, keyword="仪表"
        )
        code_columns: list[str] = []
        for name in (code_column, gauge_column):
            if name and name not in code_columns:
                code_columns.append(name)
        location_column = _find_directory_column(
            field_names, _DIRECTORY_LOCATION_COLUMNS, keyword="地点"
        )
        lookup_fields = [
            name
            for name in (
                *code_columns,
                location_column,
                _find_directory_column(
                    field_names, _DIRECTORY_NAME_COLUMNS, keyword="名称"
                ),
                _find_directory_column(
                    field_names, _DIRECTORY_PERIOD_COLUMNS, keyword="周期"
                ),
            )
            if name
        ]
        records, matched_column = await _search_directory_by_code(
            client,
            table_id,
            code_columns=code_columns,
            location_column=location_column,
            field_names=lookup_fields,
            candidates=_serial_candidates(serial_no),
        )
    except AppException as exc:
        warnings.append(
            f"设备目录未启用或配置缺失（{exc.message}），请手工核对使用地点"
        )
        return DeviceDirectoryMatch(matched=False)
    except Exception as exc:  # noqa: BLE001 - 反查失败降级为提示，不阻断识别
        logger.warning("device directory lookup failed: %s", exc)
        message = str(exc)
        if "1254302" in message or "403" in message or "Permission" in message:
            warnings.append(
                "设备目录查询无权限：请将质量飞书应用添加为 QC 设备目录 Base 的协作者"
            )
        else:
            warnings.append("设备目录查询失败，请手工核对使用地点与检定周期")
        return DeviceDirectoryMatch(matched=False)

    if not records or matched_column is None:
        warnings.append(
            f"设备目录中未找到出厂编号「{serial_no}」对应设备，请手工核对使用地点"
        )
        return DeviceDirectoryMatch(matched=False)

    fields = records[0].get("fields") or {}
    location_column = _find_directory_column(
        field_names, _DIRECTORY_LOCATION_COLUMNS, keyword="地点"
    )
    period_column = _find_directory_column(
        field_names, _DIRECTORY_PERIOD_COLUMNS, keyword="周期"
    )
    name_column = _find_directory_column(
        field_names, _DIRECTORY_NAME_COLUMNS, keyword="名称"
    )
    period_text = _normalize_text(fields.get(period_column)) if period_column else None
    name_text = _normalize_text(fields.get(name_column)) if name_column else None
    location_text = (
        _normalize_text(fields.get(location_column)) if location_column else None
    )
    return DeviceDirectoryMatch(
        matched=True,
        match_by=matched_column,
        record_id=str(records[0].get("record_id") or ""),
        instrument_name=name_text,
        location=location_text,
        period_months=_parse_period_months(period_text) if period_text else None,
        period_text=period_text,
    )


# ── 下次检定日期推算 ─────────────────────────────────────────────────


def _add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    last_day_of_month = _days_in_month(year, month)
    return date(year, month, min(day.day, last_day_of_month))


def _days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _parse_iso_date(value: str | None) -> date | None:
    if not value or not _DATE_ISO_PATTERN.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _compute_next_calibration_date(
    extracted: CertificateExtractedFields,
    directory: DeviceDirectoryMatch,
    warnings: list[str],
) -> str | None:
    """下次检定日期 = 检定日期 + 目录周期（月）- 1 天（同飞书 EDATE 公式口径）。"""
    calibration_date = _parse_iso_date(extracted.calibration_date)
    stated = _parse_iso_date(extracted.next_calibration_date_stated)
    computed: str | None = None
    if calibration_date is not None and directory.period_months:
        computed = (
            _add_months(calibration_date, directory.period_months) - timedelta(days=1)
        ).isoformat()
        if stated is not None and stated.isoformat() != computed:
            warnings.append(
                f"证书载明下次检定日期（{stated.isoformat()}）与按目录周期推算结果"
                f"（{computed}）不一致，已按目录周期推算"
            )
    if computed is not None:
        return computed
    return stated.isoformat() if stated else None


# ── 外部校准表字段映射 ───────────────────────────────────────────────


def _resolve_writable_column(
    by_norm: dict[str, tuple[str, dict[str, Any]]],
    candidates: tuple[str, ...],
) -> str | None:
    for candidate in candidates:
        hit = by_norm.get(_normalize_field_name(candidate))
        if hit:
            return hit[0]
    return None


def _column_ui_type(
    by_norm: dict[str, tuple[str, dict[str, Any]]], field_name: str
) -> str:
    hit = by_norm.get(_normalize_field_name(field_name))
    return str((hit or ("", {}))[1].get("ui_type") or "")


async def _next_table_serial(
    client: BitableClient, table_id: str, serial_column: str
) -> int:
    """按表内现有最大序号 +1 续号；无数字序号时从 1 开始。

    表可能有多千行且序号列是文本（无法服务端数值排序），因此全量分页
    只取序号一列后取数字最大值，避免只看首页导致序号回退。
    """
    max_no = 0
    page_token: str | None = None
    while True:
        page = await client.search_records_page(
            table_id,
            field_names=[serial_column],
            page_size=500,
            page_token=page_token,
        )
        for record in page["items"]:
            text = _normalize_text((record.get("fields") or {}).get(serial_column))
            if not text:
                continue
            match = re.search(r"\d+", text)
            if match:
                max_no = max(max_no, int(match.group()))
        if not page["has_more"] or not page["page_token"]:
            break
        page_token = str(page["page_token"])
    return max_no + 1


async def _map_to_cal_external_fields(
    db: AsyncSession,
    extracted: CertificateExtractedFields,
    directory: DeviceDirectoryMatch,
    computed_next: str | None,
    *,
    warnings: list[str],
    file_name: str | None = None,
    content: bytes | None = None,
    content_type: str | None = None,
    attachment_ref: dict[str, str] | None = None,
) -> tuple[dict[str, Any], str | None]:
    """把提取字段映射为外部校准表可写字段，返回 (mapped_fields, 附件token)。

    attachment_ref 传入首次识别上传的附件 token 时直接复用，不重复上传。
    """
    runtime, entity = await _resolve_runtime_entity(
        db, _CAL_EXTERNAL_ENTITY_CODE, direction="push"
    )
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    field_items = await client.list_fields(_entity_table_id(entity))
    by_norm: dict[str, tuple[str, dict[str, Any]]] = {}
    for item in field_items:
        name = str(item.get("field_name") or "").strip()
        if name:
            by_norm[_normalize_field_name(name)] = (name, item)

    mapped: dict[str, Any] = {}

    def _put(candidates: tuple[str, ...], value: Any) -> None:
        if value in (None, ""):
            return
        target = _resolve_writable_column(by_norm, candidates)
        if target is None:
            warnings.append(f"外部校准表无「{candidates[0]}」列，已跳过该字段")
            return
        mapped[target] = value

    _put(("器具名称", "仪器名称", "设备名称"), extracted.instrument_name)
    _put(("型号规格", "型号/规格", "规格型号"), extracted.model)
    _put(("器具编号", "出厂编号", "设备编号"), extracted.serial_no)
    _put(("检定日期", "校准日期", "校验日期"), extracted.calibration_date)
    if directory.location:
        _put(("使用地点", "设备安装地点", "存放地点"), directory.location)

    # 下次检定日期：当前为公式列（只读，由飞书按检定日期+12个月自动计算），
    # 不写；若未来改为普通日期列则写入按目录周期推算的值
    next_column = _resolve_writable_column(by_norm, ("下次检定日期",))
    if next_column and computed_next:
        if _column_ui_type(by_norm, next_column) in ("Formula", "Lookup"):
            if directory.period_months and directory.period_months != 12:
                warnings.append(
                    "外部校准表的下次检定日期为公式列（固定按 12 个月），与设备目录"
                    f"周期 {directory.period_months} 个月不一致；如需按实际周期计算，"
                    "建议在表中增加周期列并把公式改为引用周期"
                )
        else:
            mapped[next_column] = computed_next

    # 证书原件：存在附件列时随记录提交（首次上传 / 重新匹配复用 token）
    attachment_token: str | None = None
    attach_column = _resolve_writable_column(by_norm, ("附件",))
    if attach_column and _column_ui_type(by_norm, attach_column) == "Attachment":
        if attachment_ref and attachment_ref.get("file_token"):
            attachment_token = attachment_ref["file_token"]
        elif file_name is not None and content:
            ref = await upload_inspection_feishu_attachment(
                db,
                _CAL_EXTERNAL_ENTITY_CODE,
                file_name,
                content,
                content_type or "application/octet-stream",
            )
            attachment_token = str(ref["file_token"])
        if attachment_token:
            mapped[attach_column] = [{"file_token": attachment_token}]

    # 序号按表内现有最大序号自动续号，无需人工数行
    serial_column = _resolve_writable_column(by_norm, ("序号",))
    if serial_column and _column_ui_type(by_norm, serial_column) not in (
        "Formula",
        "Lookup",
        "AutoNumber",
    ):
        next_serial = await _next_table_serial(
            client, _entity_table_id(entity), serial_column
        )
        mapped[serial_column] = str(next_serial)
    return mapped, attachment_token


# ── 主流程 ───────────────────────────────────────────────────────────


async def _extract_fields_with_llm(
    extension: str,
    content: bytes,
    content_type: str,
) -> CertificateExtractedFields:
    if extension in (".png", ".jpg", ".jpeg"):
        raw = await _call_llm_json(
            prompt=_CERTIFICATE_EXTRACT_PROMPT,
            image_urls=[_image_data_uri(content, content_type)],
        )
        return _clean_extracted(raw)

    text = await asyncio.to_thread(_extract_pdf_text, content)
    if len(text.strip()) >= _PDF_MIN_TEXT_CHARS:
        raw = await _call_llm_json(
            prompt=(
                f"{_CERTIFICATE_EXTRACT_PROMPT}\n\n以下是证书文本内容：\n{text[:20000]}"
            ),
            text=text[:20000],
        )
        return _clean_extracted(raw)

    image_urls = await asyncio.to_thread(_render_pdf_pages, content)
    if not image_urls:
        raise AppException(
            message="无法从证书 PDF 中读取内容，请确认文件未损坏", status_code=400
        )
    raw = await _call_llm_json(
        prompt=_CERTIFICATE_EXTRACT_PROMPT, image_urls=image_urls
    )
    return _clean_extracted(raw)


async def analyze_calibration_certificate(
    db: AsyncSession,
    *,
    file_name: str,
    content: bytes,
    content_type: str,
) -> dict[str, Any]:
    """识别校准证书并返回外部校准表预填字段（不写飞书，由人工确认后提交）。"""
    extension = _validate_certificate_file(file_name, content)
    extracted = await _extract_fields_with_llm(extension, content, content_type)

    warnings: list[str] = []
    return await _build_prefill_result(
        db,
        extracted,
        warnings=warnings,
        file_name=file_name,
        content=content,
        content_type=content_type,
    )


async def _build_prefill_result(
    db: AsyncSession,
    extracted: CertificateExtractedFields,
    *,
    warnings: list[str],
    file_name: str | None = None,
    content: bytes | None = None,
    content_type: str | None = None,
    attachment_ref: dict[str, str] | None = None,
) -> dict[str, Any]:
    """反查目录 + 推算下次检定日期 + 映射预填字段（识别与人工修正共用）。"""
    directory = await _lookup_device_directory(db, extracted, warnings)
    computed_next = _compute_next_calibration_date(extracted, directory, warnings)
    mapped, attachment_token = await _map_to_cal_external_fields(
        db,
        extracted,
        directory,
        computed_next,
        warnings=warnings,
        file_name=file_name,
        content=content,
        content_type=content_type,
        attachment_ref=attachment_ref,
    )
    if attachment_ref and attachment_ref.get("file_token"):
        attachment_token = attachment_ref["file_token"]
    return {
        "extracted": extracted.model_dump(),
        "directory": directory.model_dump(),
        "computed_next_calibration_date": computed_next,
        "mapped_fields": mapped,
        "warnings": warnings,
        "attachment_file_token": attachment_token,
    }


async def rematch_certificate_fields(
    db: AsyncSession, *, request: CertificateRematchRequest
) -> dict[str, Any]:
    """人工修正识别字段后重新反查目录并重建预填（填入表单前的修正闭环）。

    附件复用首次识别上传的 token，不重复上传；使用地点/下次检定日期/序号
    全部按修正后的值重新匹配计算。
    """
    extracted = CertificateExtractedFields(
        instrument_name=_clean_text(request.instrument_name),
        model=_clean_text(request.model),
        serial_no=_clean_text(request.serial_no),
        calibration_date=_clean_date(request.calibration_date),
        next_calibration_date_stated=_clean_date(request.next_calibration_date_stated),
        certificate_no=_clean_text(request.certificate_no),
        calibration_agency=_clean_text(request.calibration_agency),
        conclusion=_clean_text(request.conclusion),
    )
    attachment_ref = (
        {"file_token": str(request.attachment_file_token)}
        if request.attachment_file_token
        else None
    )
    warnings: list[str] = []
    return await _build_prefill_result(
        db, extracted, warnings=warnings, attachment_ref=attachment_ref
    )
