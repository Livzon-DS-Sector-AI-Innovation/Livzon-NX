"""承诺批次第五组：车间配置端点/中文 base64/卡片动作入口分发。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.modules.safety.api.commitment_workshops import (
    commitment_workshops_router,
)


def _db_dep(db: Any) -> Any:
    async def _dep() -> Any:
        yield db

    return _dep


class _UserDep:
    async def __call__(self) -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(id="u-1", name="t")


async def _noop() -> Any:
    yield None


class TestWorkshopEndpoints:
    async def test_list_and_save_configs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from types import SimpleNamespace

        row = SimpleNamespace(
            id="w-1",
            workshop_name="一车间",
            reporter_open_id="ou-1",
            reporter_name="张三",
            sort_order=0,
            is_enabled=True,
        )

        async def _list(db: Any, ensure: bool = True) -> list[Any]:
            return [row]

        async def _save(db: Any, items: list[Any]) -> list[Any]:
            _save.items = items  # type: ignore[attr-defined]
            return [row]

        monkeypatch.setattr(
            "app.modules.safety.api.commitment_workshops.list_configs", _list
        )
        monkeypatch.setattr(
            "app.modules.safety.api.commitment_workshops.save_configs", _save
        )

        application = FastAPI()
        application.include_router(commitment_workshops_router, prefix="/api/v1/safety")
        from app.core.database import get_db
        from app.core.deps import get_current_user

        application.dependency_overrides[get_db] = _db_dep(object())
        application.dependency_overrides[get_current_user] = _UserDep()

        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://t"
        ) as ac:
            listed = await ac.get("/api/v1/safety/safety-commitment-workshops")
            assert listed.status_code == 200
            data = listed.json()["data"]
            assert data[0]["workshop_name"] == "一车间"
            assert data[0]["reporter_name"] == "张三"

            saved = await ac.put(
                "/api/v1/safety/safety-commitment-workshops",
                json={"items": [{"workshop_name": "一车间"}]},
            )
            assert saved.status_code == 200
            assert _save.items[0]["workshop_name"] == "一车间"  # type: ignore[attr-defined]


async def test_submit_signature_non_ascii_base64_rejected() -> None:
    """中文 base64 段 → ValueError 分支 400。"""
    from app.modules.safety.api import commitment_sign_public as relay
    from tests.modules.safety.test_commitment_sign_public import _make_token

    application = FastAPI()
    application.include_router(
        relay.commitment_sign_public_router, prefix="/api/v1/safety"
    )
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://t"
    ) as ac:
        resp = await ac.post(
            "/api/v1/safety/commitment-sign",
            json={
                "token": _make_token(),
                "image": "data:image/png;base64,中文不是base64",
            },
        )
        assert resp.status_code == 400


class TestHandleCommitmentCardAction:
    async def test_dispatch_guards(self) -> None:
        from app.modules.safety.feishu import commitment_chat_handler as h

        # 非本模块 → None
        assert await h.handle_commitment_card_action({}) is None
        # 无日期 → 参数缺失 toast
        resp = await h.handle_commitment_card_action(
            {
                "action": {"value": '{"module": "commitment", "act": "menu"}'},
                "operator": {"open_id": "ou"},
            }
        )
        assert resp is not None
        assert "参数缺失" in str(resp)

        # ws 模块 submit 无 ws 名 → 参数缺失
        value2 = json.dumps(
            {
                "module": "commitment_ws",
                "act": "submit",
                "date": "2026-11-14",
            }
        )
        resp2 = await h.handle_commitment_card_action(
            {
                "action": {"value": value2},
                "operator": {"open_id": "ou"},
            }
        )
        assert resp2 is not None
        assert "参数缺失" in str(resp2)

    async def test_dispatch_ws_submit_schedules_task(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.modules.safety.feishu import commitment_chat_handler as h

        ran: list[Any] = []

        async def _submit(open_id: str, event: Any, value: Any) -> None:
            ran.append((open_id, value))

        monkeypatch.setattr(h, "_submit_ws_form", _submit)
        value3 = json.dumps(
            {
                "module": "commitment_ws",
                "act": "submit",
                "date": "2026-11-14",
                "ws": "一车间",
            }
        )
        resp = await h.handle_commitment_card_action(
            {
                "action": {"value": value3},
                "operator": {"open_id": "ou"},
            }
        )
        assert resp is not None
        assert "提交中" in str(resp)
        import asyncio

        await asyncio.sleep(0.05)
        assert ran and ran[0][0] == "ou"
