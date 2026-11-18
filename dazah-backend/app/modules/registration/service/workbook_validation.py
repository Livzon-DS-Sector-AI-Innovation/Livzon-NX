from io import BytesIO
from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from openpyxl.workbook.workbook import Workbook

from app.modules.registration.workbook_error_contract import (
    RegistrationWorkbookErrorCode,
    workbook_validation_error,
)


def load_registration_workbook(source: Path | BytesIO, *, data_only: bool) -> Workbook:
    try:
        return load_workbook(source, data_only=data_only)
    except (
        BadZipFile,
        InvalidFileException,
        KeyError,
        OSError,
        ValueError,
        ParseError,
        SyntaxError,
    ) as exc:
        # Keep filesystem errors distinct from openpyxl's invalid-workbook error.
        if isinstance(exc, OSError) and exc.errno is not None:
            raise
        raise workbook_validation_error(
            RegistrationWorkbookErrorCode.UNREADABLE, "无法读取 Excel 工作簿"
        ) from exc
