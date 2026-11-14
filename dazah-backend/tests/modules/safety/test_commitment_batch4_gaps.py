"""承诺批次第四组缺口：签名图读取/车间填报保存/下载端点/通知内部路径。"""

from __future__ import annotations

import io
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.modules.safety.api.safety_commitments import safety_commitments_router


def _png_bytes() -> bytes:

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "black").save(buf, "PNG")
    return buf.getvalue()


class TestReadSignatureImage:
    def test_read_ok_and_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.modules.safety.service import commitment_signatures as sig

        monkeypatch.setattr(
            sig, "read_object", lambda bucket, key: (_png_bytes(), "image/png")
        )
        assert sig.read_signature_image("k") is not None

        monkeypatch.setattr(sig, "read_object", lambda bucket, key: None)
        assert sig.read_signature_image("k") is None

        def _boom(bucket: str, key: str) -> Any:
            raise RuntimeError("storage down")

        monkeypatch.setattr(sig, "read_object", _boom)
        assert sig.read_signature_image("k") is None


class TestSaveWorkshopFill:
    async def test_save_creates_and_updates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        from app.modules.safety.service import commitment_workshops as ws_mod

        existing = SimpleNamespace(
            id="f-1",
            report_date="2026-11-14",
            workshop_name="一车间",
            fields={},
            filled_by_name=None,
            filled_by_open_id=None,
            filled_at=None,
            source="",
            remark=None,
        )
        added: list[Any] = []

        async def _get_fill(db: Any, date: str, ws: str) -> Any:
            return existing if ws == "一车间" else None

        monkeypatch.setattr(ws_mod, "get_fill", _get_fill)

        async def _audit(*a: Any, **kw: Any) -> None:
            return None

        monkeypatch.setattr(ws_mod, "record_audit_log", _audit)

        class _DB:
            def add(self, obj: Any) -> None:
                added.append(obj)

            async def commit(self) -> None:
                return None

            async def refresh(self, obj: Any) -> None:
                return None

        # 更新既有
        await ws_mod.save_workshop_fill(
            _DB(),
            "2026-11-14",
            "一车间",
            {"workshop_total": 3},
            filled_by_name="张三",
            filled_by_open_id="ou",
            source="feishu",
        )
        assert existing.fields == {"workshop_total": 3}
        assert existing.filled_by_name == "张三"
        assert existing.source == "feishu"

        # 新建（另一车间）
        created = await ws_mod.save_workshop_fill(
            _DB(),
            "2026-11-14",
            "二车间",
            {"workshop_total": 1},
            filled_by_name=None,
            filled_by_open_id=None,
            source="web",
        )
        assert created.workshop_name == "二车间"
        assert added and added[0] is created


class TestCommitmentEndpoints:
    """签名图/下载端点：mock service 层走 HTTP。"""

    @pytest.fixture
    async def client(self, monkeypatch: pytest.MonkeyPatch) -> AsyncClient:
        application = FastAPI()
        application.include_router(safety_commitments_router, prefix="/api/v1/safety")

        async def _user() -> Any:
            from types import SimpleNamespace

            return SimpleNamespace(id="u-1", name="t")

        from app.core.database import get_db
        from app.core.deps import get_current_user

        class _EmptyDB:
            async def get(self, model: Any, rid: Any) -> Any:
                return None

        application.dependency_overrides[get_db] = _db_factory(_EmptyDB())
        application.dependency_overrides[get_current_user] = _user
        return AsyncClient(
            transport=ASGITransport(app=application), base_url="http://t"
        )

    async def test_signature_image_endpoints(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from types import SimpleNamespace

        from app.modules.safety.service import commitment_signatures as sig

        sig_row = SimpleNamespace(image_key="commitment-signatures/k.png")

        async def _by_date(db: Any, date: Any) -> Any:
            return sig_row

        monkeypatch.setattr(sig, "get_by_date", _by_date)
        png = _png_bytes()
        monkeypatch.setattr(sig, "read_signature_image", lambda key: png)

        async with client as ac:
            ok = await ac.get("/api/v1/safety/safety-commitments/signature-image")
            assert ok.status_code == 200
            assert ok.content == png
            assert ok.headers["content-type"] == "image/png"

    async def test_download_commitment_pdf(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from datetime import date
        from types import SimpleNamespace
        from uuid import uuid4

        import app.modules.safety.api.safety_commitments as api_mod
        from app.modules.safety.service import commitment_signatures as sig

        rid = uuid4()
        report = SimpleNamespace(
            id=rid,
            report_date=date(2026, 11, 14),
            is_deleted=False,
            enterprise_status={},
        )

        class _DB:
            async def get(self, model: Any, rid: Any) -> Any:
                return report if str(rid) == str(report.id) else None

        async def _by_date(db: Any, date: Any) -> Any:
            return SimpleNamespace(image_key="k")

        monkeypatch.setattr(sig, "get_by_date", _by_date)
        monkeypatch.setattr(sig, "read_signature_image", lambda key: _png_bytes())

        async def _render(report: Any, sig_row: Any, png: Any) -> bytes:
            return b"%PDF-1.7 commitment"

        monkeypatch.setattr(api_mod, "_render_commitment_pdf", _render)
        from app.core.database import get_db

        client._transport  # noqa: B018 - 保持引用
        # 通过 dependency override 提供带报告的 DB
        app_ref = client._transport.app  # type: ignore[attr-defined]
        app_ref.dependency_overrides[get_db] = _db_factory(_DB())

        async with client as ac:
            resp = await ac.get(f"/api/v1/safety/safety-commitments/{rid}/download")
            assert resp.status_code == 200
            assert resp.content.startswith(b"%PDF")
            assert "attachment" in resp.headers.get("content-disposition", "")


async def _not_async(*a: Any, **kw: Any) -> Any:  # pragma: no cover
    raise AssertionError("should not be called")


def _db_factory(db: Any) -> Any:
    async def _dep() -> Any:
        yield db

    return _dep
