"""Audit source workbooks and optionally load them into the local development DB.

Raw files and analysis stay in ignored data/. No notifications are sent. Existing
readings are corrected only with --correct-existing, retaining their revisions.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import sys
from calendar import monthrange
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.modules.energy.ledger_entry import write_entries
from app.modules.energy.ledger_fields import build_field_mappings, find_field
from app.modules.energy.ledger_imports import (
    confirm_import,
    inspect_xlsx,
    prepare_import,
    preview_import,
)
from app.modules.energy.ledger_models import EnergyImportBatch, EnergyReading
from app.modules.energy.ledger_schemas import (
    DirectReadingValue,
    DirectReadingWrite,
    ImportConfirm,
    ImportMapping,
)
from app.modules.energy.ledger_service import EnergyLedgerService
from app.modules.energy.ledger_source_workbook import source_period
from app.platform.identity.models import User

BACKEND = Path(__file__).resolve().parents[1]


def audit(paths: list[Path], year: int, output: Path) -> list[dict[str, object]]:
    output.mkdir(parents=True, exist_ok=True)
    previous: dict[tuple[str, int, str], str] = {}
    summaries: list[dict[str, object]] = []
    field_snapshots: list[dict[str, object]] = []
    for path in paths:
        content = path.read_bytes()
        payload = inspect_xlsx(content, year)
        conflicts: list[dict[str, object]] = []
        sheets = payload.get("sheets")
        if not isinstance(sheets, list):
            raise ValueError("缺少工作表")
        for sheet in sheets:
            if not isinstance(sheet, dict) or not sheet.get("category"):
                continue
            cells, columns = sheet.get("cells"), sheet.get("input_columns")
            if not isinstance(cells, list) or not isinstance(columns, list):
                continue
            for cell in cells:
                if not isinstance(cell, dict) or cell.get("column") not in columns:
                    continue
                key = str(sheet["name"]), int(str(cell["column"])), str(cell["date"])
                value = str(cell["value"])
                if key in previous and Decimal(previous[key]) != Decimal(value):
                    conflicts.append(
                        {
                            "sheet": key[0],
                            "column": key[1],
                            "date": key[2],
                            "earlier": previous[key],
                            "current": value,
                        }
                    )
                previous[key] = value
        summary: dict[str, object] = {
            "file": path.name,
            "sha256": hashlib.sha256(content).hexdigest(),
            "report_period": payload["report_period"],
            "sheet_count": len(sheets),
            "formula_summary": payload["formula_summary"],
            "warnings": payload["warnings"],
            "overlap_conflicts": conflicts,
            "field_mapping_count": len(build_field_mappings(payload)),
        }
        field_snapshots.append(
            {
                "file": path.name,
                "report_period": payload["report_period"],
                "fields": build_field_mappings(payload),
            }
        )
        summaries.append(summary)
        destination = output / path.name
        if path.resolve() != destination.resolve():
            shutil.copy2(path, destination)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    (output / "analysis.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "field-mappings.json").write_text(
        json.dumps(field_snapshots, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summaries


async def load_development(
    paths: list[Path], year: int, actor_id: UUID, *, correct_existing: bool
) -> list[dict[str, object]]:
    settings = get_settings()
    url = make_url(settings.DATABASE_URL)
    if (
        settings.APP_ENV != "development"
        or url.host not in {"db", "localhost", "127.0.0.1", "::1"}
        or url.query
    ):
        raise ValueError("仅允许写入根目录 .env.local 指定的本地开发库")
    # The same Compose database is reachable by service name inside the container
    # and the published loopback port when this script is run on the host.
    if url.host == "db" and not Path("/.dockerenv").exists():
        url = url.set(host="127.0.0.1")
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    engine = create_async_engine(url)
    results: list[dict[str, object]] = []
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            current = list(
                (
                    await db.execute(text("SELECT version_num FROM alembic_version"))
                ).scalars()
            )
            if len(heads) != 1 or current != heads:
                raise ValueError("开发库迁移版本与代码不一致，未写入数据")
            actor = await db.get(User, actor_id)
            if (
                actor is None
                or actor.is_deleted
                or actor.status != "active"
                or actor.role != "admin"
            ):
                raise ValueError("必须指定现有有效管理员作为本次开发数据操作人")
            service = EnergyLedgerService(db, actor)
            for path in paths:
                full = inspect_xlsx(path.read_bytes(), year)
                period = source_period(full)
                if period is None:
                    raise ValueError("无法识别月报月份")
                start = date(*period, 1)
                end = date(*period, monthrange(*period)[1])
                preview = await preview_import(
                    service, path.read_bytes(), year, start, end
                )
                if preview.status == "imported":
                    results.append({"file": path.name, "status": "already_imported"})
                    continue
                await prepare_import(service, preview.id)
                batch = await service.repo.get(EnergyImportBatch, preview.id)
                batch.payload = {
                    **batch.payload,
                    "source_file": path.name,
                    "development_dataset": True,
                }
                fields = build_field_mappings(full)
                points = {}
                for item in await service.meters():
                    binding = find_field(fields, item.definition)
                    if binding is not None and binding["kind"] == "reading":
                        points[
                            str(binding["source_sheet"]),
                            int(str(binding["source_column"])),
                        ] = item
                mappings: list[ImportMapping] = []
                corrections: dict[tuple[str, date], list[DirectReadingValue]] = {}
                sheets = full.get("sheets")
                if not isinstance(sheets, list):
                    raise ValueError("缺少工作表")
                for sheet in sheets:
                    if not isinstance(sheet, dict) or not sheet.get("category"):
                        continue
                    cells, columns = sheet.get("cells"), sheet.get("input_columns")
                    if not isinstance(cells, list) or not isinstance(columns, list):
                        raise ValueError("原始字段结构无效")
                    populated: set[int] = set()
                    for cell in cells:
                        if not isinstance(cell, dict) or cell["column"] not in columns:
                            continue
                        day = date.fromisoformat(str(cell["date"]))
                        if not start <= day <= end:
                            continue
                        column = int(str(cell["column"]))
                        point = points.get((str(sheet["name"]), column))
                        if point is None:
                            raise ValueError("原始字段映射不完整")
                        populated.add(column)
                        existing = await db.scalar(
                            select(EnergyReading).where(
                                EnergyReading.point_id == point.id,
                                EnergyReading.reading_date == day,
                            )
                        )
                        value = Decimal(str(cell["value"]))
                        if existing and (
                            existing.is_deleted or existing.draft_value is not None
                        ):
                            raise ValueError("来源日期存在作废记录或草稿，请先人工处理")
                        if existing and existing.value != value:
                            if not correct_existing:
                                raise ValueError(
                                    "已有读数与原表不同；核对后使用 --correct-existing "
                                    "保留修订记录进行更正"
                                )
                            corrections.setdefault(
                                (str(sheet["name"]), day), []
                            ).append(
                                DirectReadingValue(
                                    point_id=point.id,
                                    version=existing.version,
                                    value=value,
                                )
                            )
                    mappings.extend(
                        ImportMapping(
                            sheet=str(sheet["name"]),
                            column=column,
                            point_id=points[str(sheet["name"]), column].id,
                        )
                        for column in sorted(populated)
                    )
                corrected = 0
                for (dataset, day), entries in corrections.items():
                    await write_entries(
                        service,
                        DirectReadingWrite(
                            dataset=dataset,
                            reading_date=day,
                            values=entries,
                            reason=f"四个月能源日报表开发数据核对：{path.name}",
                        ),
                        source="development",
                        recalculate=False,
                    )
                    corrected += len(entries)
                result = await confirm_import(
                    service,
                    preview.id,
                    ImportConfirm(
                        mappings=mappings,
                        reason=f"用户授权四个月能源日报表作为开发数据：{path.name}",
                    ),
                )
                results.append(
                    {
                        "file": path.name,
                        "status": result.status,
                        "batch_id": str(result.id),
                        "imported_count": result.payload.get("imported_count"),
                        "corrected_count": corrected,
                    }
                )
                print(json.dumps(results[-1], ensure_ascii=False), flush=True)
            await db.commit()
    finally:
        await engine.dispose()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", type=Path, nargs="+")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument(
        "--output", type=Path, default=BACKEND / "data" / "energy-development"
    )
    parser.add_argument("--apply-development", action="store_true")
    parser.add_argument("--actor-id", type=UUID)
    parser.add_argument("--correct-existing", action="store_true")
    args = parser.parse_args()
    audit(args.files, args.year, args.output)
    if args.apply_development:
        if args.actor_id is None:
            parser.error("--apply-development requires --actor-id")
        try:
            results = asyncio.run(
                load_development(
                    args.files,
                    args.year,
                    args.actor_id,
                    correct_existing=args.correct_existing,
                )
            )
        except (ValueError, AppException) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except Exception as exc:
            # DB driver messages can contain connection credentials.
            print(
                f"开发数据导入失败，事务已回滚：{type(exc).__name__}", file=sys.stderr
            )
            return 1
        (args.output / "import-results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
