"""Safety business workflows."""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.llm import LLMOutputError, llm_client
from app.modules.safety.feishu.notification import send_user_card
from app.modules.safety.models import (
    Accident,
    Contractor,
    ContractorWorkRecord,
    HazardReport,
    SafetyCheck,
    SafetyTraining,
    TrainingRecord,
)
from app.modules.safety.repository import SafetyRepository
from app.modules.safety.schemas import (
    AccidentCreate,
    AccidentUpdate,
    ContractorCreate,
    ContractorUpdate,
    ContractorWorkRecordCreate,
    ContractorWorkRecordUpdate,
    HazardReportCreate,
    HazardReportUpdate,
    SafetyCheckCreate,
    SafetyCheckUpdate,
    SafetyTrainingCreate,
    SafetyTrainingUpdate,
    TrainingRecordCreate,
    TrainingRecordUpdate,
)
from app.platform.audit.service import record_audit_log
from app.platform.integrations.ai.document_parser import DocumentParser
from app.platform.integrations.ai.prompts import (
    SCRIPT_CONFIG,
    build_prompt,
)

logger = logging.getLogger(__name__)

# ── 调试文件日志：追踪通知流程的完整调用链 ──
_debug_log_path = str(Path(__file__).resolve().parents[3] / "debug_notify.log")


def _debug_log(msg: str) -> None:
    """写调试日志到文件（用于排查通知未发送问题）。"""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with open(_debug_log_path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


# ── AI 配置默认值（仅用于自动种子和 temperature fallback）──


class _SafetyCoreService:
    """Safety module service"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = SafetyRepository(session)

    async def _audit(
        self,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        try:
            await record_audit_log(
                self.session,
                action=action,
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                old_value=old_value,
                new_value=new_value,
                extra=extra,
            )
        except Exception:
            logger.exception("审计日志记录失败 (%s:%s)", resource_type, action)

    # ==================== SafetyCheck Operations ====================

    async def get_checks(
        self,
        skip: int = 0,
        limit: int = 20,
        status: str | None = None,
        check_type: str | None = None,
        department: str | None = None,
    ) -> tuple[list[SafetyCheck], int]:
        """获取安全检查列表"""
        return await self.repo.get_checks(skip, limit, status, check_type, department)

    async def get_check(self, check_id: uuid.UUID) -> SafetyCheck | None:
        """获取安全检查详情"""
        return await self.repo.get_check_by_id(check_id)

    async def create_check(self, data: SafetyCheckCreate) -> SafetyCheck:
        """创建安全检查"""
        check_data = data.model_dump()
        item = await self.repo.create_check(check_data)
        await self._audit("create", "safety_check", resource_id=item.id)
        return item

    async def update_check(
        self, check_id: uuid.UUID, data: SafetyCheckUpdate
    ) -> SafetyCheck | None:
        """更新安全检查"""
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        item = await self.repo.update_check(check_id, update_data)
        if item:
            await self._audit("update", "safety_check", resource_id=check_id)
        return item

    async def submit_check(self, check_id: uuid.UUID) -> SafetyCheck | None:
        """提交安全检查（草稿→已提交）"""
        check = await self.repo.get_check_by_id(check_id)
        if not check or check.status != "draft":
            return None
        item = await self.repo.update_check(check_id, {"status": "submitted"})
        if item:
            await self._audit("submit", "safety_check", resource_id=check_id)
        return item

    async def review_check(
        self, check_id: uuid.UUID, result: str
    ) -> SafetyCheck | None:
        """审核安全检查"""
        check = await self.repo.get_check_by_id(check_id)
        if not check or check.status not in ("submitted",):
            return None
        return await self.repo.update_check(
            check_id, {"status": "reviewed", "result": result}
        )

    async def close_check(self, check_id: uuid.UUID) -> SafetyCheck | None:
        """关闭安全检查"""
        check = await self.repo.get_check_by_id(check_id)
        if not check or check.status not in ("reviewed",):
            return None
        item = await self.repo.update_check(check_id, {"status": "closed"})
        if item:
            await self._audit("close", "safety_check", resource_id=check_id)
        return item

    async def confirm_check(self, check_id: uuid.UUID, role: str) -> SafetyCheck | None:
        """确认安全检查（检查人员 / 安全办）"""
        check = await self.repo.get_check_by_id(check_id)
        if not check:
            return None
        if role == "inspector":
            return await self.repo.update_check(check_id, {"inspector_confirmed": True})
        elif role == "safety_officer":
            return await self.repo.update_check(
                check_id, {"safety_officer_confirmed": True}
            )
        return None

    async def delete_check(self, check_id: uuid.UUID) -> bool:
        """删除安全检查"""
        result = await self.repo.delete_check(check_id)
        if result:
            await self._audit("delete", "safety_check", resource_id=check_id)
        return result

    # ==================== HazardReport Operations ====================

    async def get_hazards(
        self,
        skip: int = 0,
        limit: int = 20,
        status: str | None = None,
        rectification_status: str | None = None,
        hazard_type: str | None = None,
        hazard_level: str | None = None,
        hazard_category: str | None = None,
        inspection_category: str | None = None,
        department: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[HazardReport], int]:
        """获取隐患列表"""
        return await self.repo.get_hazards(
            skip,
            limit,
            status,
            rectification_status,
            hazard_type,
            hazard_level,
            hazard_category,
            inspection_category,
            department,
            keyword,
        )

    async def get_hazard_stats(self) -> dict[str, int]:
        """获取隐患全局统计数据"""
        return await self.repo.get_hazard_stats()

    async def get_hazard(self, hazard_id: uuid.UUID) -> HazardReport | None:
        """获取隐患详情"""
        return await self.repo.get_hazard_by_id(hazard_id)

    async def create_hazard(
        self, data: HazardReportCreate, auto_run_ai: bool = True
    ) -> HazardReport:
        """创建隐患（hazard_no 留空时自动生成），创建后自动执行 AI 工作流。"""
        hazard_data = data.model_dump(exclude_none=True)
        if not hazard_data.get("hazard_no"):
            # 自动生成：HZ-年月日-序号
            today = datetime.now().strftime("%Y%m%d")
            existing = await self.repo.count_hazards_today(today)
            hazard_data["hazard_no"] = f"HZ-{today}-{existing + 1:03d}"
        # 填充默认值以兼容DB NOT NULL约束
        hazard_data.setdefault("hazard_type", "unsafe_condition")
        hazard_data.setdefault("hazard_level", "general")
        hazard_data.setdefault("description", "待AI填写")
        hazard_data.setdefault("discovered_at", datetime.now())
        # 初始化 AI 状态
        hazard_data.setdefault("ai_node_progress", "pending_script1")
        hazard_data.setdefault("overall_status", "open")
        hazard_data.setdefault("ai_generated", False)

        item = await self.repo.create_hazard(hazard_data)

        # 记录审计日志
        await self._audit("create", "hazard_report", resource_id=item.id)

        # ── 自动执行 AI 隐患识别（插件：有照片走视觉模型，无照片走文本模型）──
        if auto_run_ai:
            logger.info(
                "触发 AI 隐患识别: hazard_id=%s hazard_no=%s", item.id, item.hazard_no
            )
            try:
                item = await self.run_hazard_ai_script(item.id, 1)
                logger.info(
                    "AI 隐患识别完成: hazard_id=%s type=%s level=%s category=%s"
                    " error=%s",
                    item.id,
                    item.hazard_type,
                    item.hazard_level,
                    item.hazard_category,
                    item.ai_error_message,
                )
            except Exception as e:
                logger.error(f"AI 隐患识别失败(hazard {item.id}): {e}")
                # 即使 AI 失败也返回记录，用户可在台账中手动重试

        return item

    async def update_hazard(
        self, hazard_id: uuid.UUID, data: HazardReportUpdate
    ) -> HazardReport | None:
        """更新隐患"""
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        item = await self.repo.update_hazard(hazard_id, update_data)
        if item:
            await self._audit("update", "hazard_report", resource_id=hazard_id)
        return item

    async def upload_hazard_photo(
        self, hazard_id: uuid.UUID, file_name: str, file_path: str
    ) -> HazardReport | None:
        """保存隐患图片路径，追加到 defect_photos JSON 数组"""
        import json

        hazard = await self.repo.get_hazard_by_id(hazard_id)
        if not hazard:
            return None
        # 标准化为 / 分隔符：避免 Windows 反斜杠在 JSON 中被当作非法转义符
        safe_path = file_path.replace("\\", "/")
        try:
            photos = json.loads(hazard.defect_photos) if hazard.defect_photos else []
        except (json.JSONDecodeError, TypeError):
            # 兼容历史损坏数据：尝试替换反斜杠后解析，仍失败则视为空列表
            try:
                photos = json.loads(hazard.defect_photos.replace("\\", "/"))
            except Exception:
                photos = []
        if not isinstance(photos, list):
            photos = []
        photos.append(safe_path)
        return await self.repo.update_hazard(
            hazard_id, {"defect_photos": json.dumps(photos, ensure_ascii=False)}
        )

    async def upload_rectification_photo(
        self, hazard_id: uuid.UUID, file_path: str
    ) -> HazardReport | None:
        """保存整改后图片路径，追加到 rectification_photos JSON 数组"""
        import json

        hazard = await self.repo.get_hazard_by_id(hazard_id)
        if not hazard:
            return None
        safe_path = file_path.replace("\\", "/")
        try:
            photos = (
                json.loads(hazard.rectification_photos)
                if hazard.rectification_photos
                else []
            )
        except (json.JSONDecodeError, TypeError):
            try:
                photos = json.loads(hazard.rectification_photos.replace("\\", "/"))
            except Exception:
                photos = []
        if not isinstance(photos, list):
            photos = []
        photos.append(safe_path)
        return await self.repo.update_hazard(
            hazard_id, {"rectification_photos": json.dumps(photos, ensure_ascii=False)}
        )

    async def start_rectification(self, hazard_id: uuid.UUID) -> HazardReport | None:
        """开始整改"""
        hazard = await self.repo.get_hazard_by_id(hazard_id)
        if not hazard or hazard.rectification_status != "pending":
            return None
        return await self.repo.update_hazard(
            hazard_id, {"rectification_status": "in_progress"}
        )

    async def reply_rectification(
        self,
        hazard_id: uuid.UUID,
        reply_content: str,
        rectification_photos: str | None,
        corrective_preventive_measures: str | None = None,
        rectification_reply: str | None = None,
        actual_completion_date: datetime | None = None,
    ) -> HazardReport | None:
        """整改回复：in_progress → replied（合并了原 complete_rectification 步骤）。"""
        hazard = await self.repo.get_hazard_by_id(hazard_id)
        if not hazard or hazard.rectification_status not in ("pending", "in_progress"):
            return None
        update_data: dict[str, Any] = {
            "rectification_status": "replied",
        }
        # 整改完成时间：优先用传入值，其次保留已有值，最后 fallback 当前时间
        if actual_completion_date:
            update_data["actual_completion_date"] = actual_completion_date
        elif not hazard.actual_completion_date:
            update_data["actual_completion_date"] = datetime.now()
        # 优先级：rectification_reply > corrective_preventive_measures > reply_content
        reply_value = (
            rectification_reply or corrective_preventive_measures or reply_content
        )
        if reply_value:
            update_data["rectification_reply"] = reply_value
        if rectification_photos is not None:
            update_data["rectification_photos"] = rectification_photos
        updated = await self.repo.update_hazard(hazard_id, update_data)

        # 记录审计日志
        if updated:
            await self._audit(
                "reply_rectification", "hazard_report", resource_id=hazard_id
            )

        # 整改回复后，异步通知一级复核人（部门负责人）
        if updated:
            asyncio.create_task(_send_verify_notification(updated, 1))

        return updated

    async def verify_level(
        self,
        hazard_id: uuid.UUID,
        level: int,
        action: str,
        opinion: str | None,
        user_id: uuid.UUID,
        user_name: str,
    ) -> HazardReport | None:
        """三级复核：按级别审批或驳回。

        一般隐患：仅需一级（部门负责人）+ 三级（隐患发现人），跳过二级。
        较大/重大隐患：三级全流程。
        """
        hazard = await self.repo.get_hazard_by_id(hazard_id)
        if not hazard:
            return None

        # 判断是否一般隐患（可跳过二级复核）
        is_general = hazard.hazard_level == "general"

        # 检查当前状态是否允许该级别复核
        if level == 1 and hazard.rectification_status != "replied":
            return None
        if level == 2 and hazard.verify_level_1_status != "approved":
            return None
        if level == 3:
            # 一般隐患：一级通过后可直接三级复核
            if is_general:
                if hazard.verify_level_1_status != "approved":
                    return None
            else:
                if hazard.verify_level_2_status != "approved":
                    return None

        datetime.now()
        if action == "rejected":
            update_data: dict[str, Any] = {
                "rectification_status": "rejected",
                f"verify_level_{level}_status": "rejected",
            }
            return await self.repo.update_hazard(hazard_id, update_data)

        # action == "approved"
        if level == 1 and is_general:
            # 一般隐患：一级通过后自动跳过二级，状态直接到 level2_approved
            update_data: dict[str, Any] = {
                "rectification_status": "level2_approved",
                "verify_level_1_status": "approved",
                "verify_level_2_status": "approved",
            }
        elif level == 3:
            update_data = {
                "rectification_status": "closed",
                "status": "closed",
                "verify_level_3_status": "approved",
            }
        else:
            next_status = f"level{level}_approved"
            update_data = {
                "rectification_status": next_status,
                f"verify_level_{level}_status": "approved",
            }
        updated = await self.repo.update_hazard(hazard_id, update_data)

        # 记录审计日志
        if updated:
            await self._audit(
                "verify",
                "hazard_report",
                resource_id=hazard_id,
                user_id=user_id,
                extra={"level": level, "action": action},
            )

        # 审核通过后，异步通知下一级复核人
        if updated and action == "approved":
            if level == 1 and is_general:
                # 一般隐患：跳过二级，直接通知三级
                asyncio.create_task(_send_verify_notification(updated, 3))
            elif level < 3:
                asyncio.create_task(_send_verify_notification(updated, level + 1))

        return updated

    async def rework_rectification(
        self,
        hazard_id: uuid.UUID,
        reply_content: str,
        rectification_photos: str | None,
        user_id: uuid.UUID,
        user_name: str,
    ) -> HazardReport | None:
        """重新整改：rejected → replied，重置所有复核级别"""
        hazard = await self.repo.get_hazard_by_id(hazard_id)
        if not hazard or hazard.rectification_status != "rejected":
            return None
        update_data: dict[str, Any] = {
            "rectification_status": "replied",
            "rectification_reply": reply_content,
            "verify_level_1_status": "pending",
            "verify_level_2_status": "pending",
            "verify_level_3_status": "pending",
        }
        if rectification_photos is not None:
            update_data["rectification_photos"] = rectification_photos
        updated = await self.repo.update_hazard(hazard_id, update_data)

        # 重新整改回复后，异步通知一级复核人
        if updated:
            asyncio.create_task(_send_verify_notification(updated, 1))

        return updated

    async def delete_hazard(self, hazard_id: uuid.UUID) -> bool:
        """删除隐患"""
        result = await self.repo.delete_hazard(hazard_id)
        if result:
            await self._audit("delete", "hazard_report", resource_id=hazard_id)
        return result

    # ── AI 工作流 ──

    async def _generate_hazard_ai_output(
        self, script_number: int, item: HazardReport
    ) -> dict:
        """调用 AI 服务为隐患模块生成工作流输出。失败时抛出 AIOutputError。

        script 1 → AIHazardIdentifier 插件（含 few-shot prompt、规则引擎、自动修正）
        script 2 → 无需额外 AI 调用（插件已在 script 1 中生成整改建议）
        """
        if script_number == 1:
            return await self._generate_hazard_identification(item)

        # Script 2: 整改建议已由插件在 script 1 中生成，无需额外调用
        logger.debug("Script 2 无需额外 AI 调用，整改建议已由插件生成")
        return {}

    async def _generate_hazard_identification(self, item: HazardReport) -> dict:
        """使用 AIHazardIdentifier 插件执行 AI 隐患识别（script 1）。

        插件负责：prompt 构建（含 few-shot）、视觉/文本路由、输出解析、
        规则验证和自动修正。
        返回 dict 供 _map_hazard_ai_output() 映射到 HazardReport 字段。
        """
        from app.modules.safety.ai_hazard_identification import (
            AIHazardIdentifier,
            HazardIdentificationInput,
            PluginConfig,
        )

        # 解析缺陷图片（本地路径 → data URI）
        image_urls = (
            self._parse_defect_photo_urls(item.defect_photos)
            if item.defect_photos
            else []
        )
        logger.info(
            "AI 隐患识别插件启动: hazard_id=%s desc=%s photos=%d",
            item.id,
            (item.description or "")[:80],
            len(image_urls),
        )

        # 构建插件输入（注意：HazardReport 模型没有 location 字段，传 None 即可）
        input_data = HazardIdentificationInput(
            hazard_no=item.hazard_no or str(item.id)[:8],
            description=item.description or "无描述",
            department=item.department or "",
            location=item.department
            or "",  # 隐患模型无独立 location，用 department 代替
            discovered_by_name=item.discovered_by_name or "",
            discovered_at=item.discovered_at,
            defect_photos=image_urls,
        )

        try:
            config = PluginConfig(
                temperature=0.05,
                strict_mode=False,  # 非严格模式：验证警告不阻塞流程
                enable_vision=bool(image_urls),
            )
            plugin = AIHazardIdentifier(config)
            output = await plugin.identify(input_data)

            # 转换为 dict 供 _map_hazard_ai_output() 使用
            return {
                "key_defect": output.key_defect,
                "hazard_type": output.hazard_type.value,
                "hazard_category": output.hazard_category.value,
                "hazard_level": output.hazard_level.value,
                "major_hazard_basis": output.major_hazard_basis,
                # 整改建议也返回，供后续 script 2 或人工参考
                "rectification_suggestion": {
                    "immediate": output.rectification_suggestion.immediate,
                    "short_term": output.rectification_suggestion.short_term,
                    "long_term": output.rectification_suggestion.long_term,
                },
            }
        except Exception as e:
            logger.error("AI 隐患识别插件执行失败: %s", e)
            raise LLMOutputError(f"AI 隐患识别失败: {e}") from e

    def _parse_defect_photo_urls(self, defect_photos: str) -> list[str]:
        """从 defect_photos JSON 字段提取图片，本地路径转 base64 data URI。"""
        import base64
        import json as _json

        try:
            photos = _json.loads(defect_photos)
        except (_json.JSONDecodeError, TypeError):
            # Windows 反斜杠路径经 json.dumps 写入后，json.loads 会报 Invalid \escape
            # 尝试把反斜杠替换为正斜杠再解析
            try:
                photos = _json.loads(defect_photos.replace("\\", "/"))
            except (_json.JSONDecodeError, TypeError):
                return []
        if isinstance(photos, str):
            photos = [photos] if photos else []
        elif not isinstance(photos, list):
            return []

        urls: list[str] = []
        for p in photos:
            p_str = str(p)
            # 已经是 http/data URL，直接使用
            if (
                p_str.startswith("http://")
                or p_str.startswith("https://")
                or p_str.startswith("data:")
            ):
                urls.append(p_str)
                continue
            # 本地路径 → base64 data URI
            # 兼容 Windows 反斜杠路径：同时检查原始路径和正斜杠版本
            check_paths = [p_str]
            if "\\" in p_str:
                check_paths.append(p_str.replace("\\", "/"))
            elif "/" in p_str:
                check_paths.append(p_str.replace("/", "\\"))
            found_path = None
            for cp in check_paths:
                if cp and os.path.exists(cp):
                    found_path = cp
                    break
            if found_path:
                try:
                    ext = os.path.splitext(found_path)[1].lower()
                    mime = {
                        ".png": "image/png",
                        ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg",
                        ".gif": "image/gif",
                        ".webp": "image/webp",
                        ".bmp": "image/bmp",
                    }.get(ext, "image/png")
                    with open(found_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    urls.append(f"data:{mime};base64,{b64}")
                    logger.debug("转换本地图片为 data URI: %s (%s)", found_path, mime)
                except Exception as exc:
                    logger.warning("无法读取图片 %s: %s", found_path, exc)
        return urls

    # ── AI 服务工厂 ──

    async def run_hazard_ai_script(
        self, hazard_id: uuid.UUID, script_number: int
    ) -> HazardReport | None:
        """执行隐患AI工作流脚本（1=AI隐患识别）。

        script 1: AIHazardIdentifier 插件（含 few-shot + 规则引擎 + 整改建议）
        script 2: 已废弃，插件在 script 1 中已生成整改建议
        """
        item = await self.repo.get_hazard_by_id(hazard_id)
        if not item:
            return None

        update_data: dict[str, Any] = {}

        try:
            generated = await self._generate_hazard_ai_output(script_number, item)
            self._map_hazard_ai_output(script_number, generated, update_data)
            update_data["ai_node_progress"] = "completed"
            update_data["ai_error_message"] = None
            update_data["ai_generated"] = True
        except LLMOutputError as e:
            logger.error(f"Hazard script {script_number} AI 输出错误: {e}")
            update_data["ai_error_message"] = str(e)
        except Exception as e:
            logger.error(f"Hazard script {script_number} 执行异常: {e}")
            update_data["ai_error_message"] = f"AI 服务调用失败：{e}"

        return await self.repo.update_hazard(hazard_id, update_data)

    # ── AI 输出字段约束（DB Enum 限制）──
    _VALID_HAZARD_TYPES = {
        "unsafe_condition",
        "unsafe_action",
        "management_defect",
        "environmental",
    }
    _VALID_HAZARD_LEVELS = {"general", "serious", "major"}
    _VALID_HAZARD_CATEGORIES = {
        "equipment",
        "hazardous_storage",
        "emergency_mgmt",
        "instrument_electrical",
        "lightning_antistatic",
        "occupational_health",
        "violation_operation",
        "six_s",
        "label_signage",
        "process_mgmt",
        "contractor_defect",
        "documentation",
        "special_operation",
    }

    def _map_hazard_ai_output(
        self, script_number: int, output: dict, update_data: dict[str, Any]
    ) -> None:
        """将 AI JSON 输出映射到 HazardReport 字段（校验枚举值）。"""
        if script_number == 1:
            for json_key, db_field in [
                ("hazard_type", "hazard_type"),
                ("hazard_level", "hazard_level"),
                ("hazard_category", "hazard_category"),
                ("key_defect", "key_defect"),
                ("major_hazard_basis", "major_hazard_basis"),
            ]:
                if json_key in output and output[json_key]:
                    val = output[json_key]
                    if (
                        db_field == "hazard_type"
                        and val not in self._VALID_HAZARD_TYPES
                    ):
                        logger.debug("AI 输出非法 hazard_type=%s，跳过", val)
                        continue
                    if (
                        db_field == "hazard_level"
                        and val not in self._VALID_HAZARD_LEVELS
                    ):
                        logger.debug("AI 输出非法 hazard_level=%s，跳过", val)
                        continue
                    if (
                        db_field == "hazard_category"
                        and val not in self._VALID_HAZARD_CATEGORIES
                    ):
                        logger.debug("AI 输出非法 hazard_category=%s，跳过", val)
                        continue
                    update_data[db_field] = val

            # 插件生成的整改建议（三层结构）→ 格式化为可读中文文本
            rs = output.get("rectification_suggestion")
            if rs and isinstance(rs, dict):
                parts: list[str] = []
                if rs.get("immediate"):
                    parts.append(f"【立即措施】{rs['immediate']}")
                if rs.get("short_term"):
                    parts.append(f"【短期整改】{rs['short_term']}")
                if rs.get("long_term"):
                    parts.append(f"【长期预防】{rs['long_term']}")
                if parts:
                    update_data["corrective_preventive_measures"] = "\n\n".join(parts)
        # script 2 已废弃：整改建议由插件在 script 1 中生成


# ═══════════════════════════════════════════════════════════════
# 测试阶段：通知硬编码目标
# ═══════════════════════════════════════════════════════════════


def _bitable_field_for_level(level: int) -> str:
    """Level → 对应的多维表格审批字段名。"""
    return {1: "部门负责人复核", 2: "分管领导复核", 3: "检查人员复核"}.get(
        level, f"{level}级复核"
    )


async def _build_verify_card_content(
    hazard: HazardReport,
    level: int,
    button_state: str | None = None,
    skip_photos: bool = False,
) -> tuple[str, str, list[dict]]:
    """构建复核通知卡片内容（header + markdown + 照片 + 操作按钮）。

    Args:
        hazard: 隐患记录
        level: 复核级别 (1/2/3)
        button_state: None=活跃按钮，approved=已同意，rejected=已驳回
        skip_photos: True=跳过照片上传（卡片按钮就地更新时使用，避免超时）

    Returns:
        (title, content, elements) 三元组 — 由调用方负责发送或作为卡片更新返回
    """
    level_labels = {1: "（部门负责人）", 2: "（分管领导）", 3: "（检查人员）"}
    level_text = level_labels.get(level, f"{level}级")

    settings = get_settings()
    bitable_file_token = settings.SAFETY_FEISHU_BITABLE_APP_TOKEN
    bitable_table_id = settings.SAFETY_FEISHU_BITABLE_HAZARD_TABLE_ID
    bitable_url = (
        f"https://www.feishu.cn/base/{bitable_file_token}"
        f"?table={bitable_table_id}&record={hazard.feishu_record_id}"
        if hazard.feishu_record_id
        else ""
    )

    reply_text = hazard.rectification_reply or "-"
    level_emoji = {"general": "🟢", "serious": "🟠", "major": "🔴"}.get(
        hazard.hazard_level, "⚪"
    )
    level_label = {
        "general": "一般隐患",
        "serious": "较大隐患",
        "major": "重大隐患",
    }.get(hazard.hazard_level, hazard.hazard_level or "-")

    discovered_date = (
        hazard.discovered_at.strftime("%Y-%m-%d") if hazard.discovered_at else "-"
    )
    content = (
        f"**检查日期：** {discovered_date}\n**隐患描述：**"
        f" {hazard.description or '-'}\n**判定依据：**"
        f" {hazard.major_hazard_basis or '-'}\n**隐患级别：** {level_emoji}"
        f" {level_label}\n**责任部门：** {hazard.department or '-'}\n**整改回复：**"
        f" {reply_text}\n"
        + ("\n⬇ 请到在下方点击「同意」或「驳回」操作" if button_state is None else "")
    )

    elements: list[dict] = []

    # ── 照片（卡片就地更新时跳过上传，避免超时）──
    if not skip_photos:

        async def _upload_photos(photo_field: str | None, label: str) -> list[str]:
            if not photo_field:
                return []
            try:
                photos = json.loads(photo_field)
                if not photos or not isinstance(photos, list):
                    return []
                clean = [p for p in photos if isinstance(p, str)]
                if not clean:
                    return []
                from app.modules.safety.feishu.notification import upload_images_batch

                logger.info(
                    "复核通知照片上传: hazard_no=%s label=%s count=%d",
                    hazard.hazard_no,
                    label,
                    len(clean),
                )
                return await upload_images_batch(clean)
            except Exception:
                logger.exception(
                    "复核通知照片处理异常: hazard_no=%s label=%s",
                    hazard.hazard_no,
                    label,
                )
                return []

        defect_keys = await _upload_photos(hazard.defect_photos, "缺陷照片")
        rectification_keys = await _upload_photos(
            hazard.rectification_photos, "整改后照片"
        )
    else:
        defect_keys = []
        rectification_keys = []

    if defect_keys or rectification_keys:
        columns: list[dict] = []
        if defect_keys:
            defect_col: dict = {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "elements": [{"tag": "markdown", "content": "📷 **缺陷照片**"}],
            }
            for key in defect_keys:
                defect_col["elements"].append(
                    {
                        "tag": "img",
                        "img_key": key,
                        "alt": {"tag": "plain_text", "content": "缺陷照片"},
                    }
                )
            columns.append(defect_col)

        if rectification_keys:
            rect_col: dict = {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "elements": [{"tag": "markdown", "content": "✅ **整改后照片**"}],
            }
            for key in rectification_keys:
                rect_col["elements"].append(
                    {
                        "tag": "img",
                        "img_key": key,
                        "alt": {"tag": "plain_text", "content": "整改后照片"},
                    }
                )
            columns.append(rect_col)

        if columns:
            elements.append({"tag": "hr"})
            if len(columns) == 1:
                elements.extend(columns[0]["elements"])
            else:
                elements.append(
                    {
                        "tag": "column_set",
                        "flex_mode": "bisect",
                        "background_style": "default",
                        "columns": columns,
                    }
                )
            logger.info(
                "复核通知照片已添加: hazard_no=%s defect=%d rect=%d",
                hazard.hazard_no,
                len(defect_keys),
                len(rectification_keys),
            )

    # ── 操作按钮 ──
    if button_state is None:
        # 活跃状态：同意 + 驳回 + 查看表格
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "✅ 同意"},
                        "type": "primary",
                        "value": {
                            "action": "approve_rectification",
                            "record_id": hazard.feishu_record_id,
                            "level": level,
                        },
                        "confirm": {
                            "title": {
                                "tag": "plain_text",
                                "content": f"确认{level_text}审核通过",
                            },
                            "text": {
                                "tag": "plain_text",
                                "content": (
                                    f"将在多维表格中将「{_bitable_field_for_level(level)}」设为「已同意」"
                                ),
                            },
                        },
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "❌ 驳回"},
                        "type": "danger",
                        "value": {
                            "action": "reject_rectification",
                            "record_id": hazard.feishu_record_id,
                            "level": level,
                        },
                        "confirm": {
                            "title": {"tag": "plain_text", "content": "确认驳回整改"},
                            "text": {
                                "tag": "plain_text",
                                "content": (
                                    f"将在多维表格中将「{_bitable_field_for_level(level)}」设为「未同意」，"
                                    "隐患退回整改阶段"
                                ),
                            },
                        },
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📋 查看飞书表格记录"},
                        "type": "default",
                        "url": bitable_url,
                    },
                ],
            }
        )
    else:
        # 已处理状态：显示结果 + 查看表格
        result_text = "✅ 已同意" if button_state == "approved" else "❌ 已驳回"
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": result_text},
                        "type": "default",
                        "disabled": True,
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📋 查看飞书表格记录"},
                        "type": "default",
                        "url": bitable_url,
                    },
                ],
            }
        )

    title = (
        f"🔔 隐患复核通知{level_text}"
        if button_state is None
        else f"🔔 隐患复核通知{level_text} — 已处理"
    )
    return title, content, elements


async def _send_verify_notification(hazard: HazardReport, level: int) -> None:
    """异步发送复核通知到飞书。

    根据复核级别动态解析通知目标：
      - Level 1 → 部门负责人 (hazard.department → 部门 leader)
      - Level 2 → 分管领导   (hazard.department → 父部门 leader)
      - Level 3 → 检查人员   (hazard.discovered_by_name → open_id)

    解析失败时记录 warning 并跳过，不发送通知。
    """
    from app.core.database import async_session_factory
    from app.modules.safety.feishu.identity_resolver import IdentityResolver

    try:
        _debug_log(
            f"VERIFY_START: hazard_no={hazard.hazard_no} level={level}"
            f" dept={hazard.department}"
        )
        async with async_session_factory() as session:
            resolver = IdentityResolver(session)

            if level == 1:
                person = await resolver.resolve_hazard_department_leader(hazard)
            elif level == 2:
                person = await resolver.resolve_hazard_supervising_leader(hazard)
            elif level == 3:
                person = await resolver.resolve_discoverer(hazard)
            else:
                _debug_log(
                    f"VERIFY_FAIL: hazard_no={hazard.hazard_no}"
                    f" 未知复核级别 level={level}"
                )
                logger.warning(
                    "未知复核级别: level=%s hazard_no=%s", level, hazard.hazard_no
                )
                return

            if not person:
                _debug_log(
                    f"VERIFY_FAIL: hazard_no={hazard.hazard_no} level={level}"
                    f" 身份解析失败 dept={hazard.department}"
                )
                logger.warning(
                    "复核通知: 身份解析失败 hazard_no=%s level=%s",
                    hazard.hazard_no,
                    level,
                )
                return

            _debug_log(
                f"VERIFY_RESOLVED: hazard_no={hazard.hazard_no} level={level}"
                f" target={person.name} user_id={person.user_id}"
                f" open_id={person.open_id}"
            )

            logger.info(
                "复核通知: hazard_no=%s level=%s target=%s user_id=%s open_id=%s",
                hazard.hazard_no,
                level,
                person.name,
                person.user_id,
                person.open_id,
            )

            title, content, elements = await _build_verify_card_content(
                hazard,
                level,
                button_state=None,
            )

            # 使用 user_id 而非 open_id（open_id 是应用专属的，跨应用不通用）
            receive_id = person.user_id or person.open_id
            id_type = "user_id" if person.user_id else "open_id"

            success = await send_user_card(
                open_id=receive_id,
                title=title,
                content=content,
                elements=elements,
                id_type=id_type,
            )
            if success:
                _debug_log(
                    f"VERIFY_SENT: hazard_no={hazard.hazard_no} level={level} "
                    f"to={person.name} receive_id={receive_id} id_type={id_type}"
                )
                logger.info(
                    "复核通知已发送: hazard_no=%s level=%s to=%s receive_id=%s"
                    " id_type=%s",
                    hazard.hazard_no,
                    level,
                    person.name,
                    receive_id,
                    id_type,
                )
            else:
                _debug_log(
                    f"VERIFY_SEND_FAIL: hazard_no={hazard.hazard_no} level={level}"
                    f" to={person.name} receive_id={receive_id} id_type={id_type} —"
                    " send_user_card returned False"
                )
                logger.warning(
                    "复核通知发送失败: hazard_no=%s level=%s to=%s receive_id=%s"
                    " id_type=%s",
                    hazard.hazard_no,
                    level,
                    person.name,
                    receive_id,
                    id_type,
                )
    except Exception as e:
        _debug_log(
            f"VERIFY_EXCEPTION: hazard_no={hazard.hazard_no} level={level} error={e}"
        )
        logger.warning(
            "复核通知异常: hazard_no=%s level=%s error=%s", hazard.hazard_no, level, e
        )


async def _send_rectification_notification(hazard: HazardReport) -> None:
    """隐患登记成功后，异步通知责任人整改。

    动态解析 rectification_responsible_person_name → open_id，
    解析失败时记录 warning 并跳过。

    卡片包含隐患信息 + 缺陷照片 + 跳转多维表格填写整改回复按钮。
    """
    from app.core.database import async_session_factory
    from app.modules.safety.feishu.identity_resolver import IdentityResolver

    try:
        _debug_log(
            f"RECTIFY_START: hazard_no={hazard.hazard_no}"
            f" resp_name={hazard.rectification_responsible_person_name}"
            f" dept={hazard.department}"
        )
        async with async_session_factory() as session:
            resolver = IdentityResolver(session)
            person = await resolver.resolve_responsible_person(hazard)

            if not person:
                _debug_log(
                    f"RECTIFY_FAIL: hazard_no={hazard.hazard_no} "
                    "无法解析责任人"
                    f" name={hazard.rectification_responsible_person_name}"
                )
                logger.warning(
                    "整改通知: 无法解析责任人 hazard_no=%s name=%s",
                    hazard.hazard_no,
                    hazard.rectification_responsible_person_name,
                )
                return

            _debug_log(
                f"RECTIFY_RESOLVED: hazard_no={hazard.hazard_no} target={person.name}"
                f" user_id={person.user_id} open_id={person.open_id}"
            )

            logger.info(
                "整改通知: hazard_no=%s target=%s user_id=%s open_id=%s",
                hazard.hazard_no,
                person.name,
                person.user_id,
                person.open_id,
            )

        settings = get_settings()
        bitable_file_token = settings.SAFETY_FEISHU_BITABLE_APP_TOKEN
        bitable_table_id = settings.SAFETY_FEISHU_BITABLE_HAZARD_TABLE_ID
        bitable_url = (
            f"https://www.feishu.cn/base/{bitable_file_token}"
            f"?table={bitable_table_id}&record={hazard.feishu_record_id}"
            if hazard.feishu_record_id
            else ""
        )

        level_emoji = {
            "general": "\U0001f7e2",
            "serious": "\U0001f7e0",
            "major": "\U0001f534",
        }.get(hazard.hazard_level, "⚪")
        level_label = {
            "general": "一般隐患",
            "serious": "较大隐患",
            "major": "重大隐患",
        }.get(hazard.hazard_level, hazard.hazard_level or "-")
        responsible = hazard.rectification_responsible_person_name or "-"
        deadline = hazard.deadline.strftime("%Y-%m-%d") if hazard.deadline else "待指定"

        discovered_date = (
            hazard.discovered_at.strftime("%Y-%m-%d") if hazard.discovered_at else "-"
        )
        content = (
            f"**检查日期：** {discovered_date}\n**隐患描述：**"
            f" {hazard.description or '-'}\n**判定依据：**"
            f" {hazard.major_hazard_basis or '-'}\n**隐患级别：** {level_emoji}"
            f" {level_label}\n**责任部门：** {hazard.department or '-'}\n**责任人员：**"
            f" {responsible}\n**整改期限：** {deadline}\n\n⬇"
            " 请在多维表格中填写「纠正预防措施」并上传整改照片，该记录可转发"
        )

        elements: list[dict] = []

        # ── 缺陷照片 ──
        if hazard.defect_photos:
            try:
                photos = json.loads(hazard.defect_photos)
                if photos and isinstance(photos, list):
                    clean = [p for p in photos if isinstance(p, str)]
                    if clean:
                        from app.modules.safety.feishu.notification import (
                            upload_images_batch,
                        )

                        image_keys = await upload_images_batch(clean)
                        if image_keys:
                            elements.append({"tag": "hr"})
                            elements.append(
                                {
                                    "tag": "markdown",
                                    "content": "\U0001f4f7 **缺陷照片**",
                                }
                            )
                            for key in image_keys:
                                elements.append(
                                    {
                                        "tag": "img",
                                        "img_key": key,
                                        "alt": {
                                            "tag": "plain_text",
                                            "content": "缺陷照片",
                                        },
                                    }
                                )
            except Exception:
                logger.exception("整改通知照片处理异常: hazard_no=%s", hazard.hazard_no)

        # ── 操作按钮 ──
        button_actions: list[dict] = []
        if bitable_url:
            button_actions.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "\U0001f4cb 填写整改回复"},
                    "type": "primary",
                    "url": bitable_url,
                }
            )
        elements.append(
            {
                "tag": "action",
                "actions": button_actions,
            }
        )

        # 使用 user_id 而非 open_id，因为 open_id 是应用专属的 —
        # identity.users 的 open_id 来自主应用，而 send_user_card 使用安全应用 token，
        # 两个应用的 open_id 命名空间不同。user_id 在同一租户内一致。
        receive_id = person.user_id or person.open_id
        id_type = "user_id" if person.user_id else "open_id"

        success = await send_user_card(
            open_id=receive_id,
            title="\U0001f514 隐患整改通知",
            content=content,
            elements=elements,
            id_type=id_type,
        )
        if success:
            _debug_log(
                f"RECTIFY_SENT: hazard_no={hazard.hazard_no} "
                f"to={person.name} receive_id={receive_id} id_type={id_type}"
            )
            logger.info(
                "整改通知已发送: hazard_no=%s to=%s receive_id=%s id_type=%s",
                hazard.hazard_no,
                person.name,
                receive_id,
                id_type,
            )
        else:
            _debug_log(
                f"RECTIFY_SEND_FAIL: hazard_no={hazard.hazard_no} "
                f"to={person.name} receive_id={receive_id} id_type={id_type}"
            )
            logger.warning(
                "整改通知发送失败: hazard_no=%s to=%s receive_id=%s id_type=%s",
                hazard.hazard_no,
                person.name,
                receive_id,
                id_type,
            )
    except Exception as e:
        _debug_log(f"RECTIFY_EXCEPTION: hazard_no={hazard.hazard_no} error={e}")
        logger.warning("整改通知异常: error=%s hazard_no=%s", e, hazard.hazard_no)


class SafetyService(_SafetyCoreService):
    """Complete safety service including the split CRUD workflows."""

    # ==================== Accident Operations ====================

    async def get_accidents(
        self,
        skip: int = 0,
        limit: int = 20,
        status: str | None = None,
        accident_type: str | None = None,
        accident_level: str | None = None,
        department: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        keyword: str | None = None,
    ) -> tuple[list[Accident], int]:
        """获取事故列表"""
        return await self.repo.get_accidents(
            skip,
            limit,
            status,
            accident_type,
            accident_level,
            department,
            date_from,
            date_to,
            keyword,
        )

    async def get_accident(self, accident_id: uuid.UUID) -> Accident | None:
        """获取事故详情"""
        return await self.repo.get_accident_by_id(accident_id)

    async def create_accident(self, data: AccidentCreate) -> Accident:
        """创建事故"""
        accident_data = data.model_dump()
        item = await self.repo.create_accident(accident_data)
        await self._audit("create", "accident", resource_id=item.id)
        return item

    async def update_accident(
        self, accident_id: uuid.UUID, data: AccidentUpdate
    ) -> Accident | None:
        """更新事故"""
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        item = await self.repo.update_accident(accident_id, update_data)
        if item:
            await self._audit("update", "accident", resource_id=accident_id)
        return item

    async def investigate_accident(
        self,
        accident_id: uuid.UUID,
        investigator: uuid.UUID,
        investigator_name: str,
    ) -> Accident | None:
        """开始调查事故"""
        accident = await self.repo.get_accident_by_id(accident_id)
        if not accident or accident.status != "reported":
            return None
        return await self.repo.update_accident(
            accident_id,
            {
                "status": "investigating",
                "investigator": investigator,
                "investigator_name": investigator_name,
            },
        )

    async def resolve_accident(
        self,
        accident_id: uuid.UUID,
        direct_cause: str,
        root_cause: str,
        handling_measures: str,
        corrective_actions: str | None = None,
        investigation_findings: str | None = None,
        investigation_method: str | None = None,
        investigation_team: list | None = None,
    ) -> Accident | None:
        """完成调查事故"""
        accident = await self.repo.get_accident_by_id(accident_id)
        if not accident or accident.status != "investigating":
            return None
        update_data: dict[str, Any] = {
            "status": "investigated",
            "direct_cause": direct_cause,
            "root_cause": root_cause,
            "handling_measures": handling_measures,
            "corrective_actions": corrective_actions,
            "investigation_findings": investigation_findings,
            "investigation_method": investigation_method,
        }
        if investigation_team is not None:
            update_data["investigation_team"] = investigation_team
        return await self.repo.update_accident(accident_id, update_data)

    async def start_capa(
        self,
        accident_id: uuid.UUID,
        corrective_action_deadline: datetime,
        corrective_action_responsible: str,
    ) -> Accident | None:
        """启动 CAPA"""
        accident = await self.repo.get_accident_by_id(accident_id)
        if not accident or accident.status != "investigated":
            return None
        return await self.repo.update_accident(
            accident_id,
            {
                "status": "capa_in_progress",
                "corrective_action_deadline": corrective_action_deadline,
                "corrective_action_responsible": corrective_action_responsible,
                "corrective_action_status": "in_progress",
            },
        )

    async def verify_capa(
        self,
        accident_id: uuid.UUID,
        verified_by: uuid.UUID,
        verified_by_name: str,
    ) -> Accident | None:
        """验证 CAPA 并关闭事故"""
        accident = await self.repo.get_accident_by_id(accident_id)
        if not accident or accident.status != "capa_in_progress":
            return None
        return await self.repo.update_accident(
            accident_id,
            {
                "status": "closed",
                "corrective_action_status": "verified",
                "verified_by": verified_by,
                "verified_by_name": verified_by_name,
                "verified_at": datetime.now(),
            },
        )

    async def close_accident(self, accident_id: uuid.UUID) -> Accident | None:
        """直接关闭事故（无CAPA时）"""
        accident = await self.repo.get_accident_by_id(accident_id)
        if not accident or accident.status != "investigated":
            return None
        return await self.repo.update_accident(accident_id, {"status": "closed"})

    async def delete_accident(self, accident_id: uuid.UUID) -> bool:
        """删除事故"""
        result = await self.repo.delete_accident(accident_id)
        if result:
            await self._audit("delete", "accident", resource_id=accident_id)
        return result

    # ==================== Contractor Operations ====================

    async def get_contractors(
        self,
        skip: int = 0,
        limit: int = 20,
        status: str | None = None,
        qualification_type: str | None = None,
        training_status: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[Contractor], int]:
        """获取承包商列表"""
        return await self.repo.get_contractors(
            skip,
            limit,
            status,
            qualification_type,
            training_status,
            keyword,
        )

    async def get_contractor(self, contractor_id: uuid.UUID) -> Contractor | None:
        """获取承包商详情"""
        return await self.repo.get_contractor_by_id(contractor_id)

    async def create_contractor(self, data: "ContractorCreate") -> Contractor:
        """创建承包商"""
        contractor_data = data.model_dump()
        item = await self.repo.create_contractor(contractor_data)
        await self._audit("create", "contractor", resource_id=item.id)
        return item

    async def update_contractor(
        self, contractor_id: uuid.UUID, data: "ContractorUpdate"
    ) -> Contractor | None:
        """更新承包商"""
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        item = await self.repo.update_contractor(contractor_id, update_data)
        if item:
            await self._audit("update", "contractor", resource_id=contractor_id)
        return item

    async def blacklist_contractor(self, contractor_id: uuid.UUID) -> Contractor | None:
        """将承包商加入黑名单"""
        contractor = await self.repo.get_contractor_by_id(contractor_id)
        if not contractor:
            return None
        return await self.repo.update_contractor(
            contractor_id, {"status": "blacklisted", "blacklisted": True}
        )

    async def activate_contractor(self, contractor_id: uuid.UUID) -> Contractor | None:
        """激活承包商"""
        contractor = await self.repo.get_contractor_by_id(contractor_id)
        if not contractor:
            return None
        return await self.repo.update_contractor(
            contractor_id, {"status": "active", "blacklisted": False}
        )

    async def update_contractor_training(
        self, contractor_id: uuid.UUID, training_status: str
    ) -> Contractor | None:
        """更新承包商培训状态"""
        contractor = await self.repo.get_contractor_by_id(contractor_id)
        if not contractor:
            return None
        return await self.repo.update_contractor(
            contractor_id,
            {
                "training_status": training_status,
                "training_date": datetime.now(),
            },
        )

    async def delete_contractor(self, contractor_id: uuid.UUID) -> bool:
        """删除承包商"""
        result = await self.repo.delete_contractor(contractor_id)
        if result:
            await self._audit("delete", "contractor", resource_id=contractor_id)
        return result

    # ── 施工记录 ──

    async def get_work_records(
        self, contractor_id: uuid.UUID
    ) -> list[ContractorWorkRecord]:
        """获取承包商的施工记录"""
        return await self.repo.get_work_records_by_contractor(contractor_id)

    async def create_work_record(
        self, contractor_id: uuid.UUID, data: "ContractorWorkRecordCreate"
    ) -> ContractorWorkRecord:
        """创建施工记录"""
        record_data = data.model_dump()
        record_data["contractor_id"] = str(contractor_id)
        return await self.repo.create_work_record(record_data)

    async def update_work_record(
        self, record_id: uuid.UUID, data: "ContractorWorkRecordUpdate"
    ) -> ContractorWorkRecord | None:
        """更新施工记录"""
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        return await self.repo.update_work_record(record_id, update_data)

    async def evaluate_work_record(
        self,
        record_id: uuid.UUID,
        score: int,
        comments: str | None = None,
        evaluator: str | None = None,
    ) -> ContractorWorkRecord | None:
        """评价施工记录"""
        record = await self.repo.get_work_record_by_id(record_id)
        if not record:
            return None
        return await self.repo.update_work_record(
            record_id,
            {
                "status": "evaluated",
                "evaluation": {
                    "score": score,
                    "comments": comments,
                    "evaluator": evaluator,
                    "date": datetime.now().isoformat(),
                },
            },
        )

    async def delete_work_record(self, record_id: uuid.UUID) -> bool:
        """删除施工记录"""
        return await self.repo.delete_work_record(record_id)

    # ==================== SafetyTraining Operations ====================

    async def get_trainings(
        self,
        skip: int = 0,
        limit: int = 20,
        status: str | None = None,
        training_type: str | None = None,
        department: str | None = None,
    ) -> tuple[list[SafetyTraining], int]:
        """获取安全培训列表"""
        return await self.repo.get_trainings(
            skip, limit, status, training_type, department
        )

    async def get_training(self, training_id: uuid.UUID) -> SafetyTraining | None:
        """获取安全培训详情"""
        return await self.repo.get_training_by_id(training_id)

    async def create_training(self, data: SafetyTrainingCreate) -> SafetyTraining:
        """创建安全培训"""
        training_data = data.model_dump()
        item = await self.repo.create_training(training_data)
        await self._audit("create", "safety_training", resource_id=item.id)
        return item

    async def update_training(
        self, training_id: uuid.UUID, data: SafetyTrainingUpdate
    ) -> SafetyTraining | None:
        """更新安全培训"""
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        item = await self.repo.update_training(training_id, update_data)
        if item:
            await self._audit("update", "safety_training", resource_id=training_id)
        return item

    async def start_training(self, training_id: uuid.UUID) -> SafetyTraining | None:
        """开始培训（草稿→进行中）"""
        training = await self.repo.get_training_by_id(training_id)
        if not training or training.status != "draft":
            return None
        return await self.repo.update_training(training_id, {"status": "in_progress"})

    async def complete_training(self, training_id: uuid.UUID) -> SafetyTraining | None:
        """完成培训"""
        training = await self.repo.get_training_by_id(training_id)
        if not training or training.status != "in_progress":
            return None
        return await self.repo.update_training(training_id, {"status": "completed"})

    async def archive_training(self, training_id: uuid.UUID) -> SafetyTraining | None:
        """归档培训"""
        training = await self.repo.get_training_by_id(training_id)
        if not training or training.status != "completed":
            return None
        return await self.repo.update_training(training_id, {"status": "archived"})

    async def delete_training(self, training_id: uuid.UUID) -> bool:
        """删除安全培训"""
        result = await self.repo.delete_training(training_id)
        if result:
            await self._audit("delete", "safety_training", resource_id=training_id)
        return result

    # ==================== TrainingRecord Operations ====================

    async def get_training_records(
        self, training_id: uuid.UUID
    ) -> list[TrainingRecord]:
        """获取培训记录列表"""
        return await self.repo.get_records_by_training(training_id)

    async def create_training_record(
        self, data: TrainingRecordCreate
    ) -> TrainingRecord:
        """创建培训记录"""
        record_data = data.model_dump()
        return await self.repo.create_training_record(record_data)

    async def update_training_record(
        self, record_id: uuid.UUID, data: TrainingRecordUpdate
    ) -> TrainingRecord | None:
        """更新培训记录"""
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        return await self.repo.update_training_record(record_id, update_data)

    async def batch_create_records(
        self, training_id: uuid.UUID, records: list[TrainingRecordCreate]
    ) -> list[TrainingRecord]:
        """批量创建培训签到记录"""
        result = []
        for record in records:
            record_data = record.model_dump()
            record_data["training_id"] = training_id
            item = await self.repo.create_training_record(record_data)
            result.append(item)
        return result

    async def delete_training_record(self, record_id: uuid.UUID) -> bool:
        """删除培训记录"""
        return await self.repo.delete_training_record(record_id)

    # ── 培训证书 ──

    async def get_training_certificates(
        self,
        skip: int = 0,
        limit: int = 20,
        certificate_status: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[TrainingRecord], int]:
        """获取培训证书列表"""
        return await self.repo.get_training_certificates(
            skip,
            limit,
            certificate_status,
            keyword,
        )

    async def get_expiring_certificates(self) -> list[TrainingRecord]:
        """获取即将过期的证书（30天内）"""
        return await self.repo.get_expiring_certificates()

    # ==================== HazardIdentification Operations ====================

    async def get_hazard_identifications(
        self,
        skip: int = 0,
        limit: int = 20,
        department: str | None = None,
        overall_status: str | None = None,
        ai_node_progress: str | None = None,
        keyword: str | None = None,
        position: str | None = None,
        risk_level: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> tuple[list, int]:
        """获取危险源辨识列表"""
        return await self.repo.get_hazard_identifications(
            skip,
            limit,
            department,
            overall_status,
            ai_node_progress,
            keyword,
            position,
            risk_level,
            date_from,
            date_to,
        )

    async def get_hazard_identification_stats(self) -> dict[str, int]:
        """获取危险源辨识工作流统计"""
        return await self.repo.get_hazard_identification_stats()

    async def get_hazard_identification_ledger_stats(
        self,
        department: str | None = None,
        position: str | None = None,
        risk_level: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, int]:
        """获取危险源辨识台账统计"""
        return await self.repo.get_hazard_identification_ledger_stats(
            department,
            position,
            risk_level,
            date_from,
            date_to,
        )

    async def get_hazard_identification(self, hid: uuid.UUID):
        """获取危险源辨识详情"""
        return await self.repo.get_hazard_identification_by_id(hid)

    async def create_hazard_identification(self, data) -> Any:
        """创建危险源辨识记录"""

        create_data = data.model_dump()
        create_data["ai_node_progress"] = "pending_input"
        create_data["overall_status"] = "draft"
        item = await self.repo.create_hazard_identification(create_data)
        await self._audit("create", "hazard_identification", resource_id=item.id)
        return item

    async def update_hazard_identification(self, hid: uuid.UUID, data) -> Any | None:
        """更新危险源辨识"""
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        item = await self.repo.update_hazard_identification(hid, update_data)
        if item:
            await self._audit("update", "hazard_identification", resource_id=hid)
        return item

    async def delete_hazard_identification(self, hid: uuid.UUID) -> bool:
        """删除危险源辨识"""
        result = await self.repo.delete_hazard_identification(hid)
        if result:
            await self._audit("delete", "hazard_identification", resource_id=hid)
        return result

    async def submit_hazard_identification(self, hid: uuid.UUID) -> Any | None:
        """提交基础信息 → 进入脚本1（待AI解析附件）"""
        item = await self.repo.get_hazard_identification_by_id(hid)
        if not item or item.overall_status not in ("draft",):
            return None
        return await self.repo.update_hazard_identification(
            hid,
            {"ai_node_progress": "pending_script1", "overall_status": "in_progress"},
        )

    # ── 工作流状态机 ──

    SCRIPT_NODE_MAP = {
        1: ("pending_script1", "pending_script2", "script1_review_status"),
        2: ("pending_script2", "pending_script3", "script2_review_status"),
        3: ("pending_script3", "pending_script4", "script3_review_status"),
        4: ("pending_script4", "pending_script5", "script4_review_status"),
        5: ("pending_script5", "pending_script6", "script5_review_status"),
        6: ("pending_script6", "pending_script7", "script6_review_status"),
        7: ("pending_script7", "completed", "script7_review_status"),
    }

    # ── AI 集成 ──

    def _build_context(self, script_number: int, item: Any) -> str:
        """从当前记录构建供 AI 使用的上下文字符串"""
        parts: list[str] = [
            f"部门：{item.department or '未知'}",
            f"岗位：{item.position or '未知'}",
            f"生产步骤：{item.production_step or '未知'}",
        ]

        # Script 1 基础字段
        if script_number >= 1:
            if item.specific_activity:
                parts.append(f"具体作业活动：{item.specific_activity}")
            if item.equipment_facilities:
                parts.append(f"设备设施：{item.equipment_facilities}")
            if item.raw_auxiliary_materials:
                parts.append(f"原辅料：{item.raw_auxiliary_materials}")
            if item.operation_frequency:
                parts.append(f"作业频次：{item.operation_frequency}")
            if item.operator_count is not None:
                parts.append(f"操作人数：{item.operator_count}")

        # Script 2 输出
        if script_number >= 3:
            if item.hazard_type:
                parts.append(f"危险类型：{item.hazard_type}")
            if item.possible_accident:
                parts.append(f"可能导致事故：{item.possible_accident}")
            if item.unsafe_behavior:
                parts.append(f"不规范作业行为表现：{item.unsafe_behavior}")

        # Script 3 输出
        if script_number >= 4:
            if item.l_inherent is not None:
                parts.append(f"可能性 L（固有）：{item.l_inherent}")
            if item.e_inherent is not None:
                parts.append(f"暴露频率 E（固有）：{item.e_inherent}")
            if item.c_inherent is not None:
                parts.append(f"严重性 C（固有）：{item.c_inherent}")
            if item.d_inherent is not None:
                parts.append(f"风险值 D（固有）：{item.d_inherent}")
            if item.inherent_risk_label:
                parts.append(f"固有风险等级：{item.inherent_risk_label}")

        # Script 4 输出
        if script_number >= 5:
            if item.existing_engineering_controls:
                parts.append(f"现有工程控制措施：{item.existing_engineering_controls}")
            if item.existing_management_controls:
                parts.append(f"现有管理控制措施：{item.existing_management_controls}")
            if item.existing_ppe:
                parts.append(f"现有个人防护措施：{item.existing_ppe}")
            if item.existing_emergency_measures:
                parts.append(f"现有应急措施：{item.existing_emergency_measures}")

        # Script 5 输出
        if script_number >= 6:
            if item.l_residual is not None:
                parts.append(f"可能性 L（残余）：{item.l_residual}")
            if item.e_residual is not None:
                parts.append(f"暴露频率 E（残余）：{item.e_residual}")
            if item.c_residual is not None:
                parts.append(f"严重性 C（残余）：{item.c_residual}")
            if item.d_residual is not None:
                parts.append(f"风险值 D（残余）：{item.d_residual}")
            if item.residual_risk_label:
                parts.append(f"残余风险等级：{item.residual_risk_label}")
            if item.control_level:
                parts.append(f"管控等级：{item.control_level}")

        # Script 6 输出
        if script_number >= 7:
            if item.recommendation_content:
                parts.append(f"建议措施内容：{item.recommendation_content}")
            if item.recommendation_type:
                parts.append(f"建议措施类型：{item.recommendation_type}")

        return "\n".join(parts)

    async def _generate_ai_output(self, script_number: int, item: Any) -> dict:
        """调用 AI 服务生成工作流输出。失败时抛出 AIOutputError。

        优先从数据库 ai_workflow_configs 表读取对应模块的工作流配置，
        fallback 到 prompts.py 的硬编码 WORKFLOW_STEP_CONFIG。
        """
        # 优先从数据库读取工作流配置
        workflow_config = await self.repo.get_ai_workflow_config_by_module(
            "hazard-identification"
        )
        if (
            workflow_config
            and workflow_config.is_enabled
            and workflow_config.script_configs
        ):
            raw = workflow_config.script_configs
            if isinstance(raw, list):
                scripts = raw
            elif isinstance(raw, dict):
                scripts = raw.get("scripts", [])
            else:
                scripts = []
            db_script = next(
                (s for s in scripts if s.get("script_number") == script_number), None
            )
            if db_script and db_script.get("is_enabled", True):
                prompt_template = build_prompt(db_script)
                expected_keys = db_script.get("expected_keys", [])
                logger.debug(
                    "使用数据库工作流配置: 步骤%d - %s",
                    script_number,
                    db_script.get("name"),
                )
            else:
                # DB 中有 workflow 但没有对应步骤 → fallback
                config = SCRIPT_CONFIG[script_number]
                prompt_template = build_prompt(config)
                expected_keys = config["expected_keys"]
                logger.debug(
                    "数据库工作流配置中未找到步骤 %d，fallback 到硬编码", script_number
                )
        else:
            # DB 无配置 → fallback 到硬编码
            config = SCRIPT_CONFIG[script_number]
            prompt_template = build_prompt(config)
            expected_keys = config["expected_keys"]
            logger.debug("无数据库工作流配置，使用硬编码步骤 %d", script_number)

        context_text = self._build_context(script_number, item)

        # Script 1 特殊处理：解析附件
        if script_number == 1:
            attachment_text = ""
            if item.attachment_path:
                try:
                    attachment_text = DocumentParser.extract_text(
                        item.attachment_path, max_chars=30000
                    )
                except Exception as e:
                    logger.warning(f"附件解析失败: {e}")
            if attachment_text:
                context_text += f"\n\n### 附件文档内容\n{attachment_text}"
            else:
                context_text += "\n\n### 附件文档内容\n（未上传附件或附件无法解析）"

        # 使用 replace 而非 format()，避免 AI 输出示例中的花括号被误解析
        if "{context}" in prompt_template:
            prompt = prompt_template.replace("{context}", context_text)
        else:
            prompt = f"## 上下文信息\n{context_text}\n\n{prompt_template}"
        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个专业的危险源辨识与风险评价专家助手，服务于原料药生产企业。"
                ),
            },
            {"role": "user", "content": prompt},
        ]
        try:
            result = await llm_client.chat_json(
                messages=messages,
                expected_keys=expected_keys,
            )
            return result
        except Exception as e:
            logger.error(f"AI 调用失败: {e}")
            raise

    async def run_script(
        self, hid: uuid.UUID, script_number: int, ai_output: dict | None = None
    ) -> Any | None:
        """执行AI脚本（状态机推进）"""

        item = await self.repo.get_hazard_identification_by_id(hid)
        if not item:
            return None

        if script_number not in self.SCRIPT_NODE_MAP:
            return None

        current_node, next_node, review_field = self.SCRIPT_NODE_MAP[script_number]

        # Check current state allows this script
        if item.ai_node_progress != current_node:
            return None

        # Check previous script's review status is approved (for scripts 2-7)
        if script_number > 1:
            prev_review = getattr(item, f"script{script_number - 1}_review_status")
            if prev_review != "approved":
                return None

        update_data: dict[str, Any] = {}

        # ── AI 生成或使用传入数据 ──
        if ai_output is not None:
            # 人工覆盖 / 前端 demo 数据
            self._map_ai_output(script_number, ai_output, update_data)
            self._calculate_risk_levels(script_number, update_data)
            update_data["ai_node_progress"] = next_node
            update_data["ai_error_message"] = None
        else:
            # 调用真实 AI
            try:
                generated = await self._generate_ai_output(script_number, item)
                self._map_ai_output(script_number, generated, update_data)
                self._calculate_risk_levels(script_number, update_data)
                update_data["ai_node_progress"] = next_node
                update_data["ai_error_message"] = None
            except LLMOutputError as e:
                logger.error(f"Script {script_number} AI 输出错误: {e}")
                update_data[f"script{script_number}_review_status"] = "rejected"
                update_data["ai_error_message"] = str(e)
            except Exception as e:
                logger.error(f"Script {script_number} 执行异常: {e}")
                update_data[f"script{script_number}_review_status"] = "rejected"
                update_data["ai_error_message"] = f"AI 服务调用失败：{e}"

        result = await self.repo.update_hazard_identification(hid, update_data)
        return result

    async def review_script(
        self, hid: uuid.UUID, script_number: int, action: str
    ) -> Any | None:
        """审核确认或驳回脚本输出"""
        item = await self.repo.get_hazard_identification_by_id(hid)
        if not item:
            return None

        if script_number not in self.SCRIPT_NODE_MAP:
            return None

        current_node, next_node, review_field = self.SCRIPT_NODE_MAP[script_number]

        # Current node must match

        update_data: dict[str, Any] = {
            f"script{script_number}_review_status": action,
        }

        if action == "approved":
            update_data["ai_node_progress"] = next_node

        # 当完成脚本7审核 → overall_status = completed
        if action == "approved" and script_number == 7:
            update_data["overall_status"] = "completed"
        elif action == "rejected":
            # 驳回：回退到之前节点，允许重新生成
            update_data["ai_node_progress"] = current_node

        result = await self.repo.update_hazard_identification(hid, update_data)
        return result

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        """将 AI 输出值转为 float；若为'待人工确认'等非数值字符串则返回 None"""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == "待人工确认":
                return None
            try:
                return float(stripped)
            except ValueError:
                return None
        return None

    def _map_ai_output(
        self, script_number: int, ai_output: dict, update_data: dict[str, Any]
    ) -> None:
        """将 AI 输出映射到模型字段。

        - 脚本1：仅输出 3 个字段（标准文件规定）
        - 脚本3/5/7：AI 同时输出 L/E/C/D 值和风险等级；若为"待人工确认"则存 None
        - 脚本6：needs_recommendation 为字符串三态（是/否/待人工确认）
        """
        if script_number == 1:
            for f in (
                "specific_activity",
                "equipment_facilities",
                "raw_auxiliary_materials",
            ):
                if f in ai_output:
                    update_data[f] = ai_output[f]

        elif script_number == 2:
            for f in ("hazard_type", "possible_accident", "unsafe_behavior"):
                if f in ai_output:
                    update_data[f] = ai_output[f]

        elif script_number == 3:
            for f in ("l_inherent", "e_inherent", "c_inherent"):
                if f in ai_output:
                    update_data[f] = self._safe_float(ai_output[f])
            # AI 直接输出 D 值和风险等级
            if "d_inherent" in ai_output:
                update_data["d_inherent"] = self._safe_float(ai_output["d_inherent"])
            if "inherent_risk_level" in ai_output:
                update_data["inherent_risk_level"] = ai_output["inherent_risk_level"]

        elif script_number == 4:
            for f in (
                "existing_engineering_controls",
                "existing_management_controls",
                "existing_ppe",
                "existing_emergency_measures",
            ):
                if f in ai_output:
                    update_data[f] = ai_output[f]

        elif script_number == 5:
            for f in ("l_residual", "e_residual", "c_residual"):
                if f in ai_output:
                    update_data[f] = self._safe_float(ai_output[f])
            if "d_residual" in ai_output:
                update_data["d_residual"] = self._safe_float(ai_output["d_residual"])
            if "residual_risk_level" in ai_output:
                update_data["residual_risk_level"] = ai_output["residual_risk_level"]

        elif script_number == 6:
            for f in (
                "needs_recommendation",
                "recommendation_type",
                "recommendation_content",
                "recommendation_priority",
            ):
                if f in ai_output:
                    update_data[f] = ai_output[f]

        elif script_number == 7:
            for f in ("l_post", "e_post", "c_post"):
                if f in ai_output:
                    update_data[f] = self._safe_float(ai_output[f])
            if "d_post" in ai_output:
                update_data["d_post"] = self._safe_float(ai_output["d_post"])
            if "post_risk_level" in ai_output:
                update_data["post_risk_level"] = ai_output["post_risk_level"]

    def _calculate_risk_levels(
        self, script_number: int, update_data: dict[str, Any]
    ) -> None:
        """补全风险等级和管控信息。

        AI 在脚本3/5/7中直接输出 D 值和风险等级；此处仅在后端可计算且 AI
        未提供对应字段时做兜底计算，同时补充 label、control_level 等展示字段。
        """
        from app.modules.safety.schemas import RISK_LEVELS, get_risk_level

        if script_number == 3:
            likelihood = update_data.get("l_inherent")
            e = update_data.get("e_inherent")
            c = update_data.get("c_inherent")
            if all(v is not None for v in (likelihood, e, c)):
                # D 值：优先用 AI 输出，否则后端计算
                if update_data.get("d_inherent") is None:
                    update_data["d_inherent"] = likelihood * e * c
                # 风险等级 key：优先用 AI 输出
                if update_data.get("inherent_risk_level") is None:
                    level = get_risk_level(update_data["d_inherent"])
                    update_data["inherent_risk_level"] = level["key"]
                # 补充 label / control_level / responsible_person（后端计算）
                for rl in RISK_LEVELS:
                    if rl["key"] == update_data.get("inherent_risk_level"):
                        update_data["inherent_risk_label"] = rl["label"]
                        update_data["control_level"] = rl["control_level"]
                        update_data["responsible_person"] = rl["responsible_person"]
                        break

        elif script_number == 5:
            likelihood = update_data.get("l_residual")
            e = update_data.get("e_residual")
            c = update_data.get("c_residual")
            if all(v is not None for v in (likelihood, e, c)):
                if update_data.get("d_residual") is None:
                    update_data["d_residual"] = likelihood * e * c
                if update_data.get("residual_risk_level") is None:
                    level = get_risk_level(update_data["d_residual"])
                    update_data["residual_risk_level"] = level["key"]
                for rl in RISK_LEVELS:
                    if rl["key"] == update_data.get("residual_risk_level"):
                        update_data["residual_risk_label"] = rl["label"]
                        break

        elif script_number == 7:
            likelihood = update_data.get("l_post")
            e = update_data.get("e_post")
            c = update_data.get("c_post")
            if all(v is not None for v in (likelihood, e, c)):
                if update_data.get("d_post") is None:
                    update_data["d_post"] = likelihood * e * c
                if update_data.get("post_risk_level") is None:
                    level = get_risk_level(update_data["post_risk_level"])
                    update_data["post_risk_level"] = level["key"]
                for rl in RISK_LEVELS:
                    if rl["key"] == update_data.get("post_risk_level"):
                        update_data["post_risk_label"] = rl["label"]
                        break

    # ==================== 附件上传 ====================

    async def upload_attachment(
        self, hid: uuid.UUID, file_name: str, file_path: str
    ) -> Any | None:
        """保存附件路径到记录"""
        return await self.repo.update_hazard_identification(
            hid,
            {
                "attachment_path": file_path,
                "attachment_original_name": file_name,
            },
        )

    # ── AI 导出 ──

    async def parse_hazard_export_query(self, natural_query: str) -> dict:
        """使用 AI 将自然语言筛选条件解析为结构化参数。

        支持的自然语言示例：
        - 「导出所有重大危险源」
        - 「原料药车间上月的记录」
        - 「合成岗位最近三个月一级和二级风险」
        """
        system_prompt = (
            "你是一个数据库查询助手，负责将用户的中文自然语言查询 "
            "转换为危险源辨识台账的结构化筛选条件。\n\n"
            "可用字段：\n"
            "- department: 部门名称（如「原料药车间」「生产部」）\n"
            "- position: 岗位名称（如「操作工」「合成岗位」）\n"
            "- risk_level: 风险等级（level_1/level_2/level_3/level_4）\n"
            "- date_from / date_to: 日期范围 YYYY-MM-DD\n"
            "- keyword: 关键词搜索（编号/部门/岗位/作业活动）\n\n"
            "只返回 JSON，不要任何其他文字。没有匹配的字段不返回。\n"
            '示例输出: {"department":"原料药车间","risk_level":"level_1"}'
        )
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": natural_query},
            ]
            response_text = await llm_client.chat(
                messages, response_format="json_object"
            )
            import json

            result = json.loads(response_text)
            return {k: v for k, v in result.items() if v is not None}
        except Exception as e:
            logger.warning("AI 自然语言解析失败(hazard-identification): %s", e)
            return {
                "explanation": f"AI 解析失败，将使用原始查询: {natural_query}",
                "keyword": natural_query,
            }

    async def export_hazard_ledger_pdf(
        self,
        natural_query: str | None = None,
        department: str | None = None,
        position: str | None = None,
        risk_level: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        keyword: str | None = None,
    ) -> bytes:
        """导出危险源辨识台账为 PDF。

        流程：
        1. AI 解析自然语言 → 筛选条件（如「导出所有重大危险源」）
        2. 按条件查询数据库
        3. Excel 标准化输出插件填表 → LibreOffice 转 PDF
        4. 回退：reportlab 固定模板
        """
        # 第一阶段：AI 解析自然语言 → 筛选条件
        if natural_query:
            parsed = await self.parse_hazard_export_query(natural_query)
            department = department or parsed.get("department")
            position = position or parsed.get("position")
            risk_level = risk_level or parsed.get("risk_level")
            date_from = date_from or parsed.get("date_from")
            date_to = date_to or parsed.get("date_to")
            keyword = keyword or parsed.get("keyword")

        # 第二阶段：按条件查询数据
        items, _ = await self.repo.get_hazard_identifications(
            skip=0,
            limit=10000,
            department=department,
            overall_status="completed",
            position=position,
            risk_level=risk_level,
            date_from=date_from,
            date_to=date_to,
            keyword=keyword,
        )

        filters = {
            k: v
            for k, v in {
                "department": department,
                "position": position,
                "risk_level": risk_level,
                "date_from": date_from,
                "date_to": date_to,
                "keyword": keyword,
            }.items()
            if v is not None
        }

        # ── 策略 1：Excel 标准化输出（最高优先级）──
        try:
            pdf_bytes = self._export_via_template_plugin(items, filters)
            if pdf_bytes and len(pdf_bytes) > 5000:
                logger.info(
                    "Excel标准化输出导出成功: %d records, %d bytes",
                    len(items),
                    len(pdf_bytes),
                )
                return pdf_bytes
        except Exception as exc:
            logger.warning("Excel标准化输出导出失败: %s，回退到固定模板", exc)

        # ── 回退：reportlab 固定模板 ──
        logger.debug("使用 reportlab 固定模板生成 PDF")
        return await self._export_hazard_ledger_pdf_fallback(items, filters)

    def _export_via_template_plugin(self, items, filters: dict) -> bytes:
        """使用 Excel 标准化输出插件填充模板并导出 PDF。

        流程：ORM 对象 → dict 列表 → openpyxl 填表 → LibreOffice → PDF bytes
        不依赖 AI，格式 100% 复刻 Excel 模板。
        """
        import tempfile
        from pathlib import Path

        from app.modules.safety.template_export import (
            HAZARD_TEMPLATE_CONFIG,
            ExcelTemplateFiller,
            ExcelToPdfConverter,
        )

        # ORM → dict
        data = [self._item_to_dict(item) for item in items]

        # 模板位置
        template_dir = Path(__file__).resolve().parent.parent / "templates"
        template_path = template_dir / "危险源辨识管控清单模板.xlsx"
        if not template_path.exists():
            raise FileNotFoundError(f"模板文件不存在: {template_path}")

        # 临时文件 → PDF bytes
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            xlsx_path = tmp / "hazard_ledger.xlsx"
            pdf_path = tmp / "hazard_ledger.pdf"

            filler = ExcelTemplateFiller(HAZARD_TEMPLATE_CONFIG)
            filler.fill_and_save(template_path, data, xlsx_path)
            ExcelToPdfConverter().convert(xlsx_path, pdf_path)

            return pdf_path.read_bytes()

    def _item_to_dict(self, item) -> dict:
        """将 HazardIdentification ORM 对象转为可 JSON 序列化的 dict"""
        return {
            "hazard_id_no": item.hazard_id_no,
            "department": item.department,
            "position": item.position,
            "production_step": item.production_step,
            "specific_activity": item.specific_activity,
            "equipment_facilities": item.equipment_facilities,
            "hazard_type": item.hazard_type,
            "possible_accident": item.possible_accident,
            "inherent_risk_level": item.inherent_risk_level,
            "inherent_risk_label": item.inherent_risk_label,
            "l_inherent": int(item.l_inherent) if item.l_inherent else None,
            "e_inherent": int(item.e_inherent) if item.e_inherent else None,
            "c_inherent": int(item.c_inherent) if item.c_inherent else None,
            "d_inherent": int(item.d_inherent) if item.d_inherent else None,
            "residual_risk_level": item.residual_risk_level,
            "residual_risk_label": item.residual_risk_label,
            "l_residual": int(item.l_residual) if item.l_residual else None,
            "e_residual": int(item.e_residual) if item.e_residual else None,
            "c_residual": int(item.c_residual) if item.c_residual else None,
            "d_residual": int(item.d_residual) if item.d_residual else None,
            "existing_engineering_controls": item.existing_engineering_controls,
            "existing_management_controls": item.existing_management_controls,
            "existing_ppe": item.existing_ppe,
            "existing_emergency_measures": item.existing_emergency_measures,
            "control_level": item.control_level,
            "responsible_person": item.responsible_person,
            "needs_recommendation": item.needs_recommendation,
            "recommendation_type": item.recommendation_type,
            "recommendation_content": item.recommendation_content,
            "overall_status": item.overall_status,
            "notes": item.notes,
        }

    # ── 固定模板 PDF 回退（reportlab）──

    async def _export_hazard_ledger_pdf_fallback(self, items, filters: dict) -> bytes:
        """固定模板 PDF 生成（reportlab）—— AI 格式化失败时的回退方案"""
        import io
        from datetime import datetime as dt_module

        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        # A4 横向
        page_w, page_h = landscape(A4)
        margin = 15 * mm
        buf = io.BytesIO()

        doc = SimpleDocTemplate(
            buf,
            pagesize=landscape(A4),
            leftMargin=margin,
            rightMargin=margin,
            topMargin=margin,
            bottomMargin=margin,
            title="危险源辨识台账",
        )

        # 字体注册
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        _font_name = "Helvetica"
        _font_name_bold = "Helvetica-Bold"
        _chinese_fonts = [
            ("C:/Windows/Fonts/simsun.ttc", "SimSun"),
            ("C:/Windows/Fonts/simhei.ttf", "SimHei"),
            ("C:/Windows/Fonts/msyh.ttc", "MicrosoftYaHei"),
        ]
        for font_path, font_alias in _chinese_fonts:
            try:
                pdfmetrics.registerFont(TTFont(font_alias, font_path))
                if font_alias == "SimSun":
                    _font_name = "SimSun"
                if font_alias == "SimHei":
                    _font_name_bold = "SimHei"
            except Exception:
                pass
        logger.debug("PDF fonts: body=%s, bold=%s", _font_name, _font_name_bold)

        styles = getSampleStyleSheet()
        body_style = ParagraphStyle(
            "BodyCN",
            parent=styles["Normal"],
            fontName=_font_name,
            fontSize=8,
            leading=12,
        )
        title_style = ParagraphStyle(
            "TitleCN",
            parent=styles["Title"],
            fontName=_font_name_bold,
            fontSize=16,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=4,
        )
        subtitle_style = ParagraphStyle(
            "SubtitleCN",
            parent=styles["Normal"],
            fontName=_font_name,
            fontSize=9,
            leading=14,
            alignment=TA_CENTER,
            textColor=colors.grey,
        )

        elements: list = []

        # 标题
        elements.append(Paragraph("危险源辨识台账", title_style))

        # 副标题
        filter_parts: list[str] = []
        for k, v in filters.items():
            if k == "risk_level":
                level_map = {
                    "level_1": "一级/重大风险",
                    "level_2": "二级/较大风险",
                    "level_3": "三级/一般风险",
                    "level_4": "四级/低风险",
                }
                filter_parts.append(f"风险等级：{level_map.get(v, v)}")
            elif k in ("date_from", "date_to"):
                label = "起" if k == "date_from" else "止"
                filter_parts.append(f"{label}：{v}")
            elif k == "keyword":
                filter_parts.append(f"关键词：{v}")
            else:
                filter_parts.append(f"{k}：{v}")
        filter_text = "；".join(filter_parts) if filter_parts else "全部记录"
        export_time = dt_module.now().strftime("%Y-%m-%d %H:%M")
        elements.append(
            Paragraph(
                f"筛选条件：{filter_text}　|　导出时间：{export_time}　|　共"
                f" {len(items)} 条",
                subtitle_style,
            )
        )
        elements.append(Spacer(1, 6 * mm))

        # ── 数据表 ──
        level_label_map = {
            "level_1": "重大",
            "level_2": "较大",
            "level_3": "一般",
            "level_4": "低",
        }
        headers = [
            "序号",
            "编号",
            "部门",
            "岗位",
            "作业活动",
            "危险类型",
            "固有风险",
            "残余风险",
            "管控层级",
            "责任人",
            "控制措施摘要",
        ]
        col_widths = [25, 70, 50, 50, 80, 55, 55, 55, 45, 50, 160]

        table_data = [headers]
        for idx, item in enumerate(items, 1):
            inherent_label = item.inherent_risk_label or level_label_map.get(
                item.inherent_risk_level or "", ""
            )
            inherent_d = (
                f"{inherent_label}(D={int(item.d_inherent)})"
                if item.d_inherent and inherent_label
                else inherent_label or "-"
            )
            residual_label = item.residual_risk_label or level_label_map.get(
                item.residual_risk_level or "", ""
            )
            residual_d = (
                f"{residual_label}(D={int(item.d_residual)})"
                if item.d_residual and residual_label
                else residual_label or "-"
            )

            controls_parts = []
            if item.existing_engineering_controls:
                controls_parts.append(
                    f"工程：{item.existing_engineering_controls[:60]}"
                )
            if item.existing_management_controls:
                controls_parts.append(f"管理：{item.existing_management_controls[:60]}")
            if item.existing_ppe:
                controls_parts.append(f"PPE：{item.existing_ppe[:40]}")
            controls_summary = "；".join(controls_parts) if controls_parts else "-"

            table_data.append(
                [
                    str(idx),
                    item.hazard_id_no or "",
                    item.department or "",
                    item.position or "",
                    item.specific_activity or item.production_step or "",
                    item.hazard_type or "",
                    inherent_d,
                    residual_d,
                    item.control_level or "",
                    item.responsible_person or "",
                    controls_summary,
                ]
            )

        table = Table(
            table_data, colWidths=[w * mm / 4 for w in col_widths], repeatRows=1
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5645D4")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), _font_name_bold),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("FONTNAME", (0, 1), (-1, -1), _font_name),
                    ("FONTSIZE", (0, 1), (-1, -1), 7.5),
                    ("ALIGN", (0, 0), (0, -1), "CENTER"),
                    ("ALIGN", (1, 1), (1, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9D9D9")),
                    ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.HexColor("#3D2DA6")),
                    *[
                        ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F7F6FB"))
                        for i in range(2, len(table_data) + 1, 2)
                    ],
                ]
            )
        )
        elements.append(table)
        elements.append(Spacer(1, 10 * mm))

        # ── 签发栏 ──
        sign_style = ParagraphStyle(
            "SignCN",
            parent=body_style,
            fontSize=10,
            leading=16,
        )
        sign_table = Table(
            [
                [
                    Paragraph("编制人：______________", sign_style),
                    Paragraph("审核人：______________", sign_style),
                    Paragraph("批准人：______________", sign_style),
                ]
            ],
            colWidths=[page_w / 3 - 20, page_w / 3 - 20, page_w / 3 - 20],
        )
        sign_table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("FONTNAME", (0, 0), (-1, -1), _font_name),
                    ("LEFTPADDING", (0, 0), (-1, -1), 30),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 30),
                ]
            )
        )
        sign_table2 = Table(
            [
                [
                    Paragraph("日期：______________", sign_style),
                    Paragraph("日期：______________", sign_style),
                    Paragraph("日期：______________", sign_style),
                ]
            ],
            colWidths=[page_w / 3 - 20, page_w / 3 - 20, page_w / 3 - 20],
        )
        sign_table2.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("FONTNAME", (0, 0), (-1, -1), _font_name),
                    ("LEFTPADDING", (0, 0), (-1, -1), 30),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 30),
                ]
            )
        )
        elements.append(sign_table)
        elements.append(Spacer(1, 4 * mm))
        elements.append(sign_table2)

        def add_page_number(canvas, doc_obj):
            canvas.saveState()
            canvas.setFont(_font_name, 8)
            canvas.drawCentredString(
                page_w / 2,
                10 * mm,
                f"第 {canvas.getPageNumber()} 页",
            )
            canvas.restoreState()

        doc.build(elements, onFirstPage=add_page_number, onLaterPages=add_page_number)
        buf.seek(0)
        return buf.getvalue()


# ==================== 操规修订 Service ====================
