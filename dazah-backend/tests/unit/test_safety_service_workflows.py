import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.safety.service import safety as safety_module
from app.modules.safety.service.safety import SafetyService


class Payload:
    def __init__(self, **values):
        self.values = values

    def model_dump(self, **kwargs):
        if kwargs.get("exclude_none"):
            return {
                key: value
                for key, value in self.values.items()
                if value is not None
            }
        return dict(self.values)


def make_service() -> tuple[SafetyService, SimpleNamespace]:
    service = SafetyService(SimpleNamespace())
    repo = SimpleNamespace()
    service.repo = repo
    service._audit = AsyncMock()
    return service, repo


@pytest.mark.anyio
async def test_check_crud_and_state_machine() -> None:
    service, repo = make_service()
    check_id = uuid4()
    item = SimpleNamespace(id=check_id, status="draft")
    repo.get_checks = AsyncMock(return_value=([item], 1))
    repo.get_check_by_id = AsyncMock(return_value=item)
    repo.create_check = AsyncMock(return_value=item)
    repo.update_check = AsyncMock(return_value=item)
    repo.delete_check = AsyncMock(return_value=True)

    assert await service.get_checks(2, 5, "draft", "daily", "质量部") == ([item], 1)
    assert await service.get_check(check_id) is item
    assert await service.create_check(Payload(title="日常检查")) is item
    assert (
        await service.update_check(check_id, Payload(title="更新", ignored=None))
        is item
    )
    assert await service.submit_check(check_id) is item

    item.status = "submitted"
    assert await service.review_check(check_id, "passed") is item
    item.status = "reviewed"
    assert await service.close_check(check_id) is item
    assert await service.confirm_check(check_id, "inspector") is item
    assert await service.confirm_check(check_id, "safety_officer") is item
    assert await service.confirm_check(check_id, "unknown") is None
    assert await service.delete_check(check_id) is True

    item.status = "closed"
    assert await service.submit_check(check_id) is None
    assert await service.review_check(check_id, "passed") is None
    assert await service.close_check(check_id) is None
    repo.get_check_by_id.return_value = None
    assert await service.confirm_check(check_id, "inspector") is None

    assert repo.create_check.await_args.args[0] == {"title": "日常检查"}
    assert repo.update_check.await_args_list[0].args[1] == {"title": "更新"}
    assert service._audit.await_count == 5


@pytest.mark.anyio
async def test_hazard_crud_photos_and_rectification_workflow(monkeypatch) -> None:
    service, repo = make_service()
    hazard_id = uuid4()
    hazard = SimpleNamespace(
        id=hazard_id,
        hazard_no="HZ-TEST-001",
        hazard_type="unsafe_condition",
        hazard_level="general",
        hazard_category=None,
        ai_error_message=None,
        defect_photos='["old/photo.jpg"]',
        rectification_photos="broken\\json",
        rectification_status="pending",
        actual_completion_date=None,
        verify_level_1_status="pending",
        verify_level_2_status="pending",
        status="open",
    )
    repo.get_hazards = AsyncMock(return_value=([hazard], 1))
    repo.get_hazard_stats = AsyncMock(return_value={"total": 1})
    repo.get_hazard_by_id = AsyncMock(return_value=hazard)
    repo.count_hazards_today = AsyncMock(return_value=4)
    repo.create_hazard = AsyncMock(return_value=hazard)
    repo.update_hazard = AsyncMock(return_value=hazard)
    repo.delete_hazard = AsyncMock(return_value=True)
    monkeypatch.setattr(
        safety_module.asyncio,
        "create_task",
        lambda coroutine: coroutine.close(),
    )

    assert await service.get_hazards(keyword="泄漏") == ([hazard], 1)
    assert await service.get_hazard_stats() == {"total": 1}
    assert await service.get_hazard(hazard_id) is hazard

    created = await service.create_hazard(
        Payload(hazard_no=None, description=None),
        auto_run_ai=False,
    )
    assert created is hazard
    create_data = repo.create_hazard.await_args.args[0]
    assert create_data["hazard_no"].endswith("-005")
    assert create_data["hazard_type"] == "unsafe_condition"
    assert create_data["overall_status"] == "open"

    assert await service.update_hazard(
        hazard_id,
        Payload(description="阀门泄漏", ignored=None),
    ) is hazard
    assert await service.upload_hazard_photo(
        hazard_id,
        "photo.jpg",
        r"uploads\photo.jpg",
    ) is hazard
    saved_photos = json.loads(repo.update_hazard.await_args.args[1]["defect_photos"])
    assert saved_photos == ["old/photo.jpg", "uploads/photo.jpg"]

    assert await service.upload_rectification_photo(
        hazard_id,
        r"uploads\fixed.jpg",
    ) is hazard
    fixed_photos = json.loads(
        repo.update_hazard.await_args.args[1]["rectification_photos"]
    )
    assert fixed_photos == ["uploads/fixed.jpg"]

    assert await service.start_rectification(hazard_id) is hazard
    assert await service.reply_rectification(
        hazard_id,
        "已整改",
        '["fixed.jpg"]',
        corrective_preventive_measures="更换阀门",
    ) is hazard
    reply = repo.update_hazard.await_args.args[1]
    assert reply["rectification_status"] == "replied"
    assert reply["rectification_reply"] == "更换阀门"
    assert isinstance(reply["actual_completion_date"], datetime)

    hazard.rectification_status = "replied"
    assert await service.verify_level(
        hazard_id,
        1,
        "approved",
        "通过",
        uuid4(),
        "负责人",
    ) is hazard
    level_one = repo.update_hazard.await_args.args[1]
    assert level_one["verify_level_2_status"] == "approved"
    assert level_one["rectification_status"] == "level2_approved"

    hazard.verify_level_1_status = "approved"
    assert await service.verify_level(
        hazard_id,
        3,
        "approved",
        None,
        uuid4(),
        "发现人",
    ) is hazard
    assert repo.update_hazard.await_args.args[1]["status"] == "closed"

    assert await service.verify_level(
        hazard_id,
        1,
        "rejected",
        "重做",
        uuid4(),
        "负责人",
    ) is hazard
    assert repo.update_hazard.await_args.args[1]["rectification_status"] == "rejected"

    hazard.rectification_status = "rejected"
    assert await service.rework_rectification(
        hazard_id,
        "重新完成",
        None,
        uuid4(),
        "整改人",
    ) is hazard
    assert repo.update_hazard.await_args.args[1]["verify_level_3_status"] == "pending"
    assert await service.delete_hazard(hazard_id) is True

    repo.get_hazard_by_id.return_value = None
    assert await service.upload_hazard_photo(hazard_id, "x", "x") is None
    assert await service.upload_rectification_photo(hazard_id, "x") is None
    assert await service.start_rectification(hazard_id) is None
    assert await service.reply_rectification(hazard_id, "x", None) is None
    assert await service.verify_level(
        hazard_id, 1, "approved", None, uuid4(), "x"
    ) is None
    assert await service.rework_rectification(
        hazard_id, "x", None, uuid4(), "x"
    ) is None


@pytest.mark.anyio
async def test_accident_contractor_and_work_record_state_machines() -> None:
    service, repo = make_service()
    item_id = uuid4()
    item = SimpleNamespace(id=item_id, status="reported")
    for name, return_value in {
        "get_accidents": ([item], 1),
        "get_accident_by_id": item,
        "create_accident": item,
        "update_accident": item,
        "delete_accident": True,
        "get_contractors": ([item], 1),
        "get_contractor_by_id": item,
        "create_contractor": item,
        "update_contractor": item,
        "delete_contractor": True,
        "get_work_records_by_contractor": [item],
        "create_work_record": item,
        "update_work_record": item,
        "get_work_record_by_id": item,
        "delete_work_record": True,
    }.items():
        setattr(repo, name, AsyncMock(return_value=return_value))

    assert await service.get_accidents(keyword="泄漏") == ([item], 1)
    assert await service.get_accident(item_id) is item
    assert await service.create_accident(Payload(title="事故")) is item
    assert (
        await service.update_accident(item_id, Payload(title="更新", empty=None))
        is item
    )
    assert await service.investigate_accident(item_id, uuid4(), "调查员") is item

    item.status = "investigating"
    assert await service.resolve_accident(
        item_id,
        "直接原因",
        "根本原因",
        "处置措施",
        investigation_team=[{"name": "甲"}],
    ) is item
    item.status = "investigated"
    assert await service.start_capa(item_id, datetime.now(), "责任人") is item
    assert await service.close_accident(item_id) is item
    item.status = "capa_in_progress"
    assert await service.verify_capa(item_id, uuid4(), "验证人") is item
    assert await service.delete_accident(item_id) is True

    assert await service.get_contractors(keyword="承包商") == ([item], 1)
    assert await service.get_contractor(item_id) is item
    assert await service.create_contractor(Payload(name="承包商")) is item
    assert await service.update_contractor(item_id, Payload(name="新名称")) is item
    assert await service.blacklist_contractor(item_id) is item
    assert await service.activate_contractor(item_id) is item
    assert await service.update_contractor_training(item_id, "passed") is item
    assert await service.delete_contractor(item_id) is True

    assert await service.get_work_records(item_id) == [item]
    assert await service.create_work_record(item_id, Payload(project="检修")) is item
    assert (
        repo.create_work_record.await_args.args[0]["contractor_id"] == str(item_id)
    )
    assert await service.update_work_record(item_id, Payload(project="大修")) is item
    assert await service.evaluate_work_record(item_id, 95, "良好", "主管") is item
    evaluation = repo.update_work_record.await_args.args[1]["evaluation"]
    assert evaluation["score"] == 95
    assert evaluation["comments"] == "良好"
    assert await service.delete_work_record(item_id) is True

    repo.get_accident_by_id.return_value = None
    assert await service.investigate_accident(item_id, uuid4(), "调查员") is None
    assert await service.resolve_accident(item_id, "a", "b", "c") is None
    assert await service.start_capa(item_id, datetime.now(), "责任人") is None
    assert await service.verify_capa(item_id, uuid4(), "验证人") is None
    assert await service.close_accident(item_id) is None
    repo.get_contractor_by_id.return_value = None
    assert await service.blacklist_contractor(item_id) is None
    assert await service.activate_contractor(item_id) is None
    assert await service.update_contractor_training(item_id, "passed") is None
    repo.get_work_record_by_id.return_value = None
    assert await service.evaluate_work_record(item_id, 50) is None


@pytest.mark.anyio
async def test_training_and_certificate_workflows() -> None:
    service, repo = make_service()
    training_id = uuid4()
    item = SimpleNamespace(id=training_id, status="draft")
    for name, return_value in {
        "get_trainings": ([item], 1),
        "get_training_by_id": item,
        "create_training": item,
        "update_training": item,
        "delete_training": True,
        "get_records_by_training": [item],
        "create_training_record": item,
        "update_training_record": item,
        "delete_training_record": True,
        "get_training_certificates": ([item], 1),
        "get_expiring_certificates": [item],
    }.items():
        setattr(repo, name, AsyncMock(return_value=return_value))

    assert await service.get_trainings(department="安全部") == ([item], 1)
    assert await service.get_training(training_id) is item
    assert await service.create_training(Payload(title="消防培训")) is item
    assert await service.update_training(
        training_id, Payload(title="更新培训", empty=None)
    ) is item
    assert await service.start_training(training_id) is item
    item.status = "in_progress"
    assert await service.complete_training(training_id) is item
    item.status = "completed"
    assert await service.archive_training(training_id) is item
    assert await service.delete_training(training_id) is True

    assert await service.get_training_records(training_id) == [item]
    assert await service.create_training_record(Payload(employee="甲")) is item
    assert await service.update_training_record(
        training_id, Payload(score=90, empty=None)
    ) is item
    records = await service.batch_create_records(
        training_id,
        [Payload(employee="甲"), Payload(employee="乙")],
    )
    assert records == [item, item]
    assert repo.create_training_record.await_args.args[0]["training_id"] == training_id
    assert await service.delete_training_record(training_id) is True
    assert await service.get_training_certificates(keyword="甲") == ([item], 1)
    assert await service.get_expiring_certificates() == [item]

    item.status = "archived"
    assert await service.start_training(training_id) is None
    assert await service.complete_training(training_id) is None
    assert await service.archive_training(training_id) is None


@pytest.mark.anyio
async def test_hazard_identification_workflow_mapping_and_risk_calculation(
    monkeypatch,
) -> None:
    from app.modules.safety import schemas
    from app.modules.safety.schemas.hazard_identifications import get_risk_level

    monkeypatch.setattr(schemas, "get_risk_level", get_risk_level, raising=False)
    service, repo = make_service()
    item_id = uuid4()
    item = SimpleNamespace(
        id=item_id,
        overall_status="draft",
        ai_node_progress="pending_script1",
        script1_review_status="pending",
        script2_review_status="approved",
        script3_review_status="approved",
        script4_review_status="approved",
        script5_review_status="approved",
        script6_review_status="approved",
    )
    repo.get_hazard_identifications = AsyncMock(return_value=([item], 1))
    repo.get_hazard_identification_stats = AsyncMock(return_value={"draft": 1})
    repo.get_hazard_identification_ledger_stats = AsyncMock(return_value={"total": 1})
    repo.get_hazard_identification_by_id = AsyncMock(return_value=item)
    repo.create_hazard_identification = AsyncMock(return_value=item)
    repo.update_hazard_identification = AsyncMock(return_value=item)
    repo.delete_hazard_identification = AsyncMock(return_value=True)

    assert await service.get_hazard_identifications(keyword="反应") == ([item], 1)
    assert await service.get_hazard_identification_stats() == {"draft": 1}
    assert await service.get_hazard_identification_ledger_stats(
        department="生产部"
    ) == {"total": 1}
    assert await service.get_hazard_identification(item_id) is item
    assert await service.create_hazard_identification(
        Payload(department="生产部")
    ) is item
    create_values = repo.create_hazard_identification.await_args.args[0]
    assert create_values["overall_status"] == "draft"
    assert await service.update_hazard_identification(
        item_id, Payload(position="操作工", empty=None)
    ) is item
    assert await service.delete_hazard_identification(item_id) is True
    assert await service.submit_hazard_identification(item_id) is item

    output_by_script = {
        1: {
            "specific_activity": "投料",
            "equipment_facilities": "反应釜",
            "raw_auxiliary_materials": "溶剂",
        },
        2: {
            "hazard_type": "火灾",
            "possible_accident": "燃烧",
            "unsafe_behavior": "未接地",
        },
        3: {"l_inherent": "3", "e_inherent": 4, "c_inherent": 5},
        4: {
            "existing_engineering_controls": "联锁",
            "existing_management_controls": "SOP",
            "existing_ppe": "护目镜",
            "existing_emergency_measures": "喷淋",
        },
        5: {"l_residual": 1, "e_residual": 2, "c_residual": 3},
        6: {
            "needs_recommendation": "是",
            "recommendation_type": "工程",
            "recommendation_content": "增加联锁",
            "recommendation_priority": "高",
        },
        7: {"l_post": 1, "e_post": 1, "c_post": 1, "post_risk_level": "level_4"},
    }
    for script_number, ai_output in output_by_script.items():
        item.ai_node_progress = f"pending_script{script_number}"
        if script_number > 1:
            setattr(item, f"script{script_number - 1}_review_status", "approved")
        assert await service.run_script(item_id, script_number, ai_output) is item

    script_three_update = repo.update_hazard_identification.await_args_list[-5].args[1]
    assert script_three_update["d_inherent"] == 60
    assert script_three_update["inherent_risk_label"]
    script_five_update = repo.update_hazard_identification.await_args_list[-3].args[1]
    assert script_five_update["d_residual"] == 6

    assert await service.review_script(item_id, 7, "approved") is item
    review_values = repo.update_hazard_identification.await_args.args[1]
    assert review_values["overall_status"] == "completed"
    assert await service.review_script(item_id, 3, "rejected") is item
    assert (
        repo.update_hazard_identification.await_args.args[1]["ai_node_progress"]
        == "pending_script3"
    )
    assert await service.upload_attachment(item_id, "sop.docx", "/tmp/sop.docx") is item
    assert SafetyService._safe_float(" 待人工确认 ") is None
    assert SafetyService._safe_float("bad") is None
    assert SafetyService._safe_float(3) == 3.0
    assert SafetyService._safe_float(object()) is None
