"""设备模块 API 聚合入口：路由挂载完整性。"""

from app.modules.equipment.api import router


def test_equipment_api_aggregation_exposes_key_routes() -> None:
    paths = {route.path for route in router.routes}
    # 车间注册表（本批新增）
    assert "/workshops" in paths
    assert "/workshops/all" in paths
    # 飞书应用库（本批新增；inspection_feishu 路由挂 /inspection 前缀下）
    assert "/inspection/feishu/apps" in paths
    # 设备核心与维护域
    assert "/equipments" in paths or "" in paths
    assert "/maintenance/work-orders" in paths
    assert "/maintenance/plans" in paths


def test_equipment_api_dual_registered_list_routes() -> None:
    """列表路由双注册（带/不带尾斜杠）：代理访问时避免 307 暴露内部地址。"""
    paths = {route.path for route in router.routes}
    for base in (
        "/maintenance/work-orders",
        "/maintenance/plans",
        "/spare-parts",
    ):
        assert base in paths, f"{base} 缺少无尾斜杠路由"
        assert f"{base}/" in paths, f"{base}/ 缺少尾斜杠路由"
