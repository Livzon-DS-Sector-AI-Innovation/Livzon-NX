"""campus map v2: refresh marker coords and sync buildings

厂区矢量底图（2.5D 等轴测，public/safety/campus-map.svg）替换扫描平面图后，
按 ``app/modules/safety/seeds/campus_buildings.json`` 同步建筑底册：
- 全部建筑 x_pct/y_pct 按新底图的等轴测投影重新标定（坐标由生成器
  ``dazah-frontend/scripts/generate-campus-map.mjs`` 计算）；
- 新增 MVR、过滤生产区、干燥间、机修间、曝气池、二沉池、污泥浓缩池、
  污水处理系统（二）等图纸建筑；污水处理系统原单条拆为（一）/（二）两栋，
  （一）承接污水相关地点别名（厌氧塔/总排在线房/压泥间等）；
- 移除误读的「原料库」（厂区北缘并无该建筑）；
- 不在种子清单内的存量建筑统一软删，保证底册与图纸一致。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "c5d7e9f1a3b6"
down_revision: str | None = "d7f3b9c1e5a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "modules"
    / "safety"
    / "seeds"
    / "campus_buildings.json"
)


def _seed_rows() -> list[dict]:
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def upgrade() -> None:
    bind = op.get_bind()
    rows = _seed_rows()
    seed_names = [row["name"] for row in rows]

    # 软删不在种子清单内的建筑（如误读的「原料库」被移除后）
    bind.execute(
        sa.text(
            "UPDATE safety.campus_buildings SET is_deleted = true, "
            "updated_at = now() "
            "WHERE is_deleted = false AND NOT (name = ANY(:names))"
        ),
        {"names": seed_names},
    )

    for index, row in enumerate(rows):
        aliases_json = json.dumps(row.get("aliases") or [], ensure_ascii=False)
        existing = bind.execute(
            sa.text(
                "SELECT id FROM safety.campus_buildings "
                "WHERE name = :name AND is_deleted = false"
            ),
            {"name": row["name"]},
        ).scalar()
        if existing is not None:
            bind.execute(
                sa.text(
                    "UPDATE safety.campus_buildings SET x_pct = :x, y_pct = :y, "
                    "category = :category, aliases = CAST(:aliases AS jsonb), "
                    "code = :code, "
                    "updated_at = now() WHERE id = :id"
                ),
                {
                    "x": row["x_pct"],
                    "y": row["y_pct"],
                    "category": row["category"],
                    "aliases": aliases_json,
                    "code": row.get("code") or "",
                    "id": str(existing),
                },
            )
        else:
            bind.execute(
                sa.text(
                    "INSERT INTO safety.campus_buildings "
                    "(id, code, name, category, x_pct, y_pct, aliases, sort_order, "
                    "created_at, updated_at) "
                    "VALUES (:id, :code, :name, :category, :x, :y, "
                    "CAST(:aliases AS jsonb), :sort, now(), now())"
                ),
                {
                    "id": str(uuid4()),
                    "code": row.get("code") or "",
                    "name": row["name"],
                    "category": row["category"],
                    "x": row["x_pct"],
                    "y": row["y_pct"],
                    "aliases": aliases_json,
                    "sort": 900 + index,
                },
            )


def downgrade() -> None:
    # campus_buildings 为纯种子数据表（无用户数据），降级直接清空
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM safety.campus_buildings"))
