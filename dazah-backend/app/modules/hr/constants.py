"""HR module constants."""

import logging

logger = logging.getLogger(__name__)

# 需要在表格视图中展开为二级部门的一级部门名称
EXPANDABLE_DEPARTMENTS = [
    "质量管理部",
    "安全部",
    "201车间",
    "生产管理部",
]

# 部门分类枚举：部门名称 -> 分类
DEPARTMENT_CATEGORIES = {
    "质量管理类": ["QC", "QA", "过程控制部"],
    "安全管理类": ["安全管理科", "应急消保队"],
    "201车间类": ["201一车间", "201二车间", "201二车间（多拉）", "201三车间"],
    "生产管理类": ["生产管理", "仓储部"],
}


def match_department_category(dept_name: str) -> str | None:
    """根据部门名称匹配分类枚举。

    Args:
        dept_name: 部门名称

    Returns:
        匹配到的分类名称，未匹配返回 None
    """
    for category, names in DEPARTMENT_CATEGORIES.items():
        if dept_name in names:
            return category
    return None


# 部门审批配置：不参与审批/不显示在配置中的部门
DEPT_APPROVAL_EXCLUDE = {"总经办"}

# 部门审批配置：有子部门但不展开，直接显示自己
DEPT_APPROVAL_NO_EXPAND = {"行政部"}
