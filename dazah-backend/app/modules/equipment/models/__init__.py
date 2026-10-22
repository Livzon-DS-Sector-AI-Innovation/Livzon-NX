"""Equipment ORM models."""

from app.modules.equipment.models.calibration import (
    CalibrationPlan,
    CalibrationRecord,
)
from app.modules.equipment.models.equipment import (
    Equipment,
    EquipmentCategory,
    EquipmentCategoryLink,
    Location,
)
from app.modules.equipment.models.equipment_ledger_archive import (
    EquipmentLedgerArchive,
)
from app.modules.equipment.models.failure_code import (
    FailureAction,
    FailureCause,
    FailureSymptom,
)
from app.modules.equipment.models.feishu_app import EquipmentFeishuApp
from app.modules.equipment.models.inspection import (
    InspectionPhoto,
    InspectionTask,
)
from app.modules.equipment.models.inspection_feishu_config import (
    EquipmentInspectionFeishuConfig,
)
from app.modules.equipment.models.inspection_feishu_mirror import (
    EquipmentInspectionFeishuDevice,
    EquipmentInspectionFeishuRecord,
    EquipmentInspectionFeishuSyncState,
)
from app.modules.equipment.models.inspection_template import (
    InspectionRecord,
    InspectionTemplate,
    InspectionTemplateItem,
)
from app.modules.equipment.models.maintenance_config import MaintenanceConfig
from app.modules.equipment.models.maintenance_plan import MaintenancePlan
from app.modules.equipment.models.personnel import (
    EquipmentPersonnel,
    EquipmentPersonnelCategory,
    EquipmentPersonnelRole,
    EquipmentRole,
)
from app.modules.equipment.models.spare_part import (
    EquipmentSparePart,
    SparePart,
    SparePartStock,
    SparePartTransaction,
)
from app.modules.equipment.models.work_order import WorkOrder
from app.modules.equipment.models.work_order_image import WorkOrderImage

__all__ = [
    "CalibrationPlan",
    "CalibrationRecord",
    "Equipment",
    "EquipmentCategory",
    "EquipmentCategoryLink",
    "EquipmentLedgerArchive",
    "EquipmentPersonnel",
    "EquipmentPersonnelCategory",
    "EquipmentPersonnelRole",
    "EquipmentRole",
    "EquipmentInspectionFeishuConfig",
    "EquipmentInspectionFeishuDevice",
    "EquipmentInspectionFeishuRecord",
    "EquipmentInspectionFeishuSyncState",
    "EquipmentFeishuApp",
    "FailureAction",
    "FailureCause",
    "FailureSymptom",
    "InspectionPhoto",
    "InspectionRecord",
    "InspectionTask",
    "InspectionTemplate",
    "InspectionTemplateItem",
    "Location",
    "MaintenancePlan",
    "EquipmentSparePart",
    "SparePart",
    "SparePartStock",
    "SparePartTransaction",
    "MaintenanceConfig",
    "WorkOrder",
    "WorkOrderImage",
]
