from __future__ import annotations

import asyncio
import concurrent.futures
import json
import sqlite3
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from services import dazah_agent_service as agent_service
from services.memory_service import (
    CompressionResult,
    MemoryCandidate,
    UserMemoryRepository,
    compact_user_memory,
    compact_user_memory_to_target,
    create_memory_store_for_user,
    review_turn,
)


def _repo(tmp_path: Path, **kwargs) -> UserMemoryRepository:
    return UserMemoryRepository(db_path=tmp_path / "memory.sqlite3", **kwargs)


def _candidate(content: str, category: str = "preference", **kwargs) -> MemoryCandidate:
    return MemoryCandidate(category=category, content=content, **kwargs)


def _request(
    *,
    tenant: str = "tenant-a",
    user: str = "user-a",
    platform: str = "feishu",
    chat_type: str = "p2p",
    message: str = "hello",
    memory_mode: str | None = "auto",
):
    payload = agent_service.AgentBackendV2Request(
        protocol_version="2.0",
        run_id=uuid.uuid4(),
        trace_id=uuid.uuid4(),
        session_id=f"feishu:{uuid.uuid4()}",
        subject={"tenant_id": tenant, "user_id": user, "source": platform},
        source={"platform": platform, "chat_type": chat_type},
        message=message,
    )
    if memory_mode is not None:
        payload.memory_policy = agent_service.AgentMemoryPolicyEnvelope(
            effective_mode=memory_mode,
            policy_version=1,
        )
    return payload


def test_missing_trusted_policy_fails_closed_when_enforced(monkeypatch) -> None:
    payload = _request(memory_mode=None)

    monkeypatch.setenv("HERMES_USER_MEMORY_REQUIRE_POLICY", "true")

    assert agent_service._effective_memory_mode(payload) == "disabled"
    assert agent_service._personal_memory_allowed(payload) is False


def test_memory_isolated_by_tenant_and_user_and_shared_by_channel(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.upsert_candidates(
        "tenant-a",
        "same-user",
        [_candidate("偏好表格输出", explicit=True)],
        session_id="web-session",
        run_id="run-1",
    )

    assert "偏好表格输出" in repo.format_for_prompt("tenant-a", "same-user")
    assert "偏好表格输出" not in repo.format_for_prompt("tenant-b", "same-user")
    assert "偏好表格输出" not in repo.format_for_prompt("tenant-a", "other-user")


def test_interaction_pattern_requires_repeated_evidence(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    candidate = _candidate(
        "通常先看结论再看依据",
        category="interaction_pattern",
        confidence=0.95,
    )
    repo.upsert_candidates("t", "u", [candidate], session_id="s1", run_id="r1")
    assert "通常先看结论" not in repo.format_for_prompt("t", "u")

    repo.upsert_candidates("t", "u", [candidate], session_id="s2", run_id="r2")
    assert "通常先看结论" in repo.format_for_prompt("t", "u")


def test_prompt_projection_is_bounded_closed_and_prioritizes_pinned(tmp_path: Path) -> None:
    repo = _repo(tmp_path, injection_bytes=1024)
    for index in range(8):
        repo.upsert_candidates(
            "t", "u", [_candidate(f"普通偏好{index}" + "内容" * 80)],
            session_id="s", run_id=f"r{index}",
        )
    repo.upsert_candidates(
        "t", "u", [_candidate("必须优先注入", pinned=True, explicit=True)],
        session_id="s", run_id="pinned",
    )

    projection = repo.format_for_prompt("t", "u")
    assert len(projection.encode("utf-8")) <= 1024
    assert projection.endswith("</user-memory>")
    assert "必须优先注入" in projection


def test_secret_and_low_confidence_candidates_are_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    stats = repo.upsert_candidates(
        "t",
        "u",
        [
            _candidate("api_key=should-not-be-stored", confidence=1),
            _candidate("也许喜欢非常长的回答", confidence=0.4),
        ],
        session_id="s",
        run_id="r",
    )

    assert stats["rejected"] == 2
    assert repo.list_entries("t", "u") == []


def test_hard_limit_never_evicts_pinned_memory(tmp_path: Path) -> None:
    repo = _repo(tmp_path, limit_bytes=4096, trigger_ratio=0.8, target_ratio=0.6)
    pinned = "固定事实" + "甲" * 600
    repo.upsert_candidates(
        "t",
        "u",
        [_candidate(pinned, pinned=True, explicit=True)],
        session_id="s",
        run_id="r1",
    )
    for index in range(5):
        repo.upsert_candidates(
            "t",
            "u",
            [_candidate(f"普通事实{index}" + "乙" * 350, category="task_history")],
            session_id="s",
            run_id=f"r-{index}",
        )

    assert repo.usage_bytes("t", "u") <= 4096
    assert any(row["content"] == pinned and row["pinned"] for row in repo.list_entries("t", "u"))


def test_compaction_is_transactional_and_preserves_pinned(tmp_path: Path) -> None:
    repo = _repo(tmp_path, limit_bytes=4096, trigger_ratio=0.35, target_ratio=0.2)
    repo.upsert_candidates(
        "t",
        "u",
        [_candidate("必须保留", pinned=True, explicit=True)],
        session_id="s",
        run_id="pinned",
    )
    for index in range(3):
        repo.upsert_candidates(
            "t",
            "u",
            [_candidate(f"任务{index}：" + "过程" * 170, category="task_history")],
            session_id="s",
            run_id=f"r{index}",
        )

    async def llm(messages, _task):
        source = json.loads(messages[-1]["content"])
        return json.dumps(
            {
                "summaries": [
                    {
                        "category": "task_history",
                        "content": "较早任务已完成并形成稳定工作经验。",
                        "source_ids": [item["id"] for item in source],
                    }
                ]
            },
            ensure_ascii=False,
        )

    assert asyncio.run(compact_user_memory(repo, tenant_id="t", user_id="u", llm_call=llm))
    rows = repo.list_entries("t", "u")
    assert any(row["content"] == "必须保留" and row["pinned"] for row in rows)
    assert any(row["entry_kind"] == "summary" for row in rows)


def test_invalid_compression_does_not_delete_sources(tmp_path: Path) -> None:
    repo = _repo(tmp_path, limit_bytes=4096, trigger_ratio=0.2, target_ratio=0.1)
    for index in range(2):
        repo.upsert_candidates(
            "t", "u", [_candidate(f"历史任务{index}" + "甲" * 300, category="task_history")],
            session_id="s", run_id=f"r{index}",
        )
    selected = repo.compression_candidates("t", "u")
    before = {row["id"] for row in repo.list_entries("t", "u")}
    invalid = CompressionResult.model_validate(
        {
            "summaries": [
                {"category": "task_history", "content": "错误摘要", "source_ids": [selected[0]["id"], "missing"]}
            ]
        }
    )

    assert not repo.apply_compression("t", "u", selected, invalid)
    assert {row["id"] for row in repo.list_entries("t", "u")} == before


def test_compaction_repeats_until_target_is_reached(tmp_path: Path) -> None:
    repo = _repo(tmp_path, limit_bytes=4096, trigger_ratio=0.35, target_ratio=0.1)
    for index in range(3):
        repo.upsert_candidates(
            "t",
            "u",
            [_candidate(f"历史任务{index}：" + "过程" * 180, category="task_history")],
            session_id="s",
            run_id=f"r{index}",
        )
    calls = 0

    async def llm(messages, _task):
        nonlocal calls
        calls += 1
        source = json.loads(messages[-1]["content"])
        content = "中间摘要" + "甲" * 180 if calls == 1 else "短摘要"
        return json.dumps(
            {
                "summaries": [{
                    "category": "task_history",
                    "content": content,
                    "source_ids": [item["id"] for item in source],
                }]
            },
            ensure_ascii=False,
        )

    assert asyncio.run(
        compact_user_memory_to_target(repo, tenant_id="t", user_id="u", llm_call=llm)
    )
    assert calls == 2
    assert repo.usage_bytes("t", "u") <= repo.target_bytes


def test_legacy_migration_is_scoped_and_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    base = tmp_path / "home" / "memories"
    user_dir = base / "users" / "user-a"
    user_dir.mkdir(parents=True)
    (user_dir / "USER.md").write_text("旧画像一\n§\n旧画像二", encoding="utf-8")
    (base / "USER.md").write_text("不得导入的全局画像", encoding="utf-8")
    repo = UserMemoryRepository(db_path=tmp_path / "memory.sqlite3")

    assert repo.migrate_legacy_user_file("tenant-a", "user-a") == 2
    assert repo.migrate_legacy_user_file("tenant-a", "user-a") == 0
    rendered = repo.format_for_user("tenant-a", "user-a")
    assert "旧画像一" in rendered
    assert "不得导入的全局画像" not in rendered
    assert repo.list_entries("tenant-a", "other-user") == []


def test_legacy_memory_store_load_is_also_user_scoped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    first = create_memory_store_for_user("user-a", user_char_limit=1000)
    assert first.add("user", "用户 A 的偏好")["success"]

    reloaded = create_memory_store_for_user("user-a", user_char_limit=1000)
    reloaded.load_from_disk()
    other = create_memory_store_for_user("user-b", user_char_limit=1000)
    other.load_from_disk()

    assert "用户 A 的偏好" in (reloaded.format_for_system_prompt("user") or "")
    assert "用户 A 的偏好" not in (other.format_for_system_prompt("user") or "")


def test_v2_memory_commands_fail_closed_outside_backend_governance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr(agent_service, "user_memory_repository", repo)
    private = _request()
    group = _request(chat_type="group")
    repo.upsert_candidates(
        "tenant-a", "user-a", [_candidate("喜欢简洁回答", explicit=True)],
        session_id="s", run_id="r",
    )

    assert "未经过 Dazah 后端治理链路" in agent_service._memory_command_response(private, "/memory")
    assert "群聊不读取" in agent_service._memory_command_response(group, "/memory")
    assert "不会直接读取、修改或清空" in agent_service._memory_command_response(
        private, "/memory clear confirm"
    )
    assert len(repo.list_entries("tenant-a", "user-a")) == 1


def test_natural_language_memory_command_also_fails_closed_in_v2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr(agent_service, "user_memory_repository", repo)
    payload = _request()
    repo.upsert_candidates(
        "tenant-a", "user-a", [_candidate("偏好使用表格", explicit=True)],
        session_id="s", run_id="r",
    )

    view = asyncio.run(
        agent_service._try_basic_command_response(payload.model_copy(update={"message": "你记得什么？"}))
    )
    forgotten = asyncio.run(
        agent_service._try_basic_command_response(payload.model_copy(update={"message": "请忘记表格"}))
    )

    assert view is not None and "未经过 Dazah 后端治理链路" in view.message
    assert forgotten is not None and "未经过 Dazah 后端治理链路" in forgotten.message
    assert len(repo.list_entries("tenant-a", "user-a")) == 1


def test_review_turn_is_idempotent_and_validates_llm_output(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    calls = 0

    async def llm(_messages, _task):
        nonlocal calls
        calls += 1
        return json.dumps(
            {
                "memories": [
                    {
                        "operation": "upsert",
                        "category": "decision_history",
                        "content": "决定每周一检查库存异常",
                        "confidence": 1,
                        "importance": 4,
                        "explicit": True,
                        "pinned": True,
                    }
                ]
            },
            ensure_ascii=False,
        )

    kwargs = dict(
        tenant_id="t", user_id="u", session_id="s", run_id="run",
        user_message="记住：每周一检查库存异常", assistant_message="好的", llm_call=llm,
    )
    asyncio.run(review_turn(repo, **kwargs))
    asyncio.run(review_turn(repo, **kwargs))

    assert calls == 1
    rows = repo.list_entries("t", "u")
    assert len(rows) == 1
    assert rows[0]["pinned"] == 1


def test_clear_confirmation_expires(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path)
    repo.request_clear("t", "u")
    future = time.time() + 301
    monkeypatch.setattr("services.memory_service.time.time", lambda: future)
    assert not repo.confirm_clear("t", "u")


def test_clear_blocks_an_inflight_review_from_repopulating_memory(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    generation = repo.generation("t", "u")
    repo.request_clear("t", "u")
    assert repo.confirm_clear("t", "u")

    stats = repo.upsert_candidates(
        "t",
        "u",
        [_candidate("清空前提取出的旧事实", explicit=True)],
        session_id="old-session",
        run_id="old-run",
        expected_generation=generation,
    )

    assert stats["rejected"] == 1
    assert repo.list_entries("t", "u") == []


def test_actual_memory_llm_adapter_reuses_dazah_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = {}

    async def fake_call(**kwargs):
        recorded.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"memories":[]}'))]
        )

    monkeypatch.setattr("agent.auxiliary_client.async_call_llm", fake_call)
    monkeypatch.setenv("DAZAH_LLM_BASE_URL", "http://app:8000/api/v1/agent/llm")
    monkeypatch.setenv("DAZAH_LLM_MODEL", "configured-model")
    monkeypatch.setenv("AGENT_LLM_PROXY_TOKEN", "test-token")

    result = asyncio.run(agent_service._call_memory_llm([{"role": "user", "content": "x"}], "test"))

    assert result == '{"memories":[]}'
    assert recorded["provider"] == "custom"
    assert recorded["base_url"] == "http://app:8000/api/v1/agent/llm"
    assert recorded["model"] == "configured-model"


@pytest.mark.parametrize(
    "failure",
    [RuntimeError("no config"), TimeoutError("timeout"), RuntimeError("rate limited"), RuntimeError("provider failed")],
)
def test_memory_review_provider_failures_do_not_write(
    tmp_path: Path, failure: Exception
) -> None:
    repo = _repo(tmp_path)

    async def failed_llm(_messages, _task):
        raise failure

    with pytest.raises(type(failure)):
        asyncio.run(
            review_turn(
                repo,
                tenant_id="t",
                user_id="u",
                session_id="s",
                run_id="r",
                user_message="记住我的偏好",
                assistant_message="好的",
                llm_call=failed_llm,
            )
        )
    assert repo.list_entries("t", "u") == []
    assert not repo.has_processed_run("t", "u", "r")


def test_invalid_memory_json_is_rejected_without_writes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    async def invalid_llm(_messages, _task):
        return "not-json"

    with pytest.raises(json.JSONDecodeError):
        asyncio.run(
            review_turn(
                repo,
                tenant_id="t",
                user_id="u",
                session_id="s",
                run_id="r",
                user_message="hello",
                assistant_message="hi",
                llm_call=invalid_llm,
            )
        )
    assert repo.list_entries("t", "u") == []


def test_persistent_queue_is_bounded_and_group_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr(agent_service, "user_memory_repository", repo)
    monkeypatch.setattr("services.memory_service.MAX_JOBS_PER_USER", 1)

    agent_service._schedule_memory_review(_request(chat_type="group"), "group reply", [])
    assert repo.job_counts() == {}
    private = _request(chat_type="p2p", message="我喜欢简洁回答")
    agent_service._schedule_memory_review(private, "private reply", [])
    assert repo.job_counts() == {"pending": 1}
    assert not repo.enqueue_job(
        "tenant-a", "user-a", "another-run", session_id="s",
        user_message="u", assistant_message="a", tool_evidence=[],
    )


def test_run_claim_is_atomic_under_concurrency(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: repo.claim_run("t", "u", "same-run"), range(4)))

    assert results.count(True) == 1
    assert results.count(False) == 3
    repo.complete_run("t", "u", "same-run")
    assert not repo.claim_run("t", "u", "same-run")


def test_expired_job_and_run_leases_can_be_recovered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    base = time.time()
    monkeypatch.setattr("services.memory_service.time.time", lambda: base)
    assert repo.enqueue_job(
        "t", "u", "r", session_id="s", user_message="u",
        assistant_message="a", tool_evidence=[],
    )
    first = repo.claim_job()
    assert first and first["attempts"] == 1
    assert repo.claim_run("t", "u", "r")

    monkeypatch.setattr("services.memory_service.time.time", lambda: base + 301)
    recovered = repo.claim_job()
    assert recovered and recovered["run_id"] == "r" and recovered["attempts"] == 2
    assert repo.claim_run("t", "u", "r")


def test_memory_key_supersedes_stale_fact_and_replace_is_supported(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.upsert_candidates(
        "t", "u", [_candidate("用户职位是质量专员", category="personal_fact", memory_key="job_role")],
        session_id="s1", run_id="r1",
    )
    repo.upsert_candidates(
        "t", "u", [_candidate("用户职位是质量经理", category="personal_fact", memory_key="job_role")],
        session_id="s2", run_id="r2",
    )
    repo.upsert_candidates(
        "t", "u",
        [_candidate(
            "用户职位是质量负责人", category="personal_fact", operation="replace",
            match_text="质量经理", memory_key="job_role",
        )],
        session_id="s3", run_id="r3",
    )

    rows = repo.list_entries("t", "u")
    assert len(rows) == 1
    assert rows[0]["content"] == "用户职位是质量负责人"


def test_tool_result_memory_requires_verified_evidence(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    async def extracted(_messages, _task):
        return json.dumps(
            {
                "memories": [{
                    "category": "task_history",
                    "content": "库存检查已完成",
                    "confidence": 1,
                    "importance": 3,
                    "evidence_source": "tool_result",
                    "tool_evidence_ids": ["call-1"],
                }]
            },
            ensure_ascii=False,
        )

    rejected = asyncio.run(review_turn(
        repo, tenant_id="t", user_id="u", session_id="s", run_id="r1",
        user_message="检查库存", assistant_message="已完成", tool_evidence=[], llm_call=extracted,
    ))
    accepted = asyncio.run(review_turn(
        repo, tenant_id="t", user_id="u", session_id="s", run_id="r2",
        user_message="再检查库存", assistant_message="已完成",
        tool_evidence=[{"evidence_id": "call-1", "verified": True, "operation": "warehouse.check"}],
        llm_call=extracted,
    ))

    assert rejected["rejected"] == 1
    assert accepted["added"] == 1


def test_persistent_worker_processes_queued_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr(agent_service, "user_memory_repository", repo)

    async def no_memory(_messages, _task):
        return '{"memories":[]}'

    monkeypatch.setattr(agent_service, "_call_memory_llm", no_memory)
    assert repo.enqueue_job(
        "t", "u", "r", session_id="s", user_message="hello",
        assistant_message="hi", tool_evidence=[],
    )

    async def scenario():
        worker = asyncio.create_task(agent_service._memory_review_worker(0))
        try:
            for _ in range(100):
                if not repo.job_counts():
                    break
                await asyncio.sleep(0.01)
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    asyncio.run(scenario())
    assert repo.job_counts() == {}
    assert repo.has_processed_run("t", "u", "r")


def test_completed_run_metadata_is_pruned_by_retention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    base = time.time()
    monkeypatch.setattr("services.memory_service.RUN_RETENTION_SECONDS", 10)
    monkeypatch.setattr("services.memory_service.time.time", lambda: base)
    assert repo.claim_run("t", "u", "old")
    repo.complete_run("t", "u", "old")

    monkeypatch.setattr("services.memory_service.time.time", lambda: base + 20)
    assert repo.claim_run("t", "u", "new")
    repo.complete_run("t", "u", "new")

    assert not repo.has_processed_run("t", "u", "old")
    assert repo.has_processed_run("t", "u", "new")


def test_existing_sqlite_schema_is_migrated_in_place(tmp_path: Path) -> None:
    db_path = tmp_path / "old.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE user_memory_entries (
                id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, user_id TEXT NOT NULL,
                category TEXT NOT NULL, content TEXT NOT NULL, content_hash TEXT NOT NULL,
                entry_kind TEXT NOT NULL, confidence REAL NOT NULL, importance INTEGER NOT NULL,
                pinned INTEGER NOT NULL, evidence_count INTEGER NOT NULL, first_seen REAL NOT NULL,
                last_seen REAL NOT NULL, source_session_id TEXT, source_run_id TEXT,
                UNIQUE (tenant_id, user_id, category, content_hash)
            );
            CREATE TABLE user_memory_runs (
                tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, run_id TEXT NOT NULL,
                processed_at REAL NOT NULL, PRIMARY KEY (tenant_id, user_id, run_id)
            );
            INSERT INTO user_memory_runs VALUES ('t', 'u', 'old-complete', 1);
            """
        )
    repo = UserMemoryRepository(db_path=db_path)

    assert repo.has_processed_run("t", "u", "old-complete")
    stats = repo.upsert_candidates(
        "t", "u", [_candidate("新职位", category="personal_fact", memory_key="job_role")],
        session_id="s", run_id="r",
    )

    assert stats["added"] == 1
    assert repo.list_entries("t", "u")[0]["memory_key"] == "job_role"


def test_explicit_remember_reports_confirmed_synchronous_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr(agent_service, "user_memory_repository", repo)

    async def saved(*_args, **_kwargs):
        return {"added": 1, "updated": 0, "forgotten": 0, "rejected": 0}

    monkeypatch.setattr(agent_service, "review_turn", saved)
    payload = _request(message="请记住我偏好简短回答")
    result = asyncio.run(agent_service._finalize_user_memory(payload, "好的。", []))

    assert "已确认保存" in result
    assert repo.job_counts() == {}


def test_explicit_remember_reports_failure_instead_of_false_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr(agent_service, "user_memory_repository", repo)

    async def failed(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(agent_service, "review_turn", failed)
    payload = _request(message="记一下：我偏好表格")
    result = asyncio.run(agent_service._finalize_user_memory(payload, "好的。", []))

    assert "保存失败" in result
    assert "已确认保存" not in result
    assert repo.job_counts() == {}


def test_generic_save_request_does_not_enter_memory_queue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr(agent_service, "user_memory_repository", repo)
    payload = _request(message="请保存这个文件")

    result = asyncio.run(agent_service._finalize_user_memory(payload, "文件已保存。", []))

    assert result == "文件已保存。"
    assert repo.job_counts() == {}


def test_memory_content_and_queue_payload_are_encrypted_at_rest(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    secret_text = "偏好使用蓝色表格"
    repo.upsert_candidates(
        "t",
        "u",
        [_candidate(secret_text, explicit=True)],
        session_id="session-sensitive-ref",
        run_id="r1",
    )
    assert repo.enqueue_job(
        "t",
        "u",
        "r2",
        session_id="session-sensitive-ref",
        user_message="我喜欢蓝色表格",
        assistant_message="以后将使用蓝色表格",
        tool_evidence=[],
    )

    persisted = b"".join(
        path.read_bytes() for path in tmp_path.glob("memory.sqlite3*") if path.is_file()
    )
    assert secret_text.encode("utf-8") not in persisted
    assert "我喜欢蓝色表格".encode("utf-8") not in persisted
    assert "session-sensitive-ref".encode("utf-8") not in persisted


@pytest.mark.parametrize(
    "content",
    [
        "我的身份证号是110101199001011234",
        "我的手机号是13800138000",
        "我的邮箱是person@example.com",
        "记住我的工资是12000元",
        "我有高血压病史",
        "保存我的银行卡号6222021234567890",
        "我受到了纪律处分",
        "我的密码是 correct-horse-battery-staple",
        "我的联系方式是公司座机010-12345678",
        "我的家庭住址是上海市浦东新区世纪大道100号",
        "我确诊糖尿病并正在服用二甲双胍",
        "我的声纹可以用于身份认证",
        "我的年薪是30万元",
    ],
)
def test_high_sensitivity_memory_is_always_rejected(tmp_path: Path, content: str) -> None:
    repo = _repo(tmp_path)
    stats = repo.upsert_candidates(
        "t",
        "u",
        [_candidate(content, explicit=True, pinned=True)],
        session_id="s",
        run_id="r",
    )

    assert stats["rejected"] == 1
    assert repo.list_entries("t", "u") == []


def test_explicit_only_skips_background_extraction(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr(agent_service, "user_memory_repository", repo)
    payload = _request(
        message="我喜欢简洁回答",
        memory_mode="explicit_only",
    )

    agent_service._schedule_memory_review(payload, "好的", [])

    assert repo.job_counts() == {}


def test_paused_memory_rejects_explicit_save(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr(agent_service, "user_memory_repository", repo)
    payload = _request(message="请记住我喜欢表格", memory_mode="disabled")

    result = asyncio.run(agent_service._finalize_user_memory(payload, "好的", []))

    assert "已暂停或被管理员禁用" in result
    assert repo.list_entries("tenant-a", "user-a") == []


def test_clear_marker_removes_restored_older_memory(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr(agent_service, "user_memory_repository", repo)
    repo.upsert_candidates(
        "tenant-a",
        "user-a",
        [_candidate("恢复备份中的旧偏好", explicit=True)],
        session_id="s",
        run_id="r",
    )
    payload = _request(memory_mode="auto")
    payload.memory_policy.last_cleared_at = datetime.now(UTC) + timedelta(seconds=1)

    assert agent_service._personal_memory_context(payload) == ""
    assert repo.list_entries("tenant-a", "user-a") == []


def test_expired_encrypted_job_is_purged(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    base = time.time()
    monkeypatch.setattr("services.memory_service.time.time", lambda: base)
    assert repo.enqueue_job(
        "t",
        "u",
        "r",
        session_id="s",
        user_message="我喜欢简洁回答",
        assistant_message="好的",
        tool_evidence=[],
    )

    monkeypatch.setattr(
        "services.memory_service.time.time",
        lambda: base + 24 * 60 * 60 + 1,
    )
    assert repo.claim_job() is None
    assert repo.job_counts() == {}


def test_memory_keyring_rotates_existing_ciphertext(tmp_path: Path, monkeypatch) -> None:
    first_key = Fernet.generate_key().decode("ascii")
    second_key = Fernet.generate_key().decode("ascii")
    db_path = tmp_path / "memory.sqlite3"
    monkeypatch.setenv("HERMES_USER_MEMORY_KEYS", first_key)
    first = UserMemoryRepository(db_path=db_path)
    first.upsert_candidates(
        "t",
        "u",
        [_candidate("喜欢简洁回答", explicit=True)],
        session_id="s",
        run_id="r",
    )

    monkeypatch.setenv("HERMES_USER_MEMORY_KEYS", f"{second_key},{first_key}")
    rotating = UserMemoryRepository(db_path=db_path)
    assert "喜欢简洁回答" in rotating.format_for_prompt("t", "u")

    monkeypatch.setenv("HERMES_USER_MEMORY_KEYS", second_key)
    reloaded = UserMemoryRepository(db_path=db_path)
    assert "喜欢简洁回答" in reloaded.format_for_prompt("t", "u")
