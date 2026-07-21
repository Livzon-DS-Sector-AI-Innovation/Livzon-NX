"""AI 填充服务的 Prompt 模板"""
from typing import List, Dict, Any


def build_extract_fields_prompt(
    fields: List[Dict[str, str]],
    asset_texts: Dict[str, str],
    product_name: str,
) -> List[Dict[str, str]]:
    """构建字段提取的 Prompt

    Args:
        fields: 需要提取的字段列表，每项包含 field_name 和 extraction_prompt
        asset_texts: 素材文件名 -> 提取的文本内容
        product_name: 品种名称
    """
    field_desc = "\n".join(
        f"  - {f['field_name']}: {f.get('extraction_prompt', '从素材中提取此字段的值')}"
        for f in fields
    )

    asset_desc = ""
    for fname, text in asset_texts.items():
        # 截断过长的文本，避免 token 爆炸
        truncated = text[:3000] if len(text) > 3000 else text
        asset_desc += f"\n--- 素材文件: {fname} ---\n{truncated}\n"

    return [
        {
            "role": "system",
            "content": (
                "你是药品申报资料撰写助手。你的任务是从药品相关素材文档中准确提取结构化字段值。\n"
                "规则：\n"
                "1. 只返回 JSON 格式结果，不要添加任何额外文字\n"
                "2. 每个字段必须包含 value（提取的值）和 source（来自哪个素材文件的哪个位置）\n"
                "3. 如果在素材中找不到某个字段的值，将 value 设为 null，不要编造\n"
                "4. 表格类字段返回 JSON 数组格式\n"
                "5. confidence 是你对提取结果的信心评分，0-1 之间"
            ),
        },
        {
            "role": "user",
            "content": (
                f"品种名称：{product_name}\n\n"
                f"需要从以下素材文档中提取这些字段：\n{field_desc}\n\n"
                f"素材文档内容：\n{asset_desc}\n\n"
                "请返回如下 JSON 格式（不要添加其他文字）：\n"
                "```json\n"
                "{\n"
                '  "fields": [\n'
                "    {\n"
                '      "field_name": "字段名",\n'
                '      "value": "提取的值（表格类为数组，找不到为 null）",\n'
                '      "source": "来源素材文件名 + 位置描述",\n'
                '      "confidence": 0.9\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "```"
            ),
        },
    ]


def build_split_pages_prompt(
    page_texts: List[Dict[str, Any]],
    available_appendix_slots: List[str],
) -> List[Dict[str, str]]:
    """构建多页文档拆分的 Prompt

    Args:
        page_texts: 每页的 OCR 文本，[{page_number, text}]
        available_appendix_slots: 模板中可用的附录位置列表
    """
    pages_desc = ""
    for p in page_texts:
        truncated = p["text"][:500] if len(p["text"]) > 500 else p["text"]
        pages_desc += f"\n--- 第 {p['page']} 页 ---\n{truncated}\n"

    appendix_desc = ", ".join(available_appendix_slots) if available_appendix_slots else "无"

    return [
        {
            "role": "system",
            "content": (
                "你是药品申报资料助手。你的任务是识别多页 PDF 文档中每一页的内容类型，"
                "并将其分配到模板中对应的附录位置。\n"
                "规则：\n"
                "1. 只返回 JSON 格式\n"
                "2. 每页需要识别出页面类型（如：营业执照、CDE公示、检验报告单、质量标准等）\n"
                "3. 如果某页内容属于可用附录中的某一类，填入对应的 appendix_slot\n"
                "4. 如果某页不属于任何附录位置，appendix_slot 设为 null\n"
                "5. 给出简短的内容摘要（content_summary）"
            ),
        },
        {
            "role": "user",
            "content": (
                f"可用的附录位置：{appendix_desc}\n\n"
                f"文档各页内容（OCR 文本）：\n{pages_desc}\n\n"
                "请返回如下 JSON 格式：\n"
                "```json\n"
                "{\n"
                '  "pages": [\n'
                "    {\n"
                '      "page_number": 1,\n'
                '      "page_type": "营业执照",\n'
                '      "content_summary": "石家庄市华辰包装有限公司营业执照副本",\n'
                '      "appendix_slot": "附录1"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "```"
            ),
        },
    ]


def build_fill_location_prompt(
    template_paragraphs: List[Dict[str, Any]],
    template_tables: List[Dict[str, Any]],
    extracted_fields: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """构建模板填充定位的 Prompt

    告诉 LLM：这是模板文档的结构，这是提取到的字段值，请告诉我每个值应该填到哪个位置。

    Args:
        template_paragraphs: 模板段落 [{index, text}]
        template_tables: 模板表格 [{index, rows, cols, preview}]
        extracted_fields: AI 提取的字段值 [{field_name, value, source}]
    """
    para_desc = ""
    for p in template_paragraphs:
        if p["text"].strip():
            para_desc += f"  段落[{p['index']}]: {p['text'][:100]}\n"

    table_desc = ""
    for t in template_tables:
        table_desc += f"  表格[{t['index']}]: {t['rows']}行 x {t['cols']}列\n"
        for row in t.get("preview", [])[:4]:
            table_desc += f"    {row}\n"

    field_desc = ""
    for f in extracted_fields:
        val_str = str(f["value"])[:80] if f["value"] else "null"
        field_desc += f"  - {f['field_name']}: {val_str}\n"

    return [
        {
            "role": "system",
            "content": (
                "你是药品申报资料排版助手。你的任务是将提取到的字段值准确定位到模板文档的正确位置。\n"
                "规则：\n"
                "1. 只返回 JSON 格式\n"
                "2. 每个字段需要指定 fill_action（填充动作）和 target（目标位置）\n"
                "3. fill_action 可以是：\n"
                "   - replace_after_colon: 替换段落中冒号后的内容\n"
                "   - fill_table_cell: 填充表格中匹配关键词的下一个单元格\n"
                "   - replace_table_rows: 替换表格中的数据行（用于完整表格字段）\n"
                "   - skip: 跳过（值为 null 时）\n"
                "4. target 需要指定 paragraph_index 或 table_index，以及匹配关键词\n"
                "5. 如果模板中没有找到对应位置，fill_action 设为 skip"
            ),
        },
        {
            "role": "user",
            "content": (
                f"模板文档段落：\n{para_desc}\n\n"
                f"模板文档表格：\n{table_desc}\n\n"
                f"需要填充的字段值：\n{field_desc}\n\n"
                "请返回如下 JSON 格式：\n"
                "```json\n"
                "{\n"
                '  "fills": [\n'
                "    {\n"
                '      "field_name": "包装形式",\n'
                '      "fill_action": "replace_after_colon",\n'
                '      "target": {"paragraph_index": 17, "keyword": "包装形式"},\n'
                '      "value": "药用铝瓶I+包装外袋+包装泡沫III+中性纸箱III"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "```"
            ),
        },
    ]
