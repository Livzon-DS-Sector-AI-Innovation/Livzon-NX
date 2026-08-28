from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.core.exceptions import AppException, NotFoundException
from app.modules.registration import schemas
from app.modules.registration.service import authorization


def _entry(product_name: str = "多拉菌素") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        product_name=product_name,
        source_sequence=1,
        company_name="客户公司",
        address="地址",
        reference_number="REF-1",
        loa_date="2026.01.01",
        submission_date="2026.01.02",
        referenced_sections="第1章",
        market_name="欧盟",
        authorization_file_name="LOA.docx",
        quality_standard="EP",
        country="爱尔兰",
        customer_code="KH-1",
        purpose="注册",
        authorization_date="2026.01.01",
        handler="张三",
        status="已递交",
        remarks="首次授权",
    )


def _service() -> authorization.AuthorizationLetterService:
    instance = authorization.AuthorizationLetterService.__new__(
        authorization.AuthorizationLetterService
    )
    instance.session = SimpleNamespace(commit=AsyncMock())
    instance.repo = SimpleNamespace()
    instance.fda_repo = SimpleNamespace()
    instance.ledger_repo = SimpleNamespace()
    return instance


@pytest.mark.asyncio
async def test_authorization_index_seed_filters_and_file_security(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fda_record = schemas.AuthorizationFdaRecord(sequence=1, company_name="FDA客户")
    ledger_record = schemas.AuthorizationLedgerRecord(
        product_name="多拉菌素",
        sequence="1",
        market_name="欧盟",
        authorization_file_name="LOA.docx",
        company_name="客户公司",
        status="已递交",
    )
    detail = schemas.AuthorizationProductDetail(
        product_name="多拉菌素",
        is_fda=True,
        material_count=2,
        market_count=1,
        record_count=1,
        fda_record_count=1,
        fda_records=[fda_record],
        ledger_records=[ledger_record],
    )
    overview = schemas.AuthorizationOverview(
        total_products=1,
        total_files=2,
        total_markets=1,
        total_records=1,
        fda_products=1,
        fda_records=1,
        ledger_records=1,
    )
    products = [schemas.ProductInfo(product_name="多拉菌素", is_fda=True)]
    monkeypatch.setattr(
        authorization,
        "_get_authorization_content_index",
        lambda: (overview, products, {"多拉菌素": detail}),
    )
    assert await authorization.AuthorizationLetterService.get_overview() == overview
    assert await authorization.AuthorizationLetterService.get_product_list() == products
    assert (
        await authorization.AuthorizationLetterService.get_product_detail("多拉菌素")
    ) == detail
    with pytest.raises(NotFoundException):
        await authorization.AuthorizationLetterService.get_product_detail("不存在")

    now = datetime.now(UTC)
    materials = [
        schemas.AuthorizationMaterialListItem(
            id="fda-1",
            product_name="多拉菌素",
            category="FDA",
            market_name=None,
            is_fda=True,
            file_name="fda.docx",
            file_ext=".docx",
            relative_path="多拉菌素/fda.docx",
            size_bytes=10,
            updated_at=now,
        ),
        schemas.AuthorizationMaterialListItem(
            id="market-1",
            product_name="多拉菌素",
            category="市场授权",
            market_name="欧盟",
            is_fda=False,
            file_name="market.docx",
            file_ext=".docx",
            relative_path="多拉菌素/market.docx",
            size_bytes=20,
            updated_at=now,
        ),
    ]
    summary = schemas.AuthorizationMaterialSummary(
        total_products=1, total_files=2, fda_products=1, fda_files=1
    )
    monkeypatch.setattr(
        authorization, "_scan_authorization_materials", lambda: (materials, summary)
    )
    (
        page,
        total,
        returned_summary,
    ) = await authorization.AuthorizationLetterService.list_materials(
        product_name="多拉",
        category="FDA",
        is_fda=True,
        page=1,
        page_size=1,
    )
    assert [item.id for item in page] == ["fda-1"]
    assert total == 1
    assert returned_summary == summary
    assert (
        await authorization.AuthorizationLetterService.get_material_summary() == summary
    )

    source = tmp_path / "authorization"
    source.mkdir()
    valid = source / "valid.docx"
    valid.write_bytes(b"document")
    monkeypatch.setattr(authorization, "_get_authorization_source_dir", lambda: source)
    assert (
        authorization.AuthorizationLetterService.get_material_file_path("valid.docx")
        == valid
    )
    with pytest.raises(NotFoundException):
        authorization.AuthorizationLetterService.get_material_file_path("../secret")
    with pytest.raises(NotFoundException):
        authorization.AuthorizationLetterService.get_material_file_path("missing.docx")


@pytest.mark.asyncio
async def test_authorization_fda_and_ledger_crud_and_seed_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = _service()
    detail = schemas.AuthorizationProductDetail(
        product_name="多拉菌素",
        fda_records=[schemas.AuthorizationFdaRecord(sequence=2, company_name="种子")],
        ledger_records=[
            schemas.AuthorizationLedgerRecord(
                product_name="多拉菌素",
                sequence="1",
                market_name="欧盟",
                authorization_file_name="LOA.docx",
                company_name="种子",
                status="已递交",
            )
        ],
    )
    monkeypatch.setattr(
        authorization,
        "_get_authorization_content_index",
        lambda: (None, [], {"多拉菌素": detail}),
    )
    fda = _entry()
    instance.fda_repo.count_entries = AsyncMock(return_value=0)
    instance.fda_repo.create_entries = AsyncMock()
    await instance.ensure_fda_seeded()
    instance.fda_repo.create_entries.assert_awaited_once()
    assert instance.session.commit.await_count == 1

    instance.fda_repo.count_entries = AsyncMock(return_value=1)
    instance.fda_repo.list_entries = AsyncMock(return_value=[fda])
    listed = await instance.list_fda_entries(product_name="多拉菌素", keyword="客户")
    assert listed[0].company_name == "客户公司"
    instance.fda_repo.create_entry = AsyncMock(return_value=fda)
    created = await instance.create_fda_entry(
        schemas.AuthorizationFdaEntryCreate(
            product_name="多拉菌素", company_name="客户公司"
        )
    )
    assert created.sequence == 1
    instance.fda_repo.get_by_id = AsyncMock(return_value=fda)
    instance.fda_repo.update_entry = AsyncMock(return_value=fda)
    updated = await instance.update_fda_entry(
        fda.id, schemas.AuthorizationFdaEntryUpdate(company_name="新客户")
    )
    assert updated.id == fda.id
    instance.fda_repo.soft_delete = AsyncMock()
    await instance.delete_fda_entry(fda.id)
    instance.fda_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await instance.delete_fda_entry(fda.id)

    ledger = _entry()
    ledger.source_sequence = "1"
    instance.ledger_repo.count_entries = AsyncMock(return_value=0)
    instance.ledger_repo.create_entries = AsyncMock()
    await instance.ensure_ledger_seeded()
    instance.ledger_repo.count_entries = AsyncMock(return_value=1)
    instance.ledger_repo.list_entries = AsyncMock(return_value=[ledger])
    records, overview = await instance.list_ledger_entries(
        product_name="多拉菌素", market_name="欧盟"
    )
    assert records[0].status == "已递交"
    assert overview.total_entries == 1
    instance.ledger_repo.create_entry = AsyncMock(return_value=ledger)
    assert (
        await instance.create_ledger_entry(
            schemas.AuthorizationLedgerEntryCreate(
                product_name="多拉菌素", authorization_file_name="LOA.docx"
            )
        )
    ).authorization_file_name == "LOA.docx"
    instance.ledger_repo.get_by_id = AsyncMock(return_value=ledger)
    instance.ledger_repo.update_entry = AsyncMock(return_value=ledger)
    assert (
        await instance.update_ledger_entry(
            ledger.id, schemas.AuthorizationLedgerEntryUpdate(status="未递交")
        )
    ).id == ledger.id
    instance.ledger_repo.soft_delete = AsyncMock()
    await instance.delete_ledger_entry(ledger.id)


@pytest.mark.asyncio
async def test_authorization_grouped_ledger_crud_and_delete_guard() -> None:
    instance = _service()
    main_id = uuid4()
    update_id = uuid4()
    main = SimpleNamespace(id=main_id)
    update = SimpleNamespace(id=update_id, ledger_main_id=main_id, sort_order=1)
    instance._to_ledger_main_read = Mock(return_value=main)
    instance._to_ledger_update_read = Mock(return_value=update)
    instance.ledger_repo.create_main_entry = AsyncMock(return_value=main)
    instance.ledger_repo.create_update_entry = AsyncMock(return_value=update)
    instance.ledger_repo.get_main_by_id = AsyncMock(side_effect=[main, main])
    created = await instance.create_ledger_main(
        schemas.AuthorizationLedgerMainCreate(
            product_name="多拉菌素",
            authorization_file_name="LOA.docx",
            initial_update=schemas.AuthorizationLedgerUpdateCreate(handler="张三"),
        )
    )
    assert created is main
    instance.ledger_repo.get_main_by_id = AsyncMock(return_value=main)
    instance.ledger_repo.get_next_update_sort_order = AsyncMock(return_value=2)
    assert (
        await instance.create_ledger_update(
            main_id, schemas.AuthorizationLedgerUpdateCreate(handler="李四")
        )
    ) is update
    instance.ledger_repo.update_main_entry = AsyncMock(return_value=main)
    instance.ledger_repo.update_update_entry = AsyncMock(return_value=update)
    assert (
        await instance.update_ledger_main(
            main_id, schemas.AuthorizationLedgerMainUpdate(status="已递交")
        )
    ) is main
    instance.ledger_repo.get_update_by_id = AsyncMock(return_value=update)
    assert (
        await instance.update_ledger_update(
            update_id, schemas.AuthorizationLedgerUpdateUpdate(handler="王五")
        )
    ) is update

    instance.ledger_repo.count_active_updates = AsyncMock(return_value=1)
    with pytest.raises(AppException):
        await instance.delete_ledger_update(update_id)
    instance.ledger_repo.count_active_updates.return_value = 2
    instance.ledger_repo.soft_delete_update_entry = AsyncMock()
    await instance.delete_ledger_update(update_id)
    instance.ledger_repo.soft_delete_main_entry = AsyncMock()
    await instance.delete_ledger_main(main_id)
    instance.ledger_repo.get_main_by_id.return_value = None
    with pytest.raises(NotFoundException):
        await instance.delete_ledger_main(main_id)

    grouped = SimpleNamespace(
        product_name="多拉菌素",
        market_name="欧盟",
        status="已递交",
        updates=[SimpleNamespace(sort_order=1), SimpleNamespace(sort_order=2)],
    )
    grouped_read = SimpleNamespace(
        product_name="多拉菌素",
        market_name="欧盟",
        status="已递交",
        updates=[SimpleNamespace(sort_order=1), SimpleNamespace(sort_order=2)],
    )
    instance.ledger_repo.list_main_entries = AsyncMock(return_value=[grouped])
    instance._to_ledger_main_read = Mock(return_value=grouped_read)
    records, grouped_overview = await instance.list_grouped_ledger_mains()
    assert records == [grouped_read]
    assert grouped_overview.total_update_records == 2


@pytest.mark.asyncio
async def test_authorization_letter_and_supplementary_reply_file_workflows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    instance = _service()
    letter_dir = tmp_path / "letters"
    letter_dir.mkdir()
    monkeypatch.setattr(authorization, "_get_upload_dir", lambda: letter_dir)
    monkeypatch.setattr(
        authorization,
        "generate_authorization_letter_bytes",
        lambda data, replacements: b"output",
    )
    letter = SimpleNamespace(
        id=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        output_file_key="out.doc",
    )
    instance.repo.create = AsyncMock(return_value=letter)
    instance._to_response = Mock(return_value=letter)
    data = schemas.AuthorizationLetterCreate(
        product_name="多拉菌素",
        registration_number="国药准字H1",
        preparation_unit="丽珠",
        preparation_name="张三",
        administration_route="口服",
    )
    created = await instance.generate_letter(
        data, b"template", "template.doc", {"{{name}}": "张三"}
    )
    assert created is letter
    assert (tmp_path / "letters").exists()
    assert (
        instance.get_output_file_path(SimpleNamespace(output_file_key="x.doc"))
        == tmp_path / "letters" / "x.doc"
    )

    instance.repo.get_by_id = AsyncMock(return_value=letter)
    assert await instance.get_letter(letter.id) is letter
    assert await instance.get_letter_model(letter.id) is letter
    instance.repo.list_letters = AsyncMock(return_value=([letter], 1))
    instance._to_list_item = Mock(return_value=letter)
    listed, total = await instance.list_letters(product_name="多拉菌素")
    assert listed == [letter]
    assert total == 1
    instance.repo.soft_delete = AsyncMock()
    await instance.delete_letter(letter.id)

    reply_module = __import__(
        "app.modules.registration.reply_generator",
        fromlist=["parse_cde_notice", "generate_reply_document"],
    )
    monkeypatch.setattr(
        reply_module,
        "parse_cde_notice",
        lambda _data: {
            "metadata": {"drug_name": "多拉菌素", "company_name": "丽珠"},
            "questions": [{"question": "补充资料"}],
        },
    )
    monkeypatch.setattr(
        reply_module, "generate_reply_document", lambda *_args: b"reply"
    )
    reply_service = authorization.SupplementaryReplyService.__new__(
        authorization.SupplementaryReplyService
    )
    reply_service.session = SimpleNamespace()
    reply = SimpleNamespace(
        id=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        output_file_key="reply.docx",
    )
    reply_service.repo = SimpleNamespace(create=AsyncMock(return_value=reply))
    reply_service._to_response = Mock(return_value=reply)
    reply_dir = tmp_path / "replies"
    reply_dir.mkdir()
    monkeypatch.setattr(authorization, "_get_reply_upload_dir", lambda: reply_dir)
    generated = await reply_service.generate_reply(
        b"notice", "notice.pdf", b"template", "template.docx"
    )
    assert generated is reply
    assert (tmp_path / "replies").exists()
    reply_service.repo.get_by_id = AsyncMock(return_value=reply)
    assert await reply_service.get_reply(reply.id) is reply
    reply_service.repo.list_replies = AsyncMock(return_value=([reply], 1))
    reply_service._to_list_item = Mock(return_value=reply)
    replies, total = await reply_service.list_replies(drug_name="多拉菌素")
    assert replies == [reply]
    assert total == 1
    reply_service.repo.soft_delete = AsyncMock()
    await reply_service.delete_reply(reply.id)
