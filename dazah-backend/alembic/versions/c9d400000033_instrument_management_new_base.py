"""仪器管理切换飞书 Base、上线飞书设置页配置行并退役两张下线子表。

背景（2026-09-14）：仪器管理从旧 Base「设备全生命周期管理系统」
（O0S2bHK6Ca5UiCsABPLcZtYhn6d）切到两张新 Base：

- 设备全生命周期管理系统：Cencb8KRja1vL8s7DLqcXiQtnMf
  设备数据管理 / 设备维护保养记录 / 设备维修记录 / 设备维保合同 /
  QC检测仪器维护保养周期表
- QC 2026年度内部校验计划：Vyn1bfLOwaUG15sWXGMcwy5Gnah
  内校汇总 / 内部校验计划 / 外部校准、检定

旧 Base 的「设备变更记录」「固资台账」两张表在新建的 Base 里不存在，
对应页面（前端路由 /quality/inspection/instruments/change 与 /assets）
已下线，这里把实体配置行软删、菜单置 disabled。

DB 配置行（quality.quality_feishu_entity_settings）优先于代码预填，且
ensure_quality_feishu_entity_settings 只在 app_token 为空时回填，因此切换
Base 必须由本迁移显式改写 app_token / base_table_id / base_table_name，
否则运行期仍会访问旧 Base。新表行不存在时一并插入（等价于 ensure 的建行，
但带上新 Base 绑定）。换表后页面镜像需一次全量回拉（页面「同步飞书数据」
按钮，或部署后由每日全量任务补）。

菜单名称同步：校准计划→内校汇总、外协合同→维保合同、年度计划→维保周期表
（数据库菜单行按 seed_menus 的"只补缺不覆盖"策略不会自动跟随代码，故在此显式
改名；退役页面置 disabled，与 e4a9c2d7b601_retire_edbo_menu 同一做法）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000033"
down_revision: str | None = "f73ddeb82366"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EQUIPMENT_APP_TOKEN = "Cencb8KRja1vL8s7DLqcXiQtnMf"
_CALIBRATION_APP_TOKEN = "Vyn1bfLOwaUG15sWXGMcwy5Gnah"
_OLD_APP_TOKEN = "O0S2bHK6Ca5UiCsABPLcZtYhn6d"

# entity_code -> (新 app_token, 新 table_id, 新 Base 表名, 旧 table_id, 旧 Base 表名)
_ENTITY_TABLE_MAP: dict[str, tuple[str, str, str, str, str]] = {
    "qc_instr_equipment": (
        _EQUIPMENT_APP_TOKEN,
        "tblIKMhgGxdLNoow",
        "设备数据管理",
        "tblUUbPOOokfxnUE",
        "设备数据管理",
    ),
    "qc_instr_maintenance": (
        _EQUIPMENT_APP_TOKEN,
        "tblTw5RseafXYYdK",
        "设备维护保养记录",
        "tbl9P17KgdD7XuEu",
        "设备维护保养记录",
    ),
    "qc_instr_repair": (
        _EQUIPMENT_APP_TOKEN,
        "tblhiX6LUYC1uxTl",
        "设备维修记录",
        "tblQbwxJHCOzffKQ",
        "设备维修记录",
    ),
    "qc_instr_contracts": (
        _EQUIPMENT_APP_TOKEN,
        "tblpyvFJI0tBZBhz",
        "设备维保合同",
        "tblLLsCm7uizb5Fn",
        "设备维保合同",
    ),
    "qc_instr_plans": (
        _EQUIPMENT_APP_TOKEN,
        "tblaLERnzZEp7JcL",
        "QC检测仪器维护保养周期表",
        "tbl11SKGWMVVllf3",
        "设备维护保养方案",
    ),
    "qc_instr_calibration": (
        _CALIBRATION_APP_TOKEN,
        "tblRELoVEYKJ6fHB",
        "内校汇总",
        "tblBUZbc5FPZLuJS",
        "设备校验记录",
    ),
    "qc_instr_cal_plan": (
        _CALIBRATION_APP_TOKEN,
        "tblcztwNpMGXLQ8j",
        "内部校验计划",
        "",
        "",
    ),
    "qc_instr_cal_external": (
        _CALIBRATION_APP_TOKEN,
        "tblvF1h7klsT2TuP",
        "外部校准、检定",
        "",
        "",
    ),
}

# 退役实体（旧 Base 独有、新 Base 已删除的表）
_RETIRED_ENTITY_CODES: tuple[str, ...] = ("qc_instr_change", "qc_instr_assets")

# 新实体插入时的名称/分组/排序（与 DEFAULT_QUALITY_FEISHU_ENTITIES 对齐）
_ENTITY_META: dict[str, tuple[str, str, int]] = {
    "qc_instr_equipment": ("设备数据管理", "仪器管理", 216),
    "qc_instr_maintenance": ("设备维护保养记录", "仪器管理", 217),
    "qc_instr_repair": ("设备维修记录", "仪器管理", 218),
    "qc_instr_contracts": ("设备维保合同", "仪器管理", 219),
    "qc_instr_plans": ("QC检测仪器维护保养周期表", "仪器管理", 220),
    "qc_instr_calibration": ("内校汇总", "仪器管理", 221),
    "qc_instr_cal_plan": ("内部校验计划", "仪器管理", 222),
    "qc_instr_cal_external": ("外部校准、检定", "仪器管理", 223),
}

# 退役菜单（key -> route_path），页面已下线：置 disabled，不删除历史行
_RETIRED_MENUS: tuple[tuple[str, str], ...] = (
    ("quality:inspection:inspection-instruments:inspection-instruments-change",
     "/quality/inspection/instruments/change"),
    ("quality:inspection:inspection-instruments:inspection-instruments-assets",
     "/quality/inspection/instruments/assets"),
)

# 菜单改名（key -> 新名称）
_RENAMED_MENUS: tuple[tuple[str, str], ...] = (
    (
        "quality:inspection:inspection-instruments:inspection-instruments-maintenance",
        "维护保养记录",
    ),
    (
        "quality:inspection:inspection-instruments:inspection-instruments-calibration",
        "内校汇总",
    ),
    (
        "quality:inspection:inspection-instruments:inspection-instruments-contracts",
        "维保合同",
    ),
    (
        "quality:inspection:inspection-instruments:inspection-instruments-plans",
        "维保周期表",
    ),
)

_UPDATE_BINDING_SQL = (
    "UPDATE quality.quality_feishu_entity_settings "
    "SET app_token = :app_token, base_table_id = :table_id, "
    "base_table_name = :table_name, is_enabled = true, "
    "enable_push_to_feishu = true, enable_pull_from_feishu = true, "
    "is_deleted = false, updated_at = now() "
    "WHERE entity_code = :entity_code"
)

_INSERT_SETTING_SQL = (
    "INSERT INTO quality.quality_feishu_entity_settings "
    "(id, entity_code, entity_name, entity_group, sort_order, app_token, "
    " base_table_id, base_table_name, is_enabled, enable_push_to_feishu, "
    " enable_pull_from_feishu, created_at, updated_at, is_deleted) "
    "VALUES (gen_random_uuid(), :entity_code, :entity_name, :entity_group, "
    " :sort_order, :app_token, :table_id, :table_name, true, true, true, "
    " now(), now(), false)"
)

_MENU_TABLE = sa.Table(
    "menus",
    sa.MetaData(),
    sa.Column("key", sa.String),
    sa.Column("name", sa.String),
    sa.Column("route_path", sa.String),
    sa.Column("status", sa.String),
    sa.Column("is_deleted", sa.Boolean),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    schema="identity",
)


def upgrade() -> None:
    bind = op.get_bind()

    for entity_code, (app_token, table_id, table_name, _old_id, _old_name) in (
        _ENTITY_TABLE_MAP.items()
    ):
        result = bind.execute(
            sa.text(_UPDATE_BINDING_SQL).bindparams(
                entity_code=entity_code,
                app_token=app_token,
                table_id=table_id,
                table_name=table_name,
            )
        )
        if result.rowcount:
            continue
        entity_name, entity_group, sort_order = _ENTITY_META[entity_code]
        bind.execute(
            sa.text(_INSERT_SETTING_SQL).bindparams(
                entity_code=entity_code,
                entity_name=entity_name,
                entity_group=entity_group,
                sort_order=sort_order,
                app_token=app_token,
                table_id=table_id,
                table_name=table_name,
            )
        )

    for entity_code in _RETIRED_ENTITY_CODES:
        bind.execute(
            sa.text(
                "UPDATE quality.quality_feishu_entity_settings "
                "SET is_deleted = true, is_enabled = false, updated_at = now() "
                "WHERE entity_code = :entity_code"
            ).bindparams(entity_code=entity_code)
        )

    for menu_key, route_path in _RETIRED_MENUS:
        bind.execute(
            _MENU_TABLE.update()
            .where(
                _MENU_TABLE.c.key == menu_key,
                _MENU_TABLE.c.route_path == route_path,
                _MENU_TABLE.c.status == "active",
                _MENU_TABLE.c.is_deleted.is_(False),
            )
            .values(status="disabled", updated_at=sa.func.now())
        )

    for menu_key, menu_name in _RENAMED_MENUS:
        bind.execute(
            _MENU_TABLE.update()
            .where(
                _MENU_TABLE.c.key == menu_key,
                _MENU_TABLE.c.is_deleted.is_(False),
            )
            .values(name=menu_name, updated_at=sa.func.now())
        )


def downgrade() -> None:
    """回滚到旧 Base 绑定并恢复旧菜单名。

    退役实体与菜单保持退役状态：无法区分"迁移退役"与"管理员主动停用"，
    与原退役迁移一致，需要恢复时由管理员在菜单/设置页显式启用。
    """
    bind = op.get_bind()

    for entity_code, (
        _app_token,
        _table_id,
        _table_name,
        old_table_id,
        old_table_name,
    ) in _ENTITY_TABLE_MAP.items():
        if not old_table_id:
            # 新实体（旧 Base 无对应表）：回滚时软删，避免指向不存在的表
            bind.execute(
                sa.text(
                    "UPDATE quality.quality_feishu_entity_settings "
                    "SET is_deleted = true, is_enabled = false, updated_at = now() "
                    "WHERE entity_code = :entity_code"
                ).bindparams(entity_code=entity_code)
            )
            continue
        bind.execute(
            sa.text(_UPDATE_BINDING_SQL).bindparams(
                entity_code=entity_code,
                app_token=_OLD_APP_TOKEN,
                table_id=old_table_id,
                table_name=old_table_name,
            )
        )

    for menu_key, _new_name in _RENAMED_MENUS:
        old_name = {
            "inspection-instruments-maintenance": "维护保养",
            "inspection-instruments-calibration": "校准计划",
            "inspection-instruments-contracts": "外协合同",
            "inspection-instruments-plans": "年度计划",
        }[menu_key.rsplit(":", 1)[-1]]
        bind.execute(
            _MENU_TABLE.update()
            .where(_MENU_TABLE.c.key == menu_key)
            .values(name=old_name, updated_at=sa.func.now())
        )
