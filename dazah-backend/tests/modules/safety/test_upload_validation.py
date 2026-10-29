"""安全模块上传接口必须拒绝带路径分隔符的文件名。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from io import BytesIO
from typing import Any
from uuid import uuid4

import pytest
from starlette.datastructures import UploadFile

from app.core.exceptions import AppException
from app.modules.safety.api import hazard_identifications, hazards, regulations

UploadInvoker = Callable[[Any, UploadFile], Awaitable[Any]]


@pytest.mark.parametrize(
    "invoker",
    [
        lambda record_id, file: hazards.upload_hazard_photo(
            record_id, file, db=object(), current_user=None
        ),
        lambda record_id, file: hazards.upload_rectification_photo(
            record_id, file, db=object(), current_user=None
        ),
        lambda record_id, file: regulations.upload_regulation_document(
            record_id, file, db=object(), current_user=None
        ),
        lambda record_id, file: regulations.manual_revision_complete(
            record_id, file, db=object(), current_user=None
        ),
        lambda record_id, file: hazard_identifications.upload_hazard_attachment(
            record_id, file, db=object(), current_user=None
        ),
    ],
)
@pytest.mark.anyio
async def test_upload_rejects_traversal_filename(invoker: UploadInvoker) -> None:
    file = UploadFile(file=BytesIO(b"payload"), filename="../../app/main.py")

    with pytest.raises(AppException) as exc_info:
        await invoker(uuid4(), file)

    assert exc_info.value.status_code == 400
