"""Registration service."""

from app.modules.registration.service.authorization import (
    AuthorizationLetterService,
    SupplementaryReplyService,
)
from app.modules.registration.service.reference_standard import (
    ReferenceStandardService,
)
from app.modules.registration.service.drug import (
    create_drug,
    delete_drug,
    get_drug,
    get_drugs,
    update_drug,
)
from app.modules.registration.service.holiday import (
    create_holiday,
    delete_holiday,
    get_holidays,
    update_holiday,
)
from app.modules.registration.service.validation_audit import (
    ValidationAuditService,
)

__all__ = [
    "AuthorizationLetterService",
    "ReferenceStandardService",
    "SupplementaryReplyService",
    "ValidationAuditService",
    "create_drug",
    "create_holiday",
    "delete_drug",
    "delete_holiday",
    "get_drug",
    "get_drugs",
    "get_holidays",
    "update_drug",
    "update_holiday",
]
