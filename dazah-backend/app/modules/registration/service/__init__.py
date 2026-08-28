"""Registration service."""

from app.modules.registration.service.authorization import (
    AuthorizationLetterService,
    SupplementaryReplyService,
)
from app.modules.registration.service.certificate import CertificateWorkbookService
from app.modules.registration.service.fee import RegistrationFeeService
from app.modules.registration.service.knowledge import RegistrationKnowledgeService
from app.modules.registration.service.reference_standard import ReferenceStandardService
from app.modules.registration.service.validation_audit import ValidationAuditService

__all__ = [
    "AuthorizationLetterService",
    "ReferenceStandardService",
    "CertificateWorkbookService",
    "RegistrationFeeService",
    "RegistrationKnowledgeService",
    "SupplementaryReplyService",
    "ValidationAuditService",
]
