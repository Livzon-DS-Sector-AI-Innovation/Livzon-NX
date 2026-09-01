"""安全模块飞书凭证读取契约：独立于全局 Settings，按环境变量注入。

本次变更把安全模块 env 加载从全局 load_workspace_env 改为独立读取
.env.<APP_ENV>；凭证常量仍必须只来自 SAFETY_FEISHU_APP_ID/SECRET 环境变量，
保证与平台共享应用隔离（用错应用会对已授权的表报 403）。
"""

import importlib

from app.modules.safety.feishu import client as safety_client

MODULE_NAME = "app.modules.safety.feishu.client"


def test_credentials_read_from_module_env_not_global_settings(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SAFETY_FEISHU_APP_ID", "cli_safety_app")
    monkeypatch.setenv("SAFETY_FEISHU_APP_SECRET", "safety-secret")
    reloaded = importlib.reload(importlib.import_module(MODULE_NAME))
    try:
        assert reloaded.SAFETY_FEISHU_APP_ID == "cli_safety_app"
        assert reloaded.SAFETY_FEISHU_APP_SECRET == "safety-secret"
    finally:
        monkeypatch.delenv("SAFETY_FEISHU_APP_ID", raising=False)
        monkeypatch.delenv("SAFETY_FEISHU_APP_SECRET", raising=False)
        importlib.reload(safety_client)


def test_client_module_has_no_global_settings_dependency() -> None:
    source = safety_client.__loader__.get_data(safety_client.__file__).decode("utf-8")
    assert "load_workspace_env" not in source
    assert "app.core.config" not in source
