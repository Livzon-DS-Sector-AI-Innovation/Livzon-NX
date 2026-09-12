"""成品检验切换飞书 Base 并更新子表绑定。

成品检验全部 qc_finished_* 实体（71 个既有 + 味之素 k6 + PF）整体迁移到
新 Base AF0aboP2ka2YmystEDLchTCHnQb（2026-09-11）。DB 配置行
（quality.quality_feishu_entity_settings）优先于代码预填，故必须同步改写
app_token / base_table_id / base_table_name，否则运行期仍会访问旧 Base。
换表后旧同步水线/镜像不再适用，部署后需对成品实体执行一次全量回拉
（scripts/sync_finished_inspection_mirror.py 或页面"同步飞书数据"按钮）。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d400000032"
down_revision: str | None = "c9d400000031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_APP_TOKEN = "AF0aboP2ka2YmystEDLchTCHnQb"
_OLD_APP_TOKEN = "CB1LbgkpGa8hxUsQ8fZcwgpPnUd"

# entity_code -> (新 table_id, 新 Base 表名, 旧 table_id, 旧 Base 表名)
_ENTITY_TABLE_MAP: dict[str, tuple[str, str, str, str]] = {
    "qc_finished_internal": (
        "tblqBNTcL5sAmWPB",
        "霉酚酸（内控）",
        "tblLHGBtnNSTycVW",
        "霉酚酸（内控）",
    ),
    "qc_finished_high_spec": (
        "tblWOnPe70lCMBE6",
        "霉酚酸（高规）",
        "tblxFdgNvgDNBH3Y",
        "霉酚酸（高规）",
    ),
    "qc_finished_mvt": (
        "tblNNSJrS63BvXjS",
        "美伐他汀（DMF）",
        "tbllOn1w98wx62j9",
        "美伐他汀（DMF）",
    ),
    "qc_finished_lft_ep": (
        "tblggX48LPZ0Necu",
        "洛伐他汀（EP）",
        "tblfb12ATBt5fzQn",
        "洛伐他汀（EP）",
    ),
    "qc_finished_lft_usp": (
        "tblzH3FCoIacWbfS",
        "洛伐他汀（USP）",
        "tblFuap3CgPGNVNN",
        "洛伐他汀（USP）",
    ),
    "qc_finished_dor_gb": (
        "tbllcsvK8NSDOFhW",
        "多拉菌素（GB）",
        "tbl2TxHcba13Dgol",
        "多拉菌素（GB）",
    ),
    "qc_finished_dor_vet": (
        "tblHu5WFFaF8rH0d",
        "多拉菌素（兽药）",
        "tbljZItMlTCvpsVR",
        "多拉菌素（兽药）",
    ),
    "qc_finished_fcc14": (
        "tbl6o4MKGzhQ24Ih",
        "FCC14",
        "tblmexymttbNuJGg",
        "FCC14",
    ),
    "qc_finished_usp": (
        "tbl6kEnRNGIMcypl",
        "USP",
        "tblxybI5aqt77ggf",
        "USP",
    ),
    "qc_finished_trp_granule": (
        "tbleN43GUDiAcXNT",
        "色氨酸颗粒",
        "tblFvH1NpacCF5av",
        "色氨酸颗粒",
    ),
    "qc_finished_trp_powder": (
        "tblKvwJRXD7u7GKC",
        "色氨酸粉末",
        "tbl1DY6IuHzn3LHs",
        "色氨酸粉末",
    ),
    "qc_finished_flu_powder": (
        "tblLYvJk3vTTreSp",
        "2%氟苯尼考预混剂",
        "tblNYlmhR82aODYU",
        "2%氟苯尼考预混剂",
    ),
    "qc_finished_fen_powder": (
        "tblOnW5HzHsZQJJ8",
        "5%芬苯达唑粉",
        "tbl8cTBptuFKqxjf",
        "5%芬苯达唑粉",
    ),
    "qc_finished_pure_water": (
        "tblf3dpM2mMrj8uF",
        "纯化水",
        "tblWXddq7Mm5jETP",
        "纯化水",
    ),
    "qc_finished_lkms_vet": (
        "tblCbhBiv7b4rnoE",
        "林可霉素（兽药）",
        "tblTum9YOFjj47TC",
        "林可霉素（兽药）",
    ),
    "qc_finished_crude": (
        "tblEABQ3HfrehXFS",
        "霉酚酸（粗品）",
        "tblRMscJ9eaFV8N8",
        "霉酚酸（粗品）",
    ),
    "qc_finished_bbas_hanguang_k1": (
        "tblJewMM317AsHXQ",
        "汉光（K1）",
        "tblAGoyVIcpbBOZj",
        "汉光（K1）",
    ),
    "qc_finished_bbas_weiduo_k2": (
        "tbltfBKzUdKTqZnP",
        "维多（K2）",
        "tblve2eOf5t9Y71X",
        "维多（K2）",
    ),
    "qc_finished_bbas_changmao_k3": (
        "tblNLiH5w5vaUWpx",
        "常茂（K3）",
        "tbll7UgN84lOt5vR",
        "常茂（K3）",
    ),
    "qc_finished_bbas_jinghai_k4": (
        "tblCnqiYEJjUlLd6",
        "晶海（k4）",
        "tblhIsGioRvTSXow",
        "晶海（k4）",
    ),
    "qc_finished_bbas_xiehe_k5": (
        "tblGGINN48sf6mav",
        "协和（K5）",
        "tblrcXfpw3IBbQpc",
        "协和（K5）",
    ),
    "qc_finished_bbas_weizhisu_k6": (
        "tbl0ZJQ3gmFama1x",
        "味之素（k6）",
        "tblmxRy6iGYhKHwk",
        "味之素（k6）",
    ),
    "qc_finished_bbas_hongshan_k10": (
        "tblXTmzGmuvyelYH",
        "红衫（K10）未做",
        "tblgZPABjiyMCNuO",
        "红衫（K10）未做",
    ),
    "qc_finished_bbas_bafeng_k11": (
        "tblKZ4fMBKSUREDD",
        "八峰（k11）",
        "tbl7ZCKelHNbymba",
        "八峰（k11）",
    ),
    "qc_finished_bbas_haitian_k12": (
        "tblG2ra9gXW49sdA",
        "海天（k12）",
        "tbldWGmEJnlqXAWF",
        "海天（k12）",
    ),
    "qc_finished_bbas_feed_q": (
        "tblXYF4OvY97V8x9",
        "饲料（Q）",
        "tblPhk0sfKvZIDhD",
        "饲料（Q）",
    ),
    "qc_finished_mvt_bt_k1": (
        "tblGeVGGlijwetNQ",
        "BT-K1",
        "tblEOE4dlJ2ERX9u",
        "BT-K1",
    ),
    "qc_finished_mvt_tw_k2": (
        "tblLbisE6ovk6LOh",
        "TW-K2",
        "tblTqssB44WRvjzk",
        "TW-K2",
    ),
    "qc_finished_mvt_zh_k3": (
        "tblqMuCsPr3vSUuN",
        "ZH-K3（未做）",
        "tbllIWEYyTNfAUNP",
        "ZH-K3（未做）",
    ),
    "qc_finished_mvt_tapi_k5": (
        "tblmR9BiIZMLRYBV",
        "TAPI-K5",
        "tblGkFOmlskC9Qoo",
        "TAPI-K5",
    ),
    "qc_finished_lft_lp_k3": (
        "tblB5Yb7ncGkuB93",
        "LP-K3",
        "tblVyUJTYFZ4c0bf",
        "LP-K3",
    ),
    "qc_finished_lft_tapi_k4": (
        "tbl2DSG2rwgZFHOT",
        "TAPI-K4",
        "tblsuSGLP8m3ZDg0",
        "TAPI-K4",
    ),
    "qc_finished_lft_gn_k6": (
        "tblDZ7EP9r4t2nlU",
        "GN-K6",
        "tbl0vEUeypHl244b",
        "GN-K6",
    ),
    "qc_finished_lft_jingxin_k7": (
        "tblPhpC87mdwRCCB",
        "京新-K7",
        "tbldchgRe5BXJwZT",
        "京新-K7",
    ),
    "qc_finished_lft_jb_k9": (
        "tblaf2D8RQ8ED6eQ",
        "JB-K9",
        "tblynYofqJLU99Lc",
        "JB-K9",
    ),
    "qc_finished_lft_jinbao_k10": (
        "tbld4qecyx8MWrR3",
        "金宝-K10",
        "tbl7JvQADKLIKinx",
        "金宝-K10",
    ),
    "qc_finished_lft_lp_crude_k11": (
        "tblxo9BVuSaoBWxj",
        "LP粗品-K11",
        "tbl0n3yArcxpcaro",
        "LP粗品-K11",
    ),
    "qc_finished_dls_norbrook_k2": (
        "tblDRqQ67E223d1Z",
        "Norbrook-K2",
        "tblhPMV6eBRPVXau",
        "Norbrook-K2",
    ),
    "qc_finished_dls_zenex_k10": (
        "tblZsdO0KKJyvGRF",
        "Zenex-K10",
        "tblAL9qgbAdC5jaO",
        "Zenex-K10",
    ),
    "qc_finished_dls_microsules_k6": (
        "tblOBYBPWhHmDHVX",
        "Microsules-K6",
        "tblC9y7KOFMgCV8V",
        "Microsules-K6",
    ),
    "qc_finished_dls_elanco_kr_k11": (
        "tblPe3Us5bpE47sL",
        "Elanco韩国-K11",
        "tblvc7VhgQK5B0vu",
        "Elanco韩国-K11",
    ),
    "qc_finished_dls_adwia_k12": (
        "tblTr49wDPWx6eOp",
        "ADWIA-K12",
        "tblpjHrHjlKoo2Rc",
        "ADWIA-K12",
    ),
    "qc_finished_dls_qilu_k13": (
        "tblhP1wmbqKEjcc5",
        "齐鲁动保-K13",
        "tblOjgHWDFCvAUK1",
        "齐鲁动保-K13",
    ),
    "qc_finished_dls_eurofarwa_k14": (
        "tblJ7DNBED84r0gi",
        "EUROFARWA-K14",
        "tblJACySZwYlCN21",
        "EUROFARWA-K14",
    ),
    "qc_finished_dls_msd_k15": (
        "tblx9N4ajDyy77xc",
        "MSD-K15",
        "tblGHeQUhyGr1jb3",
        "MSD-K15",
    ),
    "qc_finished_dls_haoze_k16": (
        "tblZcldAaXyAdt5O",
        "昊泽-K16",
        "tblcLJFhuT6Va6KQ",
        "昊泽-K16",
    ),
    "qc_finished_dls_vetni_k17": (
        "tblqobizVPPvBbzH",
        "Vetni-K17",
        "tblshNVhBoViP4b0",
        "Vetni-K17",
    ),
    "qc_finished_dls_eva_k18": (
        "tbl7LaJcKiuW5xZd",
        "EVA-K18",
        "tblRDedoJTvZ3Ljm",
        "EVA-K18",
    ),
    "qc_finished_dls_cronus_k19": (
        "tbldJRt0AFquanUF",
        "Cronus-K19",
        "tblwz5Jqul5FkNyA",
        "Cronus-K19",
    ),
    "qc_finished_mpa_tapi_k1": (
        "tblWpBWVe1ZSdzz8",
        "TAPI-K1",
        "tblzs67J6sQv1v7Z",
        "TAPI-K1",
    ),
    "qc_finished_mpa_emcure_k2": (
        "tblt5MyX6f7LoGgF",
        "Emcure-K2",
        "tbl8EgiHi5JvMI2D",
        "Emcure-K2",
    ),
    "qc_finished_mpa_rakshit_k3": (
        "tblL9tpwDDslFWy9",
        "RAKSHIT-K3",
        "tblvGhcNpp0bXTts",
        "RAKSHIT-K3",
    ),
    "qc_finished_mpa_apotex_k4": (
        "tblFSzbw5UeQlb3w",
        "APOTEX-K4",
        "tblIzMJ2Cs1Olzqn",
        "APOTEX-K4",
    ),
    "qc_finished_mpa_sloara_k6": (
        "tblDeg3cfkx6eJ8b",
        "Sloara-K6",
        "tblah6pn1ErmsNS6",
        "Sloara-K6",
    ),
    "qc_finished_mpa_concord_k7": (
        "tblSFULKsqlmQxYo",
        "Concord-K7",
        "tbld8O1fTubJRuNG",
        "Concord-K7",
    ),
    "qc_finished_mpa_concord_high_spec_k11": (
        "tblOfXVUreGJxcuT",
        "Concord高规-K11",
        "tbl3VPwVSgAqAbGw",
        "Concord高规-K11",
    ),
    "qc_finished_mpa_taiwan_china_k12": (
        "tbl1Q65Nvoc2XfdT",
        "台湾中化-K12",
        "tblNkvOo2kg7KRvn",
        "台湾中化-K12",
    ),
    "qc_finished_mpa_biocon_k13": (
        "tbl3pUrikw8xVSbe",
        "Biocon-K13",
        "tblzzr6xEKXzuXSj",
        "Biocon-K13",
    ),
    "qc_finished_mpa_fis_k15": (
        "tblsty5ITrQabct4",
        "FIS-K15",
        "tblk4cY4V8rmsrn8",
        "FIS-K15",
    ),
    "qc_finished_mpa_dasami_k14": (
        "tbleknNYxaBebkd7",
        "Dasami-K14",
        "tblAjsxrRrr31l2v",
        "Dasami-K14",
    ),
    "qc_finished_mpa_intas_k16": (
        "tblD7J1XE264ptwF",
        "Intas-K16",
        "tblvAhPgp4Ezdjbr",
        "Intas-K16",
    ),
    "qc_finished_lkms_internal": (
        "tbl3IzD32icgXFcU",
        "林可霉素内控-未做",
        "tbla0qYIg56AIa3F",
        "林可霉素内控-未做",
    ),
    "qc_finished_lkms_usp": (
        "tblXXONRRbdALt33",
        "林可霉素USP",
        "tblPODoZLCCtUQq8",
        "林可霉素USP",
    ),
    "qc_finished_lkms_k1": (
        "tbl6NLbSm53lCly6",
        "林可霉素K1",
        "tblQJNON5Nw4Glgw",
        "林可霉素K1",
    ),
    "qc_finished_lkms_k2": (
        "tbl4Agh3BDniZAg6",
        "林可霉素K2",
        "tblnAN35kgthjE2G",
        "林可霉素K2",
    ),
    "qc_finished_lkms_k3": (
        "tbldK93NpTU8CWk5",
        "林可霉素K3",
        "tblyKfZLWfV8Nfco",
        "林可霉素 K3",
    ),
    "qc_finished_boiler_water": (
        "tblOXTsCsaH7aNeu",
        "锅炉水",
        "tbldfvO2te01xsws",
        "锅炉水",
    ),
    "qc_finished_lkms_ep": (
        "tblSxeQEFOhfA2y4",
        "林可霉素（EP）",
        "tbljSra2VKUGCe12",
        "林可霉素（EP）",
    ),
    "qc_finished_pf": (
        "tblTqwQqRq9PjVYU",
        "PF",
        "tblIWylGRweSu9a0",
        "PF",
    ),
    "qc_finished_drink_water": (
        "tblTj8TPewzMGrHY",
        "饮用水",
        "tblEX9Bc8P6Ca04e",
        "饮用水",
    ),
    "qc_finished_bbas_jiuling_k7": (
        "tblT42rhDtE73HPB",
        "久凌（K7）",
        "tblvFqlwWnepXFtD",
        "久凌（K7）",
    ),
    "qc_finished_bbas_jirong_k8": (
        "tblb4jP6cV6QqotV",
        "冀荣（k8）",
        "tblOTjIv3onxL15u",
        "冀荣（k8）",
    ),
    "qc_finished_bbas_yuanda_k9": (
        "tbl9pHECCnCN4UbT",
        "远大（K9）",
        "tbluIp6Lk0ohzQlq",
        "远大（K9）",
    ),
}

_UPDATE_SQL = (
    "UPDATE quality.quality_feishu_entity_settings "
    "SET app_token = :app_token, base_table_id = :table_id, "
    "base_table_name = :table_name, updated_at = now() "
    "WHERE entity_code = :entity_code"
)


def upgrade() -> None:
    bind = op.get_bind()
    for entity_code, (table_id, table_name, _old_id, _old_name) in (
        _ENTITY_TABLE_MAP.items()
    ):
        bind.execute(
            sa.text(_UPDATE_SQL).bindparams(
                entity_code=entity_code,
                app_token=_NEW_APP_TOKEN,
                table_id=table_id,
                table_name=table_name,
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    for entity_code, (_new_id, _new_name, old_id, old_name) in (
        _ENTITY_TABLE_MAP.items()
    ):
        bind.execute(
            sa.text(_UPDATE_SQL).bindparams(
                entity_code=entity_code,
                app_token=_OLD_APP_TOKEN,
                table_id=old_id,
                table_name=old_name,
            )
        )
