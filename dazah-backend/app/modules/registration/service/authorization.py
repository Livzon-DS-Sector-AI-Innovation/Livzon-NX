"""Registration business workflows live here."""

import logging
import uuid
import zipfile
import io
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import NotFoundException
from app.modules.registration.models import AuthorizationLetter, SupplementaryReply
from app.modules.registration.repository import AuthorizationLetterRepository, SupplementaryReplyRepository
from app.modules.registration.schemas import (
    SupplementaryReplyCreate,
    SupplementaryReplyListItem,
    SupplementaryReplyResponse,
    AuthorizationLetterCreate,
    AuthorizationLetterListItem,
    AuthorizationLetterResponse,
    ProductInfo,
)

logger = logging.getLogger(__name__)

# 固定原料药企业
API_COMPANY = "珠海保税区丽珠合成制药有限公司"

# 品种登记号对照表
REGISTRATION_NUMBERS: dict[str, str] = {
    "阿魏酸钠": "Y20190001800",
    "艾普拉唑": "Y20190009784",
    "艾普拉唑钠": "Y20170001429",
    "奥美拉唑钠": "Y20190006673",
    "丙氨酰谷氨酰胺": "Y20190002584",
    "布南色林": "Y20210001289",
    "丹曲林钠": "Y20170001099",
    "丁苯酞": "Y20170001569",
    "厄贝沙坦": "Y20190001962",
    "更昔洛韦": "Y20190008005",
    "枸酸铋钾 (干品)": "Y20200001089",
    "枸橼酸铋钾 (湿品)": "Y20190003316",
    "枸橼酸铋雷尼替丁 (1:1)": "Y20190005110",
    "枸橼酸铋雷尼替丁 (1:1.1)": "Y20190001948",
    "桂利嗪": "Y20190007743",
    "酒石酸托特罗定": "Y20190001881",
    "卡维地洛": "Y20190001959",
    "磷酸川芎嗪": "Y20190007731",
    "硫酸钾": "Y20230000325",
    "硫酸头孢匹罗": "Y20190002699",
    "氯雷他定": "Y20190008122",
    "马来酸氟伏沙明": "Y20170001958",
    "马来酸茚达特罗": "Y20220000555",
    "舒巴坦钠": "Y20190001952",
    "他唑巴坦": "Y20190003875",
    "头孢地嗪钠": "Y20190001846",
    "头孢呋辛钠": "Y20190009596",
    "头孢曲松钠": "Y20190009444",
    "头孢他啶/碳酸钠": "Y20190006854",
    "头孢他啶": "Y20190007742",
    "无水碳酸钠": "Y20190006967",
    "盐酸哌罗匹隆 (新工艺)": "Y20220000720",
    "盐酸哌罗匹隆": "Y20190006883",
    "盐酸头孢吡肟": "Y20190001951",
    "盐酸伊托必利": "Y20190001876",
    "阿立哌唑": "Y20230000505",
    "盐酸鲁拉西酮": "Y20230001106",
    "棕榈酸帕利哌酮": "Y20240000016",
}


def _get_upload_dir() -> Path:
    """获取上传/生成文件存储目录"""
    settings = get_settings()
    upload_dir_setting = getattr(settings, "UPLOAD_DIR", "uploads")
    base = Path(upload_dir_setting)
    upload_dir = base / "authorization_letters"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def _is_docx_format(data: bytes) -> bool:
    """检测文件是否为 DOCX 格式（ZIP 压缩包）"""
    return data[:4] == b'PK'


def generate_authorization_letter_bytes(
    template_data: bytes,
    replacements: list[tuple[str, str]],
) -> bytes:
    """
    对模板执行文本替换。支持 .docx 格式（实际是 ZIP 压缩包）。

    Args:
        template_data: 模板文件二进制内容
        replacements: 替换规则列表 [(原文本，新文本), ...]

    Returns:
        替换后的文件二进制内容
    """
    if not _is_docx_format(template_data):
        # 如果不是 DOCX 格式，尝试旧的二进制替换方式
        return _binary_replace(template_data, replacements)
    
    # DOCX 格式：使用 XML 文本替换
    return _docx_replace(template_data, replacements)


def _docx_replace(
    template_data: bytes,
    replacements: list[tuple[str, str]],
) -> bytes:
    """对 DOCX 文件执行 XML 文本替换"""
    replacement_dict = {old: new for old, new in replacements}
    
    with zipfile.ZipFile(io.BytesIO(template_data), 'r') as z:
        # 读取所有文件
        files = {}
        for name in z.namelist():
            files[name] = z.read(name)
        
        # 处理 document.xml
        if 'word/document.xml' in files:
            try:
                doc_xml = files['word/document.xml'].decode('utf-8')
            except UnicodeDecodeError:
                raise ValueError("模板文件编码错误：DOCX 文档包含非 UTF-8 编码的内容")
            
            for old_text, new_text in replacement_dict.items():
                if old_text in doc_xml:
                    doc_xml = doc_xml.replace(old_text, new_text)
                    logger.info(f"替换：'{old_text}' -> '{new_text}'")
                else:
                    logger.warning(f"未找到文本：'{old_text}'")
            
            files['word/document.xml'] = doc_xml.encode('utf-8')
        
        # 创建新的 docx 文件
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as out_z:
            for name, content in files.items():
                out_z.writestr(name, content)
        
        return output.getvalue()


def _binary_replace(
    template_data: bytes,
    replacements: list[tuple[str, str]],
) -> bytes:
    """对 .doc 模板执行二进制等长替换（旧方式）"""
    data = bytearray(template_data)

    for old_text, new_text in replacements:
        old_bytes = old_text.encode("utf-16le")
        new_bytes = new_text.encode("utf-16le")

        if len(old_bytes) != len(new_bytes):
            raise ValueError(
                f"长度不匹配：'{old_text}' ({len(old_text)}字，{len(old_bytes)}字节) ->"
                f" '{new_text}' ({len(new_text)}字，{len(new_bytes)}字节)"
            )

        pos = 0
        while True:
            pos = data.find(old_bytes, pos)
            if pos == -1:
                break
            data[pos : pos + len(old_bytes)] = new_bytes
            pos += 1

    return bytes(data)


class AuthorizationLetterService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AuthorizationLetterRepository(session)

    def _to_response(self, obj: AuthorizationLetter) -> AuthorizationLetterResponse:
        return AuthorizationLetterResponse.model_validate(obj)

    def _to_list_item(self, obj: AuthorizationLetter) -> AuthorizationLetterListItem:
        return AuthorizationLetterListItem.model_validate(obj)

    @staticmethod
    def get_product_list() -> list[ProductInfo]:
        """获取品种登记号对照表"""
        return [
            ProductInfo(product_name=name, registration_number=number)
            for name, number in sorted(REGISTRATION_NUMBERS.items())
        ]

    @staticmethod
    def get_registration_number(product_name: str) -> str | None:
        """根据品种名称获取登记号"""
        return REGISTRATION_NUMBERS.get(product_name)

    async def generate_letter(
        self,
        data: AuthorizationLetterCreate,
        template_data: bytes,
        template_file_name: str,
        template_placeholders: dict[str, str] | None = None,
    ) -> AuthorizationLetterResponse:
        """
        生成授权书。

        Args:
            data: 生成请求数据
            template_data: 模板文件二进制内容
            template_file_name: 模板文件名
            template_placeholders: 模板中的占位符映射 {占位符文本：替换文本}
                                   如果不传，则自动根据表单数据生成替换规则
        """
        # 构建替换规则
        replacements: list[tuple[str, str]] = []

        if template_placeholders:
            for placeholder, value in template_placeholders.items():
                replacements.append((placeholder, value))
        else:
            # 自动根据表单数据生成替换规则
            pass

        # 执行替换
        output_data = generate_authorization_letter_bytes(template_data, replacements)

        # 保存生成文件
        file_id = uuid.uuid4().hex[:12]
        output_file_name = f"授权书-{data.product_name}-{data.preparation_unit}.doc"
        upload_dir = _get_upload_dir()
        output_path = upload_dir / f"{file_id}.doc"
        output_path.write_bytes(output_data)

        # 同时保存模板
        template_path = upload_dir / f"{file_id}_template.doc"
        template_path.write_bytes(template_data)

        # 创建数据库记录
        letter = AuthorizationLetter(
            api_company=API_COMPANY,
            product_name=data.product_name,
            registration_number=data.registration_number,
            preparation_unit=data.preparation_unit,
            preparation_name=data.preparation_name,
            administration_route=data.administration_route,
            template_file_key=f"{file_id}_template.doc",
            template_file_name=template_file_name,
            output_file_key=f"{file_id}.doc",
            output_file_name=output_file_name,
            remarks=data.remarks,
        )
        created = await self.repo.create(letter)
        return self._to_response(created)

    async def get_letter(self, letter_id: UUID) -> AuthorizationLetterResponse:
        """获取单条授权书记录"""
        letter = await self.repo.get_by_id(letter_id)
        if not letter:
            raise NotFoundException("授权书记录", str(letter_id))
        return self._to_response(letter)

    async def list_letters(
        self,
        *,
        product_name: str | None = None,
        preparation_unit: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AuthorizationLetterListItem], int]:
        """查询授权书列表"""
        letters, total = await self.repo.list_letters(
            product_name=product_name,
            preparation_unit=preparation_unit,
            page=page,
            page_size=page_size,
        )
        return [self._to_list_item(letter) for letter in letters], total

    async def delete_letter(self, letter_id: UUID) -> None:
        """删除授权书记录（软删除）"""
        letter = await self.repo.get_by_id(letter_id)
        if not letter:
            raise NotFoundException("授权书记录", str(letter_id))
        await self.repo.soft_delete(letter)

    def get_output_file_path(self, letter: AuthorizationLetter) -> Path:
        """获取生成文件路径"""
        return _get_upload_dir() / letter.output_file_key


# ─── 发补回复 ────────────────────────────────────────────


def _get_reply_upload_dir() -> Path:
    """获取发补回复文件存储目录"""
    settings = get_settings()
    upload_dir_setting = getattr(settings, "UPLOAD_DIR", "uploads")
    base = Path(upload_dir_setting)
    upload_dir = base / "supplementary_replies"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


class SupplementaryReplyService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = SupplementaryReplyRepository(session)

    def _to_response(self, obj: SupplementaryReply) -> SupplementaryReplyResponse:
        return SupplementaryReplyResponse.model_validate(obj)

    def _to_list_item(self, obj: SupplementaryReply) -> SupplementaryReplyListItem:
        return SupplementaryReplyListItem.model_validate(obj)

    async def generate_reply(
        self,
        notice_data: bytes,
        notice_file_name: str,
        template_data: bytes | None = None,
        template_file_name: str | None = None,
        drug_name_override: str | None = None,
        registration_number_override: str | None = None,
        acceptance_number_override: str | None = None,
        company_name_override: str | None = None,
        remarks: str | None = None,
    ) -> SupplementaryReplyResponse:
        """
        生成发补回复文档。

        流程：解析 PDF → 提取药品信息和问题 → 生成 Word → 保存记录
        """
        from app.modules.registration.reply_generator import (
            parse_cde_notice,
            generate_reply_document,
        )

        # 1. 解析 CDE 通知函 PDF
        parsed = parse_cde_notice(notice_data)
        metadata = parsed["metadata"]
        questions = parsed["questions"]

        # 2. 合并药品信息（用户手动输入优先于 PDF 提取）
        drug_info = {
            "drug_name": drug_name_override or metadata.get("drug_name", "未知药品"),
            "registration_number": registration_number_override or metadata.get("registration_number", ""),
            "acceptance_number": acceptance_number_override or metadata.get("acceptance_number", ""),
            "company_name": company_name_override or metadata.get("company_name", API_COMPANY),
            "doc_type": "补充资料",
            "application_type": "首次登记",
            "contact": "魏永红",
            "phone": "0756-8686208",
            "address": "中国，广东省，珠海市，珠海保税区联峰路22号",
            "zipcode": "519030",
            "related_no": "/",
            "email": "lzsyntpharmzhucebu@livzon.cn",
        }

        # 3. 生成 Word 文档
        output_data = generate_reply_document(drug_info, questions)

        # 4. 保存文件
        file_id = uuid.uuid4().hex[:12]
        output_file_name = f"发补回复-{drug_info['drug_name']}.docx"
        upload_dir = _get_reply_upload_dir()

        # 保存通知函
        notice_path = upload_dir / f"{file_id}_notice.pdf"
        notice_path.write_bytes(notice_data)

        # 保存模板（如有）
        template_key = None
        if template_data:
            template_path = upload_dir / f"{file_id}_template.docx"
            template_path.write_bytes(template_data)
            template_key = f"{file_id}_template.docx"

        # 保存生成的文档
        output_path = upload_dir / f"{file_id}.docx"
        output_path.write_bytes(output_data)

        # 5. 创建数据库记录
        reply = SupplementaryReply(
            drug_name=drug_info["drug_name"],
            registration_number=drug_info["registration_number"],
            acceptance_number=drug_info["acceptance_number"],
            company_name=drug_info["company_name"],
            notice_file_key=f"{file_id}_notice.pdf",
            notice_file_name=notice_file_name,
            template_file_key=template_key,
            template_file_name=template_file_name,
            output_file_key=f"{file_id}.docx",
            output_file_name=output_file_name,
            question_count=len(questions),
            remarks=remarks,
        )
        created = await self.repo.create(reply)
        return self._to_response(created)

    async def get_reply(self, reply_id: UUID) -> SupplementaryReplyResponse:
        """获取单条发补回复记录"""
        reply = await self.repo.get_by_id(reply_id)
        if not reply:
            raise NotFoundException("发补回复记录", str(reply_id))
        return self._to_response(reply)

    async def list_replies(
        self,
        *,
        drug_name: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SupplementaryReplyListItem], int]:
        """查询发补回复列表"""
        replies, total = await self.repo.list_replies(
            drug_name=drug_name,
            page=page,
            page_size=page_size,
        )
        return [self._to_list_item(r) for r in replies], total

    async def delete_reply(self, reply_id: UUID) -> None:
        """删除发补回复记录（软删除）"""
        reply = await self.repo.get_by_id(reply_id)
        if not reply:
            raise NotFoundException("发补回复记录", str(reply_id))
        await self.repo.soft_delete(reply)

    def get_output_file_path(self, reply: SupplementaryReply) -> Path:
        """获取生成文件路径"""
        return _get_reply_upload_dir() / reply.output_file_key
