"""安全承诺日报与信息卡 API 测试。

覆盖：惰性初始化（继承上一日）、编辑企业状态、发布承诺公告、
按日期只读查询、信息卡 CRUD。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import AppException
from app.modules.safety.api.safety_commitments import safety_commitments_router
from app.modules.safety.models import (
    SafetyCommitmentCard,
    SafetyCommitmentReport,
)
from app.modules.safety.service.safety_commitment import (
    get_or_create_report,
    shanghai_today,
)
from app.platform.identity.models import User

_MARK = "SC测试"


async def _cleanup(db: AsyncSession) -> None:
    # 日报无业务标记字段，按测试日期窗口清理（专用测试库，窗口外数据不受影响）
    window_start = shanghai_today() - timedelta(days=60)
    window_end = shanghai_today() + timedelta(days=60)
    await db.execute(
        delete(SafetyCommitmentReport).where(
            SafetyCommitmentReport.report_date >= window_start,
            SafetyCommitmentReport.report_date <= window_end,
        )
    )
    # 信息卡表仅本功能使用；整表清理让「首次播种」用例可重复（含软删行）
    await db.execute(delete(SafetyCommitmentCard))
    await db.commit()


@pytest.fixture(autouse=True)
def _mock_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """惰性建日报会自动 AI 研判：mock 掉 llm_client，不连真实模型。"""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.core.llm.exceptions import LLMConfigError
    from app.modules.safety.service import safety_commitment_risk

    fake = SimpleNamespace(
        chat_json=AsyncMock(side_effect=LLMConfigError("测试环境未配置模型"))
    )
    monkeypatch.setattr(safety_commitment_risk, "llm_client", fake)


@pytest.fixture
async def _user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid4(),
        name=f"{_MARK}用户{uuid4().hex[:6]}",
        role="user",
        status="active",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def commitment_app(
    db_session: AsyncSession, _user: User
) -> FastAPI:
    application = FastAPI()

    @application.exception_handler(AppException)
    async def _app_exception_handler(request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.status_code, "message": exc.message, "data": None},
        )

    application.include_router(safety_commitments_router, prefix="/api/v1/safety")
    application.dependency_overrides[get_current_user] = lambda: _user

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_db] = _override_get_db
    return application


@pytest.fixture
async def api_client(commitment_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=commitment_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
async def _clean(db_session: AsyncSession) -> AsyncIterator[None]:
    await _cleanup(db_session)
    yield
    await _cleanup(db_session)


async def test_today_lazy_creates_and_inherits(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    """首次访问惰性建当日日报；再建一天后新日报继承上一日企业状态。"""
    # 造一条历史日报（昨天）
    yesterday = shanghai_today() - timedelta(days=2)
    status = {"workshop_total": 6, "workshop_running": 5, "person_main": "秦刚"}
    db_session.add(
        SafetyCommitmentReport(
            id=uuid4(),
            report_date=yesterday,
            enterprise_status=status,
            commitment_text="昨日承诺正文",
        )
    )
    await db_session.commit()

    resp = await api_client.get("/api/v1/safety/safety-commitments/today")
    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]
    assert data["created_today"] is True
    report = data["report"]
    assert report["report_date"] == shanghai_today().isoformat()
    assert report["status"] == "draft"
    # 继承上一日企业状态与承诺正文
    assert report["enterprise_status"]["workshop_total"] == 6
    assert report["enterprise_status"]["person_main"] == "秦刚"
    assert report["commitment_text"] == "昨日承诺正文"

    # 再次访问不重复创建
    resp2 = await api_client.get("/api/v1/safety/safety-commitments/today")
    assert resp2.status_code == 200
    assert resp2.json()["data"]["created_today"] is False
    assert resp2.json()["data"]["report"]["id"] == report["id"]


async def test_update_report_and_publish(
    api_client: AsyncClient,
) -> None:
    """编辑企业状态后发布承诺公告；缺承诺人时报 422 校验失败。"""
    resp = await api_client.get("/api/v1/safety/safety-commitments/today")
    report_id = resp.json()["data"]["report"]["id"]

    update = await api_client.put(
        f"/api/v1/safety/safety-commitments/{report_id}",
        json={
            "enterprise_status": {"workshop_total": 8, "hazard_count": 1},
            "commitment_text": "今日郑重承诺：装置安全运行，风险有效管控。",
        },
    )
    assert update.status_code == 200
    updated = update.json()["data"]
    assert updated["enterprise_status"]["workshop_total"] == 8
    assert updated["fill_source"] == "web"

    # 缺少承诺正文 → 发布被拒（编辑后已有正文，先造一条空正文场景）
    empty_update = await api_client.put(
        f"/api/v1/safety/safety-commitments/{report_id}",
        json={"commitment_text": "  "},
    )
    assert empty_update.status_code == 200
    publish_missing_text = await api_client.post(
        f"/api/v1/safety/safety-commitments/{report_id}/publish",
        json={"publisher_name": "秦刚"},
    )
    assert publish_missing_text.status_code == 400

    await api_client.put(
        f"/api/v1/safety/safety-commitments/{report_id}",
        json={"commitment_text": "今日郑重承诺。"},
    )
    publish = await api_client.post(
        f"/api/v1/safety/safety-commitments/{report_id}/publish",
        json={"publisher_name": "秦刚"},
    )
    assert publish.status_code == 200
    published = publish.json()["data"]
    assert published["status"] == "published"
    assert published["publisher_name"] == "秦刚"
    assert published["published_at"] is not None


async def test_by_date_readonly(
    api_client: AsyncClient,
) -> None:
    """按日期只读查询；无记录时报 404 且不落新记录。"""
    today_resp = await api_client.get("/api/v1/safety/safety-commitments/today")
    today_report = today_resp.json()["data"]["report"]

    found = await api_client.get(
        f"/api/v1/safety/safety-commitments/by-date/{today_report['report_date']}"
    )
    assert found.status_code == 200
    assert found.json()["data"]["id"] == today_report["id"]

    missing = await api_client.get(
        "/api/v1/safety/safety-commitments/by-date/2030-01-01"
    )
    assert missing.status_code == 404


async def test_card_crud(
    api_client: AsyncClient,
) -> None:
    """信息卡新增/编辑/列表/软删除。"""
    created = await api_client.post(
        "/api/v1/safety/safety-commitment-cards",
        json={
            "card_type": "major_hazard",
            "title": f"{_MARK}储罐区管控",
            "content": "液位、温度、压力不超限",
        },
    )
    assert created.status_code == 200
    card = created.json()["data"]
    assert card["card_type"] == "major_hazard"
    assert UUID(card["id"])

    updated = await api_client.put(
        f"/api/v1/safety/safety-commitment-cards/{card['id']}",
        json={"content": "浮盘不得落底；人员在岗"},
    )
    assert updated.status_code == 200, updated.text[:300]
    assert updated.json()["data"]["content"] == "浮盘不得落底；人员在岗"

    listed = await api_client.get("/api/v1/safety/safety-commitment-cards")
    assert listed.status_code == 200
    ids = {item["id"] for item in listed.json()["data"]["cards"]}
    assert card["id"] in ids

    deleted = await api_client.delete(
        f"/api/v1/safety/safety-commitment-cards/{card['id']}"
    )
    assert deleted.status_code == 200
    listed2 = await api_client.get("/api/v1/safety/safety-commitment-cards")
    ids2 = {item["id"] for item in listed2.json()["data"]["cards"]}
    assert card["id"] not in ids2

    invalid_type = await api_client.post(
        "/api/v1/safety/safety-commitment-cards",
        json={"card_type": "bad_type", "title": "x", "content": "x"},
    )
    assert invalid_type.status_code == 422


async def test_regenerate_risk_assessment_endpoint(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """接口层研判：失败返回原因；成功返回刷新后的日报。

    回归守护：updated_at 是服务端 onupdate 表达式，UPDATE 后属性过期，
    序列化前不 refresh 会在异步会话里懒加载触发 MissingGreenlet（500）。
    """
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.modules.safety.service import safety_commitment_risk

    resp = await api_client.get("/api/v1/safety/safety-commitments/today")
    report_id = resp.json()["data"]["report"]["id"]

    # 失败分支：autouse mock 抛 LLMConfigError
    failed = await api_client.post(
        f"/api/v1/safety/safety-commitments/{report_id}/risk-assessment"
    )
    assert failed.status_code == 200
    assert failed.json()["data"]["success"] is False
    assert "未配置" in failed.json()["data"]["message"]

    # 成功分支
    fake = SimpleNamespace(
        chat_json=AsyncMock(
            return_value={
                "risk_level": "低",
                "summary": "当日无特殊作业，风险可控。",
                "key_risks": [],
                "suggestions": ["保持日常巡检"],
            }
        )
    )
    monkeypatch.setattr(safety_commitment_risk, "llm_client", fake)
    ok = await api_client.post(
        f"/api/v1/safety/safety-commitments/{report_id}/risk-assessment"
    )
    assert ok.status_code == 200, ok.text
    data = ok.json()["data"]
    assert data["success"] is True
    assert data["report"]["risk_assessment"]["risk_level"] == "低"
    assert data["report"]["updated_at"] is not None


async def test_lazy_create_seeds_default_cards_once(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    """首次建日报播种 74 号文默认信息卡；用户删除后次日不再重新播种。"""
    await api_client.get("/api/v1/safety/safety-commitments/today")
    listed = await api_client.get("/api/v1/safety/safety-commitment-cards")
    cards = listed.json()["data"]["cards"]
    assert {card["card_type"] for card in cards} == {"commitment", "major_hazard"}

    for card in cards:
        resp = await api_client.delete(
            f"/api/v1/safety/safety-commitment-cards/{card['id']}"
        )
        assert resp.status_code == 200

    # 模拟次日：删掉当日日报后再次惰性初始化
    await db_session.execute(
        delete(SafetyCommitmentReport).where(
            SafetyCommitmentReport.report_date == shanghai_today()
        )
    )
    await db_session.commit()
    again = await api_client.get("/api/v1/safety/safety-commitments/today")
    assert again.json()["data"]["created_today"] is True
    relisted = await api_client.get("/api/v1/safety/safety-commitment-cards")
    assert relisted.json()["data"]["cards"] == []


async def test_get_or_create_accepts_iso_string_date(
    db_session: AsyncSession,
) -> None:
    """飞书卡片与调度器传 'YYYY-MM-DD' 字符串；asyncpg 的 DATE 参数只收 date。"""
    day = shanghai_today().isoformat()
    report, created = await get_or_create_report(db_session, day)
    assert created is True
    assert report.report_date == shanghai_today()

    same, created_again = await get_or_create_report(db_session, day)
    assert created_again is False
    assert same.id == report.id

    with pytest.raises(AppException):
        await get_or_create_report(db_session, "not-a-date")
