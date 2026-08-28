from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.quality import mcp_tools


class _Row:
    def __init__(self, **values: object) -> None:
        self.id = values.pop("id", uuid4())
        self.__dict__.update(values)

    def __getattr__(self, _name: str) -> object:
        return None


class _ScalarResult:
    def __init__(self, rows: list[_Row]) -> None:
        self._rows = rows

    def scalars(self) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: self._rows)


@pytest.mark.asyncio
async def test_quality_mcp_query_tools_return_normalized_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deviation = _Row(
        deviation_code="PC-2608001",
        title="压差偏差",
        status="investigating",
        level="major",
        department="质量部",
        discovery_date=date(2026, 8, 20),
        handler="张三",
        root_cause_category="设备",
    )
    capa = _Row(
        capa_code="CAPA-001",
        title="改进措施",
        status="open",
        source="deviation",
        category="纠正",
        department="质量部",
        expected_completion_date=date(2026, 9, 1),
        qa_confirmer="李四",
    )
    oos = _Row(
        record_code="OOS-001",
        record_type="OOS",
        status="open",
        department="质量部",
        product_name="产品A",
        batch_number="B001",
        test_item="含量",
        specification="98-102",
        test_result="97",
        discovery_date=date(2026, 8, 20),
    )
    complaint = _Row(
        complaint_code="COM-001",
        status="pending",
        customer_name="客户A",
        product_name="产品A",
        batch_number="B001",
        complaint_date=date(2026, 8, 20),
        complaint_category="质量",
        handler="王五",
        response_date=date(2026, 8, 21),
    )
    recall = _Row(
        record_code="REC-001",
        record_type="return",
        status="open",
        product_name="产品A",
        batch_number="B001",
        quantity=2.5,
        unit="kg",
        customer_name="客户A",
        occurrence_date=date(2026, 8, 20),
        handler="赵六",
    )
    supplier = _Row(
        supplier_code="SUP-001",
        name="供应商A",
        status="active",
        category="原料",
        qualification_status="qualified",
        contact_person="供应商联系人",
        contact_phone="13800000000",
        scope_of_supply="原料",
        next_audit_date=date(2026, 12, 1),
    )
    inspection = _Row(
        inspection_no="INS-001",
        product_name="产品A",
        batch_no="B001",
        inspection_type="成品",
        inspection_item="含量",
        conclusion="合格",
        inspector="检验员",
        department="质量部",
        inspection_date=date(2026, 8, 20),
    )
    product_quality = _Row(
        record_code="PQR-001",
        title="年度回顾",
        product_name="产品A",
        batch_number="B001",
        review_type="年度回顾",
        status="completed",
        quality_trend="稳定",
        conclusion="通过",
        reviewer="审核员",
        review_date=date(2026, 8, 20),
    )
    change = _Row(
        change_code="CHG-001",
        change_object="设备",
        change_level="major",
        applicant_department="质量部",
        application_date=date(2026, 8, 20),
        execution_date=date(2026, 8, 21),
        closure_date=date(2026, 8, 22),
        impact_assessment="低风险",
    )

    db = SimpleNamespace(execute=AsyncMock())
    monkeypatch.setattr(mcp_tools, "get_db", lambda: db)

    db.execute.return_value = _ScalarResult([deviation])
    result = await mcp_tools.quality_query_deviations(
        "偏差", "investigating", "质量部", "major"
    )
    assert result[0]["deviation_code"] == deviation.deviation_code

    db.execute.return_value = _ScalarResult([capa])
    result = await mcp_tools.quality_query_capas("CAPA", "open", "deviation", "质量部")
    assert result[0]["capa_code"] == capa.capa_code

    db.execute.return_value = _ScalarResult([oos])
    result = await mcp_tools.quality_query_oos_oot("OOS", "OOS", "open", "质量部")
    assert result[0]["record_code"] == oos.record_code

    db.execute.return_value = _ScalarResult([complaint])
    result = await mcp_tools.quality_query_complaints("客户", "pending")
    assert result[0]["complaint_code"] == complaint.complaint_code

    db.execute.return_value = _ScalarResult([recall])
    result = await mcp_tools.quality_query_return_recalls("REC", "return", "open")
    assert result[0]["record_code"] == recall.record_code

    db.execute.return_value = _ScalarResult([supplier])
    result = await mcp_tools.quality_query_suppliers("供应商", "active", "原料")
    assert result[0]["supplier_code"] == supplier.supplier_code

    db.execute.return_value = _ScalarResult([inspection])
    result = await mcp_tools.quality_query_inspections("INS", "合格", "成品", "质量部")
    assert result[0]["inspection_no"] == inspection.inspection_no

    db.execute.return_value = _ScalarResult([product_quality])
    result = await mcp_tools.quality_query_product_quality(
        "PQR", "年度回顾", "completed"
    )
    assert result[0]["record_code"] == product_quality.record_code

    db.execute.return_value = _ScalarResult([change])
    result = await mcp_tools.quality_query_changes("CHG", "major", "质量部")
    assert result[0]["change_code"] == change.change_code
