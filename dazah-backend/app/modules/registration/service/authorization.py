"""Registration business workflows live here."""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import re
import subprocess
import uuid
import zipfile
from collections import defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import TypedDict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException, NotFoundException
from app.modules.registration.models import (
    AuthorizationFdaEntry,
    AuthorizationLedgerEntry,
    AuthorizationLedgerMain,
    AuthorizationLedgerUpdate,
    AuthorizationLetter,
    SupplementaryReply,
)
from app.modules.registration.repository import (
    AuthorizationFdaRepository,
    AuthorizationLedgerRepository,
    AuthorizationLetterRepository,
    SupplementaryReplyRepository,
)
from app.modules.registration.schemas import (
    AuthorizationFdaEntryCreate,
    AuthorizationFdaEntryUpdate,
    AuthorizationFdaRecord,
    AuthorizationLedgerEntryCreate,
    AuthorizationLedgerEntryUpdate,
    AuthorizationLedgerGroupedOverview,
    AuthorizationLedgerMainCreate,
    AuthorizationLedgerMainRead,
    AuthorizationLedgerMainUpdate,
    AuthorizationLedgerOverview,
    AuthorizationLedgerRecord,
    AuthorizationLedgerUpdateCreate,
    AuthorizationLedgerUpdateRead,
    AuthorizationLedgerUpdateUpdate,
    AuthorizationLetterCreate,
    AuthorizationLetterListItem,
    AuthorizationLetterResponse,
    AuthorizationMaterialListItem,
    AuthorizationMaterialSummary,
    AuthorizationOverview,
    AuthorizationProductDetail,
    ProductInfo,
    SupplementaryReplyListItem,
    SupplementaryReplyResponse,
)
from app.modules.registration.service.authorization_export import (
    AuthorizationExportArtifact,
    render_fda_export,
    render_market_export,
)

logger = logging.getLogger(__name__)


class _ProductState(TypedDict):
    is_fda: bool
    file_count: int
    fda_records: list[AuthorizationFdaRecord]
    ledger_records: list[AuthorizationLedgerRecord]
    markets: set[str]


# 固定原料药企业
API_COMPANY = "珠海保税区丽珠合成制药有限公司"
FDA_SUFFIX = "-list-of-authorized-parties-to-incorporate-by-reference"
WORD_TABLE_CELL_SEPARATOR = "\n\x07"
LEDGER_DATE_PATTERN = re.compile(
    r"(?P<year>\d{4})[./-](?P<month>\d{1,2})[./-](?P<day>\d{1,2})"
)

# 品种登记号对照表
REGISTRATION_NUMBERS: dict[str, str] = {
    "阿魏酸钠": "Y20190001800",
    "艾普拉唑": "Y20190009784",
    "艾普拉唑钠": "Y20170001429",
    "奥美拉唑钠": "Y20190006673",
    "丙氨酰谷氨酰胺": "Y20190002584",
    "布南色林": "Y20210001289",
    "丹曲林钠": "Y20170001099",
    "丁苯酞": "Y20170001569",
    "厄贝沙坦": "Y20190001962",
    "更昔洛韦": "Y20190008005",
    "枸酸铋钾 (干品)": "Y20200001089",
    "枸橼酸铋钾 (湿品)": "Y20190003316",
    "枸橼酸铋雷尼替丁 (1:1)": "Y20190005110",
    "枸橼酸铋雷尼替丁 (1:1.1)": "Y20190001948",
    "桂利嗪": "Y20190007743",
    "酒石酸托特罗定": "Y20190001881",
    "卡维地洛": "Y20190001959",
    "磷酸川芎嗪": "Y20190007731",
    "硫酸钾": "Y20230000325",
    "硫酸头孢匹罗": "Y20190002699",
    "氯雷他定": "Y20190008122",
    "马来酸氟伏沙明": "Y20170001958",
    "马来酸茚达特罗": "Y20220000555",
    "舒巴坦钠": "Y20190001952",
    "他唑巴坦": "Y20190003875",
    "头孢地嗪钠": "Y20190001846",
    "头孢呋辛钠": "Y20190009596",
    "头孢曲松钠": "Y20190009444",
    "头孢他啶/碳酸钠": "Y20190006854",
    "头孢他啶": "Y20190007742",
    "无水碳酸钠": "Y20190006967",
    "盐酸哌罗匹隆 (新工艺)": "Y20220000720",
    "盐酸哌罗匹隆": "Y20190006883",
    "盐酸头孢吡肟": "Y20190001951",
    "盐酸伊托必利": "Y20190001876",
    "阿立哌唑": "Y20230000505",
    "盐酸鲁拉西酮": "Y20230001106",
    "棕榈酸帕利哌酮": "Y20240000016",
}


def _get_authorization_source_dir() -> Path:
    """获取授权书源资料目录。"""
    settings = get_settings()
    return Path(settings.REGISTRATION_AUTHORIZATION_SOURCE_DIR).expanduser()


def _slugify_material_id(relative_path: str) -> str:
    return hashlib.md5(relative_path.encode("utf-8")).hexdigest()


def _powershell_quote(value: str) -> str:
    return value.replace("'", "''")


def _normalize_inline_text(value: str) -> str:
    sanitized = value.replace("\x07", " ")
    return re.sub(r"\s+", " ", sanitized).strip()


def _normalize_lines(value: str) -> list[str]:
    lines: list[str] = []
    for line in value.split("\n"):
        normalized = _normalize_inline_text(line)
        if normalized:
            lines.append(normalized)
    return lines


def _fit_row(row: list[str], size: int) -> list[str]:
    cleaned = [_normalize_inline_text(cell) for cell in row]
    if len(cleaned) >= size:
        head = cleaned[: size - 1]
        tail = " ".join(cell for cell in cleaned[size - 1 :] if cell)
        return head + [tail]
    return cleaned + [""] * (size - len(cleaned))


def _is_generic_trailing_note(value: str) -> bool:
    normalized = _normalize_inline_text(value)
    return normalized.startswith("注明：收回授权时")


def _merge_remark(base: str | None, extra: str) -> str:
    normalized_base = _normalize_inline_text(base or "")
    normalized_extra = _normalize_inline_text(extra)
    if not normalized_base or normalized_base in {"-", "—"}:
        return normalized_extra
    if not normalized_extra:
        return normalized_base
    return f"{normalized_base} {normalized_extra}".strip()


def _derive_ledger_status(remarks: str | None) -> str:
    normalized = _normalize_inline_text(remarks or "")
    if not normalized:
        return "待确认"
    if "收回" in normalized:
        return "已收回"
    if "暂未" in normalized or "未向官方递交" in normalized:
        return "未递交"
    if "更新" in normalized:
        return "待更新"
    if "递交" in normalized:
        return "已递交"
    return "待确认"


def _normalize_ledger_group_text(value: str | None) -> str:
    return _normalize_inline_text(value or "")


def _authorization_date_sort_key(value: str | None) -> tuple[int, int, int, int, str]:
    normalized = _normalize_ledger_group_text(value)
    if not normalized:
        return (2, 9999, 12, 31, "")

    match = LEDGER_DATE_PATTERN.search(normalized)
    if not match:
        return (1, 9999, 12, 31, normalized)

    return (
        0,
        int(match.group("year")),
        int(match.group("month")),
        int(match.group("day")),
        normalized,
    )


def _build_ledger_main_key(
    *,
    product_name: str | None,
    market_name: str | None,
    source_sequence: str | None,
    authorization_file_name: str | None,
    quality_standard: str | None,
    company_name: str | None,
    country: str | None,
    customer_code: str | None,
    purpose: str | None,
    status: str | None,
) -> tuple[str, ...]:
    return (
        _normalize_ledger_group_text(product_name),
        _normalize_ledger_group_text(market_name),
        _normalize_ledger_group_text(source_sequence),
        _normalize_ledger_group_text(authorization_file_name),
        _normalize_ledger_group_text(quality_standard),
        _normalize_ledger_group_text(company_name),
        _normalize_ledger_group_text(country),
        _normalize_ledger_group_text(customer_code),
        _normalize_ledger_group_text(purpose),
        _normalize_ledger_group_text(status),
    )


def _build_legacy_ledger_main_key(entry: AuthorizationLedgerEntry) -> tuple[str, ...]:
    return _build_ledger_main_key(
        product_name=entry.product_name,
        market_name=entry.market_name,
        source_sequence=entry.source_sequence,
        authorization_file_name=entry.authorization_file_name,
        quality_standard=entry.quality_standard,
        company_name=entry.company_name,
        country=entry.country,
        customer_code=entry.customer_code,
        purpose=entry.purpose,
        status=entry.status,
    )


def _build_grouped_ledger_main_key(entry: AuthorizationLedgerMain) -> tuple[str, ...]:
    return _build_ledger_main_key(
        product_name=entry.product_name,
        market_name=entry.market_name,
        source_sequence=entry.source_sequence,
        authorization_file_name=entry.authorization_file_name,
        quality_standard=entry.quality_standard,
        company_name=entry.company_name,
        country=entry.country,
        customer_code=entry.customer_code,
        purpose=entry.purpose,
        status=entry.status,
    )


def _build_ledger_update_signature(
    authorization_date: str | None,
    handler: str | None,
    remarks: str | None,
) -> tuple[str, str, str]:
    return (
        _normalize_ledger_group_text(authorization_date),
        _normalize_ledger_group_text(handler),
        _normalize_ledger_group_text(remarks),
    )


def _build_legacy_update_signature(
    entry: AuthorizationLedgerEntry,
) -> tuple[str, str, str]:
    return _build_ledger_update_signature(
        authorization_date=entry.authorization_date,
        handler=entry.handler,
        remarks=entry.remarks,
    )


def _build_grouped_update_signature(
    entry: AuthorizationLedgerUpdate,
) -> tuple[str, str, str]:
    return _build_ledger_update_signature(
        authorization_date=entry.authorization_date,
        handler=entry.handler,
        remarks=entry.remarks,
    )


def _sanitize_required_ledger_text(value: str | None) -> str:
    return _normalize_ledger_group_text(value)


def _sanitize_optional_ledger_text(value: str | None) -> str | None:
    normalized = _normalize_ledger_group_text(value)
    return normalized or None


def _build_sanitized_main_values(
    first_entry: AuthorizationLedgerEntry,
    last_entry: AuthorizationLedgerEntry,
) -> dict[str, object]:
    return {
        "product_name": _sanitize_required_ledger_text(first_entry.product_name),
        "market_name": _sanitize_optional_ledger_text(first_entry.market_name),
        "source_sequence": _sanitize_optional_ledger_text(first_entry.source_sequence),
        "authorization_file_name": _sanitize_required_ledger_text(
            first_entry.authorization_file_name
        ),
        "quality_standard": _sanitize_optional_ledger_text(
            first_entry.quality_standard
        ),
        "company_name": _sanitize_optional_ledger_text(first_entry.company_name),
        "country": _sanitize_optional_ledger_text(first_entry.country),
        "customer_code": _sanitize_optional_ledger_text(first_entry.customer_code),
        "purpose": _sanitize_optional_ledger_text(first_entry.purpose),
        "status": _sanitize_optional_ledger_text(first_entry.status),
        "created_at": first_entry.created_at,
        "updated_at": last_entry.updated_at,
        "created_by": first_entry.created_by,
        "updated_by": last_entry.updated_by,
    }


def _build_sanitized_update_values(
    entry: AuthorizationLedgerEntry,
) -> dict[str, object]:
    return {
        "authorization_date": _sanitize_optional_ledger_text(entry.authorization_date),
        "handler": _sanitize_optional_ledger_text(entry.handler),
        "remarks": _sanitize_optional_ledger_text(entry.remarks),
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
        "created_by": entry.created_by,
        "updated_by": entry.updated_by,
    }


def _normalize_legacy_entry_in_place(entry: AuthorizationLedgerEntry) -> None:
    entry.product_name = _sanitize_required_ledger_text(entry.product_name)
    entry.market_name = _sanitize_optional_ledger_text(entry.market_name)
    entry.source_sequence = _sanitize_optional_ledger_text(entry.source_sequence)
    entry.authorization_file_name = _sanitize_required_ledger_text(
        entry.authorization_file_name
    )
    entry.quality_standard = _sanitize_optional_ledger_text(entry.quality_standard)
    entry.company_name = _sanitize_optional_ledger_text(entry.company_name)
    entry.country = _sanitize_optional_ledger_text(entry.country)
    entry.customer_code = _sanitize_optional_ledger_text(entry.customer_code)
    entry.purpose = _sanitize_optional_ledger_text(entry.purpose)
    entry.authorization_date = _sanitize_optional_ledger_text(entry.authorization_date)
    entry.handler = _sanitize_optional_ledger_text(entry.handler)
    entry.status = _sanitize_optional_ledger_text(entry.status)
    entry.remarks = _sanitize_optional_ledger_text(entry.remarks)


def _sort_legacy_ledger_entries(
    entries: list[AuthorizationLedgerEntry],
) -> list[AuthorizationLedgerEntry]:
    return sorted(
        entries,
        key=lambda item: (
            _build_legacy_ledger_main_key(item),
            _authorization_date_sort_key(item.authorization_date),
            item.created_at,
            str(item.id),
        ),
    )


def _group_legacy_ledger_entries(
    entries: list[AuthorizationLedgerEntry],
) -> dict[tuple[str, ...], list[AuthorizationLedgerEntry]]:
    grouped: dict[tuple[str, ...], list[AuthorizationLedgerEntry]] = defaultdict(list)
    for entry in _sort_legacy_ledger_entries(entries):
        grouped[_build_legacy_ledger_main_key(entry)].append(entry)
    return dict(grouped)


def _extract_product_name(file_path: Path, source_root: Path) -> str:
    stem = file_path.stem
    if stem.endswith(FDA_SUFFIX):
        return stem[: -len(FDA_SUFFIX)]

    if stem.startswith("授权书台帐-"):
        remainder = stem.removeprefix("授权书台帐-")
        return remainder.split("-", 1)[0]

    for parent in file_path.parents:
        if parent == source_root.parent:
            break
        if "授权客户明细" in parent.name:
            return parent.name.replace("授权客户明细", "").strip("- ")

    return file_path.parent.name if file_path.parent != source_root else stem


def _extract_market_name(file_path: Path) -> str | None:
    stem = file_path.stem
    if stem.endswith(FDA_SUFFIX):
        return "FDA"

    if stem.startswith("授权书台帐-"):
        remainder = stem.removeprefix("授权书台帐-")
        parts = remainder.split("-")
        if len(parts) > 1:
            return parts[-1]

    if "授权客户明细" in str(file_path.parent):
        parts = stem.split("-")
        if len(parts) > 2:
            return parts[-1]

    return None


def _extract_category(file_path: Path) -> str:
    stem = file_path.stem
    if stem.endswith(FDA_SUFFIX):
        return "FDA 引用授权名单"
    if stem.startswith("授权书台帐-"):
        return "授权书台账"
    if "授权客户明细" in str(file_path.parent):
        return "授权客户明细"
    return "产品授权资料"


def _should_skip_source_file(file_path: Path) -> bool:
    return file_path.name.startswith("~$")


@lru_cache(maxsize=128)
def _read_word_content_cached(path_key: str, mtime_ns: int) -> str:
    del mtime_ns
    quoted_path = _powershell_quote(path_key)
    script = (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "$word = New-Object -ComObject Word.Application; "
        "$word.Visible = $false; "
        "$word.DisplayAlerts = 0; "
        "try { "
        f"$doc = $word.Documents.Open('{quoted_path}', $false, $true); "
        "$text = $doc.Content.Text; "
        "$doc.Close([ref]0); "
        "Write-Output $text "
        "} finally { "
        "try { $word.Quit() } catch {} ; "
        "try { [System.Runtime.Interopservices.Ma"
        "rshal]::ReleaseComObject($word) | Out-Nu"
        "ll } catch {} "
        "}"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or result.stdout.strip() or "Word 内容读取失败"
        )
    return result.stdout


def _read_word_content(file_path: Path) -> str:
    stat = file_path.stat()
    return _read_word_content_cached(str(file_path.resolve()), stat.st_mtime_ns)


def _parse_word_table(raw_text: str) -> tuple[list[str], list[list[str]], list[str]]:
    normalized_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    prefix_lines: list[str] = []
    rows: list[list[str]] = []
    trailing_lines: list[str] = []
    table_started = False

    for chunk in re.split(r"\n\x07\n+", normalized_text):
        if not chunk.strip():
            continue

        if WORD_TABLE_CELL_SEPARATOR not in chunk:
            lines = _normalize_lines(chunk)
            if not lines:
                continue
            if table_started:
                trailing_lines.extend(lines)
            else:
                prefix_lines.extend(lines)
            continue

        raw_cells = chunk.split(WORD_TABLE_CELL_SEPARATOR)
        first_cell_lines = _normalize_lines(raw_cells[0])
        cells: list[str] = []

        if not table_started:
            prefix_lines.extend(first_cell_lines[:-1])
            cells.append(first_cell_lines[-1] if first_cell_lines else "")
            table_started = True
        else:
            cells.append(_normalize_inline_text(raw_cells[0].replace("\n", " ")))

        for raw_cell in raw_cells[1:]:
            cells.append(_normalize_inline_text(raw_cell.replace("\n", " ")))

        while cells and not cells[-1]:
            cells.pop()

        if any(cells):
            rows.append(cells)

    return prefix_lines, rows, trailing_lines


def _split_company_and_country(value: str) -> tuple[str | None, str | None]:
    normalized = _normalize_inline_text(value)
    if not normalized:
        return None, None
    if "/" in normalized:
        company_name, country = normalized.rsplit("/", 1)
        return _normalize_inline_text(company_name), _normalize_inline_text(country)
    return normalized, None


def _parse_fda_records(
    raw_text: str,
) -> tuple[list[AuthorizationFdaRecord], str | None]:
    _, rows, trailing_lines = _parse_word_table(raw_text)
    if not rows:
        return [], None

    records: list[AuthorizationFdaRecord] = []
    previous_company: str | None = None
    previous_address: str | None = None
    previous_reference: str | None = None
    has_number_column = bool(
        rows and rows[0] and rows[0][0].strip().lower() in {"no.", "no", "序号"}
    )

    for row in rows[1:]:
        normalized_row = [_normalize_inline_text(cell) for cell in row]
        if has_number_column and len(normalized_row) >= 7:
            cells = _fit_row(normalized_row[1:], 6)
        elif len(normalized_row) == 4 and not normalized_row[0]:
            cells = [
                "",
                "",
                "",
                normalized_row[1],
                normalized_row[2],
                normalized_row[3],
            ]
        elif len(normalized_row) == 5 and not normalized_row[0]:
            cells = [
                "",
                "",
                normalized_row[1],
                normalized_row[2],
                normalized_row[3],
                normalized_row[4],
            ]
        else:
            cells = _fit_row(normalized_row, 6)

        company_name = cells[0] or previous_company
        address = cells[1] or previous_address
        reference_number = cells[2] or previous_reference
        loa_date = cells[3] or None
        submission_date = cells[4] or None
        referenced_sections = cells[5] or None

        if not any(
            [
                company_name,
                address,
                reference_number,
                loa_date,
                submission_date,
                referenced_sections,
            ]
        ):
            continue

        if cells[0]:
            previous_company = cells[0]
        if cells[1]:
            previous_address = cells[1]
        if cells[2]:
            previous_reference = cells[2]

        records.append(
            AuthorizationFdaRecord(
                sequence=len(records) + 1,
                company_name=company_name or "",
                address=address,
                reference_number=reference_number,
                loa_date=loa_date,
                submission_date=submission_date,
                referenced_sections=referenced_sections,
            )
        )

    note_lines = [
        line for line in trailing_lines if not _is_generic_trailing_note(line)
    ]
    note = " ".join(note_lines) if note_lines else None
    return records, note


def _parse_ledger_records(
    raw_text: str,
) -> tuple[list[AuthorizationLedgerRecord], str | None]:
    _, rows, trailing_lines = _parse_word_table(raw_text)
    if not rows:
        return [], None

    records: list[AuthorizationLedgerRecord] = []
    for row in rows[1:]:
        normalized_row = [
            _normalize_inline_text(cell) for cell in row if _normalize_inline_text(cell)
        ]
        if not normalized_row:
            continue

        # 某些台账会在表格中插入“首次递交/更新日期”等说明行。
        # 这类行列数明显少于正式记录，应并入上一条备注而不是生成伪记录。
        if len(normalized_row) < 7:
            if records:
                note_text = " ".join(normalized_row)
                last_record = records[-1]
                last_record.remarks = _merge_remark(last_record.remarks, note_text)
            continue

        cells = _fit_row(normalized_row, 9)
        if not any(cells):
            continue

        company_name, country = _split_company_and_country(cells[3])
        records.append(
            AuthorizationLedgerRecord(
                sequence=cells[0] or str(len(records) + 1),
                authorization_file_name=cells[1] or "",
                quality_standard=cells[2] or None,
                company_name=company_name,
                country=country,
                customer_code=cells[4] or None,
                purpose=cells[5] or None,
                authorization_date=cells[6] or None,
                handler=cells[7] or None,
                remarks=cells[8] or None,
            )
        )

    note_lines = [
        line for line in trailing_lines if not _is_generic_trailing_note(line)
    ]
    note = " ".join(note_lines) if note_lines else None
    return records, note


def _get_authorization_snapshot_key() -> str:
    source_root = _get_authorization_source_dir()
    if not source_root.exists():
        return f"{source_root.resolve()}::missing"

    parts: list[str] = []
    for file_path in sorted(source_root.rglob("*")):
        if not file_path.is_file():
            continue
        stat = file_path.stat()
        relative_path = file_path.relative_to(source_root).as_posix()
        parts.append(f"{relative_path}:{stat.st_mtime_ns}:{stat.st_size}")
    return f"{source_root.resolve()}::{'|'.join(parts)}"


@lru_cache(maxsize=4)
def _build_authorization_content_cached(
    snapshot_key: str,
) -> tuple[
    AuthorizationOverview, list[ProductInfo], dict[str, AuthorizationProductDetail]
]:
    del snapshot_key
    source_root = _get_authorization_source_dir()
    if not source_root.exists():
        return (
            AuthorizationOverview(
                total_products=0,
                total_files=0,
                total_markets=0,
                total_records=0,
                fda_products=0,
                fda_records=0,
                ledger_records=0,
            ),
            [],
            {},
        )

    product_state: dict[str, _ProductState] = {}
    total_files = 0
    failed_files: list[str] = []

    for file_path in sorted(source_root.rglob("*")):
        if not file_path.is_file():
            continue
        if _should_skip_source_file(file_path):
            continue

        total_files += 1
        product_name = _extract_product_name(file_path, source_root)
        market_name = _extract_market_name(file_path)
        is_fda = file_path.stem.endswith(FDA_SUFFIX)

        state = product_state.setdefault(
            product_name,
            _ProductState(
                is_fda=False,
                file_count=0,
                fda_records=[],
                ledger_records=[],
                markets=set(),
            ),
        )
        state["file_count"] += 1

        try:
            raw_text = _read_word_content(file_path)
            if is_fda:
                parsed_fda_records, _note = _parse_fda_records(raw_text)
                state["is_fda"] = True
                state["fda_records"].extend(parsed_fda_records)
            else:
                ledger_records, note = _parse_ledger_records(raw_text)
                normalized_market_name = market_name or "未分类"
                if note and ledger_records:
                    last_record = ledger_records[-1]
                    last_record.remarks = _merge_remark(last_record.remarks, note)
                for record in ledger_records:
                    record.market_name = normalized_market_name
                state["ledger_records"].extend(ledger_records)
                state["markets"].add(normalized_market_name)
        except Exception:
            logger.exception("文档解析失败: %s", file_path)
            failed_files.append(str(file_path))
            continue

    if failed_files:
        logger.warning(
            "共有 %d 个授权书文件解析失败: %s", len(failed_files), failed_files
        )

    product_summaries: list[ProductInfo] = []
    product_details: dict[str, AuthorizationProductDetail] = {}
    total_markets = 0
    total_records = 0
    fda_products = 0
    total_fda_records = 0

    for product_name, state in product_state.items():
        file_count = state["file_count"]
        fda_record_items = list(state["fda_records"])
        ledger_records = list(state["ledger_records"])
        markets = set(state["markets"])
        is_fda = state["is_fda"]

        ledger_records.sort(
            key=lambda item: (
                item.market_name or "",
                item.country or "",
                item.company_name or "",
                item.sequence,
            )
        )

        market_count = len(markets)
        record_count = len(fda_record_items) + len(ledger_records)

        detail = AuthorizationProductDetail(
            product_name=product_name,
            is_fda=is_fda,
            material_count=file_count,
            market_count=market_count,
            record_count=record_count,
            fda_record_count=len(fda_record_items),
            fda_records=fda_record_items,
            ledger_records=ledger_records,
        )
        product_details[product_name] = detail

        product_summaries.append(
            ProductInfo(
                product_name=product_name,
                is_fda=is_fda,
                material_count=file_count,
                market_count=market_count,
                record_count=record_count,
                fda_record_count=len(fda_record_items),
            )
        )

        total_markets += market_count
        total_records += record_count
        total_fda_records += len(fda_record_items)
        if is_fda:
            fda_products += 1

    product_summaries.sort(
        key=lambda item: (0 if item.is_fda else 1, item.product_name)
    )

    overview = AuthorizationOverview(
        total_products=len(product_summaries),
        total_files=total_files,
        total_markets=total_markets,
        total_records=total_records,
        fda_products=fda_products,
        fda_records=total_fda_records,
        ledger_records=total_records - total_fda_records,
    )
    return overview, product_summaries, product_details


def _get_authorization_content_index() -> tuple[
    AuthorizationOverview, list[ProductInfo], dict[str, AuthorizationProductDetail]
]:
    return _build_authorization_content_cached(_get_authorization_snapshot_key())


def _scan_authorization_materials() -> tuple[
    list[AuthorizationMaterialListItem], AuthorizationMaterialSummary
]:
    source_root = _get_authorization_source_dir()
    if not source_root.exists():
        logger.warning("授权书源资料目录不存在: %s", source_root)
        return [], AuthorizationMaterialSummary(
            total_products=0,
            total_files=0,
            fda_products=0,
            fda_files=0,
        )

    materials: list[AuthorizationMaterialListItem] = []

    for file_path in source_root.rglob("*"):
        if not file_path.is_file():
            continue
        if _should_skip_source_file(file_path):
            continue

        relative_path = file_path.relative_to(source_root).as_posix()
        product_name = _extract_product_name(file_path, source_root)
        is_fda = file_path.stem.endswith(FDA_SUFFIX)
        stat = file_path.stat()

        materials.append(
            AuthorizationMaterialListItem(
                id=_slugify_material_id(relative_path),
                product_name=product_name,
                category=_extract_category(file_path),
                market_name=_extract_market_name(file_path),
                is_fda=is_fda,
                file_name=file_path.name,
                file_ext=file_path.suffix.lower(),
                relative_path=relative_path,
                size_bytes=stat.st_size,
                updated_at=datetime.fromtimestamp(stat.st_mtime),
            )
        )

    materials.sort(
        key=lambda item: (
            item.product_name,
            0 if item.is_fda else 1,
            item.category,
            item.file_name,
        )
    )

    product_flags: dict[str, bool] = {}
    for item in materials:
        product_flags[item.product_name] = (
            product_flags.get(item.product_name, False) or item.is_fda
        )

    summary = AuthorizationMaterialSummary(
        total_products=len(product_flags),
        total_files=len(materials),
        fda_products=sum(1 for is_fda in product_flags.values() if is_fda),
        fda_files=sum(1 for item in materials if item.is_fda),
    )
    return materials, summary


def _get_upload_dir() -> Path:
    """获取上传/生成文件存储目录"""
    settings = get_settings()
    upload_dir_setting = getattr(settings, "UPLOAD_DIR", "uploads")
    base = Path(upload_dir_setting)
    upload_dir = base / "authorization_letters"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def _is_docx_format(data: bytes) -> bool:
    """检测文件是否为 DOCX 格式（ZIP 压缩包）"""
    return data.startswith(b"PK")


def generate_authorization_letter_bytes(
    template_data: bytes,
    replacements: list[tuple[str, str]],
) -> bytes:
    """
    对模板执行文本替换。支持 .docx 格式（实际是 ZIP 压缩包）。

    Args:
        template_data: 模板文件二进制内容
        replacements: 替换规则列表 [(原文本，新文本), ...]

    Returns:
        替换后的文件二进制内容
    """
    if not _is_docx_format(template_data):
        return _binary_replace(template_data, replacements)
    return _docx_replace(template_data, replacements)


def _docx_replace(
    template_data: bytes,
    replacements: list[tuple[str, str]],
) -> bytes:
    """对 DOCX 文件执行 XML 文本替换"""
    replacement_dict = {old: new for old, new in replacements}

    with zipfile.ZipFile(io.BytesIO(template_data), "r") as zipped:
        files = {name: zipped.read(name) for name in zipped.namelist()}

        if "word/document.xml" in files:
            try:
                doc_xml = files["word/document.xml"].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    "模板文件编码错误：DOCX 文档包含非 UTF-8 编码的内容"
                ) from exc

            for old_text, new_text in replacement_dict.items():
                if old_text in doc_xml:
                    doc_xml = doc_xml.replace(old_text, new_text)
                    logger.debug(
                        "授权书文本替换完成（%d 字符 -> %d 字符）",
                        len(old_text),
                        len(new_text),
                    )
                else:
                    logger.warning("未找到文本：'%s'", old_text)

            files["word/document.xml"] = doc_xml.encode("utf-8")

        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as out_zipped:
            for name, content in files.items():
                out_zipped.writestr(name, content)

        return output.getvalue()


def _binary_replace(
    template_data: bytes,
    replacements: list[tuple[str, str]],
) -> bytes:
    """对 .doc 模板执行二进制等长替换（旧方式）"""
    data = bytearray(template_data)

    for old_text, new_text in replacements:
        old_bytes = old_text.encode("utf-16le")
        new_bytes = new_text.encode("utf-16le")

        if len(old_bytes) != len(new_bytes):
            raise ValueError(
                f"长度不匹配：'{old_text}' ({len(old_text)}字，{len(old_bytes)}字节) ->"
                f" '{new_text}' ({len(new_text)}字，{len(new_bytes)}字节)"
            )

        pos = 0
        while True:
            pos = data.find(old_bytes, pos)
            if pos == -1:
                break
            data[pos : pos + len(old_bytes)] = new_bytes
            pos += 1

    return bytes(data)


class AuthorizationLetterService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AuthorizationLetterRepository(session)
        self.fda_repo = AuthorizationFdaRepository(session)
        self.ledger_repo = AuthorizationLedgerRepository(session)

    def _to_response(self, obj: AuthorizationLetter) -> AuthorizationLetterResponse:
        return AuthorizationLetterResponse.model_validate(obj)

    def _to_list_item(self, obj: AuthorizationLetter) -> AuthorizationLetterListItem:
        return AuthorizationLetterListItem.model_validate(obj)

    @staticmethod
    def _to_fda_record(obj: AuthorizationFdaEntry) -> AuthorizationFdaRecord:
        return AuthorizationFdaRecord(
            id=obj.id,
            product_name=obj.product_name,
            sequence=obj.source_sequence or 0,
            company_name=obj.company_name,
            address=obj.address,
            reference_number=obj.reference_number,
            loa_date=obj.loa_date,
            submission_date=obj.submission_date,
            referenced_sections=obj.referenced_sections,
        )

    @staticmethod
    def _to_ledger_record(obj: AuthorizationLedgerEntry) -> AuthorizationLedgerRecord:
        return AuthorizationLedgerRecord(
            id=obj.id,
            product_name=obj.product_name,
            sequence=obj.source_sequence or "",
            market_name=obj.market_name,
            authorization_file_name=obj.authorization_file_name,
            quality_standard=obj.quality_standard,
            company_name=obj.company_name,
            country=obj.country,
            customer_code=obj.customer_code,
            purpose=obj.purpose,
            authorization_date=obj.authorization_date,
            handler=obj.handler,
            status=obj.status,
            remarks=obj.remarks,
        )

    @staticmethod
    def _to_ledger_main_read(
        obj: AuthorizationLedgerMain,
    ) -> AuthorizationLedgerMainRead:
        return AuthorizationLedgerMainRead.model_validate(obj)

    @staticmethod
    def _to_ledger_update_read(
        obj: AuthorizationLedgerUpdate,
    ) -> AuthorizationLedgerUpdateRead:
        return AuthorizationLedgerUpdateRead.model_validate(obj)

    @staticmethod
    async def get_overview() -> AuthorizationOverview:
        overview, _, _ = await asyncio.to_thread(_get_authorization_content_index)
        return overview

    @staticmethod
    async def get_product_list() -> list[ProductInfo]:
        _, products, _ = await asyncio.to_thread(_get_authorization_content_index)
        return products

    @staticmethod
    async def get_product_detail(product_name: str) -> AuthorizationProductDetail:
        _, _, details = await asyncio.to_thread(_get_authorization_content_index)
        detail = details.get(product_name)
        if not detail:
            raise NotFoundException("授权书产品", product_name)
        return detail

    async def ensure_fda_seeded(self) -> None:
        existing_count = await self.fda_repo.count_entries()
        if existing_count > 0:
            return

        _, _, details = await asyncio.to_thread(_get_authorization_content_index)
        entries: list[AuthorizationFdaEntry] = []
        for product_name, detail in details.items():
            for record in detail.fda_records:
                entries.append(
                    AuthorizationFdaEntry(
                        product_name=product_name,
                        source_sequence=record.sequence,
                        company_name=record.company_name,
                        address=record.address,
                        reference_number=record.reference_number,
                        loa_date=record.loa_date,
                        submission_date=record.submission_date,
                        referenced_sections=record.referenced_sections,
                    )
                )

        if not entries:
            return

        await self.fda_repo.create_entries(entries)
        await self.session.commit()

    async def list_fda_entries(
        self,
        *,
        product_name: str | None = None,
        keyword: str | None = None,
    ) -> list[AuthorizationFdaRecord]:
        await self.ensure_fda_seeded()
        entries = await self.fda_repo.list_entries(
            product_name=product_name, keyword=keyword
        )
        return [self._to_fda_record(entry) for entry in entries]

    async def create_fda_entry(
        self,
        payload: AuthorizationFdaEntryCreate,
    ) -> AuthorizationFdaRecord:
        entry = AuthorizationFdaEntry(
            product_name=payload.product_name,
            source_sequence=payload.source_sequence,
            company_name=payload.company_name,
            address=payload.address,
            reference_number=payload.reference_number,
            loa_date=payload.loa_date,
            submission_date=payload.submission_date,
            referenced_sections=payload.referenced_sections,
        )
        created = await self.fda_repo.create_entry(entry)
        await self.session.commit()
        return self._to_fda_record(created)

    async def update_fda_entry(
        self,
        entry_id: UUID,
        payload: AuthorizationFdaEntryUpdate,
    ) -> AuthorizationFdaRecord:
        entry = await self.fda_repo.get_by_id(entry_id)
        if not entry:
            raise NotFoundException("FDA授权记录", str(entry_id))

        update_data = payload.model_dump(exclude_unset=True)
        updated = await self.fda_repo.update_entry(entry, update_data)
        await self.session.commit()
        return self._to_fda_record(updated)

    async def delete_fda_entry(self, entry_id: UUID) -> None:
        entry = await self.fda_repo.get_by_id(entry_id)
        if not entry:
            raise NotFoundException("FDA授权记录", str(entry_id))
        await self.fda_repo.soft_delete(entry)
        await self.session.commit()

    async def ensure_ledger_seeded(self) -> None:
        existing_count = await self.ledger_repo.count_entries()
        if existing_count > 0:
            return

        _, _, details = await asyncio.to_thread(_get_authorization_content_index)
        entries: list[AuthorizationLedgerEntry] = []
        for product_name, detail in details.items():
            for record in detail.ledger_records:
                entries.append(
                    AuthorizationLedgerEntry(
                        product_name=product_name,
                        market_name=record.market_name,
                        source_sequence=record.sequence,
                        authorization_file_name=record.authorization_file_name,
                        quality_standard=record.quality_standard,
                        company_name=record.company_name,
                        country=record.country,
                        customer_code=record.customer_code,
                        purpose=record.purpose,
                        authorization_date=record.authorization_date,
                        handler=record.handler,
                        status=_derive_ledger_status(record.remarks),
                        remarks=record.remarks,
                    )
                )

        if not entries:
            return

        await self.ledger_repo.create_entries(entries)
        await self.session.commit()

    async def list_grouped_ledger_mains(
        self,
        *,
        product_name: str | None = None,
        market_name: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[AuthorizationLedgerMainRead], AuthorizationLedgerGroupedOverview]:
        mains = await self.ledger_repo.list_main_entries(
            product_name=product_name,
            market_name=market_name,
            status=status,
            keyword=keyword,
        )
        records = [self._to_ledger_main_read(main) for main in mains]
        update_count = sum(len(record.updates) for record in records)
        overview = AuthorizationLedgerGroupedOverview(
            total_main_records=len(records),
            total_update_records=update_count,
            total_products=len(
                {record.product_name for record in records if record.product_name}
            ),
            total_markets=len(
                {record.market_name for record in records if record.market_name}
            ),
            submitted_main_records=sum(
                1 for record in records if record.status == "已递交"
            ),
            pending_main_records=sum(
                1 for record in records if record.status == "未递交"
            ),
        )
        return records, overview

    async def backfill_grouped_ledger_from_legacy(self) -> dict[str, int]:
        legacy_entries = await self.ledger_repo.list_entries()
        for legacy_entry in legacy_entries:
            _normalize_legacy_entry_in_place(legacy_entry)
        legacy_groups = _group_legacy_ledger_entries(legacy_entries)
        active_mains = await self.ledger_repo.list_main_entries()

        stats = {
            "legacy_entry_count": len(legacy_entries),
            "legacy_group_count": len(legacy_groups),
            "soft_deleted_main_count": 0,
            "soft_deleted_update_count": 0,
            "created_main_count": 0,
            "created_update_count": 0,
            "reused_main_count": 0,
        }

        current_mains_by_key: dict[tuple[str, ...], list[AuthorizationLedgerMain]] = (
            defaultdict(list)
        )
        for main in sorted(
            active_mains, key=lambda item: (item.created_at, str(item.id))
        ):
            current_mains_by_key[_build_grouped_ledger_main_key(main)].append(main)

        kept_mains: dict[tuple[str, ...], AuthorizationLedgerMain] = {}
        for key, mains in current_mains_by_key.items():
            expected_legacy_entries = legacy_groups.get(key)
            if not expected_legacy_entries:
                for main in mains:
                    stats["soft_deleted_main_count"] += 1
                    stats["soft_deleted_update_count"] += len(main.updates)
                    await self.ledger_repo.soft_delete_main_entry(main)
                continue

            expected_update_signatures = tuple(
                _build_legacy_update_signature(entry)
                for entry in expected_legacy_entries
            )
            matching_mains: list[AuthorizationLedgerMain] = []

            for main in mains:
                current_update_signatures = tuple(
                    _build_grouped_update_signature(update)
                    for update in sorted(
                        main.updates,
                        key=lambda item: (item.sort_order, item.created_at),
                    )
                )
                if current_update_signatures == expected_update_signatures:
                    matching_mains.append(main)
                    continue

                stats["soft_deleted_main_count"] += 1
                stats["soft_deleted_update_count"] += len(main.updates)
                await self.ledger_repo.soft_delete_main_entry(main)

            if matching_mains:
                kept_mains[key] = matching_mains[0]
                stats["reused_main_count"] += 1
                sanitized_main_values = _build_sanitized_main_values(
                    expected_legacy_entries[0],
                    expected_legacy_entries[-1],
                )
                for field_name, field_value in sanitized_main_values.items():
                    setattr(matching_mains[0], field_name, field_value)

                current_updates = sorted(
                    matching_mains[0].updates,
                    key=lambda item: (item.sort_order, item.created_at),
                )
                for update_row, legacy_entry in zip(
                    current_updates, expected_legacy_entries
                ):
                    sanitized_update_values = _build_sanitized_update_values(
                        legacy_entry
                    )
                    for field_name, field_value in sanitized_update_values.items():
                        setattr(update_row, field_name, field_value)

                for duplicate_main in matching_mains[1:]:
                    stats["soft_deleted_main_count"] += 1
                    stats["soft_deleted_update_count"] += len(duplicate_main.updates)
                    await self.ledger_repo.soft_delete_main_entry(duplicate_main)

        for key, grouped_entries in legacy_groups.items():
            if key in kept_mains:
                continue

            first_entry = grouped_entries[0]
            last_entry = grouped_entries[-1]
            created_main = await self.ledger_repo.create_main_entry(
                AuthorizationLedgerMain(
                    **_build_sanitized_main_values(first_entry, last_entry)
                )
            )
            stats["created_main_count"] += 1

            for sort_order, legacy_entry in enumerate(grouped_entries, start=1):
                await self.ledger_repo.create_update_entry(
                    AuthorizationLedgerUpdate(
                        ledger_main_id=created_main.id,
                        sort_order=sort_order,
                        **_build_sanitized_update_values(legacy_entry),
                    )
                )
                stats["created_update_count"] += 1

        await self.session.commit()
        return stats

    async def create_ledger_main(
        self,
        payload: AuthorizationLedgerMainCreate,
    ) -> AuthorizationLedgerMainRead:
        main_entry = AuthorizationLedgerMain(
            product_name=payload.product_name,
            market_name=payload.market_name,
            source_sequence=payload.source_sequence,
            authorization_file_name=payload.authorization_file_name,
            quality_standard=payload.quality_standard,
            company_name=payload.company_name,
            country=payload.country,
            customer_code=payload.customer_code,
            purpose=payload.purpose,
            status=payload.status or "待确认",
        )
        created_main = await self.ledger_repo.create_main_entry(main_entry)

        initial_update = AuthorizationLedgerUpdate(
            ledger_main_id=created_main.id,
            sort_order=1,
            authorization_date=payload.initial_update.authorization_date,
            handler=payload.initial_update.handler,
            remarks=payload.initial_update.remarks,
        )
        await self.ledger_repo.create_update_entry(initial_update)
        await self.session.commit()

        persisted = await self.ledger_repo.get_main_by_id(created_main.id)
        if not persisted:
            raise NotFoundException("授权主记录", str(created_main.id))
        return self._to_ledger_main_read(persisted)

    async def create_ledger_update(
        self,
        main_id: UUID,
        payload: AuthorizationLedgerUpdateCreate,
    ) -> AuthorizationLedgerUpdateRead:
        main_entry = await self.ledger_repo.get_main_by_id(main_id)
        if not main_entry:
            raise NotFoundException("授权主记录", str(main_id))

        next_sort_order = await self.ledger_repo.get_next_update_sort_order(main_id)
        update_entry = AuthorizationLedgerUpdate(
            ledger_main_id=main_id,
            sort_order=next_sort_order,
            authorization_date=payload.authorization_date,
            handler=payload.handler,
            remarks=payload.remarks,
        )
        created = await self.ledger_repo.create_update_entry(update_entry)
        await self.session.commit()
        return self._to_ledger_update_read(created)

    async def update_ledger_main(
        self,
        main_id: UUID,
        payload: AuthorizationLedgerMainUpdate,
    ) -> AuthorizationLedgerMainRead:
        main_entry = await self.ledger_repo.get_main_by_id(main_id)
        if not main_entry:
            raise NotFoundException("授权主记录", str(main_id))

        updated = await self.ledger_repo.update_main_entry(
            main_entry,
            payload.model_dump(exclude_unset=True),
        )
        await self.session.commit()
        return self._to_ledger_main_read(updated)

    async def update_ledger_update(
        self,
        update_id: UUID,
        payload: AuthorizationLedgerUpdateUpdate,
    ) -> AuthorizationLedgerUpdateRead:
        update_entry = await self.ledger_repo.get_update_by_id(update_id)
        if not update_entry:
            raise NotFoundException("授权更新记录", str(update_id))

        updated = await self.ledger_repo.update_update_entry(
            update_entry,
            payload.model_dump(exclude_unset=True),
        )
        await self.session.commit()
        return self._to_ledger_update_read(updated)

    async def delete_ledger_main(self, main_id: UUID) -> None:
        main_entry = await self.ledger_repo.get_main_by_id(main_id)
        if not main_entry:
            raise NotFoundException("授权主记录", str(main_id))
        await self.ledger_repo.soft_delete_main_entry(main_entry)
        await self.session.commit()

    async def delete_ledger_update(self, update_id: UUID) -> None:
        update_entry = await self.ledger_repo.get_update_by_id(update_id)
        if not update_entry:
            raise NotFoundException("授权更新记录", str(update_id))

        active_update_count = await self.ledger_repo.count_active_updates(
            update_entry.ledger_main_id
        )
        if active_update_count <= 1:
            raise AppException(message="主记录仅剩最后一条更新，请直接删除主记录")

        await self.ledger_repo.soft_delete_update_entry(update_entry)
        await self.session.commit()

    async def list_ledger_entries(
        self,
        *,
        product_name: str | None = None,
        market_name: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[AuthorizationLedgerRecord], AuthorizationLedgerOverview]:
        await self.ensure_ledger_seeded()
        entries = await self.ledger_repo.list_entries(
            product_name=product_name,
            market_name=market_name,
            status=status,
            keyword=keyword,
        )
        records = [self._to_ledger_record(entry) for entry in entries]
        overview = AuthorizationLedgerOverview(
            total_entries=len(records),
            total_products=len(
                {record.product_name for record in records if record.product_name}
            ),
            total_markets=len(
                {record.market_name for record in records if record.market_name}
            ),
            submitted_entries=sum(1 for record in records if record.status == "已递交"),
            pending_entries=sum(1 for record in records if record.status == "未递交"),
        )
        return records, overview

    async def create_ledger_entry(
        self,
        payload: AuthorizationLedgerEntryCreate,
    ) -> AuthorizationLedgerRecord:
        entry = AuthorizationLedgerEntry(
            product_name=payload.product_name,
            market_name=payload.market_name,
            source_sequence=payload.source_sequence,
            authorization_file_name=payload.authorization_file_name,
            quality_standard=payload.quality_standard,
            company_name=payload.company_name,
            country=payload.country,
            customer_code=payload.customer_code,
            purpose=payload.purpose,
            authorization_date=payload.authorization_date,
            handler=payload.handler,
            status=payload.status or "待确认",
            remarks=payload.remarks,
        )
        created = await self.ledger_repo.create_entry(entry)
        await self.session.commit()
        return self._to_ledger_record(created)

    async def update_ledger_entry(
        self,
        entry_id: UUID,
        payload: AuthorizationLedgerEntryUpdate,
    ) -> AuthorizationLedgerRecord:
        entry = await self.ledger_repo.get_by_id(entry_id)
        if not entry:
            raise NotFoundException("授权台账记录", str(entry_id))

        update_data = payload.model_dump(exclude_unset=True)
        updated = await self.ledger_repo.update_entry(entry, update_data)
        await self.session.commit()
        return self._to_ledger_record(updated)

    async def delete_ledger_entry(self, entry_id: UUID) -> None:
        entry = await self.ledger_repo.get_by_id(entry_id)
        if not entry:
            raise NotFoundException("授权台账记录", str(entry_id))
        await self.ledger_repo.soft_delete(entry)
        await self.session.commit()

    async def export_fda_entries(
        self,
        *,
        product_name: str | None = None,
        keyword: str | None = None,
    ) -> AuthorizationExportArtifact:
        records = await self.list_fda_entries(
            product_name=product_name, keyword=keyword
        )
        if not records:
            raise AppException(message="当前筛选结果为空，无法导出")

        matched_products = sorted(
            {
                (record.product_name or "").strip()
                for record in records
                if (record.product_name or "").strip()
            }
        )
        if len(matched_products) != 1:
            raise AppException(message="请先筛选到单一产品后再导出 FDA 授权")

        return await asyncio.to_thread(
            render_fda_export, product_name=matched_products[0], records=records
        )

    async def export_ledger_entries(
        self,
        *,
        product_name: str | None = None,
        market_name: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
    ) -> AuthorizationExportArtifact:
        records, _ = await self.list_grouped_ledger_mains(
            product_name=product_name,
            market_name=market_name,
            status=status,
            keyword=keyword,
        )
        if not records:
            raise AppException(message="当前筛选结果为空，无法导出")

        matched_products = sorted(
            {
                (record.product_name or "").strip()
                for record in records
                if (record.product_name or "").strip()
            }
        )
        matched_markets = sorted(
            {
                (record.market_name or "").strip()
                for record in records
                if (record.market_name or "").strip()
            }
        )
        if len(matched_products) != 1 or len(matched_markets) != 1:
            raise AppException(message="请先筛选到单一产品和单一市场后再导出市场授权")

        return await asyncio.to_thread(
            render_market_export,
            product_name=matched_products[0],
            market_name=matched_markets[0],
            records=records,
        )

    @staticmethod
    def get_registration_number(product_name: str) -> str | None:
        """根据品种名称获取登记号"""
        return REGISTRATION_NUMBERS.get(product_name)

    @staticmethod
    async def get_material_summary() -> AuthorizationMaterialSummary:
        """获取授权书资料汇总。"""
        _, summary = await asyncio.to_thread(_scan_authorization_materials)
        return summary

    @staticmethod
    async def list_materials(
        *,
        product_name: str | None = None,
        category: str | None = None,
        is_fda: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AuthorizationMaterialListItem], int, AuthorizationMaterialSummary]:
        """按目录扫描授权书资料并返回分页结果。"""
        materials, summary = await asyncio.to_thread(_scan_authorization_materials)

        filtered = materials
        if product_name:
            keyword = product_name.strip().lower()
            filtered = [
                item for item in filtered if keyword in item.product_name.lower()
            ]
        if category:
            filtered = [item for item in filtered if item.category == category]
        if is_fda is not None:
            filtered = [item for item in filtered if item.is_fda is is_fda]

        total = len(filtered)
        start = max(page - 1, 0) * page_size
        end = start + page_size
        return filtered[start:end], total, summary

    @staticmethod
    def get_material_file_path(file_key: str) -> Path:
        """根据相对路径获取授权书资料文件路径。"""
        source_root = _get_authorization_source_dir().resolve()
        candidate = (source_root / file_key).resolve()
        if source_root not in candidate.parents and candidate != source_root:
            raise NotFoundException("授权书文件")
        if not candidate.exists() or not candidate.is_file():
            raise NotFoundException("授权书文件")
        return candidate

    async def generate_letter(
        self,
        data: AuthorizationLetterCreate,
        template_data: bytes,
        template_file_name: str,
        template_placeholders: dict[str, str] | None = None,
    ) -> AuthorizationLetterResponse:
        """
        生成授权书。

        Args:
            data: 生成请求数据
            template_data: 模板文件二进制内容
            template_file_name: 模板文件名
            template_placeholders: 模板中的占位符映射 {占位符文本：替换文本}
                                   如果不传，则自动根据表单数据生成替换规则
        """
        replacements: list[tuple[str, str]] = []

        if template_placeholders:
            for placeholder, value in template_placeholders.items():
                replacements.append((placeholder, value))

        output_data = generate_authorization_letter_bytes(template_data, replacements)

        file_id = uuid.uuid4().hex[:12]
        output_file_name = f"授权书-{data.product_name}-{data.preparation_unit}.doc"
        upload_dir = _get_upload_dir()
        output_path = upload_dir / f"{file_id}.doc"
        output_path.write_bytes(output_data)

        template_path = upload_dir / f"{file_id}_template.doc"
        template_path.write_bytes(template_data)

        letter = AuthorizationLetter(
            api_company=API_COMPANY,
            product_name=data.product_name,
            registration_number=data.registration_number,
            preparation_unit=data.preparation_unit,
            preparation_name=data.preparation_name,
            administration_route=data.administration_route,
            template_file_key=f"{file_id}_template.doc",
            template_file_name=template_file_name,
            output_file_key=f"{file_id}.doc",
            output_file_name=output_file_name,
            remarks=data.remarks,
        )
        created = await self.repo.create(letter)
        return self._to_response(created)

    async def get_letter(self, letter_id: UUID) -> AuthorizationLetterResponse:
        """获取单条授权书记录"""
        letter = await self.repo.get_by_id(letter_id)
        if not letter:
            raise NotFoundException("授权书记录", str(letter_id))
        return self._to_response(letter)

    async def get_letter_model(self, letter_id: UUID) -> AuthorizationLetter:
        """获取单条授权书记录的 ORM 模型（用于文件下载等需要原始字段的场景）"""
        letter = await self.repo.get_by_id(letter_id)
        if not letter:
            raise NotFoundException("授权书记录", str(letter_id))
        return letter

    async def list_letters(
        self,
        *,
        product_name: str | None = None,
        preparation_unit: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AuthorizationLetterListItem], int]:
        """查询授权书列表"""
        letters, total = await self.repo.list_letters(
            product_name=product_name,
            preparation_unit=preparation_unit,
            page=page,
            page_size=page_size,
        )
        return [self._to_list_item(letter) for letter in letters], total

    async def delete_letter(self, letter_id: UUID) -> None:
        """删除授权书记录（软删除）"""
        letter = await self.repo.get_by_id(letter_id)
        if not letter:
            raise NotFoundException("授权书记录", str(letter_id))
        await self.repo.soft_delete(letter)

    def get_output_file_path(self, letter: AuthorizationLetter) -> Path:
        """获取生成文件路径"""
        return _get_upload_dir() / letter.output_file_key


def _get_reply_upload_dir() -> Path:
    """Return the private storage directory for supplementary replies."""

    settings = get_settings()
    base = Path(getattr(settings, "UPLOAD_DIR", "uploads"))
    upload_dir = base / "supplementary_replies"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


class SupplementaryReplyService:
    """Legacy supplementary-reply workflow kept behind current auth/routes."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SupplementaryReplyRepository(session)

    def _to_response(self, obj: SupplementaryReply) -> SupplementaryReplyResponse:
        return SupplementaryReplyResponse.model_validate(obj)

    def _to_list_item(self, obj: SupplementaryReply) -> SupplementaryReplyListItem:
        return SupplementaryReplyListItem.model_validate(obj)

    async def generate_reply(
        self,
        notice_data: bytes,
        notice_file_name: str,
        template_data: bytes | None = None,
        template_file_name: str | None = None,
        drug_name_override: str | None = None,
        registration_number_override: str | None = None,
        acceptance_number_override: str | None = None,
        company_name_override: str | None = None,
        remarks: str | None = None,
    ) -> SupplementaryReplyResponse:
        from app.modules.registration.reply_generator import (
            generate_reply_document,
            parse_cde_notice,
        )

        parsed = parse_cde_notice(notice_data)
        metadata = parsed["metadata"]
        questions = parsed["questions"]
        drug_info = {
            "drug_name": drug_name_override or metadata.get("drug_name", "未知药品"),
            "registration_number": registration_number_override
            or metadata.get("registration_number", ""),
            "acceptance_number": acceptance_number_override
            or metadata.get("acceptance_number", ""),
            "company_name": company_name_override
            or metadata.get("company_name", API_COMPANY),
            "doc_type": "补充资料",
            "application_type": "首次登记",
            "contact": "",
            "phone": "",
            "address": "",
            "zipcode": "",
            "related_no": "/",
            "email": "",
        }
        output_data = generate_reply_document(drug_info, questions)

        file_id = uuid.uuid4().hex
        output_file_name = f"发补回复-{drug_info['drug_name']}.docx"
        upload_dir = _get_reply_upload_dir()
        paths = [upload_dir / f"{file_id}_notice.pdf", upload_dir / f"{file_id}.docx"]
        if template_data:
            paths.insert(1, upload_dir / f"{file_id}_template.docx")
        try:
            paths[0].write_bytes(notice_data)
            template_key = None
            if template_data:
                paths[1].write_bytes(template_data)
                template_key = f"{file_id}_template.docx"
            paths[-1].write_bytes(output_data)
            reply = SupplementaryReply(
                drug_name=drug_info["drug_name"],
                registration_number=drug_info["registration_number"],
                acceptance_number=drug_info["acceptance_number"],
                company_name=drug_info["company_name"],
                notice_file_key=f"{file_id}_notice.pdf",
                notice_file_name=notice_file_name,
                template_file_key=template_key,
                template_file_name=template_file_name,
                output_file_key=f"{file_id}.docx",
                output_file_name=output_file_name,
                question_count=len(questions),
                remarks=remarks,
            )
            created = await self.repo.create(reply)
            return self._to_response(created)
        except Exception:
            for path in paths:
                path.unlink(missing_ok=True)
            raise

    async def get_reply(self, reply_id: UUID) -> SupplementaryReplyResponse:
        reply = await self.repo.get_by_id(reply_id)
        if not reply:
            raise NotFoundException("发补回复记录", str(reply_id))
        return self._to_response(reply)

    async def list_replies(
        self,
        *,
        drug_name: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SupplementaryReplyListItem], int]:
        replies, total = await self.repo.list_replies(
            drug_name=drug_name, page=page, page_size=page_size
        )
        return [self._to_list_item(reply) for reply in replies], total

    async def delete_reply(self, reply_id: UUID) -> None:
        reply = await self.repo.get_by_id(reply_id)
        if not reply:
            raise NotFoundException("发补回复记录", str(reply_id))
        await self.repo.soft_delete(reply)

    def get_output_file_path(self, reply: SupplementaryReply) -> Path:
        return _get_reply_upload_dir() / reply.output_file_key
