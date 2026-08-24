from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace as _SimpleNamespace
from typing import Any, cast

import pytest

from app.modules.procurement import service as procurement_service
from app.modules.procurement.models import ContractRecord
from app.modules.procurement.schemas import (
    ContractCategory,
    ContractGenerateRequest,
    ContractItemInput,
    ContractPartyInfo,
)

SimpleNamespace: Any = _SimpleNamespace


class FakeDb:
    async def flush(self: Any) -> None:
        return None


class FakeContractRecordRepository:
    records: dict[uuid.UUID, ContractRecord] = {}

    def __init__(self: Any, session: Any) -> None:
        self.session = session

    @classmethod
    def reset(cls: Any) -> None:
        cls.records = {}

    async def create(self: Any, record: ContractRecord) -> ContractRecord:
        now = datetime.now(UTC)
        record.created_at = now
        record.updated_at = now
        self.records[record.id] = record
        return record

    async def get(self: Any, record_id: uuid.UUID) -> ContractRecord | None:
        return self.records.get(record_id)  # type: ignore[no-any-return]

    async def list_records(
        self: Any,
        *,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ContractRecord], int]:
        records = list(self.records.values())
        if keyword:
            records = [
                record
                for record in records
                if keyword in record.title
                or keyword in record.contract_number
                or keyword in record.seller_name
            ]
        total = len(records)
        return records[(page - 1) * page_size : page * page_size], total


@pytest.fixture(autouse=True)
def fake_contract_record_repository(monkeypatch: Any) -> Any:
    FakeContractRecordRepository.reset()
    monkeypatch.setattr(
        procurement_service,
        "ContractRecordRepository",
        FakeContractRecordRepository,
    )


def test_contract_record_loads_identity_user_table_for_audit_foreign_keys() -> Any:
    assert "identity.users" in ContractRecord.metadata.tables


def _payload() -> ContractGenerateRequest:
    return ContractGenerateRequest(
        title="测试耗材采购合同",
        category=ContractCategory.consumables,
        contract_number="QA-CONTRACT-001",
        contract_date=date(2026, 7, 6),
        seller=ContractPartyInfo(name="测试供应商有限公司"),
        items=[
            ContractItemInput(
                name="测试耗材",
                quantity=Decimal("2"),
                unit="个",
                unit_price=Decimal("10"),
            )
        ],
    )


def _record(
    *,
    title: str,
    contract_number: str,
    seller_name: str,
    file_path: str = "contracts/test.docx",
) -> ContractRecord:
    return ContractRecord(
        id=uuid.uuid4(),
        title=title,
        category=ContractCategory.consumables.value,
        contract_number=contract_number,
        contract_date=date(2026, 7, 6),
        seller_name=seller_name,
        filename="测试合同.docx",
        file_path=file_path,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        file_size=12,
        payload={"title": title},
    )


@pytest.mark.anyio
async def test_generate_and_store_contract_persists_record_and_local_file(
    tmp_path: Any,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(procurement_service, "minio_enabled", lambda: False)
    monkeypatch.setattr(
        procurement_service,
        "get_settings",
        lambda: SimpleNamespace(STORAGE_ROOT=str(tmp_path)),
    )
    monkeypatch.setattr(
        procurement_service,
        "generate_contract",
        lambda payload: (
            BytesIO(b"contract-bytes"),
            "耗材合同_QA-CONTRACT-001.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    )

    (
        buffer,
        filename,
        content_type,
        record,
    ) = await procurement_service.generate_and_store_contract(
        cast(Any, FakeDb)(),
        _payload(),
    )

    assert buffer.getvalue() == b"contract-bytes"
    assert filename == "耗材合同_QA-CONTRACT-001.docx"
    assert content_type == record.content_type
    assert record.title == "测试耗材采购合同"
    assert record.contract_number == "QA-CONTRACT-001"
    assert record.seller_name == "测试供应商有限公司"
    assert record.payload["title"] == "测试耗材采购合同"
    assert record.file_size == len(b"contract-bytes")
    assert (
        tmp_path / "procurement" / "contracts" / str(record.id) / filename
    ).read_bytes() == b"contract-bytes"


@pytest.mark.anyio
async def test_list_contract_records_searches_title_number_and_seller() -> None:
    repository: Any = FakeContractRecordRepository(cast(Any, FakeDb)())
    await repository.create(
        _record(
            title="原材料采购合同",
            contract_number="RAW-001",
            seller_name="甲供应商",
        )
    )
    await repository.create(
        _record(
            title="耗材采购合同",
            contract_number="CONS-001",
            seller_name="乙供应商",
        )
    )

    title_records, title_total = await procurement_service.list_contract_records(
        cast(Any, FakeDb)(),
        keyword="原材料",
    )
    seller_records, seller_total = await procurement_service.list_contract_records(
        cast(Any, FakeDb)(),
        keyword="乙供应商",
    )

    assert title_total == 1
    assert title_records[0].contract_number == "RAW-001"
    assert seller_total == 1
    assert seller_records[0].title == "耗材采购合同"


@pytest.mark.anyio
async def test_get_contract_record_file_reads_local_file(
    tmp_path: Any, monkeypatch: Any
) -> None:
    monkeypatch.setattr(procurement_service, "minio_enabled", lambda: False)
    file_path = tmp_path / "contract.docx"
    file_path.write_bytes(b"saved-contract")
    record = _record(
        title="可查看合同",
        contract_number="VIEW-001",
        seller_name="查看供应商",
        file_path=str(file_path),
    )
    await FakeContractRecordRepository(cast(Any, FakeDb)()).create(record)

    data, content_type, filename = await procurement_service.get_contract_record_file(
        cast(Any, FakeDb)(),
        record.id,
    )

    assert data == b"saved-contract"
    assert content_type == record.content_type
    assert filename == record.filename
