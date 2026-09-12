"""人员头像映射接口（person-avatar-map）测试。

文本/单选类型的「入库人/领料人」等人员字段只存姓名字符串，前端渲染
真实头像需要按姓名查人事-飞书联系人的 avatar_url。查询实现收口在
hr.public_api.get_active_avatar_map_by_name，仓储 service 仅委托调用。
本文件验证：
- 公开函数把 (姓名, avatar_url) 行聚合为映射，且跳过空头像
- 仓储 service 委托公开函数（不自行实现查询）
- 路由对该映射原样返回
"""

from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

from app.modules.hr.public_api import get_active_avatar_map_by_name
from app.modules.warehouse.service import WarehouseService


async def test_public_api_builds_name_map_and_skips_empty_avatar() -> None:
    """同名多行按姓名聚合，avatar 为空/空串的姓名不进入映射。"""
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.all = MagicMock(
        return_value=[
            ("杨舒惠", "https://s1-imfile.feishucdn.example/a.webp"),
            ("李四", None),
            ("王五", ""),
        ]
    )
    session.execute = AsyncMock(return_value=execute_result)

    mapping = await get_active_avatar_map_by_name(session)

    assert mapping == {"杨舒惠": "https://s1-imfile.feishucdn.example/a.webp"}


async def test_service_delegates_to_hr_public_api() -> None:
    """仓储 service 不自行查询，委托 hr 公开函数。"""
    service = WarehouseService.__new__(WarehouseService)
    service.repo = AsyncMock()
    with patch(
        "app.modules.hr.public_api.get_active_avatar_map_by_name",
        new=AsyncMock(return_value={"杨舒惠": "https://s1-imfile.feishucdn.example/a.webp"}),
    ):
        mapping = await service.get_person_avatar_map()

    assert mapping == {"杨舒惠": "https://s1-imfile.feishucdn.example/a.webp"}


async def test_route_returns_avatar_map(client: AsyncClient) -> None:
    """路由返回 {姓名: 头像URL} 映射。"""
    with patch(
        "app.modules.hr.public_api.get_active_avatar_map_by_name",
        new=AsyncMock(return_value={"杨舒惠": "https://s1-imfile.feishucdn.example/a.webp"}),
    ):
        response = await client.get("/api/v1/warehouse/person-avatar-map")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["杨舒惠"] == "https://s1-imfile.feishucdn.example/a.webp"
