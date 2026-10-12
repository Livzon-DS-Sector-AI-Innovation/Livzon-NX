from services.memory_service import MemoryCandidate, UserMemoryRepository


def test_task_memory_is_not_reused_as_business_authority(tmp_path):
    repo = UserMemoryRepository(db_path=tmp_path / "memory.sqlite3")
    repo.upsert_candidates(
        "local", "user", [
            MemoryCandidate(category="preference", content="偏好中文表格", confidence=0.99, pinned=True, explicit=True),
            MemoryCandidate(category="task_history", content="旧授权供应商结果", confidence=0.99, pinned=True, explicit=True),
            MemoryCandidate(category="professional_knowledge", content="旧业务数据库知识", confidence=0.99, pinned=True, explicit=True),
        ], session_id="session", run_id="run",
    )
    projected = repo.format_for_prompt("local", "user", personal_only=True)
    assert "偏好中文表格" in projected
    assert "旧授权供应商结果" not in projected
    assert "旧业务数据库知识" not in projected
    assert "旧授权供应商结果" in repo.format_for_user("local", "user")
    assert repo.format_for_prompt("other-tenant", "user", personal_only=True) == ""
    assert repo.format_for_prompt("local", "other-user", personal_only=True) == ""
    repo.clear_scope("local", "user")
    assert repo.format_for_prompt("local", "user", personal_only=True) == ""
