"""Static grouped mappings for solid/liquid material inspection Feishu tables."""

from __future__ import annotations

import logging
from collections.abc import Iterable

logger = logging.getLogger(__name__)

# 2026-09-11：固体/液体物料检验整体迁移到新 Base（每物料子表不变，仅 Base 与
# table_id 更新）。table_id 硬编码为新 Base 内各子表，故 app_token 不再走环境变量
# 兜底（旧 env 值会与硬编码 table_id 拼成跨 Base 坏配置）；运行期以 DB 实体配置
# （质量设置-飞书设置）为准，此处仅作初始化预填默认。
SOLID_MATERIAL_BASE_TOKEN = "TGWXbQ1Pma00Nrs2rbxcJMO2nQb"
LIQUID_MATERIAL_BASE_TOKEN = "HTn4b3Xvqa2W9NsGkd6clQzZnde"


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
            "table_id": "tbl55KMVP6ckdRqS",
            "label": "YS001 食用葡萄糖",
        },
        {
            "entity_code": "qc_solid_ys002",
            "table_id": "tbl1ojnSMDzYEp4H",
            "label": "YS002 豆粕粉",
        },
        {
            "entity_code": "qc_solid_ys003",
            "table_id": "tbl5WKghY9JbtW5f",
            "label": "YS003 轻质碳酸钙",
        },
        {
            "entity_code": "qc_solid_ys004",
            "table_id": "tbl4AAFT6xX8HxEN",
            "label": "YS004 工业硫酸镁",
        },
        {
            "entity_code": "qc_solid_ys005",
            "table_id": "tbl5Ef3QzoF92t8z",
            "label": "YS005 磷酸二氢钾",
        },
        {
            "entity_code": "qc_solid_ys006",
            "table_id": "tbl6mNGHeTOTqbL6",
            "label": "YS006 氯化钠",
        },
        {
            "entity_code": "qc_solid_ys007",
            "table_id": "tbl7d0pnJCcwB12o",
            "label": "YS007 固体氢氧化钠",
        },
        {
            "entity_code": "qc_solid_ys008",
            "table_id": "tbl5QrmhRT1SXzLp",
            "label": "YS008 活性炭",
        },
        {
            "entity_code": "qc_solid_ys009",
            "table_id": "tbl30xvDVS5zycHp",
            "label": "YS009 棉籽蛋白",
        },
        {
            "entity_code": "qc_solid_ys010",
            "table_id": "tbl58sIeWibW2EaP",
            "label": "YS010 食用玉米淀粉",
        },
        {
            "entity_code": "qc_solid_ys011",
            "table_id": "tbl5FK3ZnpKOKtag",
            "label": "YS011 硫酸铵",
        },
        {
            "entity_code": "qc_solid_ys012",
            "table_id": "tbl25Wbjild4U1wI",
            "label": "YS012 琼脂",
        },
        {
            "entity_code": "qc_solid_ys013",
            "table_id": "tbl670sQxauRjXit",
            "label": "YS013 AR级氢氧化钠",
        },
        {
            "entity_code": "qc_solid_ys014",
            "table_id": "tbl6jnzPgCtZJguk",
            "label": "YS014 味精",
        },
        {
            "entity_code": "qc_solid_ys015",
            "table_id": "tbldKP1zRGNPJU8S",
            "label": "YS015 活性炭（303型湿）",
        },
        {
            "entity_code": "qc_solid_ys016",
            "table_id": "tbl6FPHHTgFxyd1w",
            "label": "YS016 AR级亚硫酸氢钠",
        },
        {
            "entity_code": "qc_solid_ys017",
            "table_id": "tbl6Vg2G9vNCpehs",
            "label": "YS017 食用级亚硫酸氢钠",
        },
        {
            "entity_code": "qc_solid_ys018",
            "table_id": "tbl1HJ3JbbDHV9vk",
            "label": "YS018 CP级磷酸二氢钾",
        },
        {
            "entity_code": "qc_solid_ys019",
            "table_id": "tbl2UtQk33tYZ6H2",
            "label": "YS019 CP级氯化钙",
        },
        {
            "entity_code": "qc_solid_ys020",
            "table_id": "tbl3ZVaguhMUQCvD",
            "label": "YS020 AR级硫酸镁",
        },
        {
            "entity_code": "qc_solid_ys021",
            "table_id": "tbl4GgsC1UXfgmGY",
            "label": "YS021 AR级氯化镁",
        },
        {
            "entity_code": "qc_solid_ys022",
            "table_id": "tbl6JWnCoxW25ToP",
            "label": "YS022 AR级无水合硫酸铜",
        },
        {
            "entity_code": "qc_solid_ys023",
            "table_id": "tbl3EwZROXy51gI7",
            "label": "YS023 无水甜菜碱",
        },
        {
            "entity_code": "qc_solid_ys024",
            "table_id": "tbl1iNRoBZ7MxN0L",
            "label": "YS024 富马酸",
        },
        {
            "entity_code": "qc_solid_ys025",
            "table_id": "tbl1UE8VlNrn1gjW",
            "label": "YS025 单硫酸卡那霉素",
        },
        {
            "entity_code": "qc_solid_ys026",
            "table_id": "tbl4mM1sDvhBAJsC",
            "label": "YS026 L-酪氨酸",
        },
        {
            "entity_code": "qc_solid_ys027",
            "table_id": "tbl5DCR2JtgpYda5",
            "label": "YS027 维生素B1",
        },
        {
            "entity_code": "qc_solid_ys028",
            "table_id": "tbl4F0g4Wb9USEam",
            "label": "YS028 维生素B2",
        },
        {
            "entity_code": "qc_solid_ys029",
            "table_id": "tbl5ZFDBBL4Hr3Ds",
            "label": "YS029 叶酸",
        },
        {
            "entity_code": "qc_solid_ys030",
            "table_id": "tbl3WA8JKwe5PuET",
            "label": "YS030 D-泛酸钙",
        },
        {
            "entity_code": "qc_solid_ys034",
            "table_id": "tblO7f2wFMTop91e",
            "label": "YS034 二水合氯化钙",
        },
        {
            "entity_code": "qc_solid_ys038",
            "table_id": "tbl3jA3rZllKRiCO",
            "label": "YS038 酵母浸膏LM800",
        },
        {
            "entity_code": "qc_solid_ys039",
            "table_id": "tbl34jQ4lJftyxt1",
            "label": "YS039 酵母浸膏LM902",
        },
        {
            "entity_code": "qc_solid_ys040",
            "table_id": "tbl5sKGfclO7wCmY",
            "label": "YS040 胰蛋白胨",
        },
        {
            "entity_code": "qc_solid_ys044",
            "table_id": "tbl27l2Gc4AjAOlj",
            "label": "YS044 磷酸氢二钾（工业级）",
        },
        {
            "entity_code": "qc_solid_ys047",
            "table_id": "tbl1HrrPioW2b921",
            "label": "YS047 麸质粉",
        },
        {
            "entity_code": "qc_solid_ys048",
            "table_id": "tbl6N57Achb7orQC",
            "label": "YS048 麦芽糊精",
        },
        {
            "entity_code": "qc_solid_ys051",
            "table_id": "tbl5smSj4wYtJD4W",
            "label": "YS051 XR-912CSS大孔吸附树脂",
        },
        {
            "entity_code": "qc_solid_ys052",
            "table_id": "tbl7MVa7fF5vJjCu",
            "label": "YS052 高温黄豆饼粉",
        },
        {
            "entity_code": "qc_solid_ys053",
            "table_id": "tbl1UsL4HFPYuWHX",
            "label": "YS053 絮凝剂",
        },
    ],
    "ys-100": [
        {
            "entity_code": "qc_solid_ys105",
            "table_id": "tbl4WQgoRQ3J8TGO",
            "label": "YS105 啤酒酵母",
        },
        {
            "entity_code": "qc_solid_ys107",
            "table_id": "tbl5IxcIHQfvMMCm",
            "label": "YS107 CP级硫酸镁",
        },
        {
            "entity_code": "qc_solid_ys110",
            "table_id": "tbl3eXe3C7eesxKl",
            "label": "YS110 RS-500硅藻土",
        },
        {
            "entity_code": "qc_solid_ys112",
            "table_id": "tblhbMNEHgQfDgB0",
            "label": "YS112 盐霉素用酵母粉",
        },
    ],
    "ys-200": [
        {
            "entity_code": "qc_solid_ys201",
            "table_id": "tbl3jK13oudOYzq9",
            "label": "YS201 麦芽糖",
        },
    ],
    "ys-300": [
        {
            "entity_code": "qc_solid_ys301",
            "table_id": "tbl5WW0O0gmmceVB",
            "label": "YS301 蔗糖",
        },
        {
            "entity_code": "qc_solid_ys302",
            "table_id": "tbl5KxdInKgh17aw",
            "label": "YS302 无水醋酸钠",
        },
        {
            "entity_code": "qc_solid_ys303",
            "table_id": "tblC4yEJ4J1iZUW4",
            "label": "YS303 污水柠檬酸",
        },
        {
            "entity_code": "qc_solid_ys304",
            "table_id": "tbl7z7lWKfiK5leu",
            "label": "YS304 酵母浸粉",
        },
    ],
    "ys-400": [
        {
            "entity_code": "qc_solid_ys401",
            "table_id": "tbl22bZRAxcDOQKK",
            "label": "YS401 低温黄豆饼粉",
        },
        {
            "entity_code": "qc_solid_ys403",
            "table_id": "tbl4NKesGBq0l09U",
            "label": "YS403 黄血盐钠",
        },
        {
            "entity_code": "qc_solid_ys404",
            "table_id": "tbl6K36H5FkUYSjZ",
            "label": "YS404 草酸",
        },
        {
            "entity_code": "qc_solid_ys405",
            "table_id": "tbl6Oz8cQbd2Tpwf",
            "label": "YS405 硝酸钠",
        },
        {
            "entity_code": "qc_solid_ys406",
            "table_id": "tbl3r5SY4ax0qMrt",
            "label": "YS406 氯化铵",
        },
        {
            "entity_code": "qc_solid_ys407",
            "table_id": "tbl1zOE9sqCG8Bkc",
            "label": "YS407 硫酸锌",
        },
        {
            "entity_code": "qc_solid_ys412",
            "table_id": "tbl3H77Ne8uyTxXu",
            "label": "YS412 七水硫酸亚铁",
        },
        {
            "entity_code": "qc_solid_ys415",
            "table_id": "tbl3QKPDvdet5KtP",
            "label": "YS415 工业盐",
        },
    ],
    "ys-500": [
        {
            "entity_code": "qc_solid_ys501",
            "table_id": "tbl7FGYsbggeTqOQ",
            "label": "YS501 硫酸亚铁（环保用）",
        },
        {
            "entity_code": "qc_solid_ys502",
            "table_id": "tbl5r47BlC2WtJ2N",
            "label": "YS502 珍珠岩助滤剂",
        },
        {
            "entity_code": "qc_solid_ys503",
            "table_id": "tbl1uT0nYgufruRw",
            "label": "YS503 蛋白胨",
        },
        {
            "entity_code": "qc_solid_ys504",
            "table_id": "tbl2yDxCr3YcZDr3",
            "label": "YS504 酵母粉",
        },
        {
            "entity_code": "qc_solid_ys505",
            "table_id": "tbl6qy1lxjyAseEs",
            "label": "YS505 淀粉酶",
        },
        {
            "entity_code": "qc_solid_ys507",
            "table_id": "tbl38gMBg2KEftmm",
            "label": "YS507 硫酸亚铁",
        },
        {
            "entity_code": "qc_solid_ys511",
            "table_id": "tbl216Uc5ax2lZgP",
            "label": "YS511 聚丙烯酰胺",
        },
        {
            "entity_code": "qc_solid_ys513",
            "table_id": "tbl5DAs5n4rJbwet",
            "label": "YS513 甘氨酸",
        },
        {
            "entity_code": "qc_solid_ys513_fvhdro",
            "table_id": "tbl6RYmm33fVHdRO",
            "label": "YS513 甘氨酸",
        },
        {
            "entity_code": "qc_solid_ys514",
            "table_id": "tbl7bhhyxdHuiODf",
            "label": "YS514 L-蛋氨酸（甲硫氨酸）",
        },
        {
            "entity_code": "qc_solid_ys514_sgx7j0",
            "table_id": "tbl3GOzcllsgX7J0",
            "label": "YS514 L-蛋氨酸",
        },
        {
            "entity_code": "qc_solid_ys515",
            "table_id": "tbl6wGGOmAJlr46s",
            "label": "YS515 固体麦精",
        },
        {
            "entity_code": "qc_solid_ys516",
            "table_id": "tbldHFLZAqG0Ditx",
            "label": "YS516 硫酸锰",
        },
        {
            "entity_code": "qc_solid_ys517",
            "table_id": "tblEg0jfAUIyn3wP",
            "label": "YS517 碳酸氢钠",
        },
        {
            "entity_code": "qc_solid_ys520",
            "table_id": "tbl6PCIzy1T5wtKu",
            "label": "YS520 柠檬酸钠",
        },
        {
            "entity_code": "qc_solid_ys524",
            "table_id": "tbl4oEP27vF7ihEg",
            "label": "YS524 硫酸钙",
        },
        {
            "entity_code": "qc_solid_ys525",
            "table_id": "tblZcvca8nqlzs44",
            "label": "YS525 黄豆粉",
        },
        {
            "entity_code": "qc_solid_ys528",
            "table_id": "tbl3eugIN7OoIynJ",
            "label": "YS528 六水合氯化钴",
        },
        {
            "entity_code": "qc_solid_ys530",
            "table_id": "tbl2gdoZPC52Vd8H",
            "label": "YS530 大孔吸附树脂",
        },
        {
            "entity_code": "qc_solid_ys531",
            "table_id": "tbl4e2KB2H9d6M3d",
            "label": "YS531 BHT",
        },
    ],
    "ys-600": [
        {
            "entity_code": "qc_solid_ys602",
            "table_id": "tbl7wUcb3RIONRkJ",
            "label": "YS602 氯化钴",
        },
        {
            "entity_code": "qc_solid_ys603",
            "table_id": "tbl5yHz9WUT2dVmW",
            "label": "YS603 无水氯化钙",
        },
        {
            "entity_code": "qc_solid_ys604",
            "table_id": "tbl5OtiQ9cyitpBt",
            "label": "YS604 工业硫酸镁",
        },
        {
            "entity_code": "qc_solid_ys606",
            "table_id": "tbl3WxBtjEUnmxti",
            "label": "YS606 食用葡萄糖",
        },
    ],
    "ys-700": [
        {
            "entity_code": "qc_solid_ys702",
            "table_id": "tblOIk3bYGgQUUGg",
            "label": "YS702 烟酸",
        },
        {
            "entity_code": "qc_solid_ys703",
            "table_id": "tbl43iBXVbFfmlgk",
            "label": "YS703 烟氨酸",
        },
        {
            "entity_code": "qc_solid_ys704",
            "table_id": "tbl49a1rhGTIN46m",
            "label": "YS704 硫酸钾",
        },
        {
            "entity_code": "qc_solid_ys704_oowx6g",
            "table_id": "tbl6sKBU5eOOwX6G",
            "label": "YS704 硫酸钾",
        },
        {
            "entity_code": "qc_solid_ys705",
            "table_id": "tbl7zHB4rdO6aARc",
            "label": "YS705 硫酸钠",
        },
        {
            "entity_code": "qc_solid_ys712",
            "table_id": "tbl34xzNDgiFC2Qp",
            "label": "YS712 聚合氯化铝",
        },
    ],
    "ys-800": [
        {
            "entity_code": "qc_solid_ys803",
            "table_id": "tbl1qskVoi00BcbT",
            "label": "YS803 酵母浸膏",
        },
        {
            "entity_code": "qc_solid_ys804",
            "table_id": "tbl7afifdB3xlHix",
            "label": "YS804 磷酸二氢钾",
        },
        {
            "entity_code": "qc_solid_ys805",
            "table_id": "tblBAMtHtz63ioLA",
            "label": "YS805 磷酸氢二钾",
        },
        {
            "entity_code": "qc_solid_ys806",
            "table_id": "tbl7yucsTEDfRdnp",
            "label": "YS806 工业硫酸镁",
        },
        {
            "entity_code": "qc_solid_ys809",
            "table_id": "tblxm1HTZQwT0hDM",
            "label": "YS809 味精",
        },
        {
            "entity_code": "qc_solid_ys810",
            "table_id": "tbl2CTvEFrGUiwyO",
            "label": "YS810 硫酸铵",
        },
        {
            "entity_code": "qc_solid_ys813",
            "table_id": "tbl5FplR13f63QN2",
            "label": "YS813 柠檬酸钠",
        },
        {
            "entity_code": "qc_solid_ys814",
            "table_id": "tbl5kbEStxM5MpqR",
            "label": "YS814 BR级琼脂",
        },
    ],
    "manual": [
        {
            "entity_code": "qc_solid_manual_msvxtv",
            "table_id": "tbl5LoATe7MSVXTv",
            "label": "L-盐酸赖氨酸（去甲用）",
        },
        {
            "entity_code": "qc_solid_manual_jgw8uq",
            "table_id": "tbl5xLjrFUjGW8UQ",
            "label": "黄血盐钠",
        },
        {
            "entity_code": "qc_solid_manual_lveh9l",
            "table_id": "tbl36xDpEnlVEH9l",
            "label": "中温淀粉酶",
        },
        {
            "entity_code": "qc_solid_manual_ufjdgx",
            "table_id": "tbl2FSI44bUFjDGX",
            "label": "十二脂肪烷基三甲基氯化铵",
        },
        {
            "entity_code": "qc_solid_manual_ntqrid",
            "table_id": "tbl2yIlXygntQRId",
            "label": "中温黄豆饼粉（去甲用）",
        },
    ],
}

LIQUID_GROUP_ITEMS: dict[str, list[dict[str, str]]] = {
    "yl-0xx": [
        {
            "entity_code": "qc_liquid_yl001",
            "table_id": "tbl34mvYJjOKmlWC",
            "label": "YL001 大豆油",
        },
        {
            "entity_code": "qc_liquid_yl002",
            "table_id": "tbl5jP9ULm5WFRKm",
            "label": "YL002 甘油",
        },
        {
            "entity_code": "qc_liquid_yl003",
            "table_id": "tbl6FpB90EtFnzcz",
            "label": "YL003 聚醚类消泡剂",
        },
        {
            "entity_code": "qc_liquid_yl004",
            "table_id": "tbl5bSzOHdHgkXWe",
            "label": "YL004 工业丙酮",
        },
        {
            "entity_code": "qc_liquid_yl005",
            "table_id": "tbl5XHljUxFP7yoD",
            "label": "YL005 甲苯",
        },
        {
            "entity_code": "qc_liquid_yl006",
            "table_id": "tbl5gRs3eKvtDICG",
            "label": "YL006 工业浓硫酸",
        },
        {
            "entity_code": "qc_liquid_yl007",
            "table_id": "tbl21Gy5gfg52HUY",
            "label": "YL007 液碱",
        },
        {
            "entity_code": "qc_liquid_yl008",
            "table_id": "tbl14hsHuAOuUvun",
            "label": "YL008 回收丙酮",
        },
        {
            "entity_code": "qc_liquid_yl009",
            "table_id": "tbl2DlDPK3b7rF1h",
            "label": "YL009 丙三醇",
        },
        {
            "entity_code": "qc_liquid_yl012",
            "table_id": "tbl1Dk3ZHKR2nXJf",
            "label": "YL012 回收甲苯",
        },
        {
            "entity_code": "qc_liquid_yl015",
            "table_id": "tbl6lBN8TF7swq7B",
            "label": "YL015 乙二醇",
        },
        {
            "entity_code": "qc_liquid_yl016",
            "table_id": "tbl4IIL2W77cJiAV",
            "label": "YL016 葡萄糖浆",
        },
        {
            "entity_code": "qc_liquid_yl017",
            "table_id": "tbl1I5nsMMwou4SB",
            "label": "YL017 甲醛",
        },
        {
            "entity_code": "qc_liquid_yl018",
            "table_id": "tbl6f64PtuOCvSTX",
            "label": "YL018 正庚烷",
        },
        {
            "entity_code": "qc_liquid_yl019",
            "table_id": "tblekZaHhUPXEkH5",
            "label": "YL019 乳化硅油",
        },
        {
            "entity_code": "qc_liquid_yl020",
            "table_id": "tbl3M44IrRngeT31",
            "label": "YL020 硫酸（分析纯）",
        },
        {
            "entity_code": "qc_liquid_yl021",
            "table_id": "tbl27EPIXVzSxSMW",
            "label": "YL021 无水乙醇（CP级）",
        },
        {
            "entity_code": "qc_liquid_yl022",
            "table_id": "tbl3iqWxXKywCYNM",
            "label": "YL022 乙醇（药用级）",
        },
        {
            "entity_code": "qc_liquid_yl023",
            "table_id": "tbl6t68ByRfMQoDn",
            "label": "YL023 乙醇（食品级）",
        },
        {
            "entity_code": "qc_liquid_yl024",
            "table_id": "tbl6lVPFNDMEvRrx",
            "label": "YL024 95%硫酸",
        },
        {
            "entity_code": "qc_liquid_yl025",
            "table_id": "tbl3X4OjtCr7H3Un",
            "label": "YL025 甲醇",
        },
        {
            "entity_code": "qc_liquid_yl026",
            "table_id": "tbl3Py8F6z5oDwLW",
            "label": "YL026 环己甲酸",
        },
        {
            "entity_code": "qc_liquid_yl027",
            "table_id": "tbl7LrLK7EsbNtbx",
            "label": "YL027 消泡剂",
        },
        {
            "entity_code": "qc_liquid_yl029",
            "table_id": "tbl3p77DCf7yxNcM",
            "label": "YL029 无水乙醇",
        },
        {
            "entity_code": "qc_liquid_yl030",
            "table_id": "tbl2mAE2U2deiaAb",
            "label": "YL030 THIX-298（消泡剂）",
        },
        {
            "entity_code": "qc_liquid_yl032",
            "table_id": "tbl3VgJ1TohP6U7B",
            "label": "YL032 乙酸乙酯",
        },
    ],
    "yl-1xx": [
        {
            "entity_code": "qc_liquid_yl101",
            "table_id": "tbl6bfosXEIlrUCb",
            "label": "YL101 硅酮类消泡剂",
        },
        {
            "entity_code": "qc_liquid_yl102",
            "table_id": "tbl5gdLKjMW9T78G",
            "label": "YL102 乳化剂",
        },
    ],
    "yl-2xx": [
        {
            "entity_code": "qc_liquid_yl201",
            "table_id": "tbl6VkB9vbXk3DDH",
            "label": "YL201 正己烷",
        },
        {
            "entity_code": "qc_liquid_yl202",
            "table_id": "tbl6qs6PXWrorJxd",
            "label": "YL202 曲拉通x-100",
        },
        {
            "entity_code": "qc_liquid_yl203",
            "table_id": "tbl6ayYoxqBFRVsb",
            "label": "YL203 玉米浆（MV）",
        },
        {
            "entity_code": "qc_liquid_yl204",
            "table_id": "tbl1NUmbaXFIsBGG",
            "label": "YL204 AR级盐酸",
        },
    ],
    "yl-3xx": [
        {
            "entity_code": "qc_liquid_yl301",
            "table_id": "tbl7LIJWEDdLFeCi",
            "label": "YL301 P-2000消泡剂",
        },
    ],
    "yl-4xx": [
        {
            "entity_code": "qc_liquid_yl401",
            "table_id": "tbl4BD2uj30ODvak",
            "label": "YL401 复合消泡剂",
        },
        {
            "entity_code": "qc_liquid_yl402",
            "table_id": "tbl7clgW00LlXCo9",
            "label": "YL402 盐酸（工业级）",
        },
        {
            "entity_code": "qc_liquid_yl403",
            "table_id": "tbl5dKOmnuDgN1iD",
            "label": "YL403 仲辛醇",
        },
        {
            "entity_code": "qc_liquid_yl404",
            "table_id": "tbl7ax6RQ5oSDnWF",
            "label": "YL404 玉米浆",
        },
        {
            "entity_code": "qc_liquid_yl405",
            "table_id": "tbl3jdbswXZlAWc3",
            "label": "YL405 CP级盐酸",
        },
        {
            "entity_code": "qc_liquid_yl407",
            "table_id": "tbl2zcAMYFP4MxRN",
            "label": "YL407 液糖",
        },
    ],
    "yl-5xx": [
        {
            "entity_code": "qc_liquid_yl501",
            "table_id": "tbl616YjXdZm9xWh",
            "label": "YL501 食用级磷酸",
        },
        {
            "entity_code": "qc_liquid_yl502",
            "table_id": "tbl5gPB6lLTUOzuL",
            "label": "YL502 高温淀粉酶",
        },
        {
            "entity_code": "qc_liquid_yl503",
            "table_id": "tbl1m9AEGDKX9W0Y",
            "label": "YL503 氨水",
        },
        {
            "entity_code": "qc_liquid_yl504",
            "table_id": "tbl4OmnxgxM1xwbI",
            "label": "YL504 双氧水",
        },
        {
            "entity_code": "qc_liquid_yl505",
            "table_id": "tbl4fDPnYkGCFZor",
            "label": "YL505 糖化酶",
        },
        {
            "entity_code": "qc_liquid_yl506",
            "table_id": "tbl6kNN68VPAXYYg",
            "label": "YL506 次氯酸钠",
        },
        {
            "entity_code": "qc_liquid_yl507",
            "table_id": "tbl6BcQRk10VNM09",
            "label": "YL507 反渗透阻垢剂",
        },
        {
            "entity_code": "qc_liquid_yl508",
            "table_id": "tbl3bwKxqCvWKZ8v",
            "label": "YL508 工业用乙酸丁酯",
        },
        {
            "entity_code": "qc_liquid_yl509",
            "table_id": "tbl2QX4mCH6zmJwX",
            "label": "YL509 4850us消泡剂",
        },
        {
            "entity_code": "qc_liquid_yl511",
            "table_id": "tbl5fU6VvY1mqoBh",
            "label": "YL511 环己甲酸",
        },
        {
            "entity_code": "qc_liquid_yl512",
            "table_id": "tbl4XOMOl9fCB9d5",
            "label": "YL512 回收甲醇",
        },
        {
            "entity_code": "qc_liquid_yl513",
            "table_id": "tbl4J6YS7mUBDPd0",
            "label": "YL513 异丙醚",
        },
    ],
    "yl-6xx": [
        {
            "entity_code": "qc_liquid_yl602",
            "table_id": "tbl1yhriDQnoLjSM",
            "label": "YL602 无水乙醇",
        },
        {
            "entity_code": "qc_liquid_yl603",
            "table_id": "tblZ5o3byoU4Fy6I",
            "label": "YL603 浓硝酸",
        },
        {
            "entity_code": "qc_liquid_yl604",
            "table_id": "tbl37aoF3RftVySf",
            "label": "YL604 稀硝酸",
        },
    ],
    "yl-7xx": [
        {
            "entity_code": "qc_liquid_yl701",
            "table_id": "tbl2iRCTJs7B32DD",
            "label": "YL701 液氨",
        },
    ],
    "yl-8xx": [
        {
            "entity_code": "qc_liquid_yl801",
            "table_id": "tbl6UTLbgPNwVpVd",
            "label": "YL801 工业浓硫酸",
        },
        {
            "entity_code": "qc_liquid_yl803",
            "table_id": "tbl25kRRlWx1zmd0",
            "label": "YL803 聚醚类消泡剂",
        },
    ],
}


def _flatten_items(groups: dict[str, list[dict[str, str]]]) -> Iterable[dict[str, str]]:
    for items in groups.values():
        yield from items


SOLID_MATERIAL_NEW_TABLE_IDS: dict[str, str] = {
    "qc_solid_ys001": "tbl22bufTp7GGXwk",
    "qc_solid_ys002": "tblr6H8kGD3gtFW8",
    "qc_solid_ys003": "tbl0fIwEomjxR8w2",
    "qc_solid_ys004": "tblPMkgoBJFeDLMJ",
    "qc_solid_ys005": "tblyybnIuNRQw36Z",
    "qc_solid_ys006": "tblfUx9DIU4opMjh",
    "qc_solid_ys007": "tblL0ZvwMiy0O5GX",
    "qc_solid_ys008": "tblwXsDyhGRlsIrf",
    "qc_solid_ys009": "tblA2qRr757pDSNK",
    "qc_solid_ys010": "tblOJoZHOnuRyGgS",
    "qc_solid_ys011": "tbljtukrBXTzMkuh",
    "qc_solid_ys012": "tbluGONgJDaHFInW",
    "qc_solid_ys013": "tblYqwmBr6JC1Srg",
    "qc_solid_ys014": "tblEyJXShRMqUa9H",
    "qc_solid_ys015": "tblKZbNSkE8c4Gkc",
    "qc_solid_ys016": "tbl2JXf6JT0rYtRk",
    "qc_solid_ys017": "tblklGwUG6KQUHvx",
    "qc_solid_ys018": "tblwax8w3R9sjw8C",
    "qc_solid_ys019": "tbld6lTYinNZLAsz",
    "qc_solid_ys020": "tbl0TlrDFJ7zMGfD",
    "qc_solid_ys021": "tblBUIudR5KjZJh0",
    "qc_solid_ys022": "tblrAUAYt8yp5PuO",
    "qc_solid_ys023": "tblgZmOFPGtwWN8C",
    "qc_solid_ys024": "tbln5iOm3saFt8vR",
    "qc_solid_ys025": "tbl1F2D8nky608V2",
    "qc_solid_ys026": "tblyZcMoHd7umvcW",
    "qc_solid_ys027": "tblldolYH7tjDDnC",
    "qc_solid_ys028": "tblXeyQR2zmDqjQG",
    "qc_solid_ys029": "tblXE8se0JAlxCeI",
    "qc_solid_ys030": "tblX0OebuCw3az6R",
    "qc_solid_ys034": "tblbZotGpQxfvtkJ",
    "qc_solid_ys038": "tblAEZKygR6yt0Yf",
    "qc_solid_ys039": "tblgx8XHVm4WWRTO",
    "qc_solid_ys040": "tbl7Pb3kdBTThCAA",
    "qc_solid_ys044": "tbl5bU4ZWtw07NLj",
    "qc_solid_ys047": "tblvMmeNguouyV3s",
    "qc_solid_ys048": "tbl2u4M9uxOX0KG3",
    "qc_solid_ys051": "tblN246yqWll3yF3",
    "qc_solid_ys052": "tblBN44qar7FBF8S",
    "qc_solid_ys053": "tblILf2E52oKNXzn",
    "qc_solid_ys105": "tblwLcTUDRBy8NgT",
    "qc_solid_ys107": "tblqOpZ4oKwjJX2r",
    "qc_solid_ys110": "tblv91nJtKDTgcmg",
    "qc_solid_ys112": "tblKMzrlnYBXHUXo",
    "qc_solid_ys201": "tbl8422kYxJxurEK",
    "qc_solid_ys301": "tblsOn5MqIeieekU",
    "qc_solid_ys302": "tblJ4zNdBvYG2CgQ",
    "qc_solid_ys303": "tblmF9AMmuSYuJQZ",
    "qc_solid_ys304": "tbljVidqjbcpJlOZ",
    "qc_solid_ys401": "tblMTk05FKLpftLG",
    "qc_solid_ys403": "tblhITS9R7QxHoHv",
    "qc_solid_ys404": "tbl9YB1p7M3j9l0Z",
    "qc_solid_ys405": "tblzTgpj72y9WZuo",
    "qc_solid_ys406": "tblbl4zeXrKhqgbK",
    "qc_solid_ys407": "tblDj7dKwvafPoVY",
    "qc_solid_ys412": "tblPAgC7HuUgqyIX",
    "qc_solid_ys415": "tbldfAG4pYL6B8Rr",
    "qc_solid_ys501": "tbl35m4mxsdBsUM8",
    "qc_solid_ys502": "tblqlfpm7hIyumrU",
    "qc_solid_ys503": "tbl3W1i2yJiYAldN",
    "qc_solid_ys504": "tblL4uT9VVZwIeFr",
    "qc_solid_ys505": "tbliSV1BQcgbrL5B",
    "qc_solid_ys507": "tblfgFt1qnXF3v5X",
    "qc_solid_ys511": "tblOecpTL6xv0v7Z",
    "qc_solid_ys513": "tbllBEW5t32kSEcV",
    "qc_solid_ys513_fvhdro": "tbllBEW5t32kSEcV",
    "qc_solid_ys514": "tblgcnJhVXRYu9tT",
    "qc_solid_ys514_sgx7j0": "tblgcnJhVXRYu9tT",
    "qc_solid_ys515": "tblYrFRQq8dAeHgl",
    "qc_solid_ys516": "tblm5EJBQdUj8qg5",
    "qc_solid_ys517": "tblOULZWquhVOFko",
    "qc_solid_ys520": "tbldZRMdOSU5dpRl",
    "qc_solid_ys524": "tblin8Gg0fVnyNa6",
    "qc_solid_ys525": "tbl29Wn2a2hqsPdb",
    "qc_solid_ys528": "tbl1Hn4BJYbxWpin",
    "qc_solid_ys530": "tblPaZrR6QDm5Odf",
    "qc_solid_ys531": "tblaHyvoJaFa2ZHz",
    "qc_solid_ys602": "tbl7wFqgQ3ZNCm7Y",
    "qc_solid_ys603": "tblQLCoHSUGbTEtz",
    "qc_solid_ys604": "tblJP5EG71A8t8gi",
    "qc_solid_ys606": "tblle6hSCX0RR2MM",
    "qc_solid_ys702": "tblHlF2aPfBegl2x",
    "qc_solid_ys703": "tblqtdcl8o4drEVl",
    "qc_solid_ys704": "tblF8ADdIpC92JjK",
    "qc_solid_ys704_oowx6g": "tblF8ADdIpC92JjK",
    "qc_solid_ys705": "tbls9Dl3dzofqFUX",
    "qc_solid_ys712": "tblzze1gVB5SCB6R",
    "qc_solid_ys803": "tblo7kybLBDmx1W4",
    "qc_solid_ys804": "tblwQ4L28qJAzyq9",
    "qc_solid_ys805": "tblfcK4WZBG81eXh",
    "qc_solid_ys806": "tblr1vud0izn1Xe7",
    "qc_solid_ys809": "tblmCvPUXXxAED9g",
    "qc_solid_ys810": "tblhMwTKvHnQt4ee",
    "qc_solid_ys813": "tblhddMjBv3drlKd",
    "qc_solid_ys814": "tblXU6F8whSe7Nxy",
    "qc_solid_manual_msvxtv": "tbl5HMLce5lCXrP2",
    "qc_solid_manual_jgw8uq": "tbl3sRv2F1yaBBJz",
    "qc_solid_manual_lveh9l": "tbl2Q2lgROvFJywd",
    "qc_solid_manual_ufjdgx": "tbln2DneffFvFXyp",
    "qc_solid_manual_ntqrid": "tblUnZXH0Fn0UFVW",
}

LIQUID_MATERIAL_NEW_TABLE_IDS: dict[str, str] = {
    "qc_liquid_yl001": "tbl4hyUkbKg5Tifv",
    "qc_liquid_yl002": "tblccmc1Y3ZUf6pj",
    "qc_liquid_yl003": "tbllIM8zSsiB9Nlx",
    "qc_liquid_yl004": "tblY5O1ejRfLtiKS",
    "qc_liquid_yl005": "tblpjisUBCCOa12H",
    "qc_liquid_yl006": "tblQizBvS3DpDFm8",
    "qc_liquid_yl007": "tblQsLax1C2Bmjxn",
    "qc_liquid_yl008": "tblIMprOC8uUqhLy",
    "qc_liquid_yl009": "tblHr0Btt8sgl7p2",
    "qc_liquid_yl012": "tblqadCdi6umdzgH",
    "qc_liquid_yl015": "tbldydSYF8m9Yoxx",
    "qc_liquid_yl016": "tbloD0JaDBq51Ozz",
    "qc_liquid_yl017": "tblbDrfWcsuX3WAG",
    "qc_liquid_yl018": "tblfLYqV2JJackAb",
    "qc_liquid_yl019": "tbld4dG8yrQvj6qi",
    "qc_liquid_yl020": "tblEmRe3xqOYS5zL",
    "qc_liquid_yl021": "tbl12nmcjsFtO2iR",
    "qc_liquid_yl022": "tbljJ1jn3y3wTSpS",
    "qc_liquid_yl023": "tblbL9OaV5gtSQYH",
    "qc_liquid_yl024": "tblod6CKL6uI0Rq9",
    "qc_liquid_yl025": "tblPO0L5w92PAnRg",
    "qc_liquid_yl026": "tbllZFytL6EVtCNw",
    "qc_liquid_yl027": "tblX3LjojomW37zt",
    "qc_liquid_yl029": "tbl7p8GpXJi3Gh0r",
    "qc_liquid_yl030": "tblP757yoylg5Ff5",
    "qc_liquid_yl032": "tblja29xj89ORdrB",
    "qc_liquid_yl101": "tblGCm4c4LPJGVMQ",
    "qc_liquid_yl102": "tbl3QVGea4JWJWGl",
    "qc_liquid_yl201": "tbl9bIPrNro8t0xe",
    "qc_liquid_yl202": "tblXwsvzEsOO57gu",
    "qc_liquid_yl203": "tblP7oEktuFydb3U",
    "qc_liquid_yl204": "tblFajtBdIsKcyGB",
    "qc_liquid_yl301": "tblxlcmGG22O4IO0",
    "qc_liquid_yl401": "tbl2u6n05vZMJRH7",
    "qc_liquid_yl402": "tblR2CPeFsezvdAN",
    "qc_liquid_yl403": "tbleny58QU8EMh41",
    "qc_liquid_yl404": "tbl1leLjMxfuoGf0",
    "qc_liquid_yl405": "tbld7Jiao6O7LDBp",
    "qc_liquid_yl407": "tblo6x7X9A0qC6wR",
    "qc_liquid_yl501": "tbld52W3kIiBwSM0",
    "qc_liquid_yl502": "tbl4Fgv5FocZLQFI",
    "qc_liquid_yl503": "tbludfJqPTaZ5eQZ",
    "qc_liquid_yl504": "tblGlTBAKjiLq3L6",
    "qc_liquid_yl505": "tblDzmtep7F1okhp",
    "qc_liquid_yl506": "tblvCR9FVk6QmyHm",
    "qc_liquid_yl507": "tbltUIpbaSEw1Mbg",
    "qc_liquid_yl508": "tblVU8kOeJPtdDoa",
    "qc_liquid_yl509": "tblLmSD0e5vtC2Oe",
    "qc_liquid_yl511": "tblPYAkI45ZZhlrY",
    "qc_liquid_yl512": "tblQXF77cfgpxOpo",
    "qc_liquid_yl513": "tbl26Yhv8iPxNYw0",
    "qc_liquid_yl602": "tbltW5WB6xb48gCH",
    "qc_liquid_yl603": "tblxHKx3t6Mlq30g",
    "qc_liquid_yl604": "tblR5UX8Gyas0Oiq",
    "qc_liquid_yl701": "tblAzE1AsODltTlH",
    "qc_liquid_yl801": "tblqeIi98bQPwWIP",
    "qc_liquid_yl803": "tblECv4dYHWPdGOn",
}


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
