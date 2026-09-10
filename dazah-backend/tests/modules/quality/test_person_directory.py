"""共享人员目录（person_directory）单元测试。

测试库的 hr_feishu_members 为共享数据，播种行统一带运行级前缀，
断言时按前缀过滤，不假设表为空。
"""

from datetime import UTC, datetime

import pytest

from app.modules.hr.models import HrFeishuMember
from app.modules.quality.service import person_directory

# 每次运行独立前缀，避免与测试库历史数据撞唯一约束、互不干扰
run_id = datetime.now(UTC).strftime("%H%M%S%f")
suffix = f"单测人员目录{run_id}"


def _member(
    open_id: str,
    name: str,
    department: str,
    *,
    status: str = "1",
    enterprise_email: str | None = None,
    job_title: str | None = None,
) -> HrFeishuMember:
    return HrFeishuMember(
        open_id=f"ou_{run_id}_{open_id}",
        name=f"{name}{suffix}",
        department=department,
        status=status,
        enterprise_email=enterprise_email,
        job_title=job_title,
        synced_at=datetime.now(UTC),
    )


def _run_options(options: list[dict]) -> list[dict]:
    return [item for item in options if str(item["name"]).endswith(suffix)]


@pytest.mark.anyio
async def test_get_person_options_dedupes_by_open_id_and_filters_resigned(
    db_session,
) -> None:
    db_session.add_all(
        [
            _member("1", "张三", "质量部"),
            _member("1", "张三", "生产部"),
            _member("2", "李四", "生产部", status="2"),
        ]
    )
    await db_session.commit()

    options = _run_options(await person_directory.get_person_options(db_session))
    assert [item["open_id"] for item in options] == [f"ou_{run_id}_1"]
    assert options[0]["department"] in ("质量部", "生产部")


@pytest.mark.anyio
async def test_get_person_options_keyword_filter(db_session) -> None:
    """keyword 过滤后为空但目录非空时，正常返回空列表而不报错。"""
    db_session.add(_member("kw", "关键词人物", "质量部"))
    await db_session.commit()

    matched = _run_options(
        await person_directory.get_person_options(
            db_session,
            keyword=f"关键词人物{suffix}",
        )
    )
    assert len(matched) == 1
    miss = _run_options(
        await person_directory.get_person_options(
            db_session,
            keyword="绝无仅有的关键词",
        )
    )
    assert miss == []


@pytest.mark.anyio
async def test_resolve_person_by_open_id_and_name(db_session) -> None:
    db_session.add_all(
        [
            _member("qa", "王QA", "研发部", enterprise_email="qa@example.com"),
            _member("dupe1", "同名", "质量部"),
            _member("dupe2", "同名", "生产部"),
        ]
    )
    await db_session.commit()

    qa_open_id = f"ou_{run_id}_qa"
    person = await person_directory.resolve_person_by_open_id(db_session, qa_open_id)
    assert person is not None
    assert str(person["name"]).endswith(suffix)
    assert person["enterprise_email"] == "qa@example.com"

    assert (
        await person_directory.resolve_person_by_open_id(db_session, "ou_none")
        is None
    )

    unique = await person_directory.resolve_person_by_name(
        db_session, f"王QA{suffix}"
    )
    assert unique is not None and unique["open_id"] == qa_open_id

    # 同名跨部门且未限定部门 → 无法消歧返回 None；限定部门后可解析
    assert (
        await person_directory.resolve_person_by_name(db_session, f"同名{suffix}")
        is None
    )
    scoped = await person_directory.resolve_person_by_name(
        db_session, f"同名{suffix}", department="生产部"
    )
    assert scoped is not None and scoped["department"] == "生产部"


@pytest.mark.anyio
async def test_resolve_person_write_id_union_translation(db_session, monkeypatch):
    db_session.add(_member("new", "赵新", "质量部"))
    await db_session.commit()

    async def _fake_translate(_db, open_ids):
        return {oid: f"on_{oid[3:]}" for oid in open_ids}

    monkeypatch.setattr(
        "app.modules.quality.service.hr_identity."
        "translate_hr_open_ids_to_union_ids",
        _fake_translate,
    )

    oid = f"ou_{run_id}_new"
    # on_ 前缀：直接透传
    assert (
        await person_directory.resolve_person_write_id(db_session, "on_direct")
        == "on_direct"
    )
    # ou_ 前缀：换发 union_id
    assert (
        await person_directory.resolve_person_write_id(db_session, oid)
        == f"on_{oid[3:]}"
    )
    # 姓名：匹配人员后换发
    resolved_by_name = await person_directory.resolve_person_write_id(
        db_session, f"赵新{suffix}"
    )
    assert resolved_by_name == f"on_{oid[3:]}"
    # 未知姓名：None
    assert (
        await person_directory.resolve_person_write_id(db_session, "绝无仅有的姓名")
        is None
    )


@pytest.mark.anyio
async def test_resolve_person_write_id_falls_back_to_raw_id(db_session, monkeypatch):
    """换发失败（历史旧 id）时原样返回，不阻断写入。"""

    async def _empty_translate(_db, open_ids):
        return {}

    monkeypatch.setattr(
        "app.modules.quality.service.hr_identity.translate_hr_open_ids_to_union_ids",
        _empty_translate,
    )
    legacy = f"ou_{run_id}_legacy"
    assert (
        await person_directory.resolve_person_write_id(db_session, legacy) == legacy
    )


@pytest.mark.anyio
async def test_get_qa_reminder_recipients_filters_by_keyword(db_session) -> None:
    db_session.add_all(
        [
            _member("qa1", "武一", "质量保证部", enterprise_email="wu1@example.com"),
            _member("qa2", "武二", "QA部", enterprise_email="wu2@example.com"),
            _member("prod", "生一", "生产部", enterprise_email="p@example.com"),
        ]
    )
    await db_session.commit()

    recipients = await person_directory.get_qa_reminder_recipients(db_session)
    recipients = [item for item in recipients if str(item["name"]).endswith(suffix)]
    assert sorted(item["open_id"] for item in recipients) == [
        f"ou_{run_id}_qa1",
        f"ou_{run_id}_qa2",
    ]
    by_id = {item["open_id"]: item for item in recipients}
    assert by_id[f"ou_{run_id}_qa1"]["enterprise_email"] == "wu1@example.com"
