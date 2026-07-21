"""Review node configuration (static data)."""


class ReviewNode:
    """审评节点配置"""

    NODES = [
        {"index": 1, "name": "CDE通知核查", "days": 40},
        {"index": 2, "name": "企业向CFDI确认核查", "days": 20},
        {"index": 3, "name": "CFDI告知企业核查", "days": 5},
        {"index": 4, "name": "开展核查", "days": 40},
        {"index": 5, "name": "企业递交核查报告", "days": 15},
        {"index": 6, "name": "CFDI递交报告给CDE", "days": 40},
        {"index": 7, "name": "预计发补日期", "days": 40},
        {"index": 8, "name": "发补递交", "days": 80},
        {"index": 9, "name": "CDE发补审评", "days": 66},
        {"index": 10, "name": "获批时间", "days": 30},
    ]

    @classmethod
    def get_all(cls) -> list[dict]:
        return cls.NODES

    @classmethod
    def get_by_index(cls, index: int) -> dict | None:
        for node in cls.NODES:
            if node["index"] == index:
                return node
        return None
