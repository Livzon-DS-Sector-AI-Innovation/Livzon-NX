"""Generate development reference identities; never restrict production data.

Run from dazah-backend: uv run python -m scripts.generate_dashboard_sources <files...>
The manifest is a test fixture. Business values are not stored in application code.
"""

import hashlib
import json
import sys
from calendar import monthrange
from datetime import date
from pathlib import Path

from app.modules.energy.ledger_imports import IMPORT_POLICY_VERSION, inspect_xlsx
from app.modules.energy.ledger_source_workbook import source_period


def generate(paths: list[Path]) -> None:
    sources = {}
    for path in paths:
        content = path.read_bytes()
        period = source_period(inspect_xlsx(content, 2026))
        if period is None or period[0] != 2026 or period[1] not in {7, 8, 9, 10}:
            raise ValueError("仅允许指定的 2026 年 7—10 月原表")
        year, month = period
        key = f"{year}-{month:02}"
        if key in sources:
            raise ValueError("原表月份重复")
        start, end = date(year, month, 1), date(year, month, monthrange(year, month)[1])
        hashes = [
            hashlib.sha256(
                f"{IMPORT_POLICY_VERSION}:{year}:{first}:{last}:".encode() + content
            ).hexdigest()
            for first, last in [(start, end), (None, None)]
        ]
        sources[key] = {
            "file": path.name,
            "sha256": hashlib.sha256(content).hexdigest(),
            "import_hashes": hashes,
        }
    if len(sources) != 4:
        raise ValueError("必须提供完整四份原表")
    destination = (
        Path(__file__).resolve().parents[1]
        / "tests/modules/energy/fixtures/reference_sources.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    generate([Path(value) for value in sys.argv[1:]])
