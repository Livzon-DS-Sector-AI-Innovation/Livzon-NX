from uuid import uuid4

import pytest

from app.modules.production.feishu_service import ProductionFeishuService
from app.modules.production.models import (
    ProductionFeishuConfig,
    ProductionFeishuSyncBinding,
)
from app.modules.production.schemas import ProductionFeishuRecordPreview


def _binding(
    field_mapping: dict[str, str],
    *,
    sync_target: str = "sales_plan_detail",
    product_name: str | None = None,
    workshop_code: str | None = None,
) -> ProductionFeishuSyncBinding:
    return ProductionFeishuSyncBinding(
        config_id=uuid4(),
        binding_name="销售执行",
        sync_target=sync_target,
        table_id="tblSalesPlan",
        field_mapping=field_mapping,
        product_name=product_name,
        workshop_code=workshop_code,
    )


def test_maps_sales_plan_record_and_coerces_numbers() -> None:
    record = ProductionFeishuRecordPreview(
        record_id="rec001",
        fields={"产品": "洛伐他汀", "计划发货": "1,234.5", "单位": "kg"},
    )

    mapped = ProductionFeishuService._map_sales_plan_record(
        _binding(
            {
                "product_name": "产品",
                "month_planned_delivery": "计划发货",
                "unit": "单位",
                "unexpected": "忽略",
            }
        ),
        record,
    )

    assert mapped == {
        "product_name": "洛伐他汀",
        "month_planned_delivery": 1234.5,
        "unit": "kg",
    }


def test_rejects_record_without_product_name_mapping() -> None:
    record = ProductionFeishuRecordPreview(
        record_id="rec002", fields={"计划发货": "10"}
    )

    with pytest.raises(ValueError, match="product_name"):
        ProductionFeishuService._map_sales_plan_record(
            _binding({"month_planned_delivery": "计划发货"}), record
        )


def test_masks_config_identifiers_in_sync_error() -> None:
    config = ProductionFeishuConfig(
        app_id="cli_secret_app",
        encrypted_app_secret="encrypted-value",
        bitable_app_token="bascn_secret_token",
    )

    message = ProductionFeishuService._safe_sync_error(
        "cli_secret_app cannot access bascn_secret_token", config
    )

    assert "cli_secret_app" not in message
    assert "bascn_secret_token" not in message
    assert message == "*** cannot access ***"


def test_maps_production_execution_plan_with_binding_product() -> None:
    record = ProductionFeishuRecordPreview(
        record_id="rec-plan",
        fields={"车间": "203", "日期": "2026-07-15", "计划产量": "1,200"},
    )

    mapped = ProductionFeishuService._map_target_record(
        _binding(
            {
                "workshop": "车间",
                "plan_date": "日期",
                "planned_yield": "计划产量",
            },
            sync_target="production_plan",
            product_name="L-苯丙氨酸",
        ),
        record,
    )

    assert mapped["product_name"] == "L-苯丙氨酸"
    assert mapped["planned_yield"] == 1200
    assert mapped["source_record_id"] == "rec-plan"


def test_groups_seed_fields_by_business_section() -> None:
    record = ProductionFeishuRecordPreview(
        record_id="rec-seed",
        fields={
            "批次": "S-001",
            "葡萄糖批次": "G-01",
            "调整前PH": "6.8",
            "培养温度": "31",
        },
    )

    mapped = ProductionFeishuService._map_target_record(
        _binding(
            {
                "batch_no": "批次",
                "glucose_batch": "葡萄糖批次",
                "ph_before_adjust": "调整前PH",
                "culture_temperature": "培养温度",
            },
            sync_target="seed_culture",
            product_name="L-苯丙氨酸",
        ),
        record,
    )

    assert mapped["materials"] == {"glucose_batch": "G-01"}
    assert mapped["quality_data"] == {"ph_before_adjust": "6.8"}
    assert mapped["operation_data"] == {"culture_temperature": "31"}


def test_maps_ceramic_binding_to_fieldized_process_record() -> None:
    record = ProductionFeishuRecordPreview(
        record_id="rec-membrane",
        fields={"批次": "B-001", "压力": "0.35", "操作人": "张三"},
    )

    mapped = ProductionFeishuService._map_target_record(
        _binding(
            {
                "batch_no": "批次",
                "run_pressure": "压力",
                "operator": "操作人",
            },
            sync_target="ceramic_ops",
            workshop_code="203",
        ),
        record,
    )

    assert mapped["process_code"] == "ceramic"
    assert mapped["workshop_code"] == "203"
    assert mapped["data"] == {
        "run_pressure": 0.35,
        "operator": "张三",
        "substage": "operations",
    }
