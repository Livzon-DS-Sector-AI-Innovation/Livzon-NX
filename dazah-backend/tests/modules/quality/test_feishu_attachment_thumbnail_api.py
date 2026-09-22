"""缩略图端点与 QC验证 preview 端点的 AsyncClient 集成测试。

覆盖：thumbnail 成功/inline 响应头、非图片 400、QC验证 preview inline、
缩略图生成单元测试（PIL 缩放尺寸约束、非图片返回 None）。
"""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient
from PIL import Image

from app.modules.quality.service.feishu_attachment_thumbnail import build_thumbnail

# ─── 缩略图生成单元测试 ───────────────────────────────────────────


def test_build_thumbnail_resizes_large_png() -> None:
    img = Image.new("RGB", (1200, 800), (200, 30, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    thumb = build_thumbnail(buf.getvalue(), "photo.png", 200, 200)
    assert thumb is not None
    with Image.open(io.BytesIO(thumb)) as out:
        assert out.format == "JPEG"
        assert out.width <= 200
        assert out.height <= 200


def test_build_thumbnail_rgba_gets_white_background() -> None:
    img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    thumb = build_thumbnail(buf.getvalue(), "alpha.png", 200, 200)
    assert thumb is not None
    with Image.open(io.BytesIO(thumb)) as out:
        assert out.mode == "RGB"


def test_build_thumbnail_rejects_non_image() -> None:
    assert build_thumbnail(b"%PDF-1.4", "report.pdf", 200, 200) is None
    assert build_thumbnail(b"hello", "notes.docx", 200, 200) is None


def test_build_thumbnail_keeps_small_image_unchanged() -> None:
    img = Image.new("RGB", (64, 64), (10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    thumb = build_thumbnail(buf.getvalue(), "small.jpg", 200, 200)
    assert thumb is not None
    with Image.open(io.BytesIO(thumb)) as out:
        assert out.width == 64
        assert out.height == 64


# ─── 缩略图端点（inspection 通用路由）─────────────────────────────


@pytest.mark.anyio
async def test_thumbnail_returns_inline_jpeg(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.api.inspection_feishu_crud as crud_api

    async def _fake_thumbnail(db, entity_code, record_id, file_token, *args, **kwargs):
        assert entity_code == "qc_items_inventory"
        assert record_id == "rec_1"
        assert file_token == "ft"
        return b"\xff\xd8\xff\xe0fakejpeg", "image/jpeg", "photo.jpg"

    monkeypatch.setattr(crud_api, "get_attachment_thumbnail", _fake_thumbnail)
    resp = await client.get(
        "/api/v1/quality/inspection/feishu/qc_items_inventory/records/rec_1/attachments/ft/thumbnail"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/jpeg")
    assert resp.headers["content-disposition"].startswith("inline")
    assert resp.headers["cache-control"] == "private, max-age=86400"


@pytest.mark.anyio
async def test_thumbnail_non_image_returns_400(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.api.inspection_feishu_crud as crud_api

    async def _fake_thumbnail(db, entity_code, record_id, file_token, *args, **kwargs):
        return None

    monkeypatch.setattr(crud_api, "get_attachment_thumbnail", _fake_thumbnail)
    resp = await client.get(
        "/api/v1/quality/inspection/feishu/qc_items_inventory/records/rec_1/attachments/ft/thumbnail"
    )
    assert resp.status_code == 400
    assert "不支持生成缩略图" in resp.json().get("message", "")


@pytest.mark.anyio
async def test_thumbnail_unknown_entity_returns_400(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/quality/inspection/feishu/not_real/records/rec_1/attachments/ft/thumbnail"
    )
    assert resp.status_code == 400


# ─── QC验证 preview / thumbnail 端点 ──────────────────────────────


@pytest.mark.anyio
async def test_qc_validation_preview_inline_pdf(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.api.validation_qc as qc_api

    async def _fake_preview(db, entity_code, record_id, file_token):
        assert entity_code == "validation_qc_2026"
        return b"%PDF-1.4 qc", "application/pdf", "验证报告.pdf"

    monkeypatch.setattr(
        qc_api, "get_inspection_feishu_attachment_preview", _fake_preview
    )
    resp = await client.get(
        "/api/v1/quality/validation-qc/records/rec_1/attachments/ft/preview?year=2026"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.headers["content-disposition"].startswith("inline")


@pytest.mark.anyio
async def test_qc_validation_thumbnail_inline_jpeg(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.api.validation_qc as qc_api

    async def _fake_thumbnail(db, entity_code, record_id, file_token, *args, **kwargs):
        assert entity_code == "validation_qc_2026"
        return b"\xff\xd8\xff\xe0qcthumb", "image/jpeg", "封面.jpg"

    monkeypatch.setattr(qc_api, "get_attachment_thumbnail", _fake_thumbnail)
    resp = await client.get(
        "/api/v1/quality/validation-qc/records/rec_1/attachments/ft/thumbnail?year=2026"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/jpeg")
    assert resp.headers["content-disposition"].startswith("inline")


# ─── 成品异常 thumbnail 端点 ──────────────────────────────────────


@pytest.mark.anyio
async def test_anomaly_thumbnail_inline_jpeg(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.api.finished_product_anomaly as anomaly_api

    async def _fake_thumbnail(db, entity_code, record_id, file_token, *args, **kwargs):
        assert entity_code == "finished_product_anomaly_2025"
        return b"\xff\xd8\xff\xe0athumb", "image/jpeg", "异常照片.jpg"

    monkeypatch.setattr(anomaly_api, "get_attachment_thumbnail", _fake_thumbnail)
    resp = await client.get(
        "/api/v1/quality/finished-product-anomaly/records/rec_1/attachments/ft/thumbnail?year=2025"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/jpeg")
    assert resp.headers["content-disposition"].startswith("inline")


# ─── 偏差报告记录附件端点 ──────────────────────────────────────


@pytest.mark.anyio
async def test_deviation_report_attachment_content_download(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.api.quality_deviation as deviation_api

    async def _fake_content(db, entity_code, record_id, file_token):
        assert entity_code == "deviation_report_record"
        assert record_id == "rec_1"
        assert file_token == "ft"
        return (
            b"document",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "报告.docx",
        )

    monkeypatch.setattr(
        deviation_api, "get_inspection_feishu_attachment_content", _fake_content
    )
    resp = await client.get(
        "/api/v1/quality/deviation-report-records/rec_1/attachments/ft/content"
    )
    assert resp.status_code == 200
    assert resp.headers["content-disposition"].startswith("attachment")


@pytest.mark.anyio
async def test_deviation_report_attachment_preview_inline_pdf(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.api.quality_deviation as deviation_api

    async def _fake_preview(db, entity_code, record_id, file_token):
        assert entity_code == "deviation_report_record"
        return b"%PDF-1.4 report", "application/pdf", "报告.pdf"

    monkeypatch.setattr(
        deviation_api, "get_inspection_feishu_attachment_preview", _fake_preview
    )
    resp = await client.get(
        "/api/v1/quality/deviation-report-records/rec_1/attachments/ft/preview"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.headers["content-disposition"].startswith("inline")


@pytest.mark.anyio
async def test_deviation_report_attachment_thumbnail_inline_jpeg(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.modules.quality.api.quality_deviation as deviation_api

    async def _fake_thumbnail(db, entity_code, record_id, file_token, *args, **kwargs):
        assert entity_code == "deviation_report_record"
        return b"\xff\xd8\xff\xe0thumb", "image/jpeg", "照片.jpg"

    monkeypatch.setattr(deviation_api, "get_attachment_thumbnail", _fake_thumbnail)
    resp = await client.get(
        "/api/v1/quality/deviation-report-records/rec_1/attachments/ft/thumbnail"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/jpeg")
    assert resp.headers["content-disposition"].startswith("inline")
