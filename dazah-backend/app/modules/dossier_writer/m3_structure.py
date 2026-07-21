"""M3 CTD 标准目录结构定义"""
from typing import List, Dict, Optional


M3_CHAPTERS: List[Dict] = [
    # Level 1: 3.2
    {"code": "3.2", "title": "主体数据", "level": 1, "parent_code": None,
     "aliases": [], "keywords": []},

    # Level 2: 3.2.S
    {"code": "3.2.S", "title": "原料药", "level": 2, "parent_code": "3.2",
     "aliases": ["drug_substance", "active_pharmaceutical_ingredient", "api"],
     "keywords": ["drug substance", "active pharmaceutical ingredient"]},

    # Level 3: 3.2.S.1
    {"code": "3.2.S.1", "title": "基本信息", "level": 3, "parent_code": "3.2.S",
     "aliases": ["s1", "general_information", "basic_info"],
     "keywords": ["general information", "basic information"]},
    {"code": "3.2.S.1.1", "title": "药品名称", "level": 4, "parent_code": "3.2.S.1",
     "aliases": ["s1_1", "drug_name", "nomenclature"],
     "keywords": ["name", "nomenclature", "drug name"]},
    {"code": "3.2.S.1.2", "title": "结构", "level": 4, "parent_code": "3.2.S.1",
     "aliases": ["s1_2", "structure"],
     "keywords": ["structure", "molecular", "chemical formula"]},
    {"code": "3.2.S.1.3", "title": "基本性质", "level": 4, "parent_code": "3.2.S.1",
     "aliases": ["s1_3", "general_properties", "physicochemical_properties"],
     "keywords": ["properties", "physicochemical"]},

    # Level 3: 3.2.S.2
    {"code": "3.2.S.2", "title": "生产", "level": 3, "parent_code": "3.2.S",
     "aliases": ["s2", "manufacture"],
     "keywords": ["manufacture", "production"]},
    {"code": "3.2.S.2.1", "title": "生产商", "level": 4, "parent_code": "3.2.S.2",
     "aliases": ["s2_1", "manufacturer"],
     "keywords": ["manufacturer", "producer"]},
    {"code": "3.2.S.2.2", "title": "生产工艺控制", "level": 4, "parent_code": "3.2.S.2",
     "aliases": ["s2_2", "manufacture_process_control"],
     "keywords": ["process control"]},
    {"code": "3.2.S.2.3", "title": "物料控制", "level": 4, "parent_code": "3.2.S.2",
     "aliases": ["s2_3", "material_control", "control_of_materials"],
     "keywords": ["material control", "materials"]},
    {"code": "3.2.S.2.4", "title": "关键步骤和中间体的控制", "level": 4, "parent_code": "3.2.S.2",
     "aliases": ["s2_4", "critical_steps", "intermediates_control"],
     "keywords": ["critical steps", "intermediates"]},
    {"code": "3.2.S.2.5", "title": "工艺验证和/或评价", "level": 4, "parent_code": "3.2.S.2",
     "aliases": ["s2_5", "process_validation", "process_evaluation"],
     "keywords": ["process validation", "process evaluation"]},
    {"code": "3.2.S.2.6", "title": "生产工艺的开发", "level": 4, "parent_code": "3.2.S.2",
     "aliases": ["s2_6", "process_development", "manufacture_development"],
     "keywords": ["process development", "manufacture development"]},

    # Level 3: 3.2.S.3
    {"code": "3.2.S.3", "title": "特性鉴定", "level": 3, "parent_code": "3.2.S",
     "aliases": ["s3", "characterisation", "characterization"],
     "keywords": ["characterisation", "characterization"]},
    {"code": "3.2.S.3.1", "title": "结构和理化性质", "level": 4, "parent_code": "3.2.S.3",
     "aliases": ["s3_1", "structure_elucidation", "physicochemical_properties"],
     "keywords": ["structure elucidation", "elucidation"]},
    {"code": "3.2.S.3.2", "title": "杂质", "level": 4, "parent_code": "3.2.S.3",
     "aliases": ["s3_2", "impurities"],
     "keywords": ["impurities", "impurity"]},

    # Level 3: 3.2.S.4
    {"code": "3.2.S.4", "title": "原料药的质量控制", "level": 3, "parent_code": "3.2.S",
     "aliases": ["s4", "quality_control"],
     "keywords": ["quality control"]},
    {"code": "3.2.S.4.1", "title": "质量标准", "level": 4, "parent_code": "3.2.S.4",
     "aliases": ["s4_1", "specification", "quality_standard"],
     "keywords": ["specification", "quality standard"]},
    {"code": "3.2.S.4.2", "title": "分析方法", "level": 4, "parent_code": "3.2.S.4",
     "aliases": ["s4_2", "analytical_procedures", "analytical_methods"],
     "keywords": ["analytical procedures", "analytical methods"]},
    {"code": "3.2.S.4.3", "title": "分析方法的验证", "level": 4, "parent_code": "3.2.S.4",
     "aliases": ["s4_3", "analytical_method_validation", "method_validation"],
     "keywords": ["validation", "analytical validation", "method validation"]},
    {"code": "3.2.S.4.4", "title": "批分析", "level": 4, "parent_code": "3.2.S.4",
     "aliases": ["s4_4", "batch_analysis", "batch_analyses"],
     "keywords": ["batch analysis", "batch analyses"]},
    {"code": "3.2.S.4.5", "title": "质量标准制定依据", "level": 4, "parent_code": "3.2.S.4",
     "aliases": ["s4_5", "justification_of_specification", "specification_justification"],
     "keywords": ["justification", "specification justification"]},

    # Level 3: 3.2.S.5
    {"code": "3.2.S.5", "title": "对照品", "level": 3, "parent_code": "3.2.S",
     "aliases": ["s5", "reference_standards", "reference_materials"],
     "keywords": ["reference standards", "reference materials"]},

    # Level 3: 3.2.S.6
    {"code": "3.2.S.6", "title": "包装系统", "level": 3, "parent_code": "3.2.S",
     "aliases": ["s6", "container_closure_system", "packaging_system"],
     "keywords": ["container closure", "packaging system"]},

    # Level 3: 3.2.S.7
    {"code": "3.2.S.7", "title": "稳定性", "level": 3, "parent_code": "3.2.S",
     "aliases": ["s7", "stability"],
     "keywords": ["stability"]},
    {"code": "3.2.S.7.1", "title": "稳定性总结和结论", "level": 4, "parent_code": "3.2.S.7",
     "aliases": ["s7_1", "stability_conclusion", "stability_summary"],
     "keywords": ["stability conclusion", "stability summary"]},
    {"code": "3.2.S.7.2", "title": "批准后稳定性研究方案和承诺", "level": 4, "parent_code": "3.2.S.7",
     "aliases": ["s7_2", "post_approval_stability_protocol", "stability_commitment"],
     "keywords": ["post approval", "stability commitment", "stability protocol"]},
    {"code": "3.2.S.7.3", "title": "稳定性数据", "level": 4, "parent_code": "3.2.S.7",
     "aliases": ["s7_3", "stability_data"],
     "keywords": ["stability data"]},
]


def get_chapter_by_code(code: str) -> Optional[Dict]:
    """根据章节编号获取章节定义"""
    for ch in M3_CHAPTERS:
        if ch["code"] == code:
            return ch
    return None


def get_children(parent_code: str) -> List[Dict]:
    """获取指定父章节的子章节"""
    return [ch for ch in M3_CHAPTERS if ch["parent_code"] == parent_code]


def match_file_to_chapter(filename: str) -> Optional[str]:
    """
    根据文件名匹配章节编号
    匹配优先级：
    1. 文件名精确匹配别名 (如 s4_3.docx)
    2. 文件名包含别名 (如 s4_3_method_validation.docx)
    3. 英文关键词匹配
    4. 章节编号匹配 (如 3-2-s-1-1, 3.2.s.1.1)
    """
    from pathlib import Path
    name = Path(filename).stem.lower().replace(' ', '_')

    # 第一优先级：精确匹配别名
    for ch in M3_CHAPTERS:
        for alias in ch.get("aliases", []):
            if name == alias.lower():
                return ch["code"]

    # 第二优先级：文件名包含别名
    best_match = None
    best_match_len = 0
    for ch in M3_CHAPTERS:
        for alias in ch.get("aliases", []):
            alias_lower = alias.lower()
            if alias_lower in name and len(alias_lower) > best_match_len:
                best_match = ch["code"]
                best_match_len = len(alias_lower)
    if best_match:
        return best_match

    # 第三优先级：英文关键词匹配
    for ch in M3_CHAPTERS:
        for kw in ch.get("keywords", []):
            if kw.lower() in name.replace('_', ' '):
                return ch["code"]

    # 第四优先级：章节编号匹配 (支持 3-2-s-1-1, 3.2.s.1.1, 3_2_s_1_1 等格式)
    import re
    # 提取文件名中的编号部分
    code_match = re.match(r'^(\d+[-._]\d+[-._][a-zA-Z]?[-._]\d+(?:[-._]\d+)*)', name)
    if code_match:
        code_str = code_match.group(1)
        # 标准化为 3.2.S.1.1 格式
        normalized = code_str.replace('-', '.').replace('_', '.').upper()
        # 查找匹配的章节
        for ch in M3_CHAPTERS:
            if ch["code"].upper() == normalized:
                return ch["code"]

    return None
