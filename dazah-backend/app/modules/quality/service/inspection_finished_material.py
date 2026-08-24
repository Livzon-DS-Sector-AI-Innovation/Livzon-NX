"""Inspection Feishu pages service - finished product and material inspection.

成品检验 (finished product) / 固体/液体物料检验 sub-modules.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.modules.quality.service import quality_feishu_sync as feishu_sync_service
from app.modules.quality.service.inspection_helpers import (
    _get_feishu_one,
    _list_feishu,
    _pull_count,
)
from app.modules.quality.service.quality_feishu_material_groups import (
    MATERIAL_ENTITY_LABELS,
    MATERIAL_GROUP_ENTITY_MAP,
)
from app.modules.quality.service.quality_feishu_pages import (
    _resolve_runtime_entity,
)
from app.modules.quality.service.quality_feishu_settings import (
    ensure_quality_feishu_entity_settings,
)
from app.platform.integrations.feishu.bitable import BitableClient

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
#  成品检验 (finished product)
# ═══════════════════════════════════════════

# 成品检验各飞书子表字段并不一致，必须按实体分别映射，不能共用一套通用字段。
FINISHED_PRODUCT_GROUP_ENTITY_MAP: dict[str, list[str]] = {
    "bbas": [
        "qc_finished_fcc14",
        "qc_finished_usp",
        "qc_finished_bbas_hanguang_k1",
        "qc_finished_bbas_weiduo_k2",
        "qc_finished_bbas_changmao_k3",
        "qc_finished_bbas_jinghai_k4",
        "qc_finished_bbas_xiehe_k5",
        "qc_finished_bbas_jiuling_k7",
        "qc_finished_bbas_jirong_k8",
        "qc_finished_bbas_yuanda_k9",
        "qc_finished_bbas_hongshan_k10",
        "qc_finished_bbas_bafeng_k11",
        "qc_finished_bbas_haitian_k12",
        "qc_finished_bbas_feed_q",
    ],
    "mvt": [
        "qc_finished_mvt",
        "qc_finished_mvt_bt_k1",
        "qc_finished_mvt_tw_k2",
        "qc_finished_mvt_zh_k3",
        "qc_finished_mvt_tapi_k5",
    ],
    "lft": [
        "qc_finished_lft_ep",
        "qc_finished_lft_usp",
        "qc_finished_lft_lp_k3",
        "qc_finished_lft_tapi_k4",
        "qc_finished_lft_gn_k6",
        "qc_finished_lft_jingxin_k7",
        "qc_finished_lft_jb_k9",
        "qc_finished_lft_jinbao_k10",
        "qc_finished_lft_lp_crude_k11",
    ],
    "dls": [
        "qc_finished_dor_gb",
        "qc_finished_dor_vet",
        "qc_finished_dls_norbrook_k2",
        "qc_finished_dls_zenex_k10",
        "qc_finished_dls_microsules_k6",
        "qc_finished_dls_elanco_kr_k11",
        "qc_finished_dls_adwia_k12",
        "qc_finished_dls_qilu_k13",
        "qc_finished_dls_eurofarwa_k14",
        "qc_finished_dls_msd_k15",
        "qc_finished_dls_haoze_k16",
        "qc_finished_dls_vetni_k17",
        "qc_finished_dls_eva_k18",
        "qc_finished_dls_cronus_k19",
    ],
    "mpa": [
        "qc_finished_internal",
        "qc_finished_high_spec",
        "qc_finished_mpa_tapi_k1",
        "qc_finished_mpa_emcure_k2",
        "qc_finished_mpa_rakshit_k3",
        "qc_finished_mpa_apotex_k4",
        "qc_finished_mpa_sloara_k6",
        "qc_finished_mpa_concord_k7",
        "qc_finished_mpa_concord_high_spec_k11",
        "qc_finished_mpa_taiwan_china_k12",
        "qc_finished_mpa_biocon_k13",
        "qc_finished_mpa_dasami_k14",
        "qc_finished_mpa_fis_k15",
        "qc_finished_mpa_intas_k16",
        "qc_finished_crude",
    ],
    "lkms": [
        "qc_finished_lkms_vet",
        "qc_finished_lkms_ep",
        "qc_finished_lkms_internal",
        "qc_finished_lkms_usp",
        "qc_finished_lkms_k1",
        "qc_finished_lkms_k2",
        "qc_finished_lkms_k3",
    ],
    "formulations": ["qc_finished_flu_powder", "qc_finished_fen_powder"],
    "water": [
        "qc_finished_pure_water",
        "qc_finished_drink_water",
        "qc_finished_boiler_water",
    ],
    "tryptophan": ["qc_finished_trp_powder", "qc_finished_trp_granule"],
}

FINISHED_ENTITY_LABELS: dict[str, str] = {
    "qc_finished_fcc14": "FCC14",
    "qc_finished_usp": "USP",
    "qc_finished_bbas_hanguang_k1": "汉光（K1）",
    "qc_finished_bbas_weiduo_k2": "维多（K2）",
    "qc_finished_bbas_changmao_k3": "常茂（K3）",
    "qc_finished_bbas_jinghai_k4": "晶海（k4）",
    "qc_finished_bbas_xiehe_k5": "协和（K5）",
    "qc_finished_bbas_jiuling_k7": "久凌（K7）",
    "qc_finished_bbas_jirong_k8": "冀荣（k8）",
    "qc_finished_bbas_yuanda_k9": "远大（K9）",
    "qc_finished_bbas_hongshan_k10": "红衫（K10）未做",
    "qc_finished_bbas_bafeng_k11": "八峰（k11）",
    "qc_finished_bbas_haitian_k12": "海天（k12）",
    "qc_finished_bbas_feed_q": "饲料（Q）",
    "qc_finished_internal": "霉酚酸（内控）",
    "qc_finished_high_spec": "霉酚酸（高规）",
    "qc_finished_crude": "霉酚酸（粗品）",
    "qc_finished_mvt": "美伐他汀（DMF）",
    "qc_finished_mvt_bt_k1": "BT-K1",
    "qc_finished_mvt_tw_k2": "TW-K2",
    "qc_finished_mvt_zh_k3": "ZH-K3（未做）",
    "qc_finished_mvt_tapi_k5": "TAPI-K5",
    "qc_finished_lft_ep": "洛伐他汀（EP）",
    "qc_finished_lft_usp": "洛伐他汀（USP）",
    "qc_finished_lft_lp_k3": "LP-K3",
    "qc_finished_lft_tapi_k4": "TAPI-K4",
    "qc_finished_lft_gn_k6": "GN-K6",
    "qc_finished_lft_jingxin_k7": "京新-K7",
    "qc_finished_lft_jb_k9": "JB-K9",
    "qc_finished_lft_jinbao_k10": "金宝-K10",
    "qc_finished_lft_lp_crude_k11": "LP粗品-K11",
    "qc_finished_dor_gb": "多拉菌素（GB）",
    "qc_finished_dor_vet": "多拉菌素（兽药）",
    "qc_finished_dls_norbrook_k2": "Norbrook-K2",
    "qc_finished_dls_zenex_k10": "Zenex-K10",
    "qc_finished_dls_microsules_k6": "Microsules-K6",
    "qc_finished_dls_elanco_kr_k11": "Elanco韩国-K11",
    "qc_finished_dls_adwia_k12": "ADWIA-K12",
    "qc_finished_dls_qilu_k13": "齐鲁动保-K13",
    "qc_finished_dls_eurofarwa_k14": "EUROFARWA-K14",
    "qc_finished_dls_msd_k15": "MSD-K15",
    "qc_finished_dls_haoze_k16": "昊泽-K16",
    "qc_finished_dls_vetni_k17": "Vetni-K17",
    "qc_finished_dls_eva_k18": "EVA-K18",
    "qc_finished_dls_cronus_k19": "Cronus-K19",
    "qc_finished_mpa_tapi_k1": "TAPI-K1",
    "qc_finished_mpa_emcure_k2": "Emcure-K2",
    "qc_finished_mpa_rakshit_k3": "RAKSHIT-K3",
    "qc_finished_mpa_apotex_k4": "APOTEX-K4",
    "qc_finished_mpa_sloara_k6": "Sloara-K6",
    "qc_finished_mpa_concord_k7": "Concord-K7",
    "qc_finished_mpa_concord_high_spec_k11": "Concord高规-K11",
    "qc_finished_mpa_taiwan_china_k12": "台湾中化-K12",
    "qc_finished_mpa_biocon_k13": "Biocon-K13",
    "qc_finished_mpa_dasami_k14": "Dasami-K14",
    "qc_finished_mpa_fis_k15": "FIS-K15",
    "qc_finished_mpa_intas_k16": "Intas-K16",
    "qc_finished_lkms_ep": "林可霉素（EP）",
    "qc_finished_lkms_vet": "林可霉素（兽药）",
    "qc_finished_lkms_internal": "林可霉素内控-未做",
    "qc_finished_lkms_usp": "林可霉素USP",
    "qc_finished_lkms_k1": "林可霉素K1",
    "qc_finished_lkms_k2": "林可霉素K2",
    "qc_finished_lkms_k3": "林可霉素K3",
    "qc_finished_flu_powder": "2%氟苯尼考预混剂",
    "qc_finished_fen_powder": "5%芬苯达唑粉",
    "qc_finished_pure_water": "纯化水",
    "qc_finished_drink_water": "饮用水",
    "qc_finished_boiler_water": "锅炉水",
    "qc_finished_trp_powder": "色氨酸粉末",
    "qc_finished_trp_granule": "色氨酸颗粒",
}

FINISHED_ENTITY_FIELDS: dict[str, list[str]] = {
    "qc_finished_fcc14": [
        "批号",
        "年",
        "月",
        "日",
        "有效期",
        "包装规格",
        "数量",
        "性状:无色或白色片状晶体或白色结晶性粉末",
        "酸度（pH）：5.4-6.0",
        "鉴别：样品与对照品在相同波长处有最大吸收",
        "含量（干燥品计）：98.5%-101.5%",
        "干燥失重：≤0.2%",
        "比旋度：-33.2°~-35.2°",
        "炽灼残渣（硫酸灰分）：≤0.1%",
        "重金属（以Pb计）：≤10ppm",
        "铅：≤5ppm",
        "报告日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_usp": [
        "批号",
        "年",
        "月",
        "日",
        "有效期",
        "包装规格kg/Bag",
        "数量kg",
        "性状:白色无味结晶体。略溶于水，极微溶于甲醇、乙醇、稀的无机酸。",
        "酸度（pH）：5.4-6.0",
        "鉴别：样品与对照品在相同波长处有最大吸收",
        "含量（干燥品计）：98.5%-101.5%",
        "干燥失重：≤0.2%",
        "比旋度：-32.7~-34.7°",
        "炽灼残渣（硫酸灰分）：≤0.4%",
        "重金属（以Pb计）：≤15ppm",
        "氯化物：≤500ppm",
        "硫酸盐：≤300ppm",
        "铁：≤30ppm",
        "色谱纯度",
        "报告日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_internal": [
        "批号",
        "年",
        "月",
        "日",
        "复验期",
        "kg/Drum",
        "Drum",
        "+kg/Drum",
        "XDrum",
        "批量kg",
        "外观:白色或类白色结晶 性粉末",
        "溶解性:溶于甲醇、丙酮、二氯甲烷、略溶于乙酸乙酯，且溶液澄清，不溶于水。",
        "IR:样品图谱与对照品图谱一致",
        "HPLC:样品与对照品主峰保留时间一致",
        "干燥失重:≤0.50%",
        "熔点:140.0~144.0℃",
        "炽灼残渣:≤0.10%",
        "重金属:≤20ppm",
        "总杂质:≤1.00%",
        "最大单一杂质:≤0.50%",
        "含量（干品）:97.0%-103.0%",
        "乙酸丁酯:≤2000ppm",
        "出报日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_high_spec": [
        "批号",
        "年",
        "月",
        "日",
        "复验期",
        "kg/Drum",
        "Drum",
        "+kg/Drum",
        "XDrum",
        "批量kg",
        "外观:白色或类白色结晶性粉末",
        "溶解性:溶于甲醇、丙酮、二氯甲烷、略溶于乙酸乙酯，且溶液澄清，不溶于水。",
        "IR:样品图谱与对照品图谱一致",
        "HPLC:样品与对照品主峰保留时间一致",
        "干燥失重:≤0.50%",
        "熔点:140.0-144.0℃",
        "炽灼残渣:≤0.10%",
        "重金属:≤20ppm",
        "总杂质:≤0.70%",
        "最大单一杂质:≤0.070%",
        "含量（干品）:98.0%-102.0%",
        "乙酸丁酯:≤2000ppm",
        "出报日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_crude": [
        "批号",
        "年",
        "月",
        "日",
        "复验期",
        "kg/Bag",
        "Bag",
        "+kg/Bag",
        "XBag",
        "批量g",
        "外观:类白色至棕色干粉",
        "HPLC:样品与对照品主峰保留时间一致",
        "干燥失重:≤10.00%",
        "色谱纯度：≥90.0%",
        "含量:≥70%",
        "出报日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_mvt": [
        "批号",
        "年",
        "月",
        "日",
        "复验期",
        "kg/Drum",
        "Drum",
        "+kg/Drum",
        "×Drum",
        "数量kg",
        "性状：白色至浅黄色晶体或结晶性粉末",
        "溶解性：易溶于氯仿，略溶于甲醇",
        "HPLC：主峰与对照品主峰的保留时间一致。",
        "IR：IR图谱与对照品图谱一致。",
        "UV：UV图谱与对照品图谱一致。",
        "比旋度（按干燥品计算）：+265°~ +290°",
        "干燥失重：≤0.5%",
        "炽灼残渣：≤0.1%",
        "重金属：≤20ppm",
        "总杂质：≤3.0%",
        "单一最大杂质：≤0.6%",
        "脱水美伐他汀：≤2.0%",
        "杂质A：≤0.15%",
        "含量（干品）：≥95.0%",
        "丙酮：≤2000ppm",
        "正己烷：≤290ppm",
        "甲苯：≤89ppm",
        "报告日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_lft_ep": [
        "批号",
        "年",
        "月",
        "日",
        "复验期",
        "kg/Drum",
        "Drum",
        "+kg/Drum",
        "XDrum",
        "数量kg",
        "外观：白色或类白色结晶性粉末",
        "溶解性：几乎不溶于水，溶于丙酮，微溶于乙醇；2023.06.25变更为（几乎不溶于水，溶于丙酮，略溶于无水乙醇）",
        "鉴别A（比旋度）：应符合规定",
        "鉴别B（IR）：红外光谱图应与对照品图谱一致",
        "比旋度（无水物）：‘＋325°～＋340°",
        "水分：≤0.5%",
        "硫酸盐灰分：≤0.2%",
        "杂质E（4，4a二氢洛伐他汀）：≤0.5%",
        "杂质A（美伐他汀）：≤0.3%",
        "杂质B（羟基酸洛伐他汀）：≤0.3%",
        "杂质C（脱水洛伐他汀）：≤0.3%",
        "杂质D（洛伐他汀二聚物）：≤0.3%",
        "杂质F：≤0.15%",
        "总杂质：≤1.0%",
        "未知杂质：≤0.10%",
        "含量（无水物）：97.0%～102.0%",
        "丙酮：≤5000ppm",
        "甲苯：≤890ppm",
        "报告日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_lft_usp": [
        "批号",
        "年",
        "月",
        "日",
        "复验期",
        "kg/Drun",
        "Drum",
        "+kg/Drum",
        "XDrum",
        "数量kg",
        "性状：白色至类白色结晶性粉末。",
        "IR：IR图谱与对照品图谱一致。",
        "UV：UV图谱与对照品图谱一致",
        "比旋度（按无水计）：+324°~+338°",
        "干燥失重：≤0.3%",
        "炽灼残渣：≤0.2%",
        "重金属：≤0.002%",
        "有关物质A：≤0.5%",
        "其他单一杂质：≤0.2%",
        "总有关杂质：≤1.0%",
        "含量（干品）：98.5%~101.0%",
        "丙酮：≤5000ppm",
        "甲苯：≤890ppm",
        "父记录",
        "报告日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_dor_gb": [
        "批号",
        "年",
        "月",
        "日",
        "复验期",
        "kg/Drun",
        "Drum",
        "+kg/Drum",
        "XDrum",
        "数量kg",
        "性状：白色或类白色结晶性粉末。",
        "HPLC：样品主峰与对照品主峰的保留时间一致。",
        "IR：IR图谱与对照品图谱一致。",
        "比旋度（按无水计）：+55°~ +65°",
        "溶液澄清度与颜色：溶液应澄清且颜色深度不超过参比溶液BY6 。",
        "水分：≤3.0%",
        "炽灼残渣：≤0.1%",
        "杂质2：≤1.0%",
        "杂质3：≤1.2%",
        "杂质4：≤0.5%",
        "杂质5：≤0.5%",
        "杂质6：≤0.50%",
        "杂质7：≤0.8%",
        "其他单个杂质：≤0.50%",
        "总杂质：≤5.0%",
        "含量（按无水计）：95.0%~102.0%",
        "BHT：200~1000ppm",
        "甲醇：≤3000ppm",
        "乙醇：≤5000ppm",
        "丙酮：≤5000ppm",
        "需氧菌总数 ≤1000cfu/g",
        "霉菌酵母菌数：≤100cfu/g",
        "大肠埃希菌：不得检出（1g）",
        "报告日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_dor_vet": [
        "批号",
        "年",
        "月",
        "日",
        "有效期",
        "kg/桶",
        "桶",
        "+kg/桶",
        "X桶",
        "数量kg",
        "性状：本品为白色或类白色结晶性粉末，无臭，有引湿性。",
        "本品在三氯甲烷、甲醇中溶解，在水中极微溶解",
        "比旋度：+58°~+63°",
        "UV：在245nm 的波长处有最大吸收",
        "HPLC：在含量测定项下记录的色谱图中，供试品溶液主峰的保留时间应与对照品溶液主峰的保留时间一致。",
        "溶液的澄清度与颜色：溶液应澄清无色；如显混浊，与1号浊度标准液比较，不得更浓；如显色，与黄绿色5号标准比色液比较，不得更深。",
        "阿维菌素：≤3.0%",
        "总杂质：≤5.0%",
        "水分：≤3.0%",
        "炽灼残渣：≤0.5%",
        "重金属：≤20ppm",
        "甲醇：≤3000ppm",
        "乙醇：≤5000ppm",
        "丙酮：≤5000ppm",
        "含量测定（按无水物计算）：≥95.0%",
        "需氧菌总数：≤1000cfu/g",
        "霉菌酵母菌数：≤100cfu/g",
        "大肠埃希菌：不得检出（1g） (1)",
        "报告日期",
        "报告单号",
        "报告单",
        "霉菌酵母菌数：≤100cfu/g (1)",
        "大肠埃希菌：不得检出（1g）",
        "报告日期 (1)",
        "报告单号 (1)",
        "报告单 (1)",
    ],
    "qc_finished_lkms_vet": [
        "批号",
        "年",
        "月",
        "日",
        "有效期",
        "十亿/桶",
        "kg/桶",
        "十亿",
        "kg",
        "本品为白色 结晶性粉末，有微臭或特殊臭",
        "HPLC:在含量测定项下记录的色谱图中，供试品溶液主峰的保留时间应与对照品溶液主峰的保留时间一致",
        "IR: 本品的IR图谱应与林可霉素对照品的图谱一致",
        "氯化物反应:本品的水溶液显氯化物鉴别（1）的反应",
        "结晶性:呈双折射和消光位现象",
        "酸度:PH值应为3.0-5.5",
        "溶液澄清度与颜色:溶液应澄清无色；如显混浊，与1号浊度标准液比较，不得更浓；如显色，与黄绿色5号标准比色液比较，不得更深。",
        "其它单一最大杂质:≤1.0%",
        "总杂质:≤2.0%",
        "林可霉素:B≤5.0%",
        "水分:3.0%-6.0%",
        "炽灼残渣:≤0.5%",
        "细菌内毒素:＜0.50EU/mg",
        "丙酮:≤2000ppm",
        "仲辛醇:≤500ppm",
        "含量测定:≥82.5%",
        "报告日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_lkms_ep": [
        "批号",
        "年",
        "月",
        "日",
        "复验期",
        "kg/Drum",
        "Drum",
        "+kg/Drum",
        "X Drum",
        "数量kg",
        "外观：白色或类白色结晶性粉末",
        "溶解性：极易溶于水，微溶于乙醇（96%），极微溶于丙酮",
        "IR：本品的IR图谱与对照品图谱一致",
        "氯化物反应：水溶液显氯化物的鉴别反应",
        "溶液外观：溶液应澄清，不得比对照液Y6颜色更深",
        "pH：3.5-5.5",
        "比旋度：135°-150°",
        "杂质A：≤0.5%",
        "杂质B：≤0.5%",
        "杂质C：≤0.2%",
        "未知杂质：≤0.10%",
        "总杂质：≤2.0%",
        "水分：3.1%-4.6%",
        "硫酸盐灰分：≤0.5%",
        "细菌内毒素：＜0.50IU/mg",
        "含量：96.0%~102.0%（无水物）",
        "林可霉素B：≤5.0%",
        "丙酮：≤2000ppm",
        "仲辛醇：≤500ppm",
        "报告日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_lkms_internal": [
        "批号",
        "年",
        "月",
        "日",
        "复验期",
        "BOU/Drum",
        "kg/Drum",
        "BOU",
        "kg",
        "外观：白色或类白色结晶性粉末。无臭或有微弱气味。",
        "溶解性：极易溶于水，溶于二甲基甲酰胺，微溶于乙醇（96%），极微溶于丙酮。",
        "粒度分布：40目筛100%通过。",
        "IR：IR图谱与对照品图谱一致",
        "氯化物反应：水溶液显氯化物的鉴别反应",
        "溶液外观：溶液应澄清，不得比对照液Y6颜色更深",
        "pH：3.5-5.5",
        "比旋度：+135°-+150°",
        "结晶性",
        "杂质A：≤0.5%",
        "杂质B：≤0.5%",
        "杂质C：≤0.2%",
        "未知杂质：≤0.10%",
        "总杂质：≤2.0%",
        "水分：3.1%-4.6%",
        "硫酸盐灰分：≤0.5%",
        "细菌内毒素：＜0.50IU/mg",
        "≥790ug/mg",
        "96.0%~102.0%",
        "林可霉素B：≤5.0%",
        "丙酮：≤2000ppm",
        "仲辛醇：≤500ppm",
        "报告日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_lkms_usp": [
        "批号",
        "年",
        "月",
        "日",
        "复验期",
        "kg/Drum",
        "Drum",
        "+kg/Drum",
        "X Drum",
        "数量kg",
        "外观：白色或类白色结晶性粉末；无臭或有微弱气味。",
        "溶解性：极易溶于水，溶于二甲基甲酰胺，极微溶于丙酮",
        "IR：本品的IR图谱与对照品图谱一致",
        "比旋度：135°-150°",
        "结晶性：符合规定",
        "pH：3.0-5.5",
        "水分：3.0%-6.0%",
        "林可霉素B：≤5.0%",
        "细菌内毒素：＜0.50EU/mg",
        "含量：≥790ug/mg",
        "丙酮：≤2000ppm",
        "仲辛醇：≤500ppm",
        "报告日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_lkms_k1": [
        "批号",
        "年",
        "月",
        "日",
        "有效期",
        "十亿/桶",
        "kg/桶",
        "十亿",
        "kg",
        "本品为白色 结晶性粉末，有微臭或特殊臭，在水或甲醇中易溶，在乙醇中略溶。",
        "HPLC:在含量测定项下记录的色谱图中，供试品溶液主峰的保留时间应与对照品溶液主峰的保留时间一致",
        "IR：IR图谱应与林可霉素对照品的图谱一致",
        "氯化物反应:本品的水溶液显氯化物鉴别（1）的反应",
        "结晶性:呈双折射和消光位现象",
        "比旋度：135-150°",
        "酸度:PH值应为3.0-5.5",
        "溶液澄清度与颜色:溶液应澄清无色；如显混浊，与1号浊度标准液比较，不得更浓；如显色，与黄绿色5号标准比色液比较，不得更深。",
        "粒度（20目）：100%",
        "其它单一最大杂质:≤1.0%",
        "总杂质:≤2.0%",
        "林可霉素:B≤5.0%",
        "水分:3.1%-4.6%",
        "炽灼残渣:≤0.5%",
        "重金属：≤0.002%",
        "砷盐：≤0.0002%",
        "细菌内毒素:＜0.50EU/mg",
        "丙酮:≤5000ppm",
        "仲辛醇:≤500ppm",
        "含量测定:≥82.5%",
        "含量：≥790ug/mg",
        "报告日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_lkms_k2": [
        "批号",
        "年",
        "月",
        "日",
        "有效期",
        "十亿/桶",
        "kg/桶",
        "十亿",
        "kg",
        "本品为白色 结晶性粉末，有微臭或特殊臭，在水或甲醇中易溶，在乙醇中略溶",
        "HPLC:在含量测定项下记录的色谱图中，供试品溶液主峰的保留时间应与对照品溶液主峰的保留时间一致",
        "IR: IR图谱应与林可霉素对照品的图谱一致",
        "氯化物反应:本品的水溶液显氯化物鉴别（1）的反应",
        "结晶性:呈双折射和消光位现象",
        "粒度：应全部通过60目筛。",
        "酸度:PH值应为3.0-5.5",
        "溶液澄清度与颜色:溶液应澄清无色；如显混浊，与1号浊度标准液比较，不得更浓；如显色，与黄绿色5号标准比色液比较，不得更深。",
        "其它单一最大杂质:≤1.0%",
        "总杂质:≤2.0%",
        "林可霉素:B≤5.0%",
        "水分:3.0%-6.0%",
        "炽灼残渣:≤0.5%",
        "细菌内毒素:＜0.50EU/mg",
        "丙酮:≤2000ppm",
        "仲辛醇:≤500ppm",
        "含量测定:≥82.5%",
        "报告日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_lkms_k3": [
        "批号",
        "年",
        "月",
        "日",
        "复验期",
        "BOU/桶",
        "kg/桶",
        "BOU",
        "KG",
        "外观：白色或类白色结晶性粉末",
        "溶解性：极易溶于水，微溶于乙醇（96%），极微溶于丙酮",
        "IR：IR图谱与对照品图谱一致",
        "氯化物反应：水溶液显氯化物的鉴别反应",
        "溶液外观：溶液应澄清，不得比对照液Y6颜色更深",
        "pH：3.5-5.5",
        "比旋度：135°-150°",
        "杂质A：≤0.5%",
        "杂质B：≤0.5%",
        "杂质C：≤0.2%",
        "未知杂质：≤0.10%",
        "总杂质：≤2.0%",
        "水分：3.1%-4.6%",
        "重金属≤10ppm",
        "硫酸盐灰分：≤0.5%",
        "细菌内毒素：＜0.50IU/mg",
        "含量：96.0%~102.0%（无水物）",
        "林可霉素B：≤5.0%",
        "丙酮：≤2000ppm",
        "仲辛醇：≤500ppm",
        "报告日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_flu_powder": [
        "批号",
        "年",
        "月",
        "日",
        "复验期",
        "kg/袋",
        "袋",
        "数量kg",
        "性状：本品为浅黄色至黄褐色粉末，无异物",
        "霉菌：目视无可见霉菌生长",
        "鉴别：在含量测定项下记录的色谱图中，供试品溶液主峰的保留时间与对照品溶液主峰的保留时间一致。",
        "粒度：100%通过二号筛",
        "干燥失重：≤10.0%",
        "装量：单个单子装量不少于标示装量的99%（9.9kg/袋）",
        "含量测定：90.0%~110.0%",
        "报告日期",
        "报告单号",
        "报告单",
        "报告日期2",
        "报告单号2",
        "默沙东报告单",
    ],
    "qc_finished_fen_powder": [
        "批号",
        "年",
        "月",
        "日",
        "复验期",
        "kg/Drum",
        "Drum",
        "数量kg",
        "性状：本品为白色至类白色粉末",
        "鉴别：UV在295nm的波长处有最大吸收",
        "干燥失重：≤2.5%",
        "粒度：100%通过五号筛",
        "外观均匀度：应色泽均匀无花纹与色斑。",
        "装量：单个桶装量不少于标示装量的99%（24.75kg/桶），平均装量不少于标示装量的100%（25kg/桶）",
        "含量测定：95.0%~105.0%",
        "报告日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_pure_water": [
        "批号",
        "来源",
        "取样量",
        "检验日期",
        "性状:本品为无色澄清液体；无臭、无味",
        "酸碱度:加甲基红指示液不得显红色；加溴麝香草酚蓝指示液不得显蓝色",
        "硝酸盐:≤0.000006%",
        "亚硝酸盐:≤0.000002%",
        "氨:≤0.00003%",
        "电导率:符合规定",
        "TOC:\n≤0.5mg/L",
        "易氧化物",
        "不挥发物:≤1mg/100ml",
        "重金属:≤0.00001%",
        (
            "微生物限度:\n需氧菌每1ml不得过100cfu；警戒限度为每1ml不得过 50c"
            "fu；纠偏限度不得过80cfu。"
        ),
        "*细菌内毒素：＜0.25IU/mL",
        "报告日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_drink_water": [
        "批号",
        "来源",
        "取样量",
        "检验日期",
        "性状：无色透明液体",
        "pH(6.5-8.5)",
        "色度：≤15度，不得呈现其他异色",
        "气味：不得有异臭和异味",
        "铁：≤0.3mg/L",
        "氯离子≤250mg/L",
        "肉眼可见异物：不得含有",
        "总硬度≤450mg/L",
        "浊度≤1NTU",
        "需氧菌总数：≤100cfu/ml",
        "总大肠菌群（不被检测）",
        "大肠埃希菌（不被检出）",
        "报告日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_trp_powder": [
        "批号",
        "外观:白色至微 黄色结晶或结晶性粉末",
        "含量(以 C11H12N2O2 计)(干基): ≥98.0%",
        "比旋度:-29.0°～-32.8°",
        "干燥失重：≤0.5%",
        "粗灰分：≤0.5%",
        "pH (1%水溶液):5.0～7.0",
        "铅：≤5mg/kg",
        "报告日期",
        "报告单号",
        "报告单",
    ],
    "qc_finished_trp_granule": [
        "批号",
        "年",
        "月",
        "日",
        "有效期",
        "包装规格kg/袋",
        "数量kg",
        "外观:白色至微 黄色结晶或结晶性颗粒",
        "含量(以 C11H12N2O2 计)(干基): ≥98.0%",
        "干燥失重：≤1.0%",
        "粗灰分：≤1.0%",
        "pH (1%水溶液):4.5～7.0",
        "报告日期",
        "报告单号",
        "报告单",
    ],
}

FINISHED_FIELD_FALLBACKS = ["批号", "报告日期", "报告单号"]


def get_finished_entity_codes(product_group: str) -> list[str]:
    return FINISHED_PRODUCT_GROUP_ENTITY_MAP.get(product_group, [])


def ensure_finished_entity_in_group(product_group: str, entity_code: str) -> None:
    entity_codes = get_finished_entity_codes(product_group)
    if not entity_codes:
        raise KeyError(product_group)
    if entity_code not in entity_codes:
        raise AppException(message=f"{entity_code} 不属于 {product_group}")


async def list_finished_subtables(
    db: AsyncSession,
    product_group: str,
) -> dict[str, Any]:
    entity_codes = get_finished_entity_codes(product_group)
    if not entity_codes:
        raise KeyError(product_group)

    configured = False
    items: list[dict[str, str]] = []
    for entity_code in entity_codes:
        label = FINISHED_ENTITY_LABELS.get(entity_code, entity_code)
        try:
            await _resolve_runtime_entity(db, entity_code, direction="pull")
            configured = True
        except AppException as e:
            logger.debug("跳过无效 runtime entity: %s", e)
        items.append(
            {
                "entity_code": entity_code,
                "label": label,
            }
        )
    return {"items": items, "configured": configured}


async def _get_finished_remote_fields(
    db: AsyncSession,
    entity_code: str,
) -> list[str]:
    runtime, entity = await _resolve_runtime_entity(db, entity_code, direction="pull")
    client = BitableClient(
        app_token=entity.app_token,
        app_id=runtime.app_id,
        app_secret=runtime.app_secret,
    )
    remote_fields = await client.list_fields(
        feishu_sync_service._require_table_id(entity)
    )
    field_names = [
        str(item.get("field_name", "")).strip()
        for item in remote_fields
        if str(item.get("field_name", "")).strip()
    ]
    return field_names or FINISHED_FIELD_FALLBACKS


async def get_finished_fields(
    db: AsyncSession,
    entity_code: str,
) -> list[str]:
    explicit_fields = FINISHED_ENTITY_FIELDS.get(entity_code)
    if explicit_fields:
        return explicit_fields
    try:
        return await _get_finished_remote_fields(db, entity_code)
    except Exception:
        logger.warning("Falling back to default finished fields for %s", entity_code)
        return FINISHED_FIELD_FALLBACKS


async def list_finished_by_entity(
    db: AsyncSession,
    entity_code: str,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    """List finished product inspections for a specific entity (product table)."""
    field_names = await get_finished_fields(db, entity_code)
    return await _list_feishu(
        db,
        entity_code,
        field_names,
        ["批号", "报告单号"],
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=filters,
    )


async def get_finished_by_entity(
    db: AsyncSession,
    entity_code: str,
    record_id: str,
) -> dict[str, Any]:
    field_names = await get_finished_fields(db, entity_code)
    return await _get_feishu_one(db, entity_code, field_names, record_id)


async def pull_finished_by_entity(db: AsyncSession, entity_code: str) -> dict[str, int]:
    return await _pull_count(db, entity_code)


# ═══════════════════════════════════════════
#  固体/液体物料检验（编号段分组 + subtables）
# ═══════════════════════════════════════════

MATERIAL_FIELD_FALLBACKS = ["批号"]


def get_material_entity_codes(module: str, group: str) -> list[str]:
    return MATERIAL_GROUP_ENTITY_MAP.get(module, {}).get(group, [])


def ensure_material_entity_in_group(module: str, group: str, entity_code: str) -> None:
    entity_codes = get_material_entity_codes(module, group)
    if not entity_codes:
        raise KeyError(group)
    if entity_code not in entity_codes:
        raise AppException(message=f"{entity_code} 不属于 {module}:{group}")


async def list_material_subtables(
    db: AsyncSession,
    module: str,
    group: str,
) -> dict[str, Any]:
    await ensure_quality_feishu_entity_settings(db)
    entity_codes = get_material_entity_codes(module, group)
    if not entity_codes:
        raise KeyError(group)

    configured = False
    items: list[dict[str, str]] = []
    for entity_code in entity_codes:
        try:
            await _resolve_runtime_entity(db, entity_code, direction="pull")
            configured = True
        except AppException as e:
            logger.debug("跳过无效物料实体: %s", e)
        items.append(
            {
                "entity_code": entity_code,
                "label": MATERIAL_ENTITY_LABELS[module].get(entity_code, entity_code),
            }
        )
    return {"items": items, "configured": configured}


async def get_material_fields(
    db: AsyncSession,
    entity_code: str,
) -> list[str]:
    await ensure_quality_feishu_entity_settings(db)
    try:
        runtime, entity = await _resolve_runtime_entity(
            db, entity_code, direction="pull"
        )
        client = BitableClient(
            app_token=entity.app_token,
            app_id=runtime.app_id,
            app_secret=runtime.app_secret,
        )
        remote_fields = await client.list_fields(
            feishu_sync_service._require_table_id(entity)
        )
        field_names = [
            str(item.get("field_name", "")).strip()
            for item in remote_fields
            if str(item.get("field_name", "")).strip()
        ]
        return field_names or MATERIAL_FIELD_FALLBACKS
    except Exception:
        logger.warning("Falling back to default material fields for %s", entity_code)
        return MATERIAL_FIELD_FALLBACKS


async def list_material_records_by_entity(
    db: AsyncSession,
    entity_code: str,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    field_names = await get_material_fields(db, entity_code)
    return await _list_feishu(
        db,
        entity_code,
        field_names,
        keyword_fields=field_names,
        keyword=keyword,
        page=page,
        page_size=page_size,
        filters=filters,
    )


async def pull_material_records_by_entity(
    db: AsyncSession,
    entity_code: str,
) -> dict[str, int]:
    await ensure_quality_feishu_entity_settings(db)
    return await _pull_count(db, entity_code)
