"""Public spreadsheet operations used by the scheduling draft exporter."""

from collections.abc import Callable, Iterable, Mapping
from importlib import import_module
from typing import BinaryIO, Protocol, cast


class DraftColumnDimension(Protocol):
    width: float


class DraftSheet(Protocol):
    title: str

    @property
    def column_dimensions(self) -> Mapping[str, DraftColumnDimension]: ...

    def append(self, values: Iterable[object]) -> None: ...


class DraftWorkbook(Protocol):
    @property
    def active(self) -> DraftSheet | None: ...

    def save(self, filename: BinaryIO) -> None: ...


# Keep the untyped external library at an explicit, exporter-specific boundary.
# Real workbook round-trip tests cover these public operations.
new_workbook = cast(Callable[[], DraftWorkbook], import_module("openpyxl").Workbook)
column_letter = cast(
    Callable[[int], str], import_module("openpyxl.utils").get_column_letter
)
