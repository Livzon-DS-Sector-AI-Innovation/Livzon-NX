"""人员特殊作业证件测试：CRUD/有效期状态/AI 识别五分支/上传建议回填。

AI 分支按 msds_extract 测试模式 mock 业务模块实际导入的 llm_client；
API 测试用子 FastAPI 真实调用路由。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.llm.exceptions import (
    LLMConfigError,
    LLMOutputError,
    LLMProviderError,
    LLMRateLimitError,
)
from app.modules.safety.api.work_certificates import work_certificates_router
from app.modules.safety.models import (
    SpecialWorkCertificate,
    SpecialWorkCertificateFile,
)
from app.modules.safety.schemas.work_certificate import (
    SpecialWorkCertificateCreate,
)
from app.modules.safety.service import work_certificate as cert_service
from app.modules.safety.service import work_certificate_extract as extract_service
from app.platform.identity.models import User

_CERT_MARK = "CERT测试"


def _cert_payload(**overrides) -> dict:
    base = {
        "person_name": f"{_CERT_MARK}王五{uuid4().hex[:6]}",
        "certificate_category": "electrician",
        "certificate_no": f"CERT{uuid4().hex[:10]}",
        "issuing_authority": "应急管理局",
        "issue_date": str(date.today() - timedelta(days=400)),
        "expiry_date": str(date.today() + timedelta(days=400)),
        "qualification_scope": "低压电工作业",
        "remark": f"{_CERT_MARK}{uuid4().hex[:8]}",
    }
    base.update(overrides)
    return base


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid4(), name=f"{_CERT_MARK}用户{uuid4().hex[:8]}",
        role="user", status="active",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def cert_client(
    db_session: AsyncSession,
    test_user: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr(
        "app.modules.safety.service.work_permit_files.storage.is_enabled",
        lambda: False,
    )
    monkeypatch.chdir(tmp_path)
    application = FastAPI()
    application.include_router(work_certificates_router, prefix="/api/v1/safety")
    application.dependency_overrides[get_current_user] = lambda: test_user

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    application.dependency_overrides.pop(get_db, None)


async def _cleanup(db: AsyncSession) -> None:
    cert_ids = list(
        await db.scalars(
            select(SpecialWorkCertificate.id).where(
                SpecialWorkCertificate.remark.like(f"{_CERT_MARK}%")
            )
        )
    )
    if cert_ids:
        await db.execute(
            delete(SpecialWorkCertificateFile).where(
                SpecialWorkCertificateFile.certificate_id.in_(cert_ids)
            )
        )
        await db.execute(
            delete(SpecialWorkCertificate).where(
                SpecialWorkCertificate.id.in_(cert_ids)
            )
        )
    await db.commit()


# ── 服务层：状态计算 / 冲突 / 类别校验 ──


async def test_compute_status(db_session: AsyncSession) -> None:
    assert cert_service.compute_status(date.today() + timedelta(days=400)) == "valid"
    assert cert_service.compute_status(date.today() + timedelta(days=10)) == "expiring"
    assert cert_service.compute_status(date.today() - timedelta(days=1)) == "expired"
    assert cert_service.compute_status(None) == "valid"
    assert cert_service.compute_status(date.today(), "revoked") == "revoked"


async def test_create_conflict_and_category(
    db_session: AsyncSession, test_user: User
) -> None:
    await _cleanup(db_session)
    payload = _cert_payload()
    first = await cert_service.create_certificate(
        db_session,
        SpecialWorkCertificateCreate(**payload),
        test_user,
    )
    assert first.status == "valid"

    from app.core.exceptions import AppException

    with pytest.raises(AppException) as exc_info:
        await cert_service.create_certificate(
            db_session,
            SpecialWorkCertificateCreate(**payload),
            test_user,
        )
    assert exc_info.value.status_code == 409

    with pytest.raises(AppException) as category_error:
        await cert_service.create_certificate(
            db_session,
            SpecialWorkCertificateCreate(
                **_cert_payload(certificate_category="pilot")
            ),
            test_user,
        )
    assert category_error.value.status_code == 422
    await _cleanup(db_session)


# ── AI 识别五分支（mock 业务模块导入的 llm_client） ──


_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def _mock_llm(monkeypatch: pytest.MonkeyPatch, **methods) -> None:
    monkeypatch.setattr(
        extract_service, "llm_client", SimpleNamespace(**methods)
    )


async def test_extract_success_image(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_llm(
        monkeypatch,
        chat_vision_json=AsyncMock(
            return_value={
                "person_name": "王五",
                "certificate_category": "低压电工作业",
                "certificate_no": "T123456",
                "issuing_authority": "北京市应急管理局",
                "issue_date": "2025-01-01",
                "expiry_date": "2027-01-01",
                "qualification_scope": "低压电工作业",
            }
        ),
    )
    suggestion, error = await extract_service.extract_certificate_suggestion(
        file_name="scan.png", content=_PNG_BYTES
    )
    assert error is None
    assert suggestion is not None
    assert suggestion.person_name == "王五"
    assert suggestion.certificate_category == "electrician"
    assert suggestion.certificate_category_label == "电工作业"
    assert suggestion.expiry_date == date(2027, 1, 1)


@pytest.mark.parametrize(
    ("exc", "expected_fragment"),
    [
        (LLMConfigError("no config"), "未配置"),
        (LLMRateLimitError("limited"), "限流"),
        (LLMOutputError("bad output"), "格式无效"),
        (LLMProviderError("down"), "暂不可用"),
    ],
)
async def test_extract_llm_failure_branches(
    monkeypatch: pytest.MonkeyPatch, exc: Exception, expected_fragment: str
) -> None:
    _mock_llm(monkeypatch, chat_vision_json=AsyncMock(side_effect=exc))
    suggestion, error = await extract_service.extract_certificate_suggestion(
        file_name="scan.png", content=_PNG_BYTES
    )
    assert suggestion is None
    assert error is not None
    assert expected_fragment in error


async def test_extract_invalid_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    suggestion, error = await extract_service.extract_certificate_suggestion(
        file_name="photo.bmp", content=b"x"
    )
    assert suggestion is None
    assert error is not None
    assert "格式暂不支持" in error


async def test_extract_no_usable_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_llm(monkeypatch, chat_vision_json=AsyncMock(return_value={}))
    suggestion, error = await extract_service.extract_certificate_suggestion(
        file_name="scan.png", content=_PNG_BYTES
    )
    assert suggestion is None
    assert "识别出有效" in (error or "")


# ── API：创建/列表/上传（含 AI 建议） ──


async def test_certificate_crud_and_expiry_summary(
    cert_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup(db_session)
    created = await cert_client.post(
        "/api/v1/safety/work-certificates", json=_cert_payload()
    )
    assert created.status_code == 200, created.text
    data = created.json()["data"]
    assert data["certificate_category_label"] == "电工作业"
    assert data["status"] == "valid"
    assert data["days_to_expiry"] == 400

    listed = await cert_client.get(
        "/api/v1/safety/work-certificates",
        params={"keyword": _CERT_MARK, "certificate_category": "electrician"},
    )
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] >= 1

    summary = await cert_client.get(
        "/api/v1/safety/work-certificates/expiry-summary"
    )
    assert summary.status_code == 200
    assert summary.json()["data"]["valid"] >= 1

    # 过期证件可按状态筛出
    await cert_client.post(
        "/api/v1/safety/work-certificates",
        json=_cert_payload(expiry_date=str(date.today() - timedelta(days=5))),
    )
    expired = await cert_client.get(
        "/api/v1/safety/work-certificates",
        params={"status": "expired", "keyword": _CERT_MARK},
    )
    assert expired.status_code == 200
    assert expired.json()["data"]["total"] >= 1

    updated = await cert_client.put(
        f"/api/v1/safety/work-certificates/{data['id']}",
        json={"expiry_date": str(date.today() + timedelta(days=10))},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["status"] == "expiring"

    deleted = await cert_client.delete(
        f"/api/v1/safety/work-certificates/{data['id']}"
    )
    assert deleted.status_code == 200
    await _cleanup(db_session)


async def test_certificate_upload_with_ai_suggestion(
    cert_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _cleanup(db_session)
    created = await cert_client.post(
        "/api/v1/safety/work-certificates", json=_cert_payload()
    )
    cert_id = created.json()["data"]["id"]

    async def _fake_extract(*, file_name: str, content: bytes):
        from app.modules.safety.schemas.work_certificate import (
            CertificateExtractionSuggestion,
        )

        return (
            CertificateExtractionSuggestion(
                person_name="王五",
                certificate_category="electrician",
                certificate_category_label="电工作业",
                certificate_no="T999",
            ),
            None,
        )

    monkeypatch.setattr(
        "app.modules.safety.api.work_certificates.extract_certificate_suggestion",
        _fake_extract,
    )
    uploaded = await cert_client.post(
        f"/api/v1/safety/work-certificates/{cert_id}/files",
        files={"file": ("scan.png", _PNG_BYTES, "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    upload_data = uploaded.json()["data"]
    assert upload_data["ai_error"] is None
    assert upload_data["ai_suggestion"]["person_name"] == "王五"
    assert len(upload_data["files"]) == 1

    # 重新识别分支
    re_extract = await cert_client.post(
        f"/api/v1/safety/work-certificates/{cert_id}"
        f"/files/{upload_data['file']['id']}/extract"
    )
    assert re_extract.status_code == 200
    assert re_extract.json()["data"]["ai_suggestion"] is not None

    download = await cert_client.get(
        f"/api/v1/safety/work-certificates/{cert_id}"
        f"/files/{upload_data['file']['id']}/content"
    )
    assert download.status_code == 200
    assert download.content.startswith(b"\x89PNG")
    await _cleanup(db_session)


async def test_certificate_upload_ai_failure_kept_file(
    cert_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _cleanup(db_session)
    created = await cert_client.post(
        "/api/v1/safety/work-certificates", json=_cert_payload()
    )
    cert_id = created.json()["data"]["id"]

    async def _fail_extract(*, file_name: str, content: bytes):
        return None, "平台未配置 AI 模型，无法自动识别"

    monkeypatch.setattr(
        "app.modules.safety.api.work_certificates.extract_certificate_suggestion",
        _fail_extract,
    )
    uploaded = await cert_client.post(
        f"/api/v1/safety/work-certificates/{cert_id}/files",
        files={"file": ("scan.png", _PNG_BYTES, "image/png")},
    )
    assert uploaded.status_code == 200
    data = uploaded.json()["data"]
    assert data["ai_suggestion"] is None
    assert "未配置" in data["ai_error"]
    assert len(data["files"]) == 1  # 识别失败不影响附件保存

    # 不支持的扩展名
    bad = await cert_client.post(
        f"/api/v1/safety/work-certificates/{cert_id}/files",
        files={"file": ("cert.bmp", b"x", "image/bmp")},
    )
    # read_upload_secure 对非法扩展名统一返回 400
    assert bad.status_code == 400
    await _cleanup(db_session)


def test_certificate_categories_cover_cert_ledger() -> None:
    """类别字典值唯一、标签完整，并覆盖持证人员汇总表全部子表类别。"""
    from app.modules.safety.service.work_permit_templates import (
        CERTIFICATE_CATEGORIES,
        CERTIFICATE_CATEGORY_LABELS,
    )

    values = [item["value"] for item in CERTIFICATE_CATEGORIES]
    assert len(values) == len(set(values))
    assert set(CERTIFICATE_CATEGORY_LABELS) == set(values)
    # 2026 持证人员汇总表 13 个子表对应的类别（含本次补充）
    for required in (
        "electrician",
        "welding_cutting",
        "high_altitude_maintenance",
        "confined_space",
        "confined_space_guardian",
        "instrument",
        "boiler_operator",
        "water_quality_analyst",
        "forklift",
        "pressure_vessel",
        "special_equipment_management",
        "crane_operator",
        "hazmat_safety_manager",
    ):
        assert required in values
        assert CERTIFICATE_CATEGORY_LABELS[required]
