"""生产历史数据迁移命令行工具。"""

import argparse
import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import async_session_factory
from app.modules.production.migration_service import ProductionMigrationService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生产模块历史数据校验、导入、对账与回滚"
    )
    parser.add_argument(
        "mode", choices=("validate", "dry-run", "import", "reconcile", "rollback")
    )
    parser.add_argument("--input-dir", type=Path, default=Path("migration-input"))
    parser.add_argument("--source-system", default="production-module")
    parser.add_argument("--run-key")
    parser.add_argument("--run-id", type=uuid.UUID)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    service_result: dict[Any, Any] = {}
    if args.mode == "validate":
        bundle, load_errors = ProductionMigrationService.load_directory(args.input_dir)
        validated, validation_errors = ProductionMigrationService.validate_bundle(
            bundle
        )
        service_result = {
            "mode": "validate",
            "counts": {key: len(value) for key, value in validated.items()},
            "errors": [*load_errors, *validation_errors],
        }
    else:
        async with async_session_factory() as session:
            service = ProductionMigrationService(session)
            if args.mode in {"dry-run", "import"}:
                bundle, errors = service.load_directory(args.input_dir)
                if errors:
                    service_result = {"mode": args.mode, "errors": errors}
                else:
                    run_key = (
                        args.run_key
                        or f"{args.mode}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
                    )
                    run = await service.execute(
                        bundle=bundle,
                        source_system=args.source_system,
                        run_key=run_key,
                        dry_run=args.mode == "dry-run",
                    )
                    await session.commit()
                    service_result = {
                        "run_id": str(run.id),
                        "run_key": run.run_key,
                        "status": run.status,
                        "inserted": run.inserted_count,
                        "updated": run.updated_count,
                        "skipped": run.skipped_count,
                        "failed": run.failed_count,
                        "report": run.report,
                    }
            elif args.mode == "reconcile":
                service_result = await service.reconcile(args.source_system)
            else:
                if not args.run_id:
                    raise SystemExit("rollback 模式必须提供 --run-id")
                timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
                run_key = args.run_key or f"rollback-{args.run_id}-{timestamp}"
                run = await service.rollback(args.run_id, run_key)
                await session.commit()
                service_result = {
                    "run_id": str(run.id),
                    "status": run.status,
                    "report": run.report,
                }
    output = json.dumps(service_result, ensure_ascii=False, indent=2, default=str)
    print(output)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n", encoding="utf-8")
    return 1 if service_result.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
