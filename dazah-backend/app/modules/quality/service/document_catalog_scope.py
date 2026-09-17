"""Department predicates shared by document lookup and attachment matching."""

from sqlalchemy import select, true
from sqlalchemy.sql.elements import ColumnElement

from app.modules.quality.models.document_catalog import (
    DocumentDepartment,
    DocumentEntry,
)
from app.platform.identity.data_scope import DepartmentScope


def document_entry_scope(scope: DepartmentScope | None) -> ColumnElement[bool]:
    """None is reserved for trusted service calls without an HTTP actor."""
    if scope is None or scope.is_all:
        return true()
    return DocumentEntry.department_id.in_(
        select(DocumentDepartment.id).where(
            DocumentDepartment.is_deleted.is_(False),
            DocumentDepartment.name.in_(scope.department_names),
        )
    )
