from dataclasses import dataclass

FEISHU_WAREHOUSE_APP_TOKEN = "IpMdbEFSlaZRoJstpFLcbTzPn2e"
FEISHU_FINISHED_PRODUCT_APP_TOKEN = "S9KobSXEIaU9K4sgohycpiLqnhg"
FEISHU_HARDWARE_APP_TOKEN = "DPjgbn78nao1lWsU7a3c3JUdnSb"

# 多维表格 Base 展示名称（页面数据来源标识）
FEISHU_WAREHOUSE_BASE_NAMES = {
    FEISHU_WAREHOUSE_APP_TOKEN: "原辅料",
    FEISHU_FINISHED_PRODUCT_APP_TOKEN: "成品",
    FEISHU_HARDWARE_APP_TOKEN: "五金",
}


@dataclass(frozen=True)
class FeishuWarehouseMaterialPage:
    page_key: str
    title: str
    table_id: str
    app_token: str = FEISHU_WAREHOUSE_APP_TOKEN


FEISHU_WAREHOUSE_MATERIAL_PAGES = {
    "raw-summary": FeishuWarehouseMaterialPage(
        "raw-summary", "原辅料库存总表", "tblVpo4DkpnA4MY9"
    ),
    "raw-detail": FeishuWarehouseMaterialPage(
        "raw-detail", "原辅料库存明细表", "tblatUqySt3gsszt"
    ),
    "raw-ledger": FeishuWarehouseMaterialPage(
        "raw-ledger", "原辅料出库总账", "tblVAr4M5pxZC5Bh"
    ),
    "packaging-summary": FeishuWarehouseMaterialPage(
        "packaging-summary", "包材库存总表", "tbl1kBwhko7730gI"
    ),
    "packaging-detail": FeishuWarehouseMaterialPage(
        "packaging-detail", "包材库存明细表", "tblseg0I5JhtVvc0"
    ),
    "packaging-ledger": FeishuWarehouseMaterialPage(
        "packaging-ledger", "包材出库总账", "tblwecS4CubKojaE"
    ),
    "inbound-ledger": FeishuWarehouseMaterialPage(
        "inbound-ledger", "入库总账", "tblIqPXnlcHNd5cO"
    ),
    "qualified-suppliers": FeishuWarehouseMaterialPage(
        "qualified-suppliers", "原辅材料合格供应商一览表", "tblwSK3AMuhoflO6"
    ),
    "material-name-code-map": FeishuWarehouseMaterialPage(
        "material-name-code-map", "物料名称及代码对应表", "tblDs6dg1S8z3HMz"
    ),
    "hardware-summary": FeishuWarehouseMaterialPage(
        "hardware-summary", "五金", "tbl7H8wRnEyVwfIk", FEISHU_HARDWARE_APP_TOKEN
    ),
    "hardware-stock-amount": FeishuWarehouseMaterialPage(
        "hardware-stock-amount",
        "库存五金金额",
        "tbl5n6VVax0LiOmX",
        FEISHU_HARDWARE_APP_TOKEN,
    ),
    "hardware-electrical": FeishuWarehouseMaterialPage(
        "hardware-electrical", "电仪", "tblXUXRU8k6yVXst", FEISHU_HARDWARE_APP_TOKEN
    ),
    "hardware-101-1-workshop": FeishuWarehouseMaterialPage(
        "hardware-101-1-workshop",
        "101-1车间",
        "tbl5Yq6l1cjjutdm",
        FEISHU_HARDWARE_APP_TOKEN,
    ),
    "hardware-101-2-workshop": FeishuWarehouseMaterialPage(
        "hardware-101-2-workshop",
        "101-2车间",
        "tbl2CYep4wkk0Rso",
        FEISHU_HARDWARE_APP_TOKEN,
    ),
    "hardware-102-workshop": FeishuWarehouseMaterialPage(
        "hardware-102-workshop",
        "102车间",
        "tblPo2CQ2MaJ9VVB",
        FEISHU_HARDWARE_APP_TOKEN,
    ),
    "hardware-103-workshop": FeishuWarehouseMaterialPage(
        "hardware-103-workshop",
        "103车间",
        "tbl4bUU7sHuPTz40",
        FEISHU_HARDWARE_APP_TOKEN,
    ),
    "hardware-201-1-workshop": FeishuWarehouseMaterialPage(
        "hardware-201-1-workshop",
        "201-1车间",
        "tbl8ZowunuIcYlGZ",
        FEISHU_HARDWARE_APP_TOKEN,
    ),
    "hardware-201-2-workshop": FeishuWarehouseMaterialPage(
        "hardware-201-2-workshop",
        "201-2车间",
        "tblmZ0axagVIXQZq",
        FEISHU_HARDWARE_APP_TOKEN,
    ),
    "hardware-201-3-workshop": FeishuWarehouseMaterialPage(
        "hardware-201-3-workshop",
        "201-3车间",
        "tblCcCM493dBNlTA",
        FEISHU_HARDWARE_APP_TOKEN,
    ),
    "hardware-202-workshop": FeishuWarehouseMaterialPage(
        "hardware-202-workshop",
        "202车间",
        "tblmlm1gScfdqV4f",
        FEISHU_HARDWARE_APP_TOKEN,
    ),
    "hardware-203-workshop": FeishuWarehouseMaterialPage(
        "hardware-203-workshop",
        "203车间",
        "tbluSk7tQI6XyoCM",
        FEISHU_HARDWARE_APP_TOKEN,
    ),
    "hardware-203-3-workshop": FeishuWarehouseMaterialPage(
        "hardware-203-3-workshop",
        "203-3车间",
        "tbliuToAcjU69AMQ",
        FEISHU_HARDWARE_APP_TOKEN,
    ),
    "hardware-thermal-station": FeishuWarehouseMaterialPage(
        "hardware-thermal-station",
        "热动站",
        "tblNWGMutusUG1e2",
        FEISHU_HARDWARE_APP_TOKEN,
    ),
    "hardware-power-department": FeishuWarehouseMaterialPage(
        "hardware-power-department",
        "动力部",
        "tblRvZqWb1ZecnZe",
        FEISHU_HARDWARE_APP_TOKEN,
    ),
    "hardware-wastewater": FeishuWarehouseMaterialPage(
        "hardware-wastewater",
        "污水处理",
        "tblzGe1FOFm3IOAI",
        FEISHU_HARDWARE_APP_TOKEN,
    ),
    "hardware-warehouse": FeishuWarehouseMaterialPage(
        "hardware-warehouse",
        "仓库",
        "tblh5gHW27KcYY1o",
        FEISHU_HARDWARE_APP_TOKEN,
    ),
    "hardware-rd-center": FeishuWarehouseMaterialPage(
        "hardware-rd-center",
        "研发中心",
        "tblgIAUVLCfGZeTi",
        FEISHU_HARDWARE_APP_TOKEN,
    ),
    "hardware-others": FeishuWarehouseMaterialPage(
        "hardware-others",
        "其它",
        "tblmhAOjtU3Rjkot",
        FEISHU_HARDWARE_APP_TOKEN,
    ),
    "hardware-inbound-ledger": FeishuWarehouseMaterialPage(
        "hardware-inbound-ledger",
        "入库记录",
        "tblhIziXz8gsBbRo",
        FEISHU_HARDWARE_APP_TOKEN,
    ),
    "hardware-outbound-ledger": FeishuWarehouseMaterialPage(
        "hardware-outbound-ledger",
        "出库记录",
        "tblT5zX43vT1tUSa",
        FEISHU_HARDWARE_APP_TOKEN,
    ),
    "product-summary": FeishuWarehouseMaterialPage(
        "product-summary",
        "产品汇总",
        "tbls0U6Le4oydpCd",
        FEISHU_FINISHED_PRODUCT_APP_TOKEN,
    ),
    "product-detail-l-phenylalanine": FeishuWarehouseMaterialPage(
        "product-detail-l-phenylalanine",
        "L-苯丙氨酸库存明细",
        "tbl58XXNcYo0WxAN",
        FEISHU_FINISHED_PRODUCT_APP_TOKEN,
    ),
    "product-detail-fumaric-acid": FeishuWarehouseMaterialPage(
        "product-detail-fumaric-acid",
        "霉酚酸库存明细",
        "tbl8XhmNLYGsYceY",
        FEISHU_FINISHED_PRODUCT_APP_TOKEN,
    ),
    "product-detail-l-tryptophan": FeishuWarehouseMaterialPage(
        "product-detail-l-tryptophan",
        "L-色氨酸库存明细",
        "tblUusYnVSKQpdI4",
        FEISHU_FINISHED_PRODUCT_APP_TOKEN,
    ),
    "product-detail-mevastatin": FeishuWarehouseMaterialPage(
        "product-detail-mevastatin",
        "美伐他汀库存明细",
        "tbl6kXYvrCJfFUTf",
        FEISHU_FINISHED_PRODUCT_APP_TOKEN,
    ),
    "product-detail-kitasamycin-hcl": FeishuWarehouseMaterialPage(
        "product-detail-kitasamycin-hcl",
        "盐酸林可霉素库存明细",
        "tbli2aDZpYa9BO2U",
        FEISHU_FINISHED_PRODUCT_APP_TOKEN,
    ),
    "product-detail-doramectin": FeishuWarehouseMaterialPage(
        "product-detail-doramectin",
        "多拉菌素库存明细",
        "tblxitcL2g0Tm53L",
        FEISHU_FINISHED_PRODUCT_APP_TOKEN,
    ),
    "product-detail-lovastatin": FeishuWarehouseMaterialPage(
        "product-detail-lovastatin",
        "洛伐他汀库存明细",
        "tbl8dfIY3O1a1M7u",
        FEISHU_FINISHED_PRODUCT_APP_TOKEN,
    ),
    "product-detail-florfenicol-premix": FeishuWarehouseMaterialPage(
        "product-detail-florfenicol-premix",
        "氟苯尼考预混剂库存明细",
        "tblsNwrKtC6CoMmx",
        FEISHU_FINISHED_PRODUCT_APP_TOKEN,
    ),
    "product-detail-demeclocycline-hcl": FeishuWarehouseMaterialPage(
        "product-detail-demeclocycline-hcl",
        "盐酸去甲金霉素库存明细",
        "tblhtyz11ZrwlMVE",
        FEISHU_FINISHED_PRODUCT_APP_TOKEN,
    ),
    "product-detail-fenbendazole-powder": FeishuWarehouseMaterialPage(
        "product-detail-fenbendazole-powder",
        "芬苯达唑粉剂库存明细",
        "tblmghZOEyVHO2Yl",
        FEISHU_FINISHED_PRODUCT_APP_TOKEN,
    ),
    "product-inbound-detail": FeishuWarehouseMaterialPage(
        "product-inbound-detail",
        "成品入库明细",
        "tblA5XrTrmoCv9SW",
        FEISHU_FINISHED_PRODUCT_APP_TOKEN,
    ),
    "product-inbound-ledger": FeishuWarehouseMaterialPage(
        "product-inbound-ledger",
        "入库总账",
        "tbloVqkVZEYmLfyB",
        FEISHU_FINISHED_PRODUCT_APP_TOKEN,
    ),
    "product-outbound-ledger": FeishuWarehouseMaterialPage(
        "product-outbound-ledger",
        "成品出库台账",
        "tblAwkQjxcKI7HAj",
        FEISHU_FINISHED_PRODUCT_APP_TOKEN,
    ),
    "product-shipping": FeishuWarehouseMaterialPage(
        "product-shipping",
        "发货情况",
        "tblo2Vacb0bpDoLi",
        FEISHU_FINISHED_PRODUCT_APP_TOKEN,
    ),
    # 成品每月出入库表（仪表盘专用）
    "product-inbound-monthly": FeishuWarehouseMaterialPage(
        "product-inbound-monthly",
        "各产品每月入库量 -26 年",
        "tblKIKUwzbDOG8vr",
        FEISHU_FINISHED_PRODUCT_APP_TOKEN,
    ),
    "product-outbound-monthly": FeishuWarehouseMaterialPage(
        "product-outbound-monthly",
        "各产品每月出库量 -26 年",
        "tblrHD0u1E9jBXlB",
        FEISHU_FINISHED_PRODUCT_APP_TOKEN,
    ),
}
