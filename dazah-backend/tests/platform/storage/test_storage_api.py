import pytest
from fastapi import HTTPException

from app.platform.storage.api import _validate_key


def test_validate_key_normalizes_windows_separators() -> None:
    assert _validate_key("quality", r"documents\report.pdf") == "documents/report.pdf"


@pytest.mark.parametrize(
    ("module", "object_key", "status_code"),
    [
        ("unknown", "documents/report.pdf", 404),
        ("quality", "../report.pdf", 400),
        ("quality", "/report.pdf", 400),
        ("quality", "", 400),
    ],
)
def test_validate_key_rejects_unsafe_values(
    module: str, object_key: str, status_code: int
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        _validate_key(module, object_key)

    assert exc_info.value.status_code == status_code
