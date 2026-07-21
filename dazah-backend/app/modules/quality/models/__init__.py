"""Quality module ORM models."""

from app.modules.quality.models.ai_analysis_log import QualityAiAnalysisLog
from app.modules.quality.models.attachment_review import AttachmentReview
from app.modules.quality.models.capa import CAPA
from app.modules.quality.models.capa_plan_track import CapaPlanTrack
from app.modules.quality.models.change_action_plan import ChangeActionPlan
from app.modules.quality.models.change_control import ChangeControl
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
from app.modules.quality.models.deviations import Deviation
from app.modules.quality.models.feishu_settings import (
    QualityFeishuAppSettings,
    QualityFeishuEntitySetting,
)
from app.modules.quality.models.feishu_read_mirror import (
    QualityFeishuReadField,
    QualityFeishuReadPageBinding,
    QualityFeishuReadRecord,
    QualityFeishuReadResource,
    QualityFeishuReadSourceRoot,
    QualityFeishuReadSyncRun,
)
from app.modules.quality.models.inspection import (
    FinishedProductInspection,
    InspectionRecord,
    LabInstrument,
    LabItem,
    LiquidMaterialInspection,
    SolidMaterialInspection,
)
from app.modules.quality.models.external_quality import (
    ComplaintRecord,
    ProductQualityRecord,
    ProductQualityStandardItem,
    ReturnRecallRecord,
    Supplier,
    SupplierQualification,
)
from app.modules.quality.models.oos_oot import (
    OosOotRecord,
    OotLimitItem,
    OotLimitProduct,
)
from app.modules.quality.models.validation_execution_record import (
    CleaningValidationRecord,
    EquipmentQualificationRecord,
    OtherValidationRecord,
    ProcessValidationRecord,
)
from app.modules.quality.models.validation_record import ValidationRecord

__all__ = [
    "CpvProduct",
    "CpvParameter",
    "CpvBatch",
    "CpvValue",
    "CpvImportTask",
    "Deviation",
    "CAPA",
    "QualityAiAnalysisLog",
    "DeviationAiSession",
    "DeviationAiSessionAttachment",
    "ChangeControl",
    "ChangeActionPlan",
    "DeviationInvestigationPushRecord",
    "CapaPlanTrack",
    "ValidationRecord",
    "EquipmentQualificationRecord",
    "ProcessValidationRecord",
    "CleaningValidationRecord",
    "OtherValidationRecord",
    "DepartmentContact",
    "DepartmentWeeklyConfirmation",
    "AttachmentReview",
    "QualityFeishuAppSettings",
    "QualityFeishuEntitySetting",
    "QualityFeishuReadSourceRoot",
    "QualityFeishuReadResource",
    "QualityFeishuReadField",
    "QualityFeishuReadRecord",
    "QualityFeishuReadPageBinding",
    "QualityFeishuReadSyncRun",
    "LabItem",
    "LabInstrument",
    "InspectionRecord",
    "FinishedProductInspection",
    "SolidMaterialInspection",
    "LiquidMaterialInspection",
    "OosOotRecord",
    "OotLimitProduct",
    "OotLimitItem",
    "Supplier",
    "SupplierQualification",
    "ComplaintRecord",
    "ReturnRecallRecord",
    "ProductQualityRecord",
    "ProductQualityStandardItem",
]
