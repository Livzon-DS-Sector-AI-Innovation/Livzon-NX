"""S.6 包装系统 AI 填充配置种子数据"""
import asyncio
import os
import sys
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.core.database import async_session_factory
from app.modules.dossier_writer.field_models import FieldMapping, AssetCategory


S6_ASSET_CATEGORIES = [
    {
        "chapter_code": "3.2.S.6",
        "category_name": "原料药质量标准",
        "category_type": "document",
        "appendix_slot": None,
        "description": "原料药（终产品）的质量标准文档，包含包装形式、包装规格等信息",
        "sort_order": 1,
    },
    {
        "chapter_code": "3.2.S.6",
        "category_name": "包材质量标准",
        "category_type": "document",
        "appendix_slot": None,
        "description": "包装材料（如药用铝瓶）的企业质量标准文档，包含包材类型、执行标准号、检验项目表等",
        "sort_order": 2,
    },
    {
        "chapter_code": "3.2.S.6",
        "category_name": "授权书",
        "category_type": "both",
        "appendix_slot": None,
        "description": "包材生产商授权给药品生产企业的授权书，包含生产商名称、登记号，同时需转为图片插入正文",
        "sort_order": 3,
    },
    {
        "chapter_code": "3.2.S.6",
        "category_name": "包材相关证明材料",
        "category_type": "image_appendix",
        "appendix_slot": None,
        "description": "可能包含营业执照、CDE公示、检验报告单等多种内容的合并文档（PDF），AI 会按页拆分识别",
        "sort_order": 4,
    },
    {
        "chapter_code": "3.2.S.6",
        "category_name": "厂家报告单",
        "category_type": "image_appendix",
        "appendix_slot": "附录4",
        "description": "包材生产商出具的检验报告单",
        "sort_order": 5,
    },
    {
        "chapter_code": "3.2.S.6",
        "category_name": "验证研究资料",
        "category_type": "document",
        "appendix_slot": None,
        "description": "包装材料选择依据的验证研究资料，包含稳定性研究、灭菌验证等（选填）",
        "sort_order": 6,
    },
]


S6_FIELD_MAPPINGS = [
    {
        "chapter_code": "3.2.S.6",
        "field_name": "包装形式",
        "field_type": "text",
        "location_type": "paragraph",
        "location_hint": "包装材料类型章节中'包装形式'段落，冒号后填入",
        "extraction_prompt": "从原料药质量标准文档中提取'包装形式'字段值，通常在'5 包装形式：...'段落中",
        "source_type": "asset_extract",
        "source_category": "原料药质量标准",
        "sort_order": 1,
        "is_required": True,
    },
    {
        "chapter_code": "3.2.S.6",
        "field_name": "包装规格",
        "field_type": "text",
        "location_type": "paragraph",
        "location_hint": "包装材料类型章节中'包装规格'段落，冒号后填入",
        "extraction_prompt": "从原料药质量标准文档中提取'包装规格'字段值，通常在'6 规格：...'或'包装规格：...'段落中",
        "source_type": "asset_extract",
        "source_category": "原料药质量标准",
        "sort_order": 2,
        "is_required": True,
    },
    {
        "chapter_code": "3.2.S.6",
        "field_name": "包材类型",
        "field_type": "text",
        "location_type": "table",
        "location_hint": "包装信息表格中'包材类型'行的第二列",
        "extraction_prompt": "从包材质量标准文档中提取直接接触药品的包材类型，如'药用铝瓶Ⅰ'、'玻璃瓶'等",
        "source_type": "asset_extract",
        "source_category": "包材质量标准",
        "sort_order": 3,
        "is_required": True,
    },
    {
        "chapter_code": "3.2.S.6",
        "field_name": "厂内名称",
        "field_type": "text",
        "location_type": "table",
        "location_hint": "包装信息表格中'厂内名称'行的第二列",
        "extraction_prompt": "从包材质量标准文档中提取厂内使用的物料名称，通常在'物料代码'或'基本信息'段落中",
        "source_type": "asset_extract",
        "source_category": "包材质量标准",
        "sort_order": 4,
        "is_required": True,
    },
    {
        "chapter_code": "3.2.S.6",
        "field_name": "包材生产商",
        "field_type": "text",
        "location_type": "table",
        "location_hint": "包装信息表格中'包材生产商'行的第二列",
        "extraction_prompt": "从授权书中提取包材生产商的完整公司名称",
        "source_type": "asset_extract",
        "source_category": "授权书",
        "sort_order": 5,
        "is_required": True,
    },
    {
        "chapter_code": "3.2.S.6",
        "field_name": "包材登记号",
        "field_type": "text",
        "location_type": "table",
        "location_hint": "包装信息表格中'包材登记号'行的第二列",
        "extraction_prompt": "从授权书中提取产品登记号，通常以字母开头加数字，如 B20180000651",
        "source_type": "asset_extract",
        "source_category": "授权书",
        "sort_order": 6,
        "is_required": True,
    },
    {
        "chapter_code": "3.2.S.6",
        "field_name": "执行质量标准号",
        "field_type": "text",
        "location_type": "table",
        "location_hint": "包装信息表格中'执行质量标准号'行的第二列",
        "extraction_prompt": "从包材质量标准文档中提取企业执行的质量标准编号，如 Q/HCH11-2017",
        "source_type": "asset_extract",
        "source_category": "包材质量标准",
        "sort_order": 7,
        "is_required": True,
    },
    {
        "chapter_code": "3.2.S.6",
        "field_name": "包装材料质量标准表",
        "field_type": "table",
        "location_type": "table",
        "location_hint": "包装材料质量标准章节中的检验项目表格",
        "extraction_prompt": "从包材质量标准文档中提取完整的检验项目表格，包含序号、检验项目、企业内控标准等列，返回二维数组格式",
        "source_type": "asset_extract",
        "source_category": "包材质量标准",
        "sort_order": 8,
        "is_required": True,
    },
    {
        "chapter_code": "3.2.S.6",
        "field_name": "厂家报告单",
        "field_type": "text",
        "location_type": "table",
        "location_hint": "包装信息表格中'厂家报告单'行的第二列",
        "extraction_prompt": None,
        "source_type": "fixed",
        "fixed_value": "详见附录4",
        "sort_order": 9,
        "is_required": False,
    },
    {
        "chapter_code": "3.2.S.6",
        "field_name": "自检报告单",
        "field_type": "text",
        "location_type": "table",
        "location_hint": "包装信息表格中'自检报告单'行的第二列",
        "extraction_prompt": None,
        "source_type": "fixed",
        "fixed_value": "详见附录5",
        "sort_order": 10,
        "is_required": False,
    },
    {
        "chapter_code": "3.2.S.6",
        "field_name": "授权书图片",
        "field_type": "image_appendix",
        "location_type": "inline_image",
        "location_hint": "包装材料授权书章节中'图3.2.S.6-1'位置",
        "extraction_prompt": None,
        "source_type": "asset_image",
        "source_category": "授权书",
        "appendix_slot": None,
        "sort_order": 11,
        "is_required": True,
    },
    {
        "chapter_code": "3.2.S.6",
        "field_name": "营业执照图片",
        "field_type": "image_appendix",
        "location_type": "appendix",
        "location_hint": "附录1 营业执照位置",
        "extraction_prompt": None,
        "source_type": "asset_image",
        "source_category": "包材相关证明材料",
        "appendix_slot": "附录1",
        "sort_order": 12,
        "is_required": True,
    },
    {
        "chapter_code": "3.2.S.6",
        "field_name": "CDE公示图片",
        "field_type": "image_appendix",
        "location_type": "appendix",
        "location_hint": "附录2 CDE公示位置",
        "extraction_prompt": None,
        "source_type": "asset_image",
        "source_category": "包材相关证明材料",
        "appendix_slot": "附录2",
        "sort_order": 13,
        "is_required": True,
    },
    {
        "chapter_code": "3.2.S.6",
        "field_name": "厂家报告单图片",
        "field_type": "image_appendix",
        "location_type": "appendix",
        "location_hint": "附录4 厂家报告单位置",
        "extraction_prompt": None,
        "source_type": "asset_image",
        "source_category": "厂家报告单",
        "appendix_slot": "附录4",
        "sort_order": 14,
        "is_required": True,
    },
    {
        "chapter_code": "3.2.S.6",
        "field_name": "厂内报告单图片",
        "field_type": "image_appendix",
        "location_type": "appendix",
        "location_hint": "附录5 厂内报告单位置",
        "extraction_prompt": None,
        "source_type": "asset_image",
        "source_category": "包材相关证明材料",
        "appendix_slot": "附录5",
        "sort_order": 15,
        "is_required": True,
    },
]


async def seed():
    async with async_session_factory() as db:
        # 清理旧的 S.6 配置
        old_mappings = await db.execute(
            select(FieldMapping).where(FieldMapping.chapter_code == "3.2.S.6")
        )
        for m in old_mappings.scalars().all():
            await db.delete(m)

        old_categories = await db.execute(
            select(AssetCategory).where(AssetCategory.chapter_code == "3.2.S.6")
        )
        for c in old_categories.scalars().all():
            await db.delete(c)

        await db.flush()

        # 插入素材分类
        for cat_data in S6_ASSET_CATEGORIES:
            cat = AssetCategory(**cat_data)
            db.add(cat)

        # 插入字段映射
        for fm_data in S6_FIELD_MAPPINGS:
            fm = FieldMapping(**fm_data)
            db.add(fm)

        await db.commit()
        print(f"✓ S.6 种子数据写入完成: {len(S6_ASSET_CATEGORIES)} 个素材分类, {len(S6_FIELD_MAPPINGS)} 个字段映射")


if __name__ == "__main__":
    asyncio.run(seed())
