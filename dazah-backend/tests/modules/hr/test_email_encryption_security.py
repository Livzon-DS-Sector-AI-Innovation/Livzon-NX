"""Mail credentials are encrypted before any configuration is committed."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.core.llm import encryption
from app.core.llm.exceptions import LLMConfigError
from app.modules.hr import api
from app.platform.identity.deps import get_current_user
from app.shared import config_reader


@pytest.mark.parametrize("configured", [False, True])
async def test_mail_config_encrypts_or_refuses_before_writes(monkeypatch, configured):
    key = Fernet.generate_key().decode() if configured else None
    monkeypatch.setattr(
        encryption, "get_settings", lambda: SimpleNamespace(LLM_ENCRYPTION_KEY=key)
    )
    write = AsyncMock()
    monkeypatch.setattr(config_reader, "set_module_setting", write)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_db] = lambda: None

    @app.exception_handler(LLMConfigError)
    async def config_error(_request: Request, _exc: LLMConfigError):
        return JSONResponse(status_code=503, content={"message": "AI 服务尚未配置"})

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.put(
            "/email/config",
            json={
                "imap_host": "mail.example.test",
                "imap_pass": "synthetic-imap",
                "smtp_pass": "synthetic-smtp",
            },
        )
    if not configured:
        assert response.status_code == 503
        write.assert_not_awaited()
        assert "synthetic" not in response.text
    else:
        assert response.status_code == 200
        saved = {call.args[2]: call.args[3] for call in write.await_args_list}
        assert (
            encryption.decrypt_api_key(saved["HR_MAIL_IMAP_PASS"]) == "synthetic-imap"
        )
        assert (
            encryption.decrypt_api_key(saved["HR_MAIL_SMTP_PASS"]) == "synthetic-smtp"
        )
        assert saved["HR_MAIL_IMAP_PASS"] != "synthetic-imap"
