"""Equipment service layer: re-export all public functions."""

from app.modules.equipment.service.ai import analyze_inspection_photo
from app.modules.equipment.service.ai.service import (
    get_inspection_items_for_session,
    parse_manual_submission,
)
from app.modules.equipment.service.calibration import (
    create_calibration_plan,
    create_calibration_record,
    delete_calibration_plan,
    get_calibration_plan_by_id,
    get_calibration_plans,
    get_calibration_record_by_id,
    get_calibration_records,
    get_overdue_calibration_plans,
    update_calibration_plan,
)
from app.modules.equipment.service.cost import (
    apply_labor_cost,
    create_labor_rate,
    delete_labor_rate,
    get_cost_report,
    list_labor_rates,
    resolve_hourly_rate,
    update_external_cost,
    update_labor_rate,
)
from app.modules.equipment.service.equipment import (
    create_equipment,
    create_equipment_category,
    create_location,
    delete_equipment,
    delete_equipment_category,
    delete_location,
    generate_equipment_no,
    get_departments_for_select,
    get_equipment_by_id,
    get_equipment_categories,
    get_equipment_category_by_id,
    get_equipment_category_tree,
    get_equipment_statistics,
    get_equipments,
    get_location_by_id,
    get_location_tree,
    get_locations,
    update_equipment,
    update_equipment_category,
    update_location,
)
from app.modules.equipment.service.failure_code import (
    FailureCodeModel,
    create_failure_code,
    delete_failure_code,
    get_failure_code_by_id,
    get_failure_codes,
    update_failure_code,
)
from app.modules.equipment.service.health import (
    collect_metrics,
    compute_health_score,
    generate_daily_snapshots,
    get_health_board,
    get_health_trend,
    get_latest_health,
    get_repair_profile,
    refresh_repair_profile,
    schedule_profile_refresh,
)
from app.modules.equipment.service.inspection import (
    close_task as close_inspection_task,
)
from app.modules.equipment.service.inspection import (
    complete_task as complete_inspection_task,
)
from app.modules.equipment.service.inspection import (
    delete_photo as delete_inspection_photo,
)
from app.modules.equipment.service.inspection import (
    get_task_by_id as get_inspection_task_by_id,
)
from app.modules.equipment.service.inspection import (
    get_task_photos,
    skip_equipment_check,
    submit_equipment_check,
)
from app.modules.equipment.service.inspection import (
    get_tasks as get_inspection_tasks,
)
from app.modules.equipment.service.inspection import (
    start_task as start_inspection_task,
)
from app.modules.equipment.service.inspection import (
    upload_photo as upload_inspection_photo,
)
from app.modules.equipment.service.inspection_template import (
    add_template_item,
    complete_inspection,
    create_inspection_template,
    delete_inspection_template,
    delete_template_item,
    get_inspection_template_by_id,
    get_inspection_templates,
    update_inspection_template,
    update_template_item,
)
from app.modules.equipment.service.knowledge import (
    create_case_draft,
    dismiss_case,
    extract_key_steps,
    list_cases,
    mark_case_used,
    schedule_draft_processing,
    search_similar_cases,
    verify_case,
)
from app.modules.equipment.service.maintenance_config import (
    get_claim_timeout_config,
    update_claim_timeout_config,
)
from app.modules.equipment.service.maintenance_plan import (
    create_maintenance_plan,
    delete_maintenance_plan,
    generate_due_work_orders,
    get_maintenance_plan_by_id,
    get_maintenance_plans,
    get_overdue_maintenance_plans,
    update_maintenance_plan,
)
from app.modules.equipment.service.monthly_report import (
    aggregate_monthly_metrics,
    generate_monthly_report,
    get_monthly_report,
    list_monthly_reports,
    previous_month,
)
from app.modules.equipment.service.personnel import (
    add_personnel,
    assign_roles,
    create_role,
    delete_personnel,
    delete_role,
    get_candidates,
    get_personnel,
    get_personnel_by_id,
    get_role,
    get_role_by_code,
    list_personnel,
    list_roles,
    refresh_feishu,
    update_categories,
    update_personnel,
    update_role,
)
from app.modules.equipment.service.purchase_suggestion import (
    calc_suggest_qty,
    cancel_suggestion,
    list_suggestions,
    register_arrival,
    scan_and_suggest,
    submit_to_procurement,
    update_suggest_qty,
)
from app.modules.equipment.service.spare_part import (
    adjust_stock,
    create_spare_part,
    delete_spare_part,
    get_spare_part_by_id,
    get_spare_parts,
    get_stock_by_spare_part_id,
    get_stock_warnings,
    inbound_stock,
    outbound_stock,
    update_spare_part,
)
from app.modules.equipment.service.work_order import (
    assign_work_order,
    claim_work_order,
    close_work_order,
    complete_work_order,
    consume_materials,
    create_work_order,
    delete_work_order,
    generate_work_order_no,
    get_work_order_by_id,
    get_work_order_events,
    get_work_order_statistics,
    get_work_orders,
    start_work_order,
    transfer_work_order,
    update_work_order,
    verify_work_order,
)
from app.modules.equipment.service.work_order_efficiency import (
    get_efficiency_statistics,
)
from app.modules.equipment.service.work_order_image import (
    delete_image as delete_work_order_image,
)
from app.modules.equipment.service.work_order_image import (
    get_images as get_work_order_images,
)
from app.modules.equipment.service.work_order_image import (
    upload_images,
)

__all__ = [
    # ai
    "analyze_inspection_photo",
    "parse_manual_submission",
    "get_inspection_items_for_session",
    # 方案E：转派与事件
    "get_work_order_events",
    "transfer_work_order",
    # purchase suggestion & cost（方案C）
    "apply_labor_cost",
    "calc_suggest_qty",
    "cancel_suggestion",
    "create_labor_rate",
    "delete_labor_rate",
    "get_cost_report",
    "list_labor_rates",
    "list_suggestions",
    "register_arrival",
    "resolve_hourly_rate",
    "scan_and_suggest",
    "submit_to_procurement",
    "update_external_cost",
    "update_labor_rate",
    "update_suggest_qty",
    # health & knowledge & monthly report（方案B）
    "collect_metrics",
    "compute_health_score",
    "create_case_draft",
    "dismiss_case",
    "extract_key_steps",
    "generate_daily_snapshots",
    "generate_monthly_report",
    "aggregate_monthly_metrics",
    "get_health_board",
    "get_health_trend",
    "get_latest_health",
    "get_monthly_report",
    "get_repair_profile",
    "list_cases",
    "list_monthly_reports",
    "mark_case_used",
    "previous_month",
    "refresh_repair_profile",
    "schedule_draft_processing",
    "schedule_profile_refresh",
    "search_similar_cases",
    "verify_case",
    # calibration
    "create_calibration_plan",
    "create_calibration_record",
    "delete_calibration_plan",
    "get_calibration_plan_by_id",
    "get_calibration_plans",
    "get_calibration_record_by_id",
    "get_calibration_records",
    "get_overdue_calibration_plans",
    "update_calibration_plan",
    # equipment
    "create_equipment",
    "create_equipment_category",
    "create_location",
    "delete_equipment",
    "delete_equipment_category",
    "delete_location",
    "generate_equipment_no",
    "get_departments_for_select",
    "get_equipment_by_id",
    "get_equipment_categories",
    "get_equipment_category_by_id",
    "get_equipment_category_tree",
    "get_equipment_statistics",
    "get_equipments",
    "get_location_by_id",
    "get_location_tree",
    "get_locations",
    "update_equipment",
    "update_equipment_category",
    "update_location",
    # inspection
    "close_inspection_task",
    "complete_inspection_task",
    "get_task_photos",
    "skip_equipment_check",
    "submit_equipment_check",
    "create_inspection_task",
    "delete_inspection_photo",
    "get_inspection_task_by_id",
    "get_inspection_tasks",
    "start_inspection_task",
    "upload_inspection_photo",
    # failure code
    "FailureCodeModel",
    "add_template_item",
    "complete_inspection",
    "create_failure_code",
    "create_inspection_template",
    "delete_failure_code",
    "delete_inspection_template",
    "delete_template_item",
    "get_failure_code_by_id",
    "get_failure_codes",
    "get_inspection_template_by_id",
    "get_inspection_templates",
    "update_failure_code",
    "update_inspection_template",
    "update_template_item",
    # maintenance plan
    "create_maintenance_plan",
    "delete_maintenance_plan",
    "generate_due_work_orders",
    "get_maintenance_plan_by_id",
    "get_maintenance_plans",
    "get_overdue_maintenance_plans",
    "update_maintenance_plan",
    # spare part
    "adjust_stock",
    "create_spare_part",
    "delete_spare_part",
    "get_spare_part_by_id",
    "get_spare_parts",
    "get_stock_by_spare_part_id",
    "get_stock_warnings",
    "inbound_stock",
    "outbound_stock",
    "update_spare_part",
    # work order
    "assign_work_order",
    "claim_work_order",
    "close_work_order",
    "delete_work_order",
    "complete_work_order",
    "consume_materials",
    "create_work_order",
    "generate_work_order_no",
    "get_work_order_by_id",
    "get_efficiency_statistics",
    "get_work_order_statistics",
    "get_work_orders",
    "start_work_order",
    "update_work_order",
    "verify_work_order",
    # maintenance config
    "get_claim_timeout_config",
    "update_claim_timeout_config",
    # work order image
    "upload_images",
    "get_work_order_images",
    "delete_work_order_image",
    # personnel
    "add_personnel",
    "assign_roles",
    "create_role",
    "delete_personnel",
    "delete_role",
    "get_candidates",
    "get_personnel",
    "get_personnel_by_id",
    "get_role",
    "get_role_by_code",
    "list_personnel",
    "list_roles",
    "refresh_feishu",
    "update_categories",
    "update_personnel",
    "update_role",
]
