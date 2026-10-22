"""split equipment workshop 201-2 into 201-2-MC and 201-2-DR

Revision ID: c9d400000063
Revises: c9d400000062
Create Date: 2026-10-21 02:40:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000063"
down_revision: str = "c9d400000062"
branch_labels: None = None
depends_on: None = None

# 设备 schema 下按 workshop_code 隔离、无车间级唯一约束的业务表：
# 数据迁移只需整体改写车间代码
PLAIN_WORKSHOP_TABLES = (
    "equipments",
    "equipment_ledger_archives",
    "equipment_personnel",
)

# 带 (workshop_code, ...) 唯一约束的表：应用在迁移前可能已按新代码写入
# （如备件同步热更新后先同步了 201-2-MC/DR 行），旧 201-2 行与新行同码时
# 冲突；迁移保留较新的新代码行，旧行软删/删除后再整体改名
MIRROR_TABLES = (
    "inspection_feishu_records",
    "inspection_feishu_devices",
    "inspection_feishu_sync_state",
)

# 旧「车间×功能」叶授权 key（equipment:workshop-201-2:<功能>-201-2）改写为新车间 key
GRANT_KEY_UPGRADE = (
    "UPDATE {table} SET page_key = regexp_replace("
    "page_key, '^equipment:workshop-201-2:([a-z-]+)-201-2$', "
    "'equipment:workshop-201-2-MC:\\1-201-2-MC') "
    "WHERE page_key ~ '^equipment:workshop-201-2:[a-z-]+-201-2$'"
)

# 设备页授权的 visible_sections 中旧车间代码归一到 MC
GRANT_SECTIONS_UPGRADE = (
    "UPDATE {table} SET visible_sections = ("
    "SELECT jsonb_agg(CASE WHEN elem = to_jsonb('201-2'::text) THEN to_jsonb('201-2-MC'::text) ELSE elem END) "
    "FROM jsonb_array_elements(visible_sections) AS t(elem)) "
    "WHERE page_key LIKE 'equipment:%' AND visible_sections @> '\"201-2\"'::jsonb"
)

GRANT_KEY_DOWNGRADE = (
    "UPDATE {table} SET page_key = regexp_replace("
    "page_key, '^equipment:workshop-201-2-MC:([a-z-]+)-201-2-MC$', "
    "'equipment:workshop-201-2:\\1-201-2') "
    "WHERE page_key ~ '^equipment:workshop-201-2-MC:[a-z-]+-201-2-MC$'"
)

# 回退时 DR 叶授权 key 拆分前不存在，直接移除，避免悬挂标识
GRANT_DR_KEY_DOWNGRADE = (
    "DELETE FROM {table} WHERE page_key LIKE 'equipment:workshop-201-2-DR:%'"
)

GRANT_SECTIONS_DOWNGRADE = (
    "UPDATE {table} SET visible_sections = ("
    "SELECT jsonb_agg(DISTINCT CASE WHEN elem IN (to_jsonb('201-2-MC'::text), to_jsonb('201-2-DR'::text)) "
    "THEN to_jsonb('201-2'::text) ELSE elem END) "
    "FROM jsonb_array_elements(visible_sections) AS t(elem)) "
    "WHERE page_key LIKE 'equipment:%' "
    "AND visible_sections ?| array['201-2-MC', '201-2-DR']"
)


def _rename_avoiding_collisions(table: str, collide: str, soft: bool) -> None:
    """先把与既有 201-2-MC 行冲突的旧 201-2 行软删/删除，再整体改名为 MC。

    collide 为业务键条件（new 行 n 与 old 行 t 撞唯一索引的比较式）。
    """
    if soft:
        op.execute(
            f"UPDATE equipment.{table} t SET is_deleted = true "
            f"WHERE t.workshop_code = '201-2' AND t.is_deleted = false "
            f"AND EXISTS (SELECT 1 FROM equipment.{table} n "
            f"WHERE n.workshop_code = '201-2-MC' AND n.is_deleted = false "
            f"AND {collide})"
        )
    else:
        op.execute(
            f"DELETE FROM equipment.{table} t WHERE workshop_code = '201-2' "
            f"AND EXISTS (SELECT 1 FROM equipment.{table} n "
            f"WHERE n.workshop_code = '201-2-MC' AND {collide})"
        )
    op.execute(
        f"UPDATE equipment.{table} "
        "SET workshop_code = '201-2-MC' WHERE workshop_code = '201-2'"
    )


def upgrade() -> None:
    # 无唯一约束表：直接改名
    for table in PLAIN_WORKSHOP_TABLES:
        op.execute(
            f"UPDATE equipment.{table} "
            "SET workshop_code = '201-2-MC' WHERE workshop_code = '201-2'"
        )
    # 备件（唯一键 code，部分索引）与巡检配置（每车间一行，部分索引）：冲突行软删
    _rename_avoiding_collisions(
        "spare_parts", "n.code = t.code", soft=True
    )
    _rename_avoiding_collisions(
        "inspection_feishu_config", "true", soft=True
    )
    # 巡检镜像（可重新同步的派生数据）：冲突行硬删
    _rename_avoiding_collisions(
        "inspection_feishu_records", "n.source = t.source AND n.record_id = t.record_id", soft=False
    )
    _rename_avoiding_collisions(
        "inspection_feishu_devices", "n.record_id = t.record_id", soft=False
    )
    _rename_avoiding_collisions(
        "inspection_feishu_sync_state", "n.table_key = t.table_key", soft=False
    )
    for table in ("identity.role_page_grants", "identity.user_page_grants"):
        op.execute(GRANT_KEY_UPGRADE.format(table=table))
        op.execute(GRANT_SECTIONS_UPGRADE.format(table=table))


def downgrade() -> None:
    # 巡检镜像是可重同步的派生数据：DR 行删除，MC 行归回 201-2
    for table in MIRROR_TABLES:
        op.execute(f"DELETE FROM equipment.{table} WHERE workshop_code = '201-2-DR'")
        op.execute(
            f"UPDATE equipment.{table} "
            "SET workshop_code = '201-2' WHERE workshop_code = '201-2-MC'"
        )
    # 巡检配置每车间仅一行（部分唯一索引）：DR 行软删后 MC 行归回
    op.execute(
        "UPDATE equipment.inspection_feishu_config SET is_deleted = true "
        "WHERE workshop_code = '201-2-DR' AND is_deleted = false"
    )
    op.execute(
        "UPDATE equipment.inspection_feishu_config "
        "SET workshop_code = '201-2' WHERE workshop_code = '201-2-MC'"
    )
    # 备件同车间同编码唯一（部分唯一索引），MC/DR 又同步自同一五金表：
    # 与归并后 201-2 同码的 DR 行是冗余副本，软删以避开唯一冲突且不动物院子表
    op.execute(
        "UPDATE equipment.spare_parts SET is_deleted = true "
        "WHERE workshop_code = '201-2-DR' AND is_deleted = false "
        "AND code IN (SELECT code FROM equipment.spare_parts "
        "WHERE workshop_code = '201-2' AND is_deleted = false)"
    )
    op.execute(
        "UPDATE equipment.spare_parts SET workshop_code = '201-2' "
        "WHERE workshop_code IN ('201-2-MC', '201-2-DR')"
    )
    for table in PLAIN_WORKSHOP_TABLES:
        op.execute(
            f"UPDATE equipment.{table} "
            "SET workshop_code = '201-2' "
            "WHERE workshop_code IN ('201-2-MC', '201-2-DR')"
        )
    for table in ("identity.role_page_grants", "identity.user_page_grants"):
        op.execute(GRANT_KEY_DOWNGRADE.format(table=table))
        op.execute(GRANT_DR_KEY_DOWNGRADE.format(table=table))
        op.execute(GRANT_SECTIONS_DOWNGRADE.format(table=table))
