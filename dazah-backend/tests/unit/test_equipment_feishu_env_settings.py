"""设备巡检飞书镜像环境变量回退契约测试。

数据库配置优先，环境变量仅作回退；本测试锁定 Settings 契约：
字段存在、类型为 str、默认空串（未配置即禁用同步）。
"""

from app.core.config import Settings

_EQUIPMENT_FEISHU_FIELDS = (
    "EQUIPMENT_FEISHU_APP_ID",
    "EQUIPMENT_FEISHU_APP_SECRET",
    "EQUIPMENT_FEISHU_BITABLE_APP_TOKEN",
    "EQUIPMENT_FEISHU_BITABLE_TODAY_TABLE_ID",
    "EQUIPMENT_FEISHU_BITABLE_HISTORY_TABLE_ID",
    "EQUIPMENT_FEISHU_BITABLE_DEVICE_TABLE_ID",
)


def test_equipment_feishu_settings_contract() -> None:
    fields = Settings.model_fields
    for name in _EQUIPMENT_FEISHU_FIELDS:
        assert name in fields, name
        assert fields[name].annotation is str, name
        assert fields[name].default == "", name
