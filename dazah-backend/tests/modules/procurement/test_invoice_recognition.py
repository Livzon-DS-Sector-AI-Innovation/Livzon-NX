import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.modules.procurement.service import (
    DuplicateInvoiceError,
    InvoiceRecognitionResult,
    _parse_invoice_text,
    batch_delete_invoice_recognition_records,
    delete_invoice_recognition_record,
    recognize_and_store_invoice_pdf,
)


def test_parse_invoice_text_from_layout_pdf_text() -> None:
    text = "\n".join(
        [
            "电子发票（增值税专用发票） 发票号码：26152000000556452706",
            "开票日期：2026年06月18日",
            (
                "购  名称：丽珠集团(宁夏)制药有限公司"
                "                            销  名称：内蒙古臻合生物科技有限公司"
            ),
            (
                "信  统一社会信用代码/纳税人识别号：91640221574877733M"
                "           信  统一社会信用代码/纳税人识别号：91150103MA0Q8T6YX5"
            ),
            (
                "项目名称 规格型号 单 位 数 量 单 价 金 额 "
                "税率/征收率 税 额"
            ),
            (
                "*食品添加剂*黄原胶       25kg/袋        kg          "
                "100012.5663716814159 12566.37   13%            1633.63"
            ),
            "合 计 ¥12566.37 ¥1633.63",
            "价税合计（大写） 壹万肆仟贰佰圆整 （小写）¥14200.00",
        ]
    )

    result = _parse_invoice_text(text)

    assert result.invoice_number == "26152000000556452706"
    assert result.invoice_date == "2026年06月18日"
    assert result.seller_name == "内蒙古臻合生物科技有限公司"
    assert result.total_tax_amount == Decimal("1633.63")
    assert result.total_amount_with_tax_small == Decimal("14200.00")
    assert result.line_items == []


def test_parse_invoice_text_uses_total_tax_amount_for_multi_page_invoice() -> None:
    text = "\n".join(
        [
            "电子发票（增值税专用发票） 发票号码：26642000000099001321",
            "开票日期：2026年03月09日",
            (
                "购  名称：丽珠集团（宁夏）制药有限公司"
                "                            销  名称：宁夏金海星宁商贸有限公司"
            ),
            (
                "项目名称 规格型号 单 位 数 量 单 价 金 额 "
                "税率/征收率 税 额"
            ),
            "*塑料制品*塑料三角瓶 250ml 个 30 4.8672566371681 146.02 13% 18.98",
            "小        计 ¥17399.99 ¥2262.01",
            "合        计 ¥70889.64 ¥9215.66",
            "价税合计（大写） 捌万零壹佰零伍圆叁角整 （小写） ¥80105.30",
        ]
    )

    result = _parse_invoice_text(text)

    assert result.invoice_number == "26642000000099001321"
    assert result.invoice_date == "2026年03月09日"
    assert result.seller_name == "宁夏金海星宁商贸有限公司"
    assert result.total_tax_amount == Decimal("9215.66")
    assert result.total_amount_with_tax_small == Decimal("80105.30")
    assert result.line_items == []


def test_parse_invoice_text_includes_line_items_when_requested() -> None:
    text = "\n".join(
        [
            "电子发票（增值税专用发票） 发票号码：26152000000556452706",
            "开票日期：2026年06月18日",
            (
                "购  名称：丽珠集团(宁夏)制药有限公司"
                "                            销  名称：内蒙古臻合生物科技有限公司"
            ),
            (
                "项目名称 规格型号 单 位 数 量 单 价 金 额 "
                "税率/征收率 税 额"
            ),
            (
                "*食品添加剂*黄原胶       25kg/袋        kg          "
                "100012.5663716814159 12566.37   13%            1633.63"
            ),
            "合 计 ¥12566.37 ¥1633.63",
            "价税合计（大写） 壹万肆仟贰佰圆整 （小写）¥14200.00",
        ]
    )

    result = _parse_invoice_text(text, include_details=True)

    assert len(result.line_items) == 1
    assert result.line_items[0].project_name == "*食品添加剂*黄原胶"
    assert result.line_items[0].unit == "kg"
    assert result.line_items[0].quantity == Decimal("1000")


def test_parse_invoice_text_infers_conjoined_detail_quantity() -> None:
    text = "\n".join(
        [
            "电子发票（增值税专用发票） 发票号码：26642000000099001321",
            "开票日期：2026年03月09日",
            (
                "购  名称：丽珠集团（宁夏）制药有限公司"
                "                            销  名称：宁夏金海星宁商贸有限公司"
            ),
            (
                "项目名称 规格型号 单 位 数 量 单 价 金 额 "
                "税率/征收率 税 额"
            ),
            (
                "*橡胶制品*丁腈手套            中号               包"
                "                  2115.0442477876106        230.09"
                "      13%                 29.91"
            ),
            "合        计 ¥70889.64 ¥9215.66",
            "价税合计（大写） 捌万零壹佰零伍圆叁角整 （小写） ¥80105.30",
        ]
    )

    result = _parse_invoice_text(text, include_details=True)

    assert len(result.line_items) == 1
    assert result.line_items[0].project_name == "*橡胶制品*丁腈手套"
    assert result.line_items[0].unit == "包"
    assert result.line_items[0].quantity == Decimal("2")


def test_parse_invoice_text_handles_reversed_seller_and_dense_amounts() -> None:
    text = "\n".join(
        [
            "电子发票（增值税专用发票） 发票号码：26642000000287037841",
            "开票日期：2026年06月22日",
            (
                "购      名称：丽珠集团（宁夏）制药有限公司"
                "                                   宁夏伊品贸易有限公司销"
                "                                           名称："
            ),
            (
                "项目名称 规格型号 单 位 数 量 单 价 金 额 "
                "税率/征收率 税 额"
            ),
            (
                "*淀粉制品*液体葡萄糖                  吨"
                "             345.021680.53095473579816.7913%"
                "            75376.19"
            ),
            "合 计 ¥579816.79 ¥75376.19",
            (
                "价税合计（大写） （小写）陆拾伍万伍仟壹佰玖拾贰圆玖角捌分"
                "                     ¥ 655192.98"
            ),
        ]
    )

    result = _parse_invoice_text(text, include_details=True)

    assert result.invoice_number == "26642000000287037841"
    assert result.invoice_date == "2026年06月22日"
    assert result.seller_name == "宁夏伊品贸易有限公司"
    assert result.total_tax_amount == Decimal("75376.19")
    assert result.total_amount_with_tax_small == Decimal("655192.98")
    assert len(result.line_items) == 1
    assert result.line_items[0].project_name == "*淀粉制品*液体葡萄糖"
    assert result.line_items[0].unit == "吨"
    assert result.line_items[0].quantity == Decimal("345.02")


@pytest.mark.asyncio
async def test_recognize_and_store_invoice_pdf_rejects_duplicate_invoice() -> None:
    db = AsyncMock()
    existing_record = SimpleNamespace(
        id=uuid.uuid4(),
        file_name="existing.pdf",
    )
    repo = AsyncMock()
    repo.find_duplicate.return_value = existing_record

    parsed_result = InvoiceRecognitionResult(
        invoice_number="26152000000556452706",
        invoice_date="2026年06月18日",
        seller_name="内蒙古臻合生物科技有限公司",
        total_amount_with_tax_small=Decimal("14200.00"),
        raw_text="raw",
    )

    with (
        patch(
            "app.modules.procurement.service.recognize_invoice_pdf",
            return_value=parsed_result,
        ),
        patch(
            "app.modules.procurement.service.InvoiceRecognitionRepository",
            return_value=repo,
        ),
    ):
        with pytest.raises(DuplicateInvoiceError):
            await recognize_and_store_invoice_pdf(
                db,
                b"%PDF-duplicate",
                file_name="duplicate.pdf",
            )

    repo.find_duplicate.assert_awaited_once()
    repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_recognize_invoice_api_rejects_oversized_pdf(
    client: AsyncClient,
) -> None:
    with patch("app.modules.procurement.api.MAX_INVOICE_PDF_UPLOAD_BYTES", 8):
        response = await client.post(
            "/api/v1/procurement/invoices/recognize",
            files={"file": ("invoice.pdf", b"0123456789", "application/pdf")},
    )

    assert response.status_code == 413
    assert "不能超过" in response.json()["message"]


@pytest.mark.asyncio
async def test_recognize_invoice_api_maps_duplicate_to_409(
    client: AsyncClient,
) -> None:
    existing_record = SimpleNamespace(
        id=uuid.uuid4(),
        file_name="existing.pdf",
    )

    async def _raise_duplicate(*args, **kwargs):
        raise DuplicateInvoiceError(existing_record)

    with patch(
        "app.modules.procurement.api.recognize_and_store_invoice_pdf",
        side_effect=_raise_duplicate,
    ):
        response = await client.post(
            "/api/v1/procurement/invoices/recognize",
            files={"file": ("invoice.pdf", b"%PDF-1.4", "application/pdf")},
        )

    assert response.status_code == 409
    assert "发票已识别过" in response.json()["message"]


@pytest.mark.asyncio
async def test_delete_invoice_recognition_record_delegates_to_repository() -> None:
    db = AsyncMock()
    record_id = uuid.uuid4()
    repo = AsyncMock()
    repo.delete_record.return_value = True

    with patch(
        "app.modules.procurement.service.InvoiceRecognitionRepository",
        return_value=repo,
    ):
        deleted = await delete_invoice_recognition_record(db, record_id)

    assert deleted is True
    repo.delete_record.assert_awaited_once_with(record_id)


@pytest.mark.asyncio
async def test_batch_delete_invoice_records_delegates_to_repository() -> None:
    db = AsyncMock()
    record_ids = [uuid.uuid4(), uuid.uuid4()]
    repo = AsyncMock()
    repo.batch_delete_records.return_value = 2

    with patch(
        "app.modules.procurement.service.InvoiceRecognitionRepository",
        return_value=repo,
    ):
        deleted_count = await batch_delete_invoice_recognition_records(db, record_ids)

    assert deleted_count == 2
    repo.batch_delete_records.assert_awaited_once_with(record_ids)
