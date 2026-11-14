"""承诺聊天 handler 状态机：车间填报起表/装载/提交（mock cache 与会话）。"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import pytest

from app.modules.safety.feishu import commitment_chat_handler as h


def _user(name: str = "填报人甲") -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(id="u-1", name=name, feishu_open_id="ou-f")


class _DB:
    def __init__(self, result: Any = None) -> None:
        self._result = result

    async def execute(self, *_a: Any, **_kw: Any) -> Any:
        from types import SimpleNamespace

        return SimpleNamespace(scalar_one_or_none=lambda: self._result)


def _patch_cache(
    monkeypatch: pytest.MonkeyPatch, store: dict[str, str]
) -> list[tuple[str, str]]:
    saved: list[tuple[str, str]] = []

    async def _get(key: str) -> str | None:
        return store.get(key)

    async def _set(key: str, payload: str, ex: int = 0) -> None:
        store[key] = payload
        saved.append((key, payload))

    async def _delete(key: str) -> None:
        store.pop(key, None)

    monkeypatch.setattr(h, "cache_get", _get)
    monkeypatch.setattr(h, "cache_set", _set)
    monkeypatch.setattr(h, "cache_delete", _delete)
    return saved


class TestWsStateMachine:
    async def test_start_ws_form_prefills_existing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        fill = SimpleNamespace(fields={"workshop_total": 6})

        async def _get_fill(db: Any, date: str, ws: str) -> Any:
            return fill

        import app.modules.safety.service.commitment_workshops as ws_mod

        monkeypatch.setattr(ws_mod, "get_fill", _get_fill)

        async def _bound(db: Any, oid: str) -> Any:
            return _user()

        monkeypatch.setattr(h, "_ensure_bound_user", _bound)
        store: dict[str, str] = {}
        _patch_cache(monkeypatch, store)

        card = await h._start_ws_form(object(), "ou-f", "2026-11-14", "一车间", "旧名")
        assert card
        assert store and "一车间" in list(store.keys())[0]
        # 预填值进入状态
        state = json.loads(list(store.values())[0])
        assert state["values"]["workshop_total"] == 6
        assert state["reporter"] == "填报人甲"

    async def test_load_ws_state_variants(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_cache(monkeypatch, {"k": json.dumps({"step": 2})})
        monkeypatch.setattr(
            h,
            "_state_key",
            lambda *a, **kw: "k",
        )
        assert (await h._load_ws_state("ou", "d", "w")) == {"step": 2}

        _patch_cache(monkeypatch, {"k": "{bad"})
        assert (await h._load_ws_state("ou", "d", "w")) is None

        _patch_cache(monkeypatch, {})
        assert (await h._load_ws_state("ou", "d", "w")) is None

    async def test_submit_ws_form_expired_and_unconfirmed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        replied: list[str] = []

        async def _reply(open_id: str, text: str) -> None:
            replied.append(text)

        monkeypatch.setattr(h, "_reply_error", _reply)
        _patch_cache(monkeypatch, {})

        event: dict[str, Any] = {"action": {"form_value": {}}}
        await h._submit_ws_form("ou-f", event, {"date": "2026-11-14", "ws": "一车间"})
        assert replied and "填报会话已过期" in replied[0]

        # 有状态但未确认承诺 → 拒绝
        state = {"date": "2026-11-14", "values": {"commitment_confirm": "no"}}
        _patch_cache(
            monkeypatch,
            {"k": json.dumps(state, ensure_ascii=False)},
        )
        monkeypatch.setattr(h, "_state_key", lambda *a, **kw: "k")
        replied.clear()
        await h._submit_ws_form("ou-f", event, {"date": "2026-11-14", "ws": "一车间"})
        assert replied and "承诺确认" in replied[0]

    async def test_submit_ws_form_success_paths(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        state = {
            "date": "2026-11-14",
            "values": {"commitment_confirm": "yes", "workshop_total": 5},
        }
        store = {"k": json.dumps(state, ensure_ascii=False)}
        _patch_cache(monkeypatch, store)
        monkeypatch.setattr(h, "_state_key", lambda *a, **kw: "k")

        patched: list[tuple[str, Any]] = []

        async def _patch_msg(event: Any, card: Any) -> None:
            patched.append(("ok", card))

        monkeypatch.setattr(h, "_patch_open_message", _patch_msg)

        @asynccontextmanager
        async def _factory():
            yield _DB()

        monkeypatch.setattr(h, "async_session_factory", _factory)

        async def _bound(db: Any, oid: str) -> Any:
            return _user()

        monkeypatch.setattr(h, "_ensure_bound_user", _bound)
        replied: list[str] = []

        async def _reply(open_id: str, text: str) -> None:
            replied.append(text)

        monkeypatch.setattr(h, "_reply_error", _reply)

        import app.modules.safety.service.commitment_workshops as ws_mod

        fill = SimpleNamespace(filled_by_name="填报人甲")

        async def _save_fill(
            db: Any,
            date: str,
            ws: str,
            status: Any,
            *,
            filled_by_name: str,
            filled_by_open_id: str,
            source: str,
        ) -> Any:
            return fill

        async def _summarize(db: Any, date: str) -> tuple[bool, Any]:
            return (True, SimpleNamespace(report_date=date))

        monkeypatch.setattr(ws_mod, "save_workshop_fill", _save_fill)
        monkeypatch.setattr(ws_mod, "summarize_if_complete", _summarize)

        import app.modules.safety.service.safety_commitment as report_mod

        async def _get_report(db: Any, date: str) -> Any:
            return SimpleNamespace(report_date=date)

        monkeypatch.setattr(report_mod, "get_report_by_date", _get_report)

        import app.modules.safety.service.commitment_notify as notify_mod

        async def _push_group(db: Any, item: Any) -> None:
            patched.append(("group", item))

        monkeypatch.setattr(notify_mod, "push_summary_to_group", _push_group)

        event: dict[str, Any] = {"action": {"form_value": {}}}
        await h._submit_ws_form("ou-f", event, {"date": "2026-11-14", "ws": "一车间"})
        # 成功：PATCH 回执 + 汇总推群 + 状态清除
        kinds = [k for k, _ in patched]
        assert "ok" in kinds and "group" in kinds, f"replied={replied}"
        assert "k" not in store
        receipt = json.dumps(patched[0][1], ensure_ascii=False)
        assert "自动汇总" in receipt

        # 未齐全路径：summarize=False → 不推群
        store["k"] = json.dumps(state, ensure_ascii=False)
        patched.clear()

        async def _summarize_false(db: Any, date: str) -> tuple[bool, Any]:
            return (False, None)

        monkeypatch.setattr(ws_mod, "summarize_if_complete", _summarize_false)
        await h._submit_ws_form("ou-f", event, {"date": "2026-11-14", "ws": "一车间"})
        kinds = [k for k, _ in patched]
        assert "ok" in kinds and "group" not in kinds

    async def test_ensure_bound_user_rejects_unbound(self) -> None:
        from app.core.exceptions import AppException

        with pytest.raises(AppException) as exc:
            await h._ensure_bound_user(_DB(None), "ou-unknown")
        assert "未绑定" in str(exc.value.message)

        user = await h._ensure_bound_user(_DB(_user()), "ou-f")
        assert user.name == "填报人甲"
