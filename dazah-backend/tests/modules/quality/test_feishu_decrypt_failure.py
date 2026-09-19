"""质量模块飞书密钥解密失败分支：必须转明确业务提示而非"AI 未配置"503。"""

import pytest

from app.core.exceptions import AppException
from app.core.llm.exceptions import LLMConfigError
from app.modules.quality.service import quality_feishu_sync


@pytest.mark.asyncio
async def test_decrypt_failure_raises_clear_business_error(db_session, monkeypatch):
    """App Secret 解密失败（密钥轮换）→ 400 明确提示，不再冒泡成"AI 未配置"503。"""
    def _raise_bad_key(_value: str) -> str:
        raise LLMConfigError("bad key")

    monkeypatch.setattr(quality_feishu_sync, "decrypt_api_key", _raise_bad_key)

    from app.modules.quality.models import QualityFeishuAppSettings

    row = QualityFeishuAppSettings(
        app_id="cli_quality_test",
        app_secret="encrypted-payload",
        is_enabled=True,
    )
    db_session.add(row)
    await db_session.flush()

    svc = quality_feishu_sync.QualityFeishuSync()
    with pytest.raises(AppException) as exc:
        await svc._resolve_runtime(db_session)
    assert "解密失败" in exc.value.message
    assert "飞书" in exc.value.message
