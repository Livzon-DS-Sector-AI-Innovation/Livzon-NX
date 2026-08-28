"""Registration repository."""

from app.modules.registration.repository.authorization import (
    AuthorizationFdaRepository,
    AuthorizationLedgerRepository,
    AuthorizationLetterRepository,
    ReferenceStandardRepository,
    SupplementaryReplyRepository,
)
from app.modules.registration.repository.certificate import (
    RegistrationCertificateRepository,
)
from app.modules.registration.repository.declaration_progress import (
    RegistrationDeclarationProgressRepository,
)
from app.modules.registration.repository.declaration_progress_workbook import (
    RegistrationDeclarationProgressWorkbookRepository,
)
from app.modules.registration.repository.fee import RegistrationFeeRepository
from app.modules.registration.repository.knowledge import (
    RegistrationKnowledgeRepository,
)
from app.modules.registration.repository.project_ledger import (
    RegistrationProjectLedgerRepository,
)

__all__ = [
    "AuthorizationFdaRepository",
    "AuthorizationLedgerRepository",
    "AuthorizationLetterRepository",
    "ReferenceStandardRepository",
    "RegistrationCertificateRepository",
    "RegistrationDeclarationProgressRepository",
    "RegistrationDeclarationProgressWorkbookRepository",
    "RegistrationFeeRepository",
    "RegistrationKnowledgeRepository",
    "RegistrationProjectLedgerRepository",
    "SupplementaryReplyRepository",
]
