"""Static grouped mappings for solid/liquid material inspection Feishu tables."""

from __future__ import annotations

import logging
from collections.abc import Iterable

logger = logging.getLogger(__name__)

# 表绑定属于部署数据，不进代码：固体/液体物料各实体的 Base/Table 由用户在
# 质量设置-飞书设置中配置（或经 env 预填渠道下发）。本文件只维护实体清单
# （entity_code/分组/标签）供设置页与同步遍历使用，token/table_id 一律留空。
SOLID_MATERIAL_BASE_TOKEN = ""
LIQUID_MATERIAL_BASE_TOKEN = ""


SOLID_GROUPS: list[dict[str, str]] = [
    {"key": "ys-000", "label": "YS000"},
    {"key": "ys-100", "label": "YS100"},
    {"key": "ys-200", "label": "YS200"},
    {"key": "ys-300", "label": "YS300"},
    {"key": "ys-400", "label": "YS400"},
    {"key": "ys-500", "label": "YS500"},
    {"key": "ys-600", "label": "YS600"},
    {"key": "ys-700", "label": "YS700"},
    {"key": "ys-800", "label": "YS800"},
    {"key": "manual", "label": "待人工归组"},
]

LIQUID_GROUPS: list[dict[str, str]] = [
    {"key": "yl-0xx", "label": "YL0xx"},
    {"key": "yl-1xx", "label": "YL1xx"},
    {"key": "yl-2xx", "label": "YL2xx"},
    {"key": "yl-3xx", "label": "YL3xx"},
    {"key": "yl-4xx", "label": "YL4xx"},
    {"key": "yl-5xx", "label": "YL5xx"},
    {"key": "yl-6xx", "label": "YL6xx"},
    {"key": "yl-7xx", "label": "YL7xx"},
    {"key": "yl-8xx", "label": "YL8xx"},
]

SOLID_GROUP_ITEMS: dict[str, list[dict[str, str]]] = {
    "ys-000": [
        {
            "entity_code": "qc_solid_ys001",
            "table_id": "",
            "label": "YS001 食用葡萄糖",
        },
        {
            "entity_code": "qc_solid_ys002",
            "table_id": "",
            "label": "YS002 豆粕粉",
        },
        {
            "entity_code": "qc_solid_ys003",
            "table_id": "",
            "label": "YS003 轻质碳酸钙",
        },
        {
            "entity_code": "qc_solid_ys004",
            "table_id": "",
            "label": "YS004 工业硫酸镁",
        },
        {
            "entity_code": "qc_solid_ys005",
            "table_id": "",
            "label": "YS005 磷酸二氢钾",
        },
        {
            "entity_code": "qc_solid_ys006",
            "table_id": "",
            "label": "YS006 氯化钠",
        },
        {
            "entity_code": "qc_solid_ys007",
            "table_id": "",
            "label": "YS007 固体氢氧化钠",
        },
        {
            "entity_code": "qc_solid_ys008",
            "table_id": "",
            "label": "YS008 活性炭",
        },
        {
            "entity_code": "qc_solid_ys009",
            "table_id": "",
            "label": "YS009 棉籽蛋白",
        },
        {
            "entity_code": "qc_solid_ys010",
            "table_id": "",
            "label": "YS010 食用玉米淀粉",
        },
        {
            "entity_code": "qc_solid_ys011",
            "table_id": "",
            "label": "YS011 硫酸铵",
        },
        {
            "entity_code": "qc_solid_ys012",
            "table_id": "",
            "label": "YS012 琼脂",
        },
        {
            "entity_code": "qc_solid_ys013",
            "table_id": "",
            "label": "YS013 AR级氢氧化钠",
        },
        {
            "entity_code": "qc_solid_ys014",
            "table_id": "",
            "label": "YS014 味精",
        },
        {
            "entity_code": "qc_solid_ys015",
            "table_id": "",
            "label": "YS015 活性炭（303型湿）",
        },
        {
            "entity_code": "qc_solid_ys016",
            "table_id": "",
            "label": "YS016 AR级亚硫酸氢钠",
        },
        {
            "entity_code": "qc_solid_ys017",
            "table_id": "",
            "label": "YS017 食用级亚硫酸氢钠",
        },
        {
            "entity_code": "qc_solid_ys018",
            "table_id": "",
            "label": "YS018 CP级磷酸二氢钾",
        },
        {
            "entity_code": "qc_solid_ys019",
            "table_id": "",
            "label": "YS019 CP级氯化钙",
        },
        {
            "entity_code": "qc_solid_ys020",
            "table_id": "",
            "label": "YS020 AR级硫酸镁",
        },
        {
            "entity_code": "qc_solid_ys021",
            "table_id": "",
            "label": "YS021 AR级氯化镁",
        },
        {
            "entity_code": "qc_solid_ys022",
            "table_id": "",
            "label": "YS022 AR级无水合硫酸铜",
        },
        {
            "entity_code": "qc_solid_ys023",
            "table_id": "",
            "label": "YS023 无水甜菜碱",
        },
        {
            "entity_code": "qc_solid_ys024",
            "table_id": "",
            "label": "YS024 富马酸",
        },
        {
            "entity_code": "qc_solid_ys025",
            "table_id": "",
            "label": "YS025 单硫酸卡那霉素",
        },
        {
            "entity_code": "qc_solid_ys026",
            "table_id": "",
            "label": "YS026 L-酪氨酸",
        },
        {
            "entity_code": "qc_solid_ys027",
            "table_id": "",
            "label": "YS027 维生素B1",
        },
        {
            "entity_code": "qc_solid_ys028",
            "table_id": "",
            "label": "YS028 维生素B2",
        },
        {
            "entity_code": "qc_solid_ys029",
            "table_id": "",
            "label": "YS029 叶酸",
        },
        {
            "entity_code": "qc_solid_ys030",
            "table_id": "",
            "label": "YS030 D-泛酸钙",
        },
        {
            "entity_code": "qc_solid_ys034",
            "table_id": "",
            "label": "YS034 二水合氯化钙",
        },
        {
            "entity_code": "qc_solid_ys038",
            "table_id": "",
            "label": "YS038 酵母浸膏LM800",
        },
        {
            "entity_code": "qc_solid_ys039",
            "table_id": "",
            "label": "YS039 酵母浸膏LM902",
        },
        {
            "entity_code": "qc_solid_ys040",
            "table_id": "",
            "label": "YS040 胰蛋白胨",
        },
        {
            "entity_code": "qc_solid_ys044",
            "table_id": "",
            "label": "YS044 磷酸氢二钾（工业级）",
        },
        {
            "entity_code": "qc_solid_ys047",
            "table_id": "",
            "label": "YS047 麸质粉",
        },
        {
            "entity_code": "qc_solid_ys048",
            "table_id": "",
            "label": "YS048 麦芽糊精",
        },
        {
            "entity_code": "qc_solid_ys051",
            "table_id": "",
            "label": "YS051 XR-912CSS大孔吸附树脂",
        },
        {
            "entity_code": "qc_solid_ys052",
            "table_id": "",
            "label": "YS052 高温黄豆饼粉",
        },
        {
            "entity_code": "qc_solid_ys053",
            "table_id": "",
            "label": "YS053 絮凝剂",
        },
    ],
    "ys-100": [
        {
            "entity_code": "qc_solid_ys105",
            "table_id": "",
            "label": "YS105 啤酒酵母",
        },
        {
            "entity_code": "qc_solid_ys107",
            "table_id": "",
            "label": "YS107 CP级硫酸镁",
        },
        {
            "entity_code": "qc_solid_ys110",
            "table_id": "",
            "label": "YS110 RS-500硅藻土",
        },
        {
            "entity_code": "qc_solid_ys112",
            "table_id": "",
            "label": "YS112 盐霉素用酵母粉",
        },
    ],
    "ys-200": [
        {
            "entity_code": "qc_solid_ys201",
            "table_id": "",
            "label": "YS201 麦芽糖",
        },
    ],
    "ys-300": [
        {
            "entity_code": "qc_solid_ys301",
            "table_id": "",
            "label": "YS301 蔗糖",
        },
        {
            "entity_code": "qc_solid_ys302",
            "table_id": "",
            "label": "YS302 无水醋酸钠",
        },
        {
            "entity_code": "qc_solid_ys303",
            "table_id": "",
            "label": "YS303 污水柠檬酸",
        },
        {
            "entity_code": "qc_solid_ys304",
            "table_id": "",
            "label": "YS304 酵母浸粉",
        },
    ],
    "ys-400": [
        {
            "entity_code": "qc_solid_ys401",
            "table_id": "",
            "label": "YS401 低温黄豆饼粉",
        },
        {
            "entity_code": "qc_solid_ys403",
            "table_id": "",
            "label": "YS403 黄血盐钠",
        },
        {
            "entity_code": "qc_solid_ys404",
            "table_id": "",
            "label": "YS404 草酸",
        },
        {
            "entity_code": "qc_solid_ys405",
            "table_id": "",
            "label": "YS405 硝酸钠",
        },
        {
            "entity_code": "qc_solid_ys406",
            "table_id": "",
            "label": "YS406 氯化铵",
        },
        {
            "entity_code": "qc_solid_ys407",
            "table_id": "",
            "label": "YS407 硫酸锌",
        },
        {
            "entity_code": "qc_solid_ys412",
            "table_id": "",
            "label": "YS412 七水硫酸亚铁",
        },
        {
            "entity_code": "qc_solid_ys415",
            "table_id": "",
            "label": "YS415 工业盐",
        },
    ],
    "ys-500": [
        {
            "entity_code": "qc_solid_ys501",
            "table_id": "",
            "label": "YS501 硫酸亚铁（环保用）",
        },
        {
            "entity_code": "qc_solid_ys502",
            "table_id": "",
            "label": "YS502 珍珠岩助滤剂",
        },
        {
            "entity_code": "qc_solid_ys503",
            "table_id": "",
            "label": "YS503 蛋白胨",
        },
        {
            "entity_code": "qc_solid_ys504",
            "table_id": "",
            "label": "YS504 酵母粉",
        },
        {
            "entity_code": "qc_solid_ys505",
            "table_id": "",
            "label": "YS505 淀粉酶",
        },
        {
            "entity_code": "qc_solid_ys507",
            "table_id": "",
            "label": "YS507 硫酸亚铁",
        },
        {
            "entity_code": "qc_solid_ys511",
            "table_id": "",
            "label": "YS511 聚丙烯酰胺",
        },
        {
            "entity_code": "qc_solid_ys513",
            "table_id": "",
            "label": "YS513 甘氨酸",
        },
        {
            "entity_code": "qc_solid_ys513_fvhdro",
            "table_id": "",
            "label": "YS513 甘氨酸",
        },
        {
            "entity_code": "qc_solid_ys514",
            "table_id": "",
            "label": "YS514 L-蛋氨酸（甲硫氨酸）",
        },
        {
            "entity_code": "qc_solid_ys514_sgx7j0",
            "table_id": "",
            "label": "YS514 L-蛋氨酸",
        },
        {
            "entity_code": "qc_solid_ys515",
            "table_id": "",
            "label": "YS515 固体麦精",
        },
        {
            "entity_code": "qc_solid_ys516",
            "table_id": "",
            "label": "YS516 硫酸锰",
        },
        {
            "entity_code": "qc_solid_ys517",
            "table_id": "",
            "label": "YS517 碳酸氢钠",
        },
        {
            "entity_code": "qc_solid_ys520",
            "table_id": "",
            "label": "YS520 柠檬酸钠",
        },
        {
            "entity_code": "qc_solid_ys524",
            "table_id": "",
            "label": "YS524 硫酸钙",
        },
        {
            "entity_code": "qc_solid_ys525",
            "table_id": "",
            "label": "YS525 黄豆粉",
        },
        {
            "entity_code": "qc_solid_ys528",
            "table_id": "",
            "label": "YS528 六水合氯化钴",
        },
        {
            "entity_code": "qc_solid_ys530",
            "table_id": "",
            "label": "YS530 大孔吸附树脂",
        },
        {
            "entity_code": "qc_solid_ys531",
            "table_id": "",
            "label": "YS531 BHT",
        },
    ],
    "ys-600": [
        {
            "entity_code": "qc_solid_ys602",
            "table_id": "",
            "label": "YS602 氯化钴",
        },
        {
            "entity_code": "qc_solid_ys603",
            "table_id": "",
            "label": "YS603 无水氯化钙",
        },
        {
            "entity_code": "qc_solid_ys604",
            "table_id": "",
            "label": "YS604 工业硫酸镁",
        },
        {
            "entity_code": "qc_solid_ys606",
            "table_id": "",
            "label": "YS606 食用葡萄糖",
        },
    ],
    "ys-700": [
        {
            "entity_code": "qc_solid_ys702",
            "table_id": "",
            "label": "YS702 烟酸",
        },
        {
            "entity_code": "qc_solid_ys703",
            "table_id": "",
            "label": "YS703 烟氨酸",
        },
        {
            "entity_code": "qc_solid_ys704",
            "table_id": "",
            "label": "YS704 硫酸钾",
        },
        {
            "entity_code": "qc_solid_ys704_oowx6g",
            "table_id": "",
            "label": "YS704 硫酸钾",
        },
        {
            "entity_code": "qc_solid_ys705",
            "table_id": "",
            "label": "YS705 硫酸钠",
        },
        {
            "entity_code": "qc_solid_ys712",
            "table_id": "",
            "label": "YS712 聚合氯化铝",
        },
    ],
    "ys-800": [
        {
            "entity_code": "qc_solid_ys803",
            "table_id": "",
            "label": "YS803 酵母浸膏",
        },
        {
            "entity_code": "qc_solid_ys804",
            "table_id": "",
            "label": "YS804 磷酸二氢钾",
        },
        {
            "entity_code": "qc_solid_ys805",
            "table_id": "",
            "label": "YS805 磷酸氢二钾",
        },
        {
            "entity_code": "qc_solid_ys806",
            "table_id": "",
            "label": "YS806 工业硫酸镁",
        },
        {
            "entity_code": "qc_solid_ys809",
            "table_id": "",
            "label": "YS809 味精",
        },
        {
            "entity_code": "qc_solid_ys810",
            "table_id": "",
            "label": "YS810 硫酸铵",
        },
        {
            "entity_code": "qc_solid_ys813",
            "table_id": "",
            "label": "YS813 柠檬酸钠",
        },
        {
            "entity_code": "qc_solid_ys814",
            "table_id": "",
            "label": "YS814 BR级琼脂",
        },
    ],
    "manual": [
        {
            "entity_code": "qc_solid_manual_msvxtv",
            "table_id": "",
            "label": "L-盐酸赖氨酸（去甲用）",
        },
        {
            "entity_code": "qc_solid_manual_jgw8uq",
            "table_id": "",
            "label": "黄血盐钠",
        },
        {
            "entity_code": "qc_solid_manual_lveh9l",
            "table_id": "",
            "label": "中温淀粉酶",
        },
        {
            "entity_code": "qc_solid_manual_ufjdgx",
            "table_id": "",
            "label": "十二脂肪烷基三甲基氯化铵",
        },
        {
            "entity_code": "qc_solid_manual_ntqrid",
            "table_id": "",
            "label": "中温黄豆饼粉（去甲用）",
        },
    ],
}

LIQUID_GROUP_ITEMS: dict[str, list[dict[str, str]]] = {
    "yl-0xx": [
        {
            "entity_code": "qc_liquid_yl001",
            "table_id": "",
            "label": "YL001 大豆油",
        },
        {
            "entity_code": "qc_liquid_yl002",
            "table_id": "",
            "label": "YL002 甘油",
        },
        {
            "entity_code": "qc_liquid_yl003",
            "table_id": "",
            "label": "YL003 聚醚类消泡剂",
        },
        {
            "entity_code": "qc_liquid_yl004",
            "table_id": "",
            "label": "YL004 工业丙酮",
        },
        {
            "entity_code": "qc_liquid_yl005",
            "table_id": "",
            "label": "YL005 甲苯",
        },
        {
            "entity_code": "qc_liquid_yl006",
            "table_id": "",
            "label": "YL006 工业浓硫酸",
        },
        {
            "entity_code": "qc_liquid_yl007",
            "table_id": "",
            "label": "YL007 液碱",
        },
        {
            "entity_code": "qc_liquid_yl008",
            "table_id": "",
            "label": "YL008 回收丙酮",
        },
        {
            "entity_code": "qc_liquid_yl009",
            "table_id": "",
            "label": "YL009 丙三醇",
        },
        {
            "entity_code": "qc_liquid_yl012",
            "table_id": "",
            "label": "YL012 回收甲苯",
        },
        {
            "entity_code": "qc_liquid_yl015",
            "table_id": "",
            "label": "YL015 乙二醇",
        },
        {
            "entity_code": "qc_liquid_yl016",
            "table_id": "",
            "label": "YL016 葡萄糖浆",
        },
        {
            "entity_code": "qc_liquid_yl017",
            "table_id": "",
            "label": "YL017 甲醛",
        },
        {
            "entity_code": "qc_liquid_yl018",
            "table_id": "",
            "label": "YL018 正庚烷",
        },
        {
            "entity_code": "qc_liquid_yl019",
            "table_id": "",
            "label": "YL019 乳化硅油",
        },
        {
            "entity_code": "qc_liquid_yl020",
            "table_id": "",
            "label": "YL020 硫酸（分析纯）",
        },
        {
            "entity_code": "qc_liquid_yl021",
            "table_id": "",
            "label": "YL021 无水乙醇（CP级）",
        },
        {
            "entity_code": "qc_liquid_yl022",
            "table_id": "",
            "label": "YL022 乙醇（药用级）",
        },
        {
            "entity_code": "qc_liquid_yl023",
            "table_id": "",
            "label": "YL023 乙醇（食品级）",
        },
        {
            "entity_code": "qc_liquid_yl024",
            "table_id": "",
            "label": "YL024 95%硫酸",
        },
        {
            "entity_code": "qc_liquid_yl025",
            "table_id": "",
            "label": "YL025 甲醇",
        },
        {
            "entity_code": "qc_liquid_yl026",
            "table_id": "",
            "label": "YL026 环己甲酸",
        },
        {
            "entity_code": "qc_liquid_yl027",
            "table_id": "",
            "label": "YL027 消泡剂",
        },
        {
            "entity_code": "qc_liquid_yl029",
            "table_id": "",
            "label": "YL029 无水乙醇",
        },
        {
            "entity_code": "qc_liquid_yl030",
            "table_id": "",
            "label": "YL030 THIX-298（消泡剂）",
        },
        {
            "entity_code": "qc_liquid_yl032",
            "table_id": "",
            "label": "YL032 乙酸乙酯",
        },
    ],
    "yl-1xx": [
        {
            "entity_code": "qc_liquid_yl101",
            "table_id": "",
            "label": "YL101 硅酮类消泡剂",
        },
        {
            "entity_code": "qc_liquid_yl102",
            "table_id": "",
            "label": "YL102 乳化剂",
        },
    ],
    "yl-2xx": [
        {
            "entity_code": "qc_liquid_yl201",
            "table_id": "",
            "label": "YL201 正己烷",
        },
        {
            "entity_code": "qc_liquid_yl202",
            "table_id": "",
            "label": "YL202 曲拉通x-100",
        },
        {
            "entity_code": "qc_liquid_yl203",
            "table_id": "",
            "label": "YL203 玉米浆（MV）",
        },
        {
            "entity_code": "qc_liquid_yl204",
            "table_id": "",
            "label": "YL204 AR级盐酸",
        },
    ],
    "yl-3xx": [
        {
            "entity_code": "qc_liquid_yl301",
            "table_id": "",
            "label": "YL301 P-2000消泡剂",
        },
    ],
    "yl-4xx": [
        {
            "entity_code": "qc_liquid_yl401",
            "table_id": "",
            "label": "YL401 复合消泡剂",
        },
        {
            "entity_code": "qc_liquid_yl402",
            "table_id": "",
            "label": "YL402 盐酸（工业级）",
        },
        {
            "entity_code": "qc_liquid_yl403",
            "table_id": "",
            "label": "YL403 仲辛醇",
        },
        {
            "entity_code": "qc_liquid_yl404",
            "table_id": "",
            "label": "YL404 玉米浆",
        },
        {
            "entity_code": "qc_liquid_yl405",
            "table_id": "",
            "label": "YL405 CP级盐酸",
        },
        {
            "entity_code": "qc_liquid_yl407",
            "table_id": "",
            "label": "YL407 液糖",
        },
    ],
    "yl-5xx": [
        {
            "entity_code": "qc_liquid_yl501",
            "table_id": "",
            "label": "YL501 食用级磷酸",
        },
        {
            "entity_code": "qc_liquid_yl502",
            "table_id": "",
            "label": "YL502 高温淀粉酶",
        },
        {
            "entity_code": "qc_liquid_yl503",
            "table_id": "",
            "label": "YL503 氨水",
        },
        {
            "entity_code": "qc_liquid_yl504",
            "table_id": "",
            "label": "YL504 双氧水",
        },
        {
            "entity_code": "qc_liquid_yl505",
            "table_id": "",
            "label": "YL505 糖化酶",
        },
        {
            "entity_code": "qc_liquid_yl506",
            "table_id": "",
            "label": "YL506 次氯酸钠",
        },
        {
            "entity_code": "qc_liquid_yl507",
            "table_id": "",
            "label": "YL507 反渗透阻垢剂",
        },
        {
            "entity_code": "qc_liquid_yl508",
            "table_id": "",
            "label": "YL508 工业用乙酸丁酯",
        },
        {
            "entity_code": "qc_liquid_yl509",
            "table_id": "",
            "label": "YL509 4850us消泡剂",
        },
        {
            "entity_code": "qc_liquid_yl511",
            "table_id": "",
            "label": "YL511 环己甲酸",
        },
        {
            "entity_code": "qc_liquid_yl512",
            "table_id": "",
            "label": "YL512 回收甲醇",
        },
        {
            "entity_code": "qc_liquid_yl513",
            "table_id": "",
            "label": "YL513 异丙醚",
        },
    ],
    "yl-6xx": [
        {
            "entity_code": "qc_liquid_yl602",
            "table_id": "",
            "label": "YL602 无水乙醇",
        },
        {
            "entity_code": "qc_liquid_yl603",
            "table_id": "",
            "label": "YL603 浓硝酸",
        },
        {
            "entity_code": "qc_liquid_yl604",
            "table_id": "",
            "label": "YL604 稀硝酸",
        },
    ],
    "yl-7xx": [
        {
            "entity_code": "qc_liquid_yl701",
            "table_id": "",
            "label": "YL701 液氨",
        },
    ],
    "yl-8xx": [
        {
            "entity_code": "qc_liquid_yl801",
            "table_id": "",
            "label": "YL801 工业浓硫酸",
        },
        {
            "entity_code": "qc_liquid_yl803",
            "table_id": "",
            "label": "YL803 聚醚类消泡剂",
        },
    ],
}


def _flatten_items(groups: dict[str, list[dict[str, str]]]) -> Iterable[dict[str, str]]:
    for items in groups.values():
        yield from items


SOLID_MATERIAL_NEW_TABLE_IDS: dict[str, str] = {}

LIQUID_MATERIAL_NEW_TABLE_IDS: dict[str, str] = {}


MATERIAL_GROUPS = {
    "solid": SOLID_GROUPS,
    "liquid": LIQUID_GROUPS,
}

MATERIAL_GROUP_LABELS: dict[str, dict[str, str]] = {
    "solid": {item["key"]: item["label"] for item in SOLID_GROUPS},
    "liquid": {item["key"]: item["label"] for item in LIQUID_GROUPS},
}

MATERIAL_GROUP_ENTITY_MAP: dict[str, dict[str, list[str]]] = {
    "solid": {
        group_key: [item["entity_code"] for item in items]
        for group_key, items in SOLID_GROUP_ITEMS.items()
    },
    "liquid": {
        group_key: [item["entity_code"] for item in items]
        for group_key, items in LIQUID_GROUP_ITEMS.items()
    },
}

MATERIAL_ENTITY_LABELS: dict[str, dict[str, str]] = {
    "solid": {
        item["entity_code"]: item["label"] for item in _flatten_items(SOLID_GROUP_ITEMS)
    },
    "liquid": {
        item["entity_code"]: item["label"]
        for item in _flatten_items(LIQUID_GROUP_ITEMS)
    },
}

MATERIAL_ENTITY_TABLE_IDS: dict[str, dict[str, str]] = {
    "solid": {
        item["entity_code"]: item["table_id"]
        for item in _flatten_items(SOLID_GROUP_ITEMS)
    },
    "liquid": {
        item["entity_code"]: item["table_id"]
        for item in _flatten_items(LIQUID_GROUP_ITEMS)
    },
}

MATERIAL_ENTITY_GROUPS: dict[str, dict[str, str]] = {
    "solid": {
        item["entity_code"]: MATERIAL_GROUP_LABELS["solid"][group_key]
        for group_key, items in SOLID_GROUP_ITEMS.items()
        for item in items
    },
    "liquid": {
        item["entity_code"]: MATERIAL_GROUP_LABELS["liquid"][group_key]
        for group_key, items in LIQUID_GROUP_ITEMS.items()
        for item in items
    },
}

MATERIAL_ENTITY_PREFILLS: dict[str, dict[str, str]] = {
    **{
        item["entity_code"]: {
            "app_token": SOLID_MATERIAL_BASE_TOKEN,
            "table_id": SOLID_MATERIAL_NEW_TABLE_IDS.get(
                item["entity_code"], item["table_id"]
            ),
            "table_name": item["label"],
            "source_note": "默认预填：QC固体物料结果统计表",
        }
        for item in _flatten_items(SOLID_GROUP_ITEMS)
    },
    **{
        item["entity_code"]: {
            "app_token": LIQUID_MATERIAL_BASE_TOKEN,
            "table_id": LIQUID_MATERIAL_NEW_TABLE_IDS.get(
                item["entity_code"], item["table_id"]
            ),
            "table_name": item["label"],
            "source_note": "默认预填：QC液体物料结果统计表",
        }
        for item in _flatten_items(LIQUID_GROUP_ITEMS)
    },
}

MATERIAL_DEFAULT_QUALITY_FEISHU_ENTITIES: list[tuple[str, str, str, int]] = []
_sort_order = 500
# 统一分组：固体物料检验 / 液体物料检验（不再按子组分散）
MODULE_GROUP_LABEL = {"solid": "固体物料检验", "liquid": "液体物料检验"}
for module in ("solid", "liquid"):
    group_label = MODULE_GROUP_LABEL[module]
    for group in MATERIAL_GROUPS[module]:
        group_key = group["key"]
        for entity_code in MATERIAL_GROUP_ENTITY_MAP[module][group_key]:
            MATERIAL_DEFAULT_QUALITY_FEISHU_ENTITIES.append(
                (
                    entity_code,
                    MATERIAL_ENTITY_LABELS[module][entity_code],
                    group_label,
                    _sort_order,
                )
            )
            _sort_order += 1

MATERIAL_ENTITY_CODES: tuple[str, ...] = tuple(MATERIAL_ENTITY_PREFILLS.keys())
