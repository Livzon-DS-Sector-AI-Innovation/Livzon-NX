import pytest
from pydantic import ValidationError

from app.main import app
from app.platform.identity.page_policy import api_binding_for_route, get_page_definition
from app.shared.todo_schemas import BusinessTodoPage


@pytest.mark.parametrize(
    "module", ["quality", "equipment", "safety", "registration", "hr"]
)
def test_todo_endpoints_are_registered_with_page_scope_contracts(module: str) -> None:
    path = f"/api/v1/{module}/my-todos"
    assert path in app.openapi()["paths"]
    binding = api_binding_for_route("GET", path)
    assert binding is not None and binding.scope_adapter == f"{module}.personal_todos"
    for key in binding.page_keys:
        assert get_page_definition(key).module_code == module


def test_todo_response_cannot_claim_negative_totals_or_unbounded_pages() -> None:
    for data in (
        {"items": [], "total": -1, "page": 1, "page_size": 5},
        {"items": [], "total": 0, "page": 1, "page_size": 1000},
    ):
        with pytest.raises(ValidationError):
            BusinessTodoPage.model_validate(data)
