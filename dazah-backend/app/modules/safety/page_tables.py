"""安全模块「页面 ↔ 飞书多维表格」镜像页注册表。

这里只登记「哪些页面支持飞书表格镜像」这一代码侧事实（页面本身由菜单、
权限与前端页面构成）。具体绑定到哪张飞书表（app_token / table_id /
view_id / 隐藏字段）存在 ``safety.page_feishu_configs``，由
「安全管理 → 系统配置 → 飞书设置」页维护，不写死在代码里。

新增一个镜像页时：在下面追加一条定义 → 菜单与权限登记 → 前端页面
（复用 PageFeishuTable）→ 在飞书设置页配置表格绑定。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PageTableDefinition:
    """一个支持飞书多维表格镜像的页面。"""

    page_key: str
    page_name: str
    route_path: str


PAGE_TABLE_DEFINITIONS: tuple[PageTableDefinition, ...] = (
    PageTableDefinition(
        page_key="safety:ops-safety:daily-risk-report",
        page_name="关键风险作业报备",
        route_path="/safety/risk-reporting",
    ),
    PageTableDefinition(
        page_key="safety:ops-safety:special-danger-work",
        page_name="次日特殊危险作业审批",
        route_path="/safety/special-danger-work",
    ),
    PageTableDefinition(
        page_key="safety:ops-safety:risk-work-registration",
        page_name="关键风险作业报备表",
        route_path="/safety/risk-work-registration",
    ),
    PageTableDefinition(
        page_key="safety:ops-safety:feeding-inspection",
        page_name="投料巡查表",
        route_path="/safety/feeding-inspection",
    ),
    PageTableDefinition(
        page_key="safety:ops-safety:hazchem-unloading-inspection",
        page_name="危险化学品卸车巡查表",
        route_path="/safety/hazchem-unloading-inspection",
    ),
    PageTableDefinition(
        page_key="safety:ops-safety:centrifuge-discharge-inspection",
        page_name="离心出料风险巡查表",
        route_path="/safety/centrifuge-discharge-inspection",
    ),
    PageTableDefinition(
        page_key="safety:risk-hazard:hazard-inspection:hazard-duty",
        page_name="24小时值班隐患",
        route_path="/safety/hazard-duty",
    ),
)

PAGE_TABLES_BY_KEY: dict[str, PageTableDefinition] = {
    item.page_key: item for item in PAGE_TABLE_DEFINITIONS
}


def get_page_table(page_key: str) -> PageTableDefinition | None:
    """按页面标识取镜像页定义；未登记返回 None。"""
    return PAGE_TABLES_BY_KEY.get(page_key)
