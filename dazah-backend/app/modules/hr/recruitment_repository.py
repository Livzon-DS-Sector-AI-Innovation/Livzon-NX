"""Recruitment Bitable repository – wraps Feishu Bitable for 招聘 / 入职 flow."""

import logging
from datetime import UTC
from typing import Any

from app.core.exceptions import NotFoundException, RecruitmentNotConfigured
from app.modules.hr.feishu.bitable import BitableClient
from app.shared.config_reader import get_module_setting

logger = logging.getLogger(__name__)

# ─── Table IDs ───

TBL_JOB_POSTING = "tbldWBRTNm5RrQHw"
TBL_CANDIDATE = "tblx3KvkQoHdGjFL"
TBL_ONBOARDING = "tblK1IWXATe2Nn2q"
TBL_EMPLOYEE = "tblDThp5wAUfDopZ"  # 员工档案表

# ═══════════════════════════════════════════════════════════════
# Read maps: English → Chinese field name (search_records returns Chinese names)
# ═══════════════════════════════════════════════════════════════

F_JOB_R = {
    "title": "职位名称",
    "description": "岗位描述",
    "requirement": "任职要求",
    "salary_range": "薪资范围",
    "location": "工作地点",
    "req_skills": "要求技能",
    "status": "招聘状态",
    "publish_date": "发布时间",
}

F_CANDIDATE_R = {
    "name": "姓名",
    "contact": "联系方式",
    "email": "邮箱",
    "job_id": "应聘职位",
    "job_position": "应聘职位",  # 前端读 job_position，飞书返回中文键
    "education": "学历",
    "work_years": "工作经验 (年)",
    "skills": "技能标签",
    "match_rate": "技能匹配度",
    "resume_score": "简历评分",
    "fit_level": "招聘符合程度",
    "interview_status": "面试状态",
    "remark": "备注",
}

F_ONBOARDING_R = {
    "name": "姓名",
    "onboard_date": "入职日期",
    "department": "入职部门",
    "level": "岗位",
    "status": "入职状态",
    "health_status": "体检状态",
    "resignation_cert": "离职证明",
    "id_card": "身份证信息",
    "education_cert": "学历证明",
}

# ═══════════════════════════════════════════════════════════════
# Write maps: English → Chinese field name (create/update uses Chinese names)
# ═══════════════════════════════════════════════════════════════

F_JOB_W = {
    "title": "职位名称",
    "description": "岗位描述",
    "requirement": "任职要求",
    "salary_range": "薪资范围",
    "location": "工作地点",
    "req_skills": "要求技能",
    "status": "招聘状态",
    "publish_date": "发布时间",
}

F_CANDIDATE_W = {
    "name": "姓名",
    "contact": "联系方式",
    "email": "邮箱",
    "job_id": "应聘职位",
    "education": "学历",
    "work_years": "工作经验(年)",
    "skills": "技能标签",
    "match_rate": "技能匹配度",
    "resume_score": "简历评分",
    "fit_level": "招聘符合程度",
    "interview_status": "面试状态",
    "remark": "备注",
    "resume_attachment": "简历附件",
}

F_ONBOARDING_W = {
    "name": "姓名",
    "onboard_date": "入职日期",
    "department": "入职部门",
    "level": "岗位",
    "status": "入职状态",
    "health_status": "体检状态",
    "resignation_cert": "离职证明",
    "id_card": "身份证信息",
    "education_cert": "学历证明",
}


def _to_feishu_fields(
    write_map: dict[str, Any], data: dict[str, Any]
) -> dict[str, Any]:
    """Map Python key → field_id for Feishu Bitable write/create/update.

    Handles date string → millisecond timestamp conversion for DateTime fields.
    Skips empty strings (Feishu API rejects empty values for non-text fields).
    """
    from datetime import datetime

    fields: dict[str, Any] = {}
    for py_key, fid in write_map.items():
        if py_key not in data or data[py_key] is None:
            continue
        val = data[py_key]
        # Skip empty strings — Feishu rejects them for DateTime/Select fields
        if val == "":
            continue
        # Convert date strings to Feishu millisecond timestamps
        if isinstance(val, str) and "date" in py_key.lower():
            try:
                d = datetime.strptime(val, "%Y-%m-%d").date()
                val = int(
                    datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp() * 1000
                )
            except ValueError:
                pass
        fields[fid] = val
    return fields


def _from_feishu_fields(
    read_map: dict[str, Any], feishu_record: dict[str, Any]
) -> dict[str, Any]:
    """Map Chinese field name → Python key from search_records response."""
    fields = feishu_record.get("fields", {})
    result: dict[str, Any] = {"id": feishu_record.get("record_id", "")}
    for py_key, chinese_name in read_map.items():
        if chinese_name in fields:
            val = fields[chinese_name]
            # Feishu text fields come as [{"text":"value","type":"text"}]
            if (
                isinstance(val, list)
                and len(val) > 0
                and isinstance(val[0], dict)
                and "text" in val[0]
            ):
                val = val[0]["text"]
            # Feishu link fields from search_records: [{"id":"rec_xxx"}]
            elif (
                isinstance(val, list)
                and len(val) > 0
                and isinstance(val[0], dict)
                and "id" in val[0]
            ):
                val = val[0]["id"]
            # Feishu link fields: {"link_record_ids": ["recxxx"]} -> "recxxx"
            elif isinstance(val, dict) and "link_record_ids" in val:
                ids = val["link_record_ids"]
                val = ids[0] if ids else None
            # Convert Feishu millisecond timestamps to date strings
            if (
                isinstance(val, int)
                and val > 1000000000000
                and "date" in py_key.lower()
            ):
                from datetime import datetime

                try:
                    val = datetime.fromtimestamp(val / 1000, tz=UTC).strftime(
                        "%Y-%m-%d"
                    )
                except Exception:
                    pass
            result[py_key] = val
    return result


class RecruitmentBitableRepo:
    """Recruitment bitable data access — reads from Feishu multidimensional tables."""

    def __init__(self, app_token: str | None = None) -> None:
        self._app_token = app_token
        self._client: BitableClient | None = None
        self._resolved_token: str | None = None

    async def _get_client(self) -> BitableClient | None:
        "延迟初始化 client。从 module_settings → env → entity_settings 依次查找 token。"
        if self._client is None:
            token = self._app_token
            if not token:
                token = await get_module_setting("hr", "HR_FEISHU_APP_TOKEN", "")
            if not token:
                from app.core.config import get_settings

                token = get_settings().FEISHU_BITABLE_APP_TOKEN
            if not token:
                # 兜底：从 HR 飞书实体设置表读取（HR设置-飞书设置 页面配置的）
                token = await self._read_token_from_entity_settings()
            if not token:
                logger.warning(
                    "Feishu bitable app_token not configured,"
                    " recruitment features unavailable"
                )
                self._resolved_token = ""
                return None
            self._resolved_token = token
            self._client = BitableClient(app_token=token)
        elif not self._resolved_token:
            return None
        return self._client

    @staticmethod
    async def _read_token_from_entity_settings() -> str | None:
        """从 hr_feishu_entity_settings 读取招聘实体的 app_token。"""
        try:
            from sqlalchemy import text

            from app.core.database import async_session_factory

            async with async_session_factory() as session:
                result = await session.execute(
                    text(
                        "SELECT app_token FROM hr.hr_feishu_entity_settings "
                        "WHERE entity_code IN ('job_posting', 'ca"
                        "ndidate', 'onboarding') "
                        "AND is_enabled = true AND app_token IS N"
                        "OT NULL AND app_token != '' "
                        "LIMIT 1"
                    )
                )
                row = result.fetchone()
                if row and row[0]:
                    logger.info(
                        "Using app_token from hr_feishu_entity_settings for recruitment"
                    )
                    return str(row[0])
        except Exception:
            logger.exception(
                "Failed to read recruitment token from hr_feishu_entity_settings"
            )
        return None

    # ─── Job Posting ────────────────────────────────────────────────

    async def list_jobs(
        self, page: int = 1, page_size: int = 20, keyword: str | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        client = await self._get_client()
        if not client:
            return [], 0
        records = await client.search_records(TBL_JOB_POSTING, page_size=500)
        items = [_from_feishu_fields(F_JOB_R, r) for r in records]
        if keyword:
            kw = keyword.lower()
            items = [it for it in items if kw in (it.get("title") or "").lower()]
        total = len(items)
        start = (page - 1) * page_size
        return items[start : start + page_size], total

    async def create_job(self, fields: dict[str, Any]) -> dict[str, Any]:
        client = await self._get_client()
        if not client:
            raise RecruitmentNotConfigured()
        record = await client.create_record(
            TBL_JOB_POSTING, _to_feishu_fields(F_JOB_W, fields)
        )
        return _from_feishu_fields(F_JOB_R, record)

    async def get_job(self, record_id: str) -> dict[str, Any]:
        client = await self._get_client()
        if not client:
            raise RecruitmentNotConfigured()
        records = await client.search_records(TBL_JOB_POSTING, page_size=500)
        for r in records:
            if r.get("record_id") == record_id:
                return _from_feishu_fields(F_JOB_R, r)
        raise ValueError(f"Job not found: {record_id}")

    async def get_job_names(self) -> dict[str, str]:
        """返回 {record_id: job_title} 的映射表。"""
        client = await self._get_client()
        if not client:
            return {}
        records = await client.search_records(TBL_JOB_POSTING, page_size=500)
        result = {}
        for r in records:
            rid = r.get("record_id", "")
            fields = r.get("fields", {})
            title = fields.get("职位名称", "")
            if (
                isinstance(title, list)
                and len(title) > 0
                and isinstance(title[0], dict)
                and "text" in title[0]
            ):
                title = title[0]["text"]
            result[rid] = title or rid
        return result

    async def update_job(
        self, record_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        client = await self._get_client()
        if not client:
            raise RecruitmentNotConfigured()
        await client.update_record(
            TBL_JOB_POSTING, record_id, _to_feishu_fields(F_JOB_W, fields)
        )
        # 飞书 update 接口只返回变更字段，需重新获取完整记录
        return await self.get_job(record_id)

    # ─── Candidate ──────────────────────────────────────────────────

    async def list_candidates(
        self,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        fit_level: str | None = None,
        interview_status: str | None = None,
        job_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        client = await self._get_client()
        if not client:
            return [], 0
        records = await client.search_records(TBL_CANDIDATE, page_size=500)
        items = [_from_feishu_fields(F_CANDIDATE_R, r) for r in records]
        if keyword:
            kw = keyword.lower()
            items = [
                it
                for it in items
                if kw in (it.get("name") or "").lower()
                or kw in (it.get("contact") or "").lower()
            ]
        if fit_level:
            items = [it for it in items if it.get("fit_level") == fit_level]
        if interview_status:
            items = [
                it for it in items if it.get("interview_status") == interview_status
            ]
        if job_id:
            items = [it for it in items if it.get("job_id") == job_id]
        # Filter out soft-deleted
        items = [it for it in items if it.get("interview_status") != "已删除"]
        total = len(items)
        start = (page - 1) * page_size
        return items[start : start + page_size], total

    async def create_candidate(self, fields: dict[str, Any]) -> dict[str, Any]:
        client = await self._get_client()
        if not client:
            raise RecruitmentNotConfigured()
        record = await client.create_record(
            TBL_CANDIDATE, _to_feishu_fields(F_CANDIDATE_W, fields)
        )
        return _from_feishu_fields(F_CANDIDATE_R, record)

    async def get_candidate(self, record_id: str) -> dict[str, Any]:
        client = await self._get_client()
        if not client:
            raise RecruitmentNotConfigured()
        records = await client.search_records(TBL_CANDIDATE, page_size=500)
        for r in records:
            if r.get("record_id") == record_id:
                result = _from_feishu_fields(F_CANDIDATE_R, r)
                # Attach resume file info from raw fields
                raw_fields = r.get("fields", {})
                att = raw_fields.get("简历附件")
                if att and isinstance(att, list) and len(att) > 0:
                    result["resume_attachment"] = {
                        "file_token": att[0].get("file_token", ""),
                        "name": att[0].get("name", ""),
                        "type": att[0].get("type", ""),
                        "size": att[0].get("size", 0),
                    }
                return result
        raise NotFoundException("候选人", record_id)

    async def update_candidate(
        self, record_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        client = await self._get_client()
        if not client:
            raise RecruitmentNotConfigured()
        await client.update_record(
            TBL_CANDIDATE, record_id, _to_feishu_fields(F_CANDIDATE_W, fields)
        )
        # 飞书 update 接口只返回变更字段，需重新获取完整记录
        return await self.get_candidate(record_id)

    async def soft_delete_candidate(self, record_id: str) -> None:
        """Permanently delete the candidate record from Feishu Bitable."""
        client = await self._get_client()
        if not client:
            raise RecruitmentNotConfigured()
        await client.delete_record(TBL_CANDIDATE, record_id)

    # ─── Onboarding ─────────────────────────────────────────────────

    async def list_onboarding(
        self,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        dept_alias_set: set[str] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        client = await self._get_client()
        if not client:
            return [], 0
        records = await client.search_records(TBL_ONBOARDING, page_size=500)
        items = [_from_feishu_fields(F_ONBOARDING_R, r) for r in records]
        if dept_alias_set is not None:
            # 部门级数据隔离：可见部门别名集合（入职部门）
            items = [
                it for it in items if (it.get("department") or "") in dept_alias_set
            ]
        if keyword:
            kw = keyword.lower()
            items = [it for it in items if kw in (it.get("name") or "").lower()]
        total = len(items)
        start = (page - 1) * page_size
        return items[start : start + page_size], total

    async def create_onboarding(self, fields: dict[str, Any]) -> dict[str, Any]:
        client = await self._get_client()
        if not client:
            raise RecruitmentNotConfigured()
        record = await client.create_record(
            TBL_ONBOARDING, _to_feishu_fields(F_ONBOARDING_W, fields)
        )
        record_id = record.get("record_id", "")
        if record_id:
            return await self.get_onboarding(record_id)
        return _from_feishu_fields(F_ONBOARDING_R, record)

    async def get_onboarding(self, record_id: str) -> dict[str, Any]:
        client = await self._get_client()
        if not client:
            raise RecruitmentNotConfigured()
        records = await client.search_records(TBL_ONBOARDING, page_size=500)
        for r in records:
            if r.get("record_id") == record_id:
                return _from_feishu_fields(F_ONBOARDING_R, r)
        raise NotFoundException("入职记录", record_id)

    async def update_onboarding(
        self, record_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        client = await self._get_client()
        if not client:
            raise RecruitmentNotConfigured()
        await client.update_record(
            TBL_ONBOARDING, record_id, _to_feishu_fields(F_ONBOARDING_W, fields)
        )
        # 飞书 update 接口只返回变更字段，需重新获取完整记录
        return await self.get_onboarding(record_id)

    # ─── Dashboard ──────────────────────────────────────────────────

    async def get_dashboard_stats(
        self, dept_alias_set: set[str] | None = None
    ) -> dict[str, Any]:
        client = await self._get_client()
        if not client:
            return {"stages": {}, "total": 0}
        records = await client.search_records(TBL_ONBOARDING, page_size=500)

        stage_1 = stage_2 = stage_3 = stage_4 = stage_5 = 0
        total = 0
        for ob in records:
            fs = ob.get("fields", {})
            if dept_alias_set is not None:
                # 部门级数据隔离：非管理员仅统计可见部门
                ob_dept = fs.get("入职部门", "")
                if ob_dept not in dept_alias_set:
                    continue
            total += 1
            ob_status = fs.get("入职状态", "")
            ob_date = fs.get("入职日期")
            health_status = fs.get("体检状态", "")
            resignation_cert = fs.get("离职证明", "")
            id_card = fs.get("身份证信息", "")
            education_cert = fs.get("学历证明", "")

            if ob_status == "已完成":
                stage_5 += 1
                continue

            all_materials_provided = (
                resignation_cert == "已提供"
                and id_card == "已提供"
                and education_cert == "已提供"
            )

            if (
                ob_status == "进行中"
                and health_status == "合格"
                and all_materials_provided
            ):
                stage_4 += 1
                continue

            if (
                ob_status == "进行中"
                and health_status not in ("未进行", "")
                and not all_materials_provided
            ):
                stage_3 += 1
                continue

            if (
                ob_status == "进行中"
                and ob_date
                and health_status == "未进行"
                and not all_materials_provided
            ):
                stage_2 += 1
                continue

            if ob_status == "进行中" and not ob_date:
                stage_1 += 1
                continue

        return {
            "stages": {
                "stage_1_pending": {"count": stage_1, "label": "待入职"},
                "stage_2_info": {"count": stage_2, "label": "信息录入"},
                "stage_3_health": {"count": stage_3, "label": "体检"},
                "stage_4_material": {"count": stage_4, "label": "材料登记"},
                "stage_5_done": {"count": stage_5, "label": "完成"},
            },
            "total": total,
        }
