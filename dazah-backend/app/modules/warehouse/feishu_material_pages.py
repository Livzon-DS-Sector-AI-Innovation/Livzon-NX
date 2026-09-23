from dataclasses import dataclass

# 表绑定属于部署数据，不进代码：各页面实际读写的 Base/Table 由仓储设置页
# （warehouse.warehouse_page_feishu_configs）维护。本注册表只定义页面清单
# （page_key/标题），供菜单、权限映射与定时同步遍历使用；table_id/app_token
# 一律留空，禁止回填任何环境标识符。


@dataclass(frozen=True)
class FeishuWarehouseMaterialPage:
    page_key: str
    title: str
    table_id: str = ""
    app_token: str = ""


FEISHU_WAREHOUSE_MATERIAL_PAGES = {
    "raw-summary": FeishuWarehouseMaterialPage("raw-summary", "原辅料库存总表"),
    "raw-detail": FeishuWarehouseMaterialPage("raw-detail", "原辅料库存明细表"),
    "raw-ledger": FeishuWarehouseMaterialPage("raw-ledger", "原辅料出库总账"),
    "packaging-summary": FeishuWarehouseMaterialPage(
        "packaging-summary", "包材库存总表"
    ),
    "packaging-detail": FeishuWarehouseMaterialPage(
        "packaging-detail", "包材库存明细表"
    ),
    "packaging-ledger": FeishuWarehouseMaterialPage("packaging-ledger", "包材出库总账"),
    "inbound-ledger": FeishuWarehouseMaterialPage("inbound-ledger", "入库总账"),
    "qualified-suppliers": FeishuWarehouseMaterialPage(
        "qualified-suppliers", "原辅材料合格供应商一览表"
    ),
    "material-name-code-map": FeishuWarehouseMaterialPage(
        "material-name-code-map", "物料名称及代码对应表"
    ),
    # 液体入库（独立 Base）：列表仅展示到备注列，其余字段在详情弹窗查看
    "liquid-raw-inbound": FeishuWarehouseMaterialPage(
        "liquid-raw-inbound", "液体原辅料入库"
    ),
    "liquid-sugar-inbound": FeishuWarehouseMaterialPage(
        "liquid-sugar-inbound", "液糖入库"
    ),
    "hardware-summary": FeishuWarehouseMaterialPage("hardware-summary", "五金"),
    "hardware-stock-amount": FeishuWarehouseMaterialPage(
        "hardware-stock-amount", "库存五金金额"
    ),
    "hardware-electrical": FeishuWarehouseMaterialPage("hardware-electrical", "电仪"),
    "hardware-101-1-workshop": FeishuWarehouseMaterialPage(
        "hardware-101-1-workshop", "101-1车间"
    ),
    "hardware-101-2-workshop": FeishuWarehouseMaterialPage(
        "hardware-101-2-workshop", "101-2车间"
    ),
    "hardware-102-workshop": FeishuWarehouseMaterialPage(
        "hardware-102-workshop", "102车间"
    ),
    "hardware-103-workshop": FeishuWarehouseMaterialPage(
        "hardware-103-workshop", "103车间"
    ),
    "hardware-201-1-workshop": FeishuWarehouseMaterialPage(
        "hardware-201-1-workshop", "201-1车间"
    ),
    "hardware-201-2-workshop": FeishuWarehouseMaterialPage(
        "hardware-201-2-workshop", "201-2车间"
    ),
    "hardware-201-3-workshop": FeishuWarehouseMaterialPage(
        "hardware-201-3-workshop", "201-3车间"
    ),
    "hardware-202-workshop": FeishuWarehouseMaterialPage(
        "hardware-202-workshop", "202车间"
    ),
    "hardware-203-workshop": FeishuWarehouseMaterialPage(
        "hardware-203-workshop", "203车间"
    ),
    "hardware-203-3-workshop": FeishuWarehouseMaterialPage(
        "hardware-203-3-workshop", "203-3车间"
    ),
    "hardware-thermal-station": FeishuWarehouseMaterialPage(
        "hardware-thermal-station", "热动站"
    ),
    "hardware-power-department": FeishuWarehouseMaterialPage(
        "hardware-power-department", "动力部"
    ),
    "hardware-wastewater": FeishuWarehouseMaterialPage(
        "hardware-wastewater", "污水处理"
    ),
    "hardware-warehouse": FeishuWarehouseMaterialPage("hardware-warehouse", "仓库"),
    "hardware-rd-center": FeishuWarehouseMaterialPage("hardware-rd-center", "研发中心"),
    "hardware-others": FeishuWarehouseMaterialPage("hardware-others", "其它"),
    "hardware-inbound-ledger": FeishuWarehouseMaterialPage(
        "hardware-inbound-ledger", "入库记录"
    ),
    "hardware-outbound-ledger": FeishuWarehouseMaterialPage(
        "hardware-outbound-ledger", "出库记录"
    ),
    "product-summary": FeishuWarehouseMaterialPage("product-summary", "产品汇总"),
    "product-detail-l-phenylalanine": FeishuWarehouseMaterialPage(
        "product-detail-l-phenylalanine", "L-苯丙氨酸库存明细"
    ),
    "product-detail-fumaric-acid": FeishuWarehouseMaterialPage(
        "product-detail-fumaric-acid", "霉酚酸库存明细"
    ),
    "product-detail-l-tryptophan": FeishuWarehouseMaterialPage(
        "product-detail-l-tryptophan", "L-色氨酸库存明细"
    ),
    "product-detail-mevastatin": FeishuWarehouseMaterialPage(
        "product-detail-mevastatin", "美伐他汀库存明细"
    ),
    "product-detail-kitasamycin-hcl": FeishuWarehouseMaterialPage(
        "product-detail-kitasamycin-hcl", "盐酸林可霉素库存明细"
    ),
    "product-detail-doramectin": FeishuWarehouseMaterialPage(
        "product-detail-doramectin", "多拉菌素库存明细"
    ),
    "product-detail-lovastatin": FeishuWarehouseMaterialPage(
        "product-detail-lovastatin", "洛伐他汀库存明细"
    ),
    "product-detail-florfenicol-premix": FeishuWarehouseMaterialPage(
        "product-detail-florfenicol-premix", "氟苯尼考预混剂库存明细"
    ),
    "product-detail-demeclocycline-hcl": FeishuWarehouseMaterialPage(
        "product-detail-demeclocycline-hcl", "盐酸去甲金霉素库存明细"
    ),
    "product-detail-fenbendazole-powder": FeishuWarehouseMaterialPage(
        "product-detail-fenbendazole-powder", "芬苯达唑粉剂库存明细"
    ),
    "product-inbound-detail": FeishuWarehouseMaterialPage(
        "product-inbound-detail", "成品入库明细"
    ),
    "product-inbound-ledger": FeishuWarehouseMaterialPage(
        "product-inbound-ledger", "入库总账"
    ),
    "product-outbound-ledger": FeishuWarehouseMaterialPage(
        "product-outbound-ledger", "成品出库台账"
    ),
    "product-shipping": FeishuWarehouseMaterialPage("product-shipping", "发货情况"),
    # 成品每月出入库表（仪表盘专用）
    "product-inbound-monthly": FeishuWarehouseMaterialPage(
        "product-inbound-monthly", "各产品每月入库量"
    ),
    "product-outbound-monthly": FeishuWarehouseMaterialPage(
        "product-outbound-monthly", "各产品每月出库量"
    ),
}

# 成品入库总账（跨模块聚合口径，供 public_api 使用；字段名与飞书表头保持一致）
FINISHED_INBOUND_LEDGER_PAGE_KEY = "product-inbound-ledger"
FINISHED_INBOUND_PRODUCT_FIELD = "产品名称"
FINISHED_INBOUND_DATE_FIELD = "入库日期"
FINISHED_INBOUND_KG_FIELD = "入库数量（KG）"

# 成品入库明细（飞书实际表名「入库台账（明细）」；批次级实际入库口径，
# 供 public_api 使用；字段名与飞书表头保持一致）
FINISHED_INBOUND_DETAIL_PAGE_KEY = "product-inbound-detail"
FINISHED_INBOUND_DETAIL_BATCH_FIELD = "入库标签批号"
FINISHED_INBOUND_DETAIL_QTY_FIELD = "入库量"
FINISHED_INBOUND_DETAIL_CONFIRM_FIELD = "入库确认"
