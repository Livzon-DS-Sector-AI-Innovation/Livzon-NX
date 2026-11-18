"""物料与成品检验共用的批号镜像分页同步。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.quality.models.inspection_items_mirror import QualityItemsPageRow
from app.modules.quality.repository import inspection_items_mirror as repo
from app.platform.integrations.feishu.bitable import BitableClient

logger = logging.getLogger(__name__)

_PAGE_SIZE = 500
_MAX_PAGES = 200

Record = dict[str, Any]
NormalizeCells = Callable[[Record, list[Record]], Record]


class _RecordPullError(AppException):
    def __init__(self, message: str) -> None:
        super().__init__(status_code=503, message=message)


def _business_cells(cells: Record) -> Record:
    return {key: value for key, value in cells.items() if not key.startswith("__")}


async def _request_page(
    client: BitableClient,
    table_id: str,
    token: str,
    *,
    sorted_search: bool,
) -> Record:
    path = f"/bitable/v1/apps/{client.app_token}/tables/{table_id}/records"
    params: Record = {
        "page_size": _PAGE_SIZE,
        "field_name_type": "name",
        "automatic_fields": True,
    }
    if token:
        params["page_token"] = token
    try:
        if sorted_search:
            return await client.client.request(
                "POST",
                f"{path}/search",
                params=params,
                json={"sort": [{"field_name": "批号", "desc": True}]},
                timeout=60.0,
            )
        return await client.client.request("GET", path, params=params, timeout=60.0)
    except (RuntimeError, ValueError, httpx.HTTPError) as exc:
        raise _RecordPullError(
            f"从飞书拉取质量镜像记录失败（{type(exc).__name__}）"
        ) from None


async def _sync_pages(
    db: AsyncSession,
    client: BitableClient,
    table_id: str,
    snapshot_id: UUID,
    columns: list[Record],
    *,
    incremental: bool,
    sorted_search: bool,
    now: datetime,
    normalize_cells: NormalizeCells,
    extract_batch: Callable[[Record], str | None],
    build_search_text: Callable[[Record], str],
) -> set[str]:
    seen_ids: set[str] = set()
    seen_tokens: set[str] = set()
    token = ""
    row_order = 0
    records_read = 0
    for _ in range(_MAX_PAGES):
        data = await _request_page(client, table_id, token, sorted_search=sorted_search)
        has_more = data.get("has_more")
        records = data.get("items")
        if records is None and data.get("total") == 0 and has_more is False:
            records = []
        if (
            not isinstance(has_more, bool)
            or not isinstance(records, list)
            or len(records) > _PAGE_SIZE
            or any(
                not isinstance(record, dict)
                or not isinstance(record.get("record_id"), str)
                or not record["record_id"]
                or len(record["record_id"]) > 64
                or (
                    record.get("fields") is not None
                    and not isinstance(record["fields"], dict)
                )
                for record in records
            )
        ):
            raise _RecordPullError("飞书质量镜像记录分页响应无效")

        batches = [extract_batch(record) for record in records] if incremental else []
        current_cells = await repo.get_cells_by_batches(
            db,
            snapshot_id,
            {batch for batch in batches if batch},
        )
        changed = False
        rows: list[QualityItemsPageRow] = []
        for index, record in enumerate(records):
            cells = normalize_cells(record, columns)
            batch = batches[index] if incremental else None
            if (
                batch
                and batch in current_cells
                and (_business_cells(cells) == _business_cells(current_cells[batch]))
            ):
                continue
            changed = True
            row_order += 1
            record_id = record["record_id"]
            if record_id in seen_ids:
                continue
            seen_ids.add(record_id)
            rows.append(
                QualityItemsPageRow(
                    page_snapshot_id=snapshot_id,
                    source_record_id=record_id,
                    row_order=row_order,
                    cells=cells,
                    search_text=build_search_text(cells),
                    last_synced_at=now,
                )
            )
        await repo.upsert_mirror_batch(
            db, snapshot_id, rows, revive_deleted=not incremental
        )
        records_read += len(records)
        if not has_more:
            total = data.get("total")
            if isinstance(total, int) and total > (
                records_read if incremental else len(seen_ids)
            ):
                raise _RecordPullError("飞书质量镜像记录分页未拉取完整")
            return seen_ids
        if sorted_search and records and not changed:
            return seen_ids
        next_token = data.get("page_token")
        if (
            not isinstance(next_token, str)
            or not next_token
            or next_token in seen_tokens
        ):
            raise _RecordPullError("飞书质量镜像分页游标缺失或重复")
        seen_tokens.add(next_token)
        token = next_token
    raise _RecordPullError("飞书质量镜像超过单次分页上限")


async def sync_batch_mirror(
    db: AsyncSession,
    client: BitableClient,
    *,
    entity_code: str,
    label: str,
    table_id: str,
    columns: list[Record],
    incremental: bool,
    normalize_cells: NormalizeCells,
    extract_batch: Callable[[Record], str | None],
    build_search_text: Callable[[Record], str],
) -> dict[str, int]:
    """逐页落库，完整全量成功后才对账，分页失败回滚整轮。"""
    async with db.begin_nested():
        await repo.lock_batch_mirror(db, entity_code)
        previous = await repo.get_snapshot(db, entity_code)
        use_incremental = (
            incremental and previous is not None and previous.total_rows > 0
        )
        now = datetime.now(UTC)
        snapshot = await repo.upsert_snapshot(
            db,
            page_key=entity_code,
            page_title=label,
            table_name=label,
            table_id=table_id,
            columns=columns,
            total_rows=0,
            last_synced_at=now,
        )
        snapshot_id = snapshot.id

        async def sync_pages(*, sorted_search: bool) -> set[str]:
            return await _sync_pages(
                db,
                client,
                table_id,
                snapshot_id,
                columns,
                incremental=use_incremental,
                sorted_search=sorted_search,
                now=now,
                normalize_cells=normalize_cells,
                extract_batch=extract_batch,
                build_search_text=build_search_text,
            )

        if use_incremental:
            try:
                async with db.begin_nested():
                    seen_ids = await sync_pages(sorted_search=True)
            except _RecordPullError:
                logger.warning("质量镜像批号搜索失败，逐页回退: entity=%s", entity_code)
                seen_ids = await sync_pages(sorted_search=False)
            snapshot.total_rows = await repo.count_rows(db, snapshot_id)
        else:
            seen_ids = await sync_pages(sorted_search=False)
            await repo.soft_delete_missing_mirror_rows(db, snapshot_id, seen_ids)
            snapshot.total_rows = len(seen_ids)
    await db.commit()

    logger.info(
        "质量镜像同步完成: entity=%s incremental=%s rows=%d",
        entity_code,
        use_incremental,
        len(seen_ids),
    )
    return {"synced": len(seen_ids), "removed": 0, "total": len(seen_ids)}
