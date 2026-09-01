"""Quality module ORM models."""

from app.modules.quality.models.ai_analysis_log import QualityAiAnalysisLog
from app.modules.quality.models.attachment_review import AttachmentReview
from app.modules.quality.models.capa import CAPA
from app.modules.quality.models.capa_plan_track import CapaPlanTrack
from app.modules.quality.models.change_action_plan import ChangeActionPlan
from app.modules.quality.models.change_control import ChangeControl
from app.modules.quality.models.complaint import ComplaintRecord
from app.modules.quality.models.contacts import (
    DepartmentContact,
    DepartmentWeeklyConfirmation,
)
from app.modules.quality.models.cpv_batch import CpvBatch
from app.modules.quality.models.cpv_import_task import CpvImportTask
from app.modules.quality.models.cpv_parameter import CpvParameter
from app.modules.quality.models.cpv_product import CpvProduct
from app.modules.quality.models.cpv_value import CpvValue
from app.modules.quality.models.deviation_ai_session import (
    DeviationAiSession,
    DeviationAiSessionAttachment,
)
from app.modules.quality.models.deviation_investigation_push_record import (
    DeviationInvestigationPushRecord,
)
from app.modules.quality.models.deviation_workbench import (
    DeviationWorkbenchReport,
    DeviationWorkbenchSettings,
)
from app.modules.quality.models.deviations import Deviation
from app.modules.quality.models.document_catalog import (
    DocumentDepartment,
    DocumentEntry,
)
from app.modules.quality.models.external_quality import (
    ProductQualityStandardItem,
    SupplierQualification,
)
from app.modules.quality.models.feishu_read_mirror import (
    QualityFeishuReadField,
    QualityFeishuReadPageBinding,
    QualityFeishuReadRecord,
    QualityFeishuReadResource,
    QualityFeishuReadSourceRoot,
    QualityFeishuReadSyncRun,
)
from app.modules.quality.models.feishu_settings import (
    QualityFeishuAppSettings,
    QualityFeishuEntitySetting,
)
from app.modules.quality.models.finished_product_inspection import (
    FinishedProductInspection,
)
from app.modules.quality.models.finished_trend_alert_notification import (
    FinishedTrendAlertNotification,
)
from app.modules.quality.models.historical_deviation import HistoricalDeviation
from app.modules.quality.models.inspection import InspectionRecord
from app.modules.quality.models.lab_instrument import LabInstrument
from app.modules.quality.models.lab_item import LabItem
from app.modules.quality.models.liquid_material_inspection import (
    LiquidMaterialInspection,
)
from app.modules.quality.models.oos_oot import OosOotRecord
from app.modules.quality.models.oot_limit import OotLimitItem, OotLimitProduct
from app.modules.quality.models.product_quality import ProductQualityRecord
from app.modules.quality.models.return_recall import ReturnRecallRecord
from app.modules.quality.models.solid_material_inspection import SolidMaterialInspection
from app.modules.quality.models.supplier import Supplier
from app.modules.quality.models.validation_execution_record import (
    CleaningValidationRecord,
    EquipmentQualificationRecord,
    OtherValidationRecord,
    ProcessValidationRecord,
)
from app.modules.quality.models.validation_record import ValidationRecord

__all__ = [
    "Deviation",
    "HistoricalDeviation",
    "DeviationWorkbenchSettings",
    "DeviationWorkbenchReport",
    "CAPA",
    "CapaPlanTrack",
    "QualityAiAnalysisLog",
    "ChangeControl",
    "ChangeActionPlan",
    "ValidationRecord",
    "EquipmentQualificationRecord",
    "ProcessValidationRecord",
    "CleaningValidationRecord",
    "OtherValidationRecord",
    "DepartmentContact",
    "DepartmentWeeklyConfirmation",
    "AttachmentReview",
    "DeviationInvestigationPushRecord",
    "QualityFeishuAppSettings",
    "QualityFeishuEntitySetting",
    "DeviationAiSession",
    "DeviationAiSessionAttachment",
    "OotLimitProduct",
    "OotLimitItem",
    "FinishedTrendAlertNotification",
    "LiquidMaterialInspection",
    "SolidMaterialInspection",
    "FinishedProductInspection",
    "LabInstrument",
    "LabItem",
    "InspectionRecord",
    "ProductQualityRecord",
    "Supplier",
    "ReturnRecallRecord",
    "ComplaintRecord",
    "OosOotRecord",
    "DocumentDepartment",
    "DocumentEntry",
    "CpvProduct",
    "CpvParameter",
    "CpvBatch",
    "CpvValue",
    "CpvImportTask",
    "SupplierQualification",
    "ProductQualityStandardItem",
    "QualityFeishuReadSourceRoot",
    "QualityFeishuReadResource",
    "QualityFeishuReadField",
    "QualityFeishuReadRecord",
    "QualityFeishuReadPageBinding",
    "QualityFeishuReadSyncRun",
]
