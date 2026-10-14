"""Typed openpyxl boundary for equipment ledgers.

Only the public operations used by ledger import/export are described here.
Other modules' legacy spreadsheet APIs retain their existing typing boundary.
"""

from collections.abc import Callable, Iterable, Iterator
from importlib import import_module
from typing import BinaryIO, Literal, Protocol, cast


class LedgerCell(Protocol):
    @property
    def value(self) -> object: ...


class LedgerCellRange(Protocol):
    min_row: int
    max_row: int
    min_col: int
    max_col: int


class LedgerMergedCells(Protocol):
    @property
    def ranges(self) -> Iterable[LedgerCellRange]: ...


class LedgerSheet(Protocol):
    title: str

    @property
    def merged_cells(self) -> LedgerMergedCells: ...

    def append(self, values: Iterable[object]) -> None: ...

    def iter_rows(
        self, *, values_only: Literal[True]
    ) -> Iterator[tuple[object, ...]]: ...

    def cell(self, row: int, column: int) -> LedgerCell: ...


class LedgerWorkbook(Protocol):
    @property
    def active(self) -> LedgerSheet | None: ...

    def save(self, filename: BinaryIO) -> None: ...


class LedgerExcel(Protocol):
    Workbook: Callable[[], LedgerWorkbook]

    def load_workbook(
        self, filename: BinaryIO, *, data_only: bool
    ) -> LedgerWorkbook: ...


# openpyxl's public ledger operations satisfy these protocols; tests exercise
# the actual library, including merged cells, template writing and date cells.
ledger_excel = cast(LedgerExcel, import_module("openpyxl"))
