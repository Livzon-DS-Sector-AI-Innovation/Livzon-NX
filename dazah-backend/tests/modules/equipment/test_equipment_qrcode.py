"""设备报修二维码批量出码测试：码内容、PDF 渲染与 API 契约。"""

from unittest.mock import AsyncMock

import pytest

from app.modules.equipment.service.equipment_qrcode import (
    QrcodeItem,
    build_repair_text,
    render_qrcode_pdf,
)


def _items(count: int = 2) -> list[QrcodeItem]:
    return [
        QrcodeItem(
            workshop_name="201一车间",
            equipment_name=f"离心泵{i}",
            equipment_no=f"LB-{i:03d}",
        )
        for i in range(1, count + 1)
    ]


def test_build_repair_text_contains_full_identity():
    text = build_repair_text("201一车间", "离心泵A", "LB-001")
    assert text == "报修 201一车间 离心泵A LB-001"


def test_qrcode_item_repair_text_property():
    assert _items(1)[0].repair_text == "报修 201一车间 离心泵1 LB-001"


def test_render_qrcode_pdf_outputs_valid_pdf():
    pdf = render_qrcode_pdf(_items(3))
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 10_000


def test_render_qrcode_pdf_empty_items_rejected():
    with pytest.raises(ValueError):
        render_qrcode_pdf([])


@pytest.mark.asyncio
async def test_qrcode_pdf_api_success(client, monkeypatch):
    from app.modules.equipment.api import equipment as equipment_api

    captured: dict[str, str] = {}

    async def _fake_generate(db, workshop_code):
        captured["workshop"] = workshop_code
        return b"%PDF-1.4 fake-bytes", "201一车间"

    monkeypatch.setattr(
        equipment_api.equipment_qrcode,
        "generate_workshop_qrcode_pdf",
        _fake_generate,
    )
    resp = await client.get(
        "/api/v1/equipment/equipments/qrcode-pdf?workshop=201-1"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content == b"%PDF-1.4 fake-bytes"
    assert captured["workshop"] == "201-1"


@pytest.mark.asyncio
async def test_qrcode_pdf_api_unknown_workshop_404(client, monkeypatch):
    from app.modules.equipment.api import equipment as equipment_api

    async def _raise(db, workshop_code):
        raise LookupError(workshop_code)

    monkeypatch.setattr(
        equipment_api.equipment_qrcode,
        "generate_workshop_qrcode_pdf",
        _raise,
    )
    resp = await client.get(
        "/api/v1/equipment/equipments/qrcode-pdf?workshop=404-x"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_qrcode_pdf_api_empty_workshop_404(client, monkeypatch):
    from app.modules.equipment.api import equipment as equipment_api

    async def _raise(db, workshop_code):
        raise ValueError("没有可出码的设备")

    monkeypatch.setattr(
        equipment_api.equipment_qrcode,
        "generate_workshop_qrcode_pdf",
        _raise,
    )
    resp = await client.get(
        "/api/v1/equipment/equipments/qrcode-pdf?workshop=201-1"
    )
    assert resp.status_code == 404
    assert "没有可出码的设备" in resp.text


@pytest.mark.asyncio
async def test_qrcode_pdf_api_requires_workshop(client, monkeypatch):
    # workshop 是必填参数，缺省应被 422 拒绝
    called = AsyncMock()
    from app.modules.equipment.api import equipment as equipment_api

    monkeypatch.setattr(
        equipment_api.equipment_qrcode,
        "generate_workshop_qrcode_pdf",
        called,
    )
    resp = await client.get("/api/v1/equipment/equipments/qrcode-pdf")
    assert resp.status_code == 422
    called.assert_not_awaited()
