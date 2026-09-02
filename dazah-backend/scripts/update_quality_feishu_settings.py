"""质量模块飞书配置更新：新凭证 + 各组 Base token + 相关表格表映射。

在新线 venv 下运行（写 docker 库 quality schema）。
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.core.database import async_session_factory

NEW_APP_ID = os.environ.get("QUALITY_FEISHU_APP_ID", "cli_aa1fa68e34b89cd4")
# 密钥仅从环境变量注入，禁止硬编码入仓库
NEW_APP_SECRET = os.environ.get("QUALITY_FEISHU_APP_SECRET", "")
if not NEW_APP_SECRET:
    raise SystemExit(
        "请先设置环境变量 QUALITY_FEISHU_APP_SECRET 再运行本脚本"
    )

GROUP_TOKENS = {
    "固体物料检验": "Bz6Eb0cmFactEysOpuocmfwJnWb",
    "液体物料检验": "IRR0bY7fla1HARs0ZT9ce8ShnLf",
    "验证与确认": "EZUib0hvTa7lnfsz9xScjFpAnvc",
    "供应商管理": "Mbi5bHLMnaahEJs8gizcR2CNnTc",
    "偏差管理": "NLQlbJFsjaY37Vs65gyc6VdtnXf",
    "CAPA管理": "NLQlbJFsjaY37Vs65gyc6VdtnXf",
    "OOS/OOT管理": "NLQlbJFsjaY37Vs65gyc6VdtnXf",
    "投诉管理": "NLQlbJFsjaY37Vs65gyc6VdtnXf",
    "退货与召回管理": "NLQlbJFsjaY37Vs65gyc6VdtnXf",
    "部门联系人": "NLQlbJFsjaY37Vs65gyc6VdtnXf",
}

# 相关表格 Base 的表映射：实体名 → table_id
ENTITY_TABLES = {
    "报告记录": "tblFXGZYErT0fpZk",
    "调查推送": "tblizEvuhtSPFDni",
    "偏差台账": "tblPFpceLDpJJHgS",
    "CAPA台账": "tblcZJV469M63HMH",
    "计划跟踪": "tblWJ11KfqZj4SIF",
    "OOSOOT报告记录": "tblKKn5FUtBzzYBI",
    "OOSOOT调查推送记录": "tbldvIRaxdpAInzI",
    "OOS台账": "tblZYOgYW2c2kaol",
    "OOT台账": "tblv1dJiiObbwsrv",
    "产品涉及部门": "tblawcZVRbVbOrgC",
    "投诉台账": "tbl2abeGm2IaFaYU",
    "退货申请表": "tblHLZpklFejOlhm",
    "退回台账": "tbleGUC1m2Mkdp4c",
    "召回台账": "tbleGUC1m2Mkdp4c",
    "验证主计划": "tblQeNmOWMCAaLrX",
    "设备确认": "tblQeNmOWMCAaLrX",
    "工艺验证": "tblQeNmOWMCAaLrX",
    "清洁验证": "tblQeNmOWMCAaLrX",
    "其他验证": "tblQeNmOWMCAaLrX",
}


async def main() -> None:
    async with async_session_factory() as db:
        # 1. 应用凭证更新
        r = await db.execute(
            text(
                "UPDATE quality.quality_feishu_app_settings "
                "SET app_id=:aid, app_secret=:sec, is_enabled=true, "
                "last_test_status=NULL, last_test_error=NULL "
                "RETURNING app_id"
            ),
            {"aid": NEW_APP_ID, "sec": NEW_APP_SECRET},
        )
        print("应用凭证已更新 →", r.scalar())

        # 2. 组级 token + 启用
        for group, token in GROUP_TOKENS.items():
            r = await db.execute(
                text(
                    "UPDATE quality.quality_feishu_entity_settings "
                    "SET app_token=:tok, is_enabled=true "
                    "WHERE entity_group=:g RETURNING entity_code"
                ),
                {"tok": token, "g": group},
            )
            codes = [row[0] for row in r]
            print(f"组[{group}] 配置 {len(codes)} 实体 → {token[:10]}...")

        # 3. 按实体名补 base_table_id（为空时才补）
        for entity_name, table_id in ENTITY_TABLES.items():
            r = await db.execute(
                text(
                    "UPDATE quality.quality_feishu_entity_settings "
                    "SET base_table_id=:tid "
                    "WHERE entity_name=:n "
                    "AND (base_table_id IS NULL OR base_table_id='') "
                    "RETURNING entity_code"
                ),
                {"tid": table_id, "n": entity_name},
            )
            codes = [row[0] for row in r]
            if codes:
                print(f"表映射[{entity_name}] → {table_id}: {codes}")

        await db.commit()

        # 4. 核对输出
        r = await db.execute(
            text(
                "SELECT entity_group, count(*), count(app_token), bool_or(is_enabled) "
                "FROM quality.quality_feishu_entity_settings "
                "GROUP BY entity_group ORDER BY entity_group"
            )
        )
        print("--- 更新后各组状态（实体数/有token/启用）---")
        for row in r:
            print("  ", tuple(row))


asyncio.run(main())
