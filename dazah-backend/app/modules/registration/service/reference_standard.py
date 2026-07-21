"""对照物质说明表生成业务逻辑"""

import logging
import uuid
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import NotFoundException
from app.modules.registration.models import ReferenceStandard
from app.modules.registration.repository import ReferenceStandardRepository
from app.modules.registration.schemas import (
    ReferenceStandardListItem,
    ReferenceStandardResponse,
)

logger = logging.getLogger(__name__)

# 模板文件路径（相对于模块目录）
TEMPLATE_PATH = (
    Path(__file__).parent.parent
    / "dui-zhao-pin-shuo-ming-biao"
    / "assets"
    / "对照物质说明表模板.docx"
)


def _get_upload_dir() -> Path:
    """获取对照物质说明表文件存储目录"""
    settings = get_settings()
    upload_dir_setting = getattr(settings, "UPLOAD_DIR", "uploads")
    base = Path(upload_dir_setting)
    upload_dir = base / "reference_standards"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def _load_template() -> bytes:
    """加载说明表模板文件"""
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"模板文件不存在: {TEMPLATE_PATH}")
    return TEMPLATE_PATH.read_bytes()


class ReferenceStandardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ReferenceStandardRepository(session)

    def _to_response(self, obj: ReferenceStandard) -> ReferenceStandardResponse:
        return ReferenceStandardResponse.model_validate(obj)

    def _to_list_item(self, obj: ReferenceStandard) -> ReferenceStandardListItem:
        return ReferenceStandardListItem.model_validate(obj)

    async def generate_document(
        self,
        coa_data: bytes,
        coa_file_name: str,
        drug_name: str,
        reference_substance_name: str | None = None,
        batch_number: str | None = None,
        manufacturer: str | None = None,
        english_name: str | None = None,
        molecular_formula: str | None = None,
        molecular_weight: str | None = None,
        cas_number: str | None = None,
        content: str | None = None,
        moisture: str | None = None,
        rsd: str | None = None,
        expiration_date: str | None = None,
        storage_condition: str | None = None,
        remarks: str | None = None,
    ) -> ReferenceStandardResponse:
        """
        生成对照物质说明表文档。

        流程：加载模板 → 填充数据 → 生成 Word → 保存记录
        """
        from app.modules.registration.reference_standard_generator import (
            generate_reference_standard_document,
        )

        # 1. 加载模板
        template_data = _load_template()

        # 2. 构造 COA 数据
        coa_info = {
            "药品名称": drug_name,
            "对照物质名称": reference_substance_name or drug_name,
            "批号": batch_number or "",
            "生产厂家": manufacturer or "",
            "英文名": english_name or "",
            "分子式": molecular_formula or "",
            "分子量": molecular_weight or "",
            "CAS号": cas_number or "",
            "含量": content or "",
            "水分/干燥失重": moisture or "",
            "RSD": rsd or "",
            "有效期": expiration_date or "",
            "贮存条件": storage_condition or "",
        }

        # 3. 生成 Word 文档
        output_data = generate_reference_standard_document(coa_info, template_data)

        # 4. 保存文件
        file_id = uuid.uuid4().hex[:12]
        output_file_name = f"对照物质说明表-{drug_name}.docx"
        upload_dir = _get_upload_dir()

        # 保存 COA 原始文件
        coa_path = upload_dir / f"{file_id}_coa.pdf"
        coa_path.write_bytes(coa_data)

        # 保存生成的文档
        output_path = upload_dir / f"{file_id}.docx"
        output_path.write_bytes(output_data)

        # 5. 创建数据库记录
        record = ReferenceStandard(
            drug_name=drug_name,
            reference_substance_name=reference_substance_name,
            batch_number=batch_number,
            manufacturer=manufacturer,
            english_name=english_name,
            molecular_formula=molecular_formula,
            molecular_weight=molecular_weight,
            cas_number=cas_number,
            content=content,
            moisture=moisture,
            rsd=rsd,
            expiration_date=expiration_date,
            storage_condition=storage_condition,
            coa_file_key=f"{file_id}_coa.pdf",
            coa_file_name=coa_file_name,
            output_file_key=f"{file_id}.docx",
            output_file_name=output_file_name,
            remarks=remarks,
        )
        created = await self.repo.create(record)
        return self._to_response(created)

    async def get_record(self, record_id: UUID) -> ReferenceStandardResponse:
        """获取单条记录"""
        record = await self.repo.get_by_id(record_id)
        if not record:
            raise NotFoundException("对照物质说明表记录", str(record_id))
        return self._to_response(record)

    async def list_records(
        self,
        *,
        drug_name: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ReferenceStandardListItem], int]:
        """查询记录列表"""
        records, total = await self.repo.list_records(
            drug_name=drug_name,
            page=page,
            page_size=page_size,
        )
        return [self._to_list_item(r) for r in records], total

    async def delete_record(self, record_id: UUID) -> None:
        """删除记录（软删除）"""
        record = await self.repo.get_by_id(record_id)
        if not record:
            raise NotFoundException("对照物质说明表记录", str(record_id))
        await self.repo.soft_delete(record)

    def get_output_file_path(self, record: ReferenceStandard) -> Path:
        """获取生成文件路径"""
        return _get_upload_dir() / record.output_file_key
