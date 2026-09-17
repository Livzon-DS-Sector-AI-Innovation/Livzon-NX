"""校准证书 AI 识别 + QC 设备目录反查测试（mock llm_client 与 Bitable，不触网）。"""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

import app.modules.quality.api.inspection_feishu as instr_api
import app.modules.quality.service.instrument_certificate_analyze as service
from app.core.exceptions import AppException
from app.core.llm import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from app.main import app
from app.modules.quality.api import deps as quality_deps
from app.platform.identity.deps import get_current_user
from app.platform.identity.models import User

PNG_1PX: bytes = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

ANALYZE_URL = "/api/v1/quality/instruments/cal-external/certificate-analyze"
REMATCH_URL = "/api/v1/quality/instruments/cal-external/certificate-rematch"

_FULL_EXTRACTION = {
    "instrument_name": "电子天平",
    "model": "MS204S/01",
    "serial_no": "B303717218",
    "calibration_date": "2025-06-03",
    "next_calibration_date_stated": None,
    "certificate_no": "JC2025-0603-01",
    "calibration_agency": "区计量院",
    "conclusion": "合格",
}

_DIRECTORY_FIELDS = [
    {"field_name": "序号", "ui_type": "AutoNumber"},
    {"field_name": "器具名称", "ui_type": "Text"},
    {"field_name": "型号规格", "ui_type": "Text"},
    {"field_name": "器具编号", "ui_type": "Text"},
    {"field_name": "仪表编号", "ui_type": "Text"},
    {"field_name": "检定周期（月）", "ui_type": "Text"},
    {"field_name": "使用地点", "ui_type": "Text"},
]

_CAL_EXTERNAL_FIELDS = [
    {"field_name": "序号", "ui_type": "Text"},
    {"field_name": "器具名称", "ui_type": "Text"},
    {"field_name": "型号规格", "ui_type": "Text"},
    {"field_name": "器具编号", "ui_type": "Text"},
    {"field_name": "使用地点", "ui_type": "Text"},
    {"field_name": "检定日期", "ui_type": "DateTime"},
    {"field_name": "下次检定日期", "ui_type": "Formula"},
    {"field_name": "附件", "ui_type": "Attachment"},
]

_DIRECTORY_RECORD = {
    "record_id": "rec_dir_1",
    "fields": {
        "器具编号": [{"text": "B303717218", "type": "text"}],
        "器具名称": [{"text": "电子天平", "type": "text"}],
        "检定周期（月）": [{"text": "24", "type": "text"}],
        "使用地点": [{"text": "二楼天平室QC-2-2-042", "type": "text"}],
    },
}


class _Runtime:
    app_id = "cli_test"
    app_secret = "secret_test"


class _Entity:
    def __init__(self, app_token: str, table_id: str) -> None:
        self.app_token = app_token
        self.table_id = table_id


class _FakeBitable:
    """list_fields/search_records 按 app_token 区分目录表与外部校准表。"""

    def __init__(
        self,
        *,
        fields_by_token: dict[str, list[dict[str, Any]]],
        directory_records: list[dict[str, Any]],
    ) -> None:
        self.fields_by_token = fields_by_token
        self.directory_records = directory_records
        self.calls: list[dict[str, Any]] = []

    async def list_fields(self, table_id: str) -> list[dict[str, Any]]:
        return self.fields_by_token[table_id]

    async def search_records_page(
        self, table_id: str, *, field_names: list[str] | None = None, **_kwargs: Any
    ) -> dict[str, Any]:
        # 序号续号的全文分页扫描（外部校准表，每页给一个递增序号验证翻页取最大值）
        page_index = sum(
            1 for c in self.calls if c["table_id"] == "tbl_cal_external_page"
        )
        self.calls.append({"table_id": "tbl_cal_external_page", "filter_str": None})
        rows = [
            {"fields": {"序号": str(300 + page_index * 10 + offset)}}
            for offset in range(1, 4)
        ]
        return {
            "items": rows,
            "has_more": page_index < 1,
            "page_token": "next" if page_index < 1 else None,
            "total": 6,
        }

    async def search_records(
        self,
        table_id: str,
        *,
        filter_str: str | None = None,
        field_names: list[str] | None = None,
        page_size: int = 500,
        **_kwargs: Any,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "table_id": table_id,
                "filter_str": filter_str,
                "field_names": field_names,
                "page_size": page_size,
            }
        )
        if table_id != "tbl_directory":
            # 外部校准表：序号续号扫描调用
            return list(self.serial_rows)
        if filter_str:
            return list(self.directory_records)
        # 回退全量扫描路径
        target = "b303717218"
        return [
            record
            for record in self.directory_records
            if target in str(record.get("fields", {}).get("器具编号", "")).lower()
        ]


def _patch_runtime(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    async def _fake_resolve(db: Any, entity_code: str, *, direction: str) -> Any:
        calls.append((entity_code, direction))
        if entity_code == "qc_instr_device_directory":
            return _Runtime(), _Entity("app_directory", "tbl_directory")
        return _Runtime(), _Entity("app_cal_external", "tbl_cal_external")

    monkeypatch.setattr(service, "_resolve_runtime_entity", _fake_resolve)
    return calls


def _patch_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[_FakeBitable, AsyncMock]:
    _patch_runtime(monkeypatch)
    fake = _FakeBitable(
        fields_by_token={
            "tbl_directory": _DIRECTORY_FIELDS,
            "tbl_cal_external": _CAL_EXTERNAL_FIELDS,
        },
        directory_records=[_DIRECTORY_RECORD],
    )
    monkeypatch.setattr(service, "BitableClient", lambda **_kw: fake)
    vision = AsyncMock(return_value=dict(_FULL_EXTRACTION))
    monkeypatch.setattr(service.llm_client, "chat_vision_json", vision)
    upload_ref = {
        "file_token": "ft_cert",
        "name": "证书.pdf",
        "size": 1,
        "type": "application/pdf",
    }
    upload = AsyncMock(return_value=upload_ref)
    monkeypatch.setattr(service, "upload_inspection_feishu_attachment", upload)
    return fake, vision


@pytest.mark.asyncio
async def test_analyze_image_full_flow_maps_fields_and_computes_next_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake, vision = _patch_happy_path(monkeypatch)

    result = await service.analyze_calibration_certificate(
        None,  # type: ignore[arg-type]
        file_name="证书.png",
        content=PNG_1PX,
        content_type="image/png",
    )

    assert result["extracted"]["instrument_name"] == "电子天平"
    assert result["extracted"]["calibration_date"] == "2025-06-03"
    assert result["directory"] == {
        "matched": True,
        "match_by": "器具编号",
        "record_id": "rec_dir_1",
        "instrument_name": "电子天平",
        "location": "二楼天平室QC-2-2-042",
        "period_months": 24,
        "period_text": "24",
    }
    # 检定日期 2025-06-03 + 24 个月 - 1 天 = 2027-06-02（同飞书 EDATE 公式口径）
    assert result["computed_next_calibration_date"] == "2027-06-02"
    assert result["mapped_fields"] == {
        "器具名称": "电子天平",
        "型号规格": "MS204S/01",
        "器具编号": "B303717218",
        "检定日期": "2025-06-03",
        "使用地点": "二楼天平室QC-2-2-042",
        "附件": [{"file_token": "ft_cert"}],
        "序号": "314",
    }
    assert result["warnings"] == [
        "外部校准表的下次检定日期为公式列（固定按 12 个月），与设备目录"
        "周期 24 个月不一致；如需按实际周期计算，建议在表中增加周期列"
        "并把公式改为引用周期"
    ]
    # 下次检定日期为公式列，不写入 mapped_fields
    assert "下次检定日期" not in result["mapped_fields"]
    # 视觉调用收到 data URI；目录检索走编号公式过滤
    assert vision.await_args.args[1][0].startswith("data:image/png;base64,")
    directory_calls = [c for c in fake.calls if c["table_id"] == "tbl_directory"]
    assert directory_calls[0]["filter_str"] == 'CurrentValue.[器具编号] = "B303717218"'
    # 附件上传走外部校准表实体
    upload_call = service.upload_inspection_feishu_attachment.await_args
    assert upload_call.args[1] == "qc_instr_cal_external"


@pytest.mark.asyncio
async def test_analyze_pdf_with_text_layer_uses_text_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_happy_path(monkeypatch)
    monkeypatch.setattr(service, "_extract_pdf_text", lambda _content: "证书" * 200)
    text_llm = AsyncMock(return_value=dict(_FULL_EXTRACTION))
    monkeypatch.setattr(service.llm_client, "chat_json", text_llm)
    render_calls: list[bytes] = []

    def _fake_render_unused(content: bytes) -> list[str]:
        render_calls.append(content)
        return []

    monkeypatch.setattr(service, "_render_pdf_pages", _fake_render_unused)

    result = await service.analyze_calibration_certificate(
        None,  # type: ignore[arg-type]
        file_name="证书.pdf",
        content=b"%PDF-1.4 fake",
        content_type="application/pdf",
    )

    text_llm.assert_awaited_once()
    assert render_calls == []
    assert result["extracted"]["serial_no"] == "B303717218"


@pytest.mark.asyncio
async def test_analyze_scanned_pdf_renders_pages_for_vision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_happy_path(monkeypatch)
    monkeypatch.setattr(service, "_extract_pdf_text", lambda _content: "")
    render_calls: list[bytes] = []

    def _fake_render(content: bytes) -> list[str]:
        render_calls.append(content)
        return ["data:image/jpeg;base64,page1"]

    monkeypatch.setattr(service, "_render_pdf_pages", _fake_render)
    text_llm = AsyncMock()
    monkeypatch.setattr(service.llm_client, "chat_json", text_llm)

    result = await service.analyze_calibration_certificate(
        None,  # type: ignore[arg-type]
        file_name="扫描证书.pdf",
        content=b"%PDF-1.4 scanned",
        content_type="application/pdf",
    )

    assert render_calls == [b"%PDF-1.4 scanned"]
    text_llm.assert_not_awaited()
    assert result["extracted"]["serial_no"] == "B303717218"


@pytest.mark.asyncio
async def test_analyze_without_serial_skips_directory_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake, _vision = _patch_happy_path(monkeypatch)
    monkeypatch.setattr(
        service.llm_client,
        "chat_vision_json",
        AsyncMock(return_value={**_FULL_EXTRACTION, "serial_no": None}),
    )

    result = await service.analyze_calibration_certificate(
        None,  # type: ignore[arg-type]
        file_name="证书.png",
        content=PNG_1PX,
        content_type="image/png",
    )

    assert result["directory"]["matched"] is False
    assert not any(c["table_id"] == "tbl_directory" for c in fake.calls)
    assert any("未识别到出厂编号" in w for w in result["warnings"])
    assert "使用地点" not in result["mapped_fields"]


@pytest.mark.asyncio
async def test_analyze_directory_miss_falls_back_to_stated_next_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_runtime(monkeypatch)
    fake = _FakeBitable(
        fields_by_token={
            "tbl_directory": _DIRECTORY_FIELDS,
            "tbl_cal_external": _CAL_EXTERNAL_FIELDS,
        },
        directory_records=[],
    )
    monkeypatch.setattr(service, "BitableClient", lambda **_kw: fake)
    monkeypatch.setattr(
        service.llm_client,
        "chat_vision_json",
        AsyncMock(
            return_value={
                **_FULL_EXTRACTION,
                "next_calibration_date_stated": "2026-06-02",
            }
        ),
    )
    monkeypatch.setattr(
        service,
        "upload_inspection_feishu_attachment",
        AsyncMock(
            return_value={"file_token": "ft_cert", "name": "c", "size": 1, "type": ""}
        ),
    )

    result = await service.analyze_calibration_certificate(
        None,  # type: ignore[arg-type]
        file_name="证书.png",
        content=PNG_1PX,
        content_type="image/png",
    )

    assert result["directory"]["matched"] is False
    assert any("未找到出厂编号" in w for w in result["warnings"])
    # 无目录周期时回退证书载明的下次检定日期
    assert result["computed_next_calibration_date"] == "2026-06-02"


@pytest.mark.asyncio
async def test_analyze_directory_permission_error_adds_collaborator_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_runtime(monkeypatch)

    class _DeniedClient:
        """仅目录表拒绝访问（模拟应用未获 Base 协作者授权）。"""

        async def list_fields(self, table_id: str) -> list[dict[str, Any]]:
            if table_id == "tbl_directory":
                raise RuntimeError(
                    "Feishu API error code=1254302 msg=Permission denied"
                )
            return _CAL_EXTERNAL_FIELDS

        async def search_records_page(
            self, _table_id: str, **_kwargs: Any
        ) -> dict[str, Any]:
            return {
                "items": [{"fields": {"序号": "3333"}}],
                "has_more": False,
                "page_token": None,
                "total": 1,
            }

        async def search_records(self, *_args: Any, **_kwargs: Any) -> list[Any]:
            return []

    monkeypatch.setattr(service, "BitableClient", lambda **_kw: _DeniedClient())
    monkeypatch.setattr(
        service.llm_client,
        "chat_vision_json",
        AsyncMock(return_value=dict(_FULL_EXTRACTION)),
    )
    monkeypatch.setattr(
        service,
        "upload_inspection_feishu_attachment",
        AsyncMock(
            return_value={"file_token": "ft", "name": "c", "size": 1, "type": ""}
        ),
    )

    result = await service.analyze_calibration_certificate(
        None,  # type: ignore[arg-type]
        file_name="证书.png",
        content=PNG_1PX,
        content_type="image/png",
    )

    assert result["directory"]["matched"] is False
    assert any("协作者" in w for w in result["warnings"])


@pytest.mark.asyncio
async def test_analyze_directory_hits_location_containing_serial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """目录编号列都未命中时，使用地点包含仪器编号也应命中。"""
    _patch_runtime(monkeypatch)
    directory_record = {
        "record_id": "rec_loc_1",
        "fields": {
            "器具编号": [{"text": "XT009", "type": "text"}],
            "器具名称": [{"text": "移液器", "type": "text"}],
            "使用地点": [{"text": "滴定间2 QCPD-007", "type": "text"}],
            "检定周期（月）": [{"text": "12", "type": "text"}],
        },
    }

    class _Client:
        async def list_fields(self, table_id: str) -> list[dict[str, Any]]:
            return (
                _CAL_EXTERNAL_FIELDS
                if table_id == "tbl_cal_external"
                else _DIRECTORY_FIELDS
            )

        async def search_records_page(
            self, _table_id: str, **_kwargs: Any
        ) -> dict[str, Any]:
            return {
                "items": [{"fields": {"序号": "3333"}}],
                "has_more": False,
                "page_token": None,
                "total": 1,
            }

        async def search_records(
            self, _table_id: str, *, filter_str: str | None = None, **_kwargs: Any
        ) -> list[dict[str, Any]]:
            if filter_str:
                return []  # 编号列精确检索全部未命中
            return [directory_record]

    monkeypatch.setattr(service, "BitableClient", lambda **_kw: _Client())
    monkeypatch.setattr(
        service.llm_client,
        "chat_vision_json",
        AsyncMock(
            return_value={
                **_FULL_EXTRACTION,
                "instrument_name": "移液器",
                "serial_no": "H29465 (QCPD-007)",
            }
        ),
    )
    monkeypatch.setattr(
        service,
        "upload_inspection_feishu_attachment",
        AsyncMock(
            return_value={"file_token": "ft", "name": "c", "size": 1, "type": ""}
        ),
    )

    result = await service.analyze_calibration_certificate(
        None,  # type: ignore[arg-type]
        file_name="证书.png",
        content=PNG_1PX,
        content_type="image/png",
    )

    assert result["directory"]["matched"] is True
    assert result["directory"]["match_by"] == "使用地点"
    assert result["directory"]["location"] == "滴定间2 QCPD-007"
    assert result["mapped_fields"]["使用地点"] == "滴定间2 QCPD-007"


@pytest.mark.asyncio
async def test_analyze_formula_period_mismatch_warns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_happy_path(monkeypatch)

    result = await service.analyze_calibration_certificate(
        None,  # type: ignore[arg-type]
        file_name="证书.png",
        content=PNG_1PX,
        content_type="image/png",
    )

    # 目录周期 24 个月 ≠ 外部校准表公式固定的 12 个月 → 提示口径不一致
    assert any("公式列" in w and "24" in w for w in result["warnings"])


@pytest.mark.asyncio
async def test_analyze_stated_date_conflict_with_period_prefers_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_happy_path(monkeypatch)
    monkeypatch.setattr(
        service.llm_client,
        "chat_vision_json",
        AsyncMock(
            return_value={
                **_FULL_EXTRACTION,
                "next_calibration_date_stated": "2026-06-03",
            }
        ),
    )

    result = await service.analyze_calibration_certificate(
        None,  # type: ignore[arg-type]
        file_name="证书.png",
        content=PNG_1PX,
        content_type="image/png",
    )

    assert result["computed_next_calibration_date"] == "2027-06-02"
    assert any("不一致" in w for w in result["warnings"])


@pytest.mark.asyncio
async def test_analyze_stated_date_matching_period_does_not_warn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """证书载明日期与推算一致时不得误报不一致。"""
    _patch_happy_path(monkeypatch)
    monkeypatch.setattr(
        service.llm_client,
        "chat_vision_json",
        AsyncMock(
            return_value={
                **_FULL_EXTRACTION,
                "next_calibration_date_stated": "2027-06-02",
            }
        ),
    )

    result = await service.analyze_calibration_certificate(
        None,  # type: ignore[arg-type]
        file_name="证书.png",
        content=PNG_1PX,
        content_type="image/png",
    )

    assert result["computed_next_calibration_date"] == "2027-06-02"
    assert not any(w.startswith("证书载明") for w in result["warnings"])


@pytest.mark.asyncio
async def test_analyze_skips_missing_columns_and_unwritable_next_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_runtime(monkeypatch)
    fake = _FakeBitable(
        fields_by_token={
            "tbl_directory": _DIRECTORY_FIELDS,
            # 外部校准表缺 型号规格/附件 列，且下次检定日期为普通日期列
            "tbl_cal_external": [
                {"field_name": "器具名称", "ui_type": "Text"},
                {"field_name": "器具编号", "ui_type": "Text"},
                {"field_name": "检定日期", "ui_type": "DateTime"},
                {"field_name": "下次检定日期", "ui_type": "DateTime"},
            ],
        },
        directory_records=[_DIRECTORY_RECORD],
    )
    monkeypatch.setattr(service, "BitableClient", lambda **_kw: fake)
    monkeypatch.setattr(
        service.llm_client,
        "chat_vision_json",
        AsyncMock(return_value=dict(_FULL_EXTRACTION)),
    )
    upload = AsyncMock()
    monkeypatch.setattr(service, "upload_inspection_feishu_attachment", upload)

    result = await service.analyze_calibration_certificate(
        None,  # type: ignore[arg-type]
        file_name="证书.png",
        content=PNG_1PX,
        content_type="image/png",
    )

    assert "型号规格" not in result["mapped_fields"]
    assert "附件" not in result["mapped_fields"]
    upload.assert_not_awaited()
    # 普通日期列的下次检定日期直接写入推算值
    assert result["mapped_fields"]["下次检定日期"] == "2027-06-02"
    assert any("型号规格" in w for w in result["warnings"])


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (LLMConfigError("no config"), 503),
        (LLMRateLimitError("rate limited"), 429),
        (LLMOutputError("bad output"), 502),
        (LLMProviderError("provider down"), 502),
    ],
)
@pytest.mark.asyncio
async def test_analyze_llm_errors_map_to_business_errors(
    monkeypatch: pytest.MonkeyPatch, error: Exception, status_code: int
) -> None:
    _patch_happy_path(monkeypatch)
    vision = AsyncMock(side_effect=error)
    monkeypatch.setattr(service.llm_client, "chat_vision_json", vision)

    with pytest.raises(AppException) as exc_info:
        await service.analyze_calibration_certificate(
            None,  # type: ignore[arg-type]
            file_name="证书.png",
            content=PNG_1PX,
            content_type="image/png",
        )
    assert exc_info.value.status_code == status_code


@pytest.mark.asyncio
async def test_analyze_cleans_garbage_llm_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_happy_path(monkeypatch)
    monkeypatch.setattr(
        service.llm_client,
        "chat_vision_json",
        AsyncMock(
            return_value={
                "instrument_name": "null",
                "model": "  ",
                "serial_no": "B303717218",
                "calibration_date": "2025/06/03",  # 非 ISO 格式 → 丢弃
                "next_calibration_date_stated": "不知道",
                "certificate_no": "无",
                "calibration_agency": "区计量院",
                "conclusion": "合格",
            }
        ),
    )

    result = await service.analyze_calibration_certificate(
        None,  # type: ignore[arg-type]
        file_name="证书.png",
        content=PNG_1PX,
        content_type="image/png",
    )

    extracted = result["extracted"]
    assert extracted["instrument_name"] is None
    assert extracted["model"] is None
    assert extracted["calibration_date"] is None
    assert extracted["next_calibration_date_stated"] is None
    assert extracted["certificate_no"] is None
    assert extracted["serial_no"] == "B303717218"


@pytest.mark.parametrize(
    ("file_name", "content"),
    [
        ("证书.docx", b"not allowed"),
        ("证书.txt", b"x"),
        ("证书.png", b""),
    ],
)
@pytest.mark.asyncio
async def test_analyze_rejects_invalid_files(
    monkeypatch: pytest.MonkeyPatch, file_name: str, content: bytes
) -> None:
    with pytest.raises(AppException) as exc_info:
        await service.analyze_calibration_certificate(
            None,  # type: ignore[arg-type]
            file_name=file_name,
            content=content,
            content_type="",
        )
    assert exc_info.value.status_code == 400


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("24", 24),
        ("12个月", 12),
        ("6 月", 6),
        ("1年", 12),
        ("2年", 24),
        ("abc", None),
        ("0", None),
        ("999999", None),
        (None, None),
    ],
)
def test_parse_period_months(text: str | None, expected: int | None) -> None:
    assert service._parse_period_months(text) == expected


def test_add_months_clamps_end_of_month() -> None:
    from datetime import date

    assert service._add_months(date(2025, 1, 31), 1) == date(2025, 2, 28)
    assert service._add_months(date(2024, 11, 30), 3) == date(2025, 2, 28)
    assert service._add_months(date(2025, 6, 3), 24) == date(2027, 6, 3)


def test_serial_candidates_splits_parenthesized_parts() -> None:
    assert service._serial_candidates("H29465 (QCPD-007)") == [
        "H29465 (QCPD-007)",
        "H29465",
        "QCPD-007",
    ]
    # 中文括号同样拆分
    assert service._serial_candidates("A123（B456）") == [
        "A123（B456）",
        "A123",
        "B456",
    ]
    # 无括号时只有完整值
    assert service._serial_candidates("B303717218") == ["B303717218"]


@pytest.mark.asyncio
async def test_analyze_directory_hits_gauge_column_via_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """出厂编号「H29465 (QCPD-007)」应拆候选并命中目录「仪表编号」列。"""
    _patch_runtime(monkeypatch)

    directory_record = {
        "record_id": "rec_gauge_1",
        "fields": {
            "器具编号": [{"text": "JH29465", "type": "text"}],
            "仪表编号": "QCPD-007",
            "器具名称": [{"text": "移液器", "type": "text"}],
            "检定周期（月）": [{"text": "12", "type": "text"}],
            "使用地点": [{"text": "抗生素效价室滴定间2", "type": "text"}],
        },
    }

    class _FilterAwareClient:
        async def list_fields(self, table_id: str) -> list[dict[str, Any]]:
            if table_id == "tbl_cal_external":
                return _CAL_EXTERNAL_FIELDS
            return _DIRECTORY_FIELDS

        async def search_records_page(
            self, _table_id: str, **_kwargs: Any
        ) -> dict[str, Any]:
            return {
                "items": [{"fields": {"序号": "3333"}}],
                "has_more": False,
                "page_token": None,
                "total": 1,
            }

        async def search_records(
            self, _table_id: str, *, filter_str: str | None = None, **_kwargs: Any
        ) -> list[dict[str, Any]]:
            if not filter_str:
                return []
            # 只在 仪表编号=QCPD-007 时命中（模拟真实目录编号体系）
            if "仪表编号" in filter_str and "QCPD-007" in filter_str:
                return [directory_record]
            return []

    monkeypatch.setattr(service, "BitableClient", lambda **_kw: _FilterAwareClient())
    monkeypatch.setattr(
        service.llm_client,
        "chat_vision_json",
        AsyncMock(
            return_value={
                **_FULL_EXTRACTION,
                "serial_no": "H29465 (QCPD-007)",
            }
        ),
    )
    monkeypatch.setattr(
        service,
        "upload_inspection_feishu_attachment",
        AsyncMock(
            return_value={"file_token": "ft", "name": "c", "size": 1, "type": ""}
        ),
    )

    result = await service.analyze_calibration_certificate(
        None,  # type: ignore[arg-type]
        file_name="证书.png",
        content=PNG_1PX,
        content_type="image/png",
    )

    assert result["directory"]["matched"] is True
    assert result["directory"]["match_by"] == "仪表编号"
    assert result["directory"]["location"] == "抗生素效价室滴定间2"
    assert result["directory"]["period_months"] == 12
    assert result["mapped_fields"]["使用地点"] == "抗生素效价室滴定间2"
    assert result["warnings"] == []


@pytest.mark.asyncio
async def test_rematch_corrects_fields_and_reuses_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """人工修正出厂编号后重新匹配命中；附件复用 token 不重复上传。"""
    _patch_runtime(monkeypatch)

    directory_record = {
        "record_id": "rec_gauge_1",
        "fields": {
            "器具编号": [{"text": "JH29465", "type": "text"}],
            "仪表编号": "QCPD-007",
            "器具名称": [{"text": "移液器", "type": "text"}],
            "检定周期（月）": [{"text": "12", "type": "text"}],
            "使用地点": [{"text": "抗生素效价室滴定间2", "type": "text"}],
        },
    }

    class _FilterAwareClient:
        async def list_fields(self, table_id: str) -> list[dict[str, Any]]:
            if table_id == "tbl_cal_external":
                return _CAL_EXTERNAL_FIELDS
            return _DIRECTORY_FIELDS

        async def search_records_page(
            self, _table_id: str, **_kwargs: Any
        ) -> dict[str, Any]:
            return {
                "items": [{"fields": {"序号": "3333"}}],
                "has_more": False,
                "page_token": None,
                "total": 1,
            }

        async def search_records(
            self, _table_id: str, *, filter_str: str | None = None, **_kwargs: Any
        ) -> list[dict[str, Any]]:
            if not filter_str:
                return []
            if "仪表编号" in filter_str and "QCPD-007" in filter_str:
                return [directory_record]
            return []

    monkeypatch.setattr(service, "BitableClient", lambda **_kw: _FilterAwareClient())
    upload = AsyncMock()
    monkeypatch.setattr(service, "upload_inspection_feishu_attachment", upload)

    from app.modules.quality.schemas.instrument_certificate import (
        CertificateRematchRequest,
    )

    result = await service.rematch_certificate_fields(
        None,  # type: ignore[arg-type]
        request=CertificateRematchRequest(
            instrument_name="移液器",
            model="10μL~100μL",
            serial_no="H29465 (QCPD-007)",
            calibration_date="2026-08-13",
            attachment_file_token="ft_uploaded_earlier",
            attachment_name="20260917-131604.jpg",
        ),
    )

    assert result["extracted"]["serial_no"] == "H29465 (QCPD-007)"
    assert result["directory"]["match_by"] == "仪表编号"
    assert result["mapped_fields"]["使用地点"] == "抗生素效价室滴定间2"
    assert result["mapped_fields"]["附件"] == [{"file_token": "ft_uploaded_earlier"}]
    assert result["attachment_file_token"] == "ft_uploaded_earlier"
    upload.assert_not_awaited()


# ── 路由层（AsyncClient 真实调用） ───────────────────────────────────


@pytest.fixture
async def auth_client(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> AsyncClient:
    monkeypatch.setattr(
        quality_deps, "resolve_user_permissions", AsyncMock(return_value=["*"])
    )

    async def _override_current_user() -> User:
        return User(
            id=uuid4(),
            name="证书测试用户",
            username=f"cert-test-{uuid4().hex[:10]}",
            role="admin",
            status="active",
            auth_source="local",
            grant_version=0,
        )

    app.dependency_overrides[get_current_user] = _override_current_user
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_route_analyze_success(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    canned = {
        "extracted": dict(_FULL_EXTRACTION),
        "directory": {"matched": False},
        "computed_next_calibration_date": None,
        "mapped_fields": {"器具名称": "电子天平"},
        "warnings": [],
    }
    monkeypatch.setattr(
        instr_api, "analyze_calibration_certificate", AsyncMock(return_value=canned)
    )
    response = await auth_client.post(
        ANALYZE_URL,
        files={"file": ("证书.png", PNG_1PX, "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["extracted"]["instrument_name"] == "电子天平"
    assert body["data"]["mapped_fields"] == {"器具名称": "电子天平"}


@pytest.mark.asyncio
async def test_route_analyze_requires_login(client: AsyncClient) -> None:
    # 覆盖身份解析为 None，模拟未登录请求（绕过 DEV_BYPASS_AUTH）
    async def _no_user() -> None:
        return None

    app.dependency_overrides[get_current_user] = _no_user
    try:
        response = await client.post(
            ANALYZE_URL,
            files={"file": ("证书.png", PNG_1PX, "image/png")},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_route_analyze_rejects_disallowed_extension(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(instr_api, "analyze_calibration_certificate", AsyncMock())
    response = await auth_client.post(
        ANALYZE_URL,
        files={"file": ("说明.txt", b"text", "text/plain")},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_route_analyze_forbidden_without_permission(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        quality_deps, "resolve_user_permissions", AsyncMock(return_value=[])
    )

    async def _override_current_user() -> User:
        return User(
            id=uuid4(),
            name="普通用户",
            username=f"cert-deny-{uuid4().hex[:10]}",
            role="viewer",
            status="active",
            auth_source="local",
            grant_version=0,
        )

    app.dependency_overrides[get_current_user] = _override_current_user
    try:
        response = await client.post(
            ANALYZE_URL,
            files={"file": ("证书.png", PNG_1PX, "image/png")},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_route_rematch_success(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    canned = {
        "extracted": dict(_FULL_EXTRACTION),
        "directory": {"matched": True, "match_by": "仪表编号"},
        "computed_next_calibration_date": "2027-08-12",
        "mapped_fields": {"器具编号": "H29465 (QCPD-007)"},
        "warnings": [],
        "attachment_file_token": "ft_old",
    }
    rematch = AsyncMock(return_value=canned)
    monkeypatch.setattr(instr_api, "rematch_certificate_fields", rematch)
    response = await auth_client.post(
        REMATCH_URL,
        json={
            "instrument_name": "移液器",
            "serial_no": "H29465 (QCPD-007)",
            "calibration_date": "2026-08-13",
            "attachment_file_token": "ft_old",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["directory"]["matched"] is True
    assert body["data"]["attachment_file_token"] == "ft_old"
    rematch.assert_awaited_once()


@pytest.mark.asyncio
async def test_route_rematch_requires_login(client: AsyncClient) -> None:
    async def _no_user() -> None:
        return None

    app.dependency_overrides[get_current_user] = _no_user
    try:
        response = await client.post(REMATCH_URL, json={})
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 401
