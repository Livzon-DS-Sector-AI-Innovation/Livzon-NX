"""ICH Q3C/Q3D 杂质识别服务 - 完整版"""

import json
import re
import tempfile
from pathlib import Path
from typing import Any

try:
    from docx import Document
except ImportError:
    Document = None


# 数据目录
DATA_DIR = Path(__file__).parent / "data"


def load_q3d_elements() -> dict:
    """加载 Q3D 元素数据库"""
    q3d_path = DATA_DIR / "q3d_elements.json"
    if q3d_path.exists():
        with open(q3d_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_q3c_solvents() -> dict:
    """加载 Q3C 溶剂数据库"""
    q3c_path = DATA_DIR / "ich-q3c-full.json"
    if q3c_path.exists():
        with open(q3c_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_solvent_synonyms() -> dict:
    """加载溶剂同义词数据库"""
    syn_path = DATA_DIR / "solvent-synonyms.json"
    if syn_path.exists():
        with open(syn_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# 加载数据
Q3D_DATA = load_q3d_elements()
Q3C_DATA = load_q3c_solvents()


def extract_text_from_docx(file_content: bytes) -> str:
    """从 DOCX 文件提取文本"""
    if Document is None:
        raise ImportError("python-docx not installed")
    
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(file_content)
        tmp_path = tmp.name
    
    try:
        doc = Document(tmp_path)
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def parse_process_steps(text: str) -> list[dict]:
    """解析工艺步骤
    
    支持的格式：
    - 步骤1: ...
    - Step 1: ...
    - 1. ...
    - (1) ...
    """
    steps = []
    
    # 尝试多种步骤格式
    patterns = [
        r'(?:步骤|Step)\s*(\d+)[：:]\s*(.+?)(?=(?:步骤|Step)\s*\d+[：:]|$)',
        r'(\d+)[.、]\s*(.+?)(?=\d+[.、]|$)',
        r'\((\d+)\)\s*(.+?)(?=\(\d+\)|$)',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
        if matches:
            for step_num, step_content in matches:
                steps.append({
                    "step_number": int(step_num),
                    "content": step_content.strip(),
                })
            break
    
    # 如果没有匹配到步骤格式，将整个文本作为一个步骤
    if not steps:
        steps.append({
            "step_number": 1,
            "content": text,
        })
    
    return steps


def remove_concentration_prefix(solvent_name: str) -> str:
    """去除浓度前缀
    
    例如：
    - 95%乙醇 → 乙醇
    - 无水乙醇 → 乙醇
    - Absolute ethanol → ethanol
    """
    # 去除百分比前缀
    solvent_name = re.sub(r'^\d+%?\s*', '', solvent_name)
    
    # 去除浓度描述
    prefixes = ['无水', '绝对', 'Absolute', 'Anhydrous', '干燥']
    for prefix in prefixes:
        if solvent_name.startswith(prefix):
            solvent_name = solvent_name[len(prefix):].strip()
    
    return solvent_name.strip()


def get_element_data(symbol: str) -> dict:
    """获取元素数据"""
    for class_name, class_data in Q3D_DATA.get("classes", {}).items():
        elements = class_data.get("elements", {})
        if symbol in elements:
            return {"class": class_name, **elements[symbol]}
    return {}


def get_all_mandatory_elements() -> dict:
    """Get all elements that must be assessed per ICH Q3D(R2) Table 5.1."""
    mandatory = {}
    for class_name, class_data in Q3D_DATA.get("classes", {}).items():
        if class_name in ("Class 1", "Class 2A", "Class 3"):
            for symbol, data in class_data.get("elements", {}).items():
                if class_name in ("Class 1", "Class 2A"):
                    oral_assess = parenteral_assess = inhalation_assess = cutaneous_assess = True
                else:  # Class 3
                    oral_assess = False
                    parenteral_assess = data.get("parenteral_assess", True)
                    inhalation_assess = data.get("inhalation_assess", True)
                    cutaneous_assess = data.get("cutaneous_assess", False)
                
                mandatory[symbol] = {
                    "source": "起始物料、辅料、工艺用水或设备中的潜在杂质",
                    "intentionally_added": False,
                    "assessment_required": True,
                    "q3d_class": class_name,
                    "oral_pde": data.get("oral_pde"),
                    "parenteral_pde": data.get("parenteral_pde"),
                    "inhalation_pde": data.get("inhalation_pde"),
                    "cutaneous_pde": data.get("cutaneous_pde"),
                    "ctcl": data.get("ctcl"),
                    "oral_assess": oral_assess,
                    "parenteral_assess": parenteral_assess,
                    "inhalation_assess": inhalation_assess,
                    "cutaneous_assess": cutaneous_assess,
                    "notes": data.get("notes", ""),
                }
    return mandatory


def get_option1_concentrations(symbol: str) -> dict:
    """Get Option 1 permitted concentrations for an element (ICH Q3D Table 1)."""
    option1_data = Q3D_DATA.get("option_1_concentrations", {})
    return option1_data.get("elements", {}).get(symbol, {})


def identify_elements(llm_response: dict) -> dict:
    """Build element assessment from LLM-identified elements + Q3D rules.
    
    LLM only needs to identify:
    - symbol: Element symbol
    - source: Where it comes from in the process
    - intentionally_added: true if catalyst/reagent, false if equipment/impurity
    
    Script decides everything else based on Q3D rules:
    - Class 1, 2A: Always assess all routes
    - Class 3: Assess based on per-element flags in q3d_elements.json
    - Class 2B: Assess only if intentionally added
    - Other: Assess only if intentionally added
    """
    # Start with all mandatory elements (Class 1, 2A, 3)
    elements_found = get_all_mandatory_elements()
    
    # Track which elements LLM identified as intentionally added
    llm_intentionally_added = set()
    llm_sources = {}
    
    for elem_data in llm_response.get("elements", []):
        symbol = elem_data.get("symbol", "")
        if not symbol:
            continue
        
        # Track LLM's source description
        if elem_data.get("source"):
            llm_sources[symbol] = elem_data["source"]
        
        # Track intentionally added status from LLM
        if elem_data.get("intentionally_added", False):
            llm_intentionally_added.add(symbol)
    
    # Update mandatory elements with LLM source info
    for symbol in elements_found:
        if symbol in llm_sources:
            elements_found[symbol]["source"] = llm_sources[symbol]
        # If LLM says it's intentionally added, update that too
        if symbol in llm_intentionally_added:
            elements_found[symbol]["intentionally_added"] = True
    
    # Add intentionally added "Other" class elements
    for symbol in llm_intentionally_added:
        if symbol not in elements_found:
            # Look up in q3d_elements.json
            hardcoded = get_element_data(symbol)
            if hardcoded:
                # It's in our database
                q3d_class = hardcoded.get("class", "Other")
                if q3d_class == "Other":
                    elements_found[symbol] = {
                        "source": llm_sources.get(symbol, "有意添加的试剂/催化剂"),
                        "intentionally_added": True,
                        "assessment_required": True,
                        "q3d_class": "Other",
                        "oral_pde": hardcoded.get("oral_pde"),
                        "parenteral_pde": hardcoded.get("parenteral_pde"),
                        "inhalation_pde": hardcoded.get("inhalation_pde"),
                        "cutaneous_pde": hardcoded.get("cutaneous_pde"),
                        "ctcl": hardcoded.get("ctcl"),
                        "notes": hardcoded.get("notes", ""),
                    }
            else:
                # Not in database at all - still include if intentionally added
                elements_found[symbol] = {
                    "source": llm_sources.get(symbol, "有意添加的试剂/催化剂"),
                    "intentionally_added": True,
                    "assessment_required": True,
                    "q3d_class": "Other",
                    "oral_pde": None,
                    "parenteral_pde": None,
                    "inhalation_pde": None,
                    "cutaneous_pde": None,
                    "ctcl": None,
                    "notes": "该元素不在ICH Q3D范围内，未建立PDE。需要逐案进行毒理学论证。",
                }
    
    return elements_found


def generate_report(process_text: str, elements: dict) -> str:
    """Generate ICH Q3D report from skill's generate_report, returns markdown string."""
    from datetime import datetime
    
    report = []
    report.append("# 元素杂质评估报告")
    report.append("")
    report.append("**评估依据：** ICH Q3D(R2) 元素杂质指导原则")
    report.append(f"**生成日期：** {datetime.now().strftime('%Y-%m-%d')}")
    report.append("")
    report.append("---")
    report.append("")
    report.append("## 计算方法说明")
    report.append("")
    report.append("**本报告仅采用选项1：** 日剂量≤10g的药品各组分通用允许浓度")
    report.append("- 公式：Concentration (μg/g) = PDE (μg/day) / 10 (g/day)")
    report.append("")
    report.append("**注意：** 本报告中所有浓度限度（μg/g）均基于选项1计算得出。选项2a、2b和3不在本评估范围内。")
    report.append("")
    report.append("---")
    report.append("")

    # Sort by class priority
    class_priority = {"Class 1": 1, "Class 2A": 2, "Class 2B": 3, "Class 3": 4, "Other": 5}
    sorted_elements = sorted(elements.items(), key=lambda x: class_priority.get(x[1].get("q3d_class", ""), 99))

    # Summary table
    report.append("## 风险评估汇总")
    report.append("")
    report.append("| 元素 | Q3D类别 | 有意添加 | 口服 | 注射 | 吸入 | 皮肤 |")
    report.append("|------|---------|----------|------|------|------|------|")

    for symbol, data in sorted_elements:
        q3d_class = data.get("q3d_class", "")
        intentionally = "是" if data.get("intentionally_added") else "否"

        if q3d_class == "Other":
            oral = parenteral = inhalation = cutaneous = "逐案评估"
        elif q3d_class in ("Class 1", "Class 2A"):
            oral = parenteral = inhalation = cutaneous = "需要"
        elif q3d_class == "Class 2B":
            if data.get("intentionally_added"):
                oral = parenteral = inhalation = cutaneous = "需要"
            else:
                oral = parenteral = inhalation = cutaneous = "不需要"
        elif q3d_class == "Class 3":
            if data.get("intentionally_added"):
                oral = parenteral = inhalation = cutaneous = "需要"
            else:
                oral = "不需要" if not data.get("oral_assess") else "需要"
                parenteral = "不需要" if not data.get("parenteral_assess") else "需要"
                inhalation = "不需要" if not data.get("inhalation_assess") else "需要"
                cutaneous = "不需要" if not data.get("cutaneous_assess") else "需要"
        else:
            oral = parenteral = inhalation = cutaneous = "需要" if data.get("assessment_required") else "不需要"
        report.append(f"| {symbol} | {q3d_class} | {intentionally} | {oral} | {parenteral} | {inhalation} | {cutaneous} |")

    report.append("")
    report.append("---")
    report.append("")
    report.append("## 元素杂质评估")
    report.append("")

    for symbol, data in sorted_elements:
        q3d_class = data.get("q3d_class", "")
        hardcoded = get_element_data(symbol)
        source = data.get("source", "Unknown")
        intentionally = data.get("intentionally_added", False)

        report.append(f"### {symbol}")
        report.append("")
        report.append("**基本信息**")
        report.append("")
        report.append("| 属性 | 详情 |")
        report.append("|------|------|")
        report.append(f"| **Q3D类别** | {q3d_class} |")
        report.append(f"| **来源** | {source} |")
        report.append(f"| **有意添加** | {'是' if intentionally else '否'} |")

        notes = data.get("notes") or hardcoded.get("notes", "")
        if notes:
            report.append(f"| **备注** | {notes} |")
        report.append("")

        # PDE values
        oral = data.get("oral_pde")
        parenteral = data.get("parenteral_pde")
        inhalation = data.get("inhalation_pde")
        cutaneous = data.get("cutaneous_pde")

        option1 = get_option1_concentrations(symbol)
        cutaneous_option1 = cutaneous / 10 if cutaneous is not None else None

        report.append("**PDE值与选项1限度**")
        report.append("")
        report.append("| 途径 | PDE (μg/天) | 选项1限度 (μg/g) |")
        report.append("|------|-------------|------------------|")
        report.append(f"| 口服 | {oral if oral is not None else '未建立'} | {option1.get('oral', 'N/A') if option1 else 'N/A'} |")
        report.append(f"| 注射 | {parenteral if parenteral is not None else '未建立'} | {option1.get('parenteral', 'N/A') if option1 else 'N/A'} |")
        report.append(f"| 吸入 | {inhalation if inhalation is not None else '未建立'} | {option1.get('inhalation', 'N/A') if option1 else 'N/A'} |")
        report.append(f"| 皮肤 | {cutaneous if cutaneous is not None else '未建立'} | {cutaneous_option1 if cutaneous_option1 is not None else 'N/A'} |")
        report.append("")

        # CTCL for Ni and Co
        ctcl = data.get("ctcl") or hardcoded.get("ctcl")
        if ctcl:
            report.append("**皮肤途径**")
            report.append("")
            report.append(f"- 皮肤PDE = {cutaneous} μg/天（Table A.5.1）")
            report.append(f"- 皮肤选项1限度 = {cutaneous_option1} μg/g")
            report.append(f"- 皮肤毒性浓度限度（CTCL）= {ctcl} μg/g")
            report.append("")
        elif cutaneous is not None and q3d_class != "Other":
            report.append("**皮肤途径**")
            report.append("")
            report.append(f"- 皮肤PDE = {cutaneous} μg/天（Table A.5.1）")
            report.append(f"- 皮肤选项1限度 = {cutaneous_option1} μg/g")
            report.append("")

        # Assessment logic
        if q3d_class == "Class 1":
            report.append("**评估：** 1类元素必须在风险评估中评估所有潜在来源和给药途径。")
        elif q3d_class == "Class 2A":
            report.append("**评估：** 2A类元素出现概率较高，需要对所有潜在来源进行风险评估。")
        elif q3d_class == "Class 2B":
            if intentionally:
                report.append("**评估：** 2B类元素有意添加，需要评估。")
            else:
                report.append("**评估：** 2B类元素未有意添加，可从风险评估中排除。")
        elif q3d_class == "Class 3":
            if intentionally:
                report.append("**评估：** 3类元素有意添加，需要评估。")
            else:
                parts = []
                if data.get("oral_assess"):
                    parts.append("口服途径需评估")
                else:
                    parts.append("口服途径无需评估")
                if data.get("parenteral_assess"):
                    parts.append("注射途径需评估")
                else:
                    parts.append("注射途径无需评估")
                if data.get("inhalation_assess"):
                    parts.append("吸入途径需评估")
                else:
                    parts.append("吸入途径无需评估")
                if data.get("cutaneous_assess"):
                    parts.append("皮肤途径需评估")
                else:
                    parts.append("皮肤途径无需评估")
                report.append("**评估：** " + "；".join(parts) + "。")
        elif q3d_class == "Other":
            report.append("**评估：** 该元素不在ICH Q3D范围内，未建立PDE。需要逐案进行毒理学论证。")

        report.append("")

    report.append("")
    report.append("---")
    report.append("")
    report.append("## 关键要点")
    report.append("")

    counts = {"Class 1": 0, "Class 2A": 0, "Class 2B": 0, "Class 3": 0, "Other": 0}
    for _, d in elements.items():
        cls = d.get("q3d_class", "")
        if cls in counts:
            counts[cls] += 1

    report.append(f"1. 识别出 {len(elements)} 个元素杂质需要关注")
    if counts["Class 1"] > 0:
        report.append(f"2. {counts['Class 1']} 个1类元素必须评估所有来源和给药途径")
    if counts["Class 2A"] > 0:
        report.append(f"3. {counts['Class 2A']} 个2A类元素需要评估所有潜在来源")
    if counts["Class 2B"] > 0:
        report.append(f"4. {counts['Class 2B']} 个2B类元素（仅有意添加时需要评估）")
    if counts["Class 3"] > 0:
        report.append(f"5. {counts['Class 3']} 个3类元素（口服途径除非有意添加否则无需评估）")
    if counts["Other"] > 0:
        report.append(f"6. {counts['Other']} 个元素不在Q3D范围内，需要单独毒理学论证")

    report.append("")
    report.append("---")
    report.append("")
    report.append("## 特殊考虑")
    report.append("")
    report.append("### 控制阈值")
    report.append("")
    report.append("- 控制阈值 = **30% of PDE**")
    report.append("- 如果药品中元素杂质总量持续低于控制阈值，则无需额外控制措施")
    report.append("")
    report.append("### 皮肤/经皮给药途径（附录5）")
    report.append("")
    report.append("- 皮肤PDE = 注射PDE × CMF（转换系数）")
    report.append("- 默认CMF = 10（As的CMF = 2，Tl的CMF = 1）")
    report.append("- Ni和Co的皮肤毒性浓度限度（CTCL）= 35 μg/g")
    report.append("- 控制阈值 = 30% of PDE AND 30% of CTCL")
    report.append("")
    report.append("### 形态分析")
    report.append("")
    report.append("- 可使用总元素含量评估合规性")
    report.append("- 如已知特定形态毒性不同，可调整限度")
    report.append("")
    report.append("### 生命周期管理")
    report.append("")
    report.append("以下变更可能改变元素杂质含量，需重新评估：")
    report.append("- 合成路线变更")
    report.append("- 辅料供应商变更")
    report.append("- 设备变更")
    report.append("- 容器密封系统变更")
    report.append("")
    report.append("---")
    report.append("")
    report.append("## 参考文献")
    report.append("")
    report.append("- ICH Q3D(R2) 元素杂质指导原则（2022年4月）")
    report.append("")

    return "\n".join(report)


def _add_frontend_fields(elements: dict, llm_response: dict) -> dict:
    """Add fields needed by frontend table display.
    
    The skill's identify_elements returns dict keyed by symbol,
    but frontend needs:
    - symbol field on each element
    - found_in_text flag
    - needs_assessment boolean (computed per Q3D rules)
    """
    llm_symbols = set()
    for elem_data in llm_response.get("elements", []):
        symbol = elem_data.get("symbol", "")
        if symbol:
            llm_symbols.add(symbol)
    
    for symbol, data in elements.items():
        # Add symbol field
        data["symbol"] = symbol
        
        # Add found_in_text flag
        data["found_in_text"] = symbol in llm_symbols
        
        # Compute needs_assessment based on Q3D class rules
        q3d_class = data.get("q3d_class", "")
        intentionally = data.get("intentionally_added", False)
        
        if q3d_class in ("Class 1", "Class 2A"):
            # Always need assessment
            data["needs_assessment"] = True
        elif q3d_class == "Class 2B":
            # Only if intentionally added
            data["needs_assessment"] = intentionally
        elif q3d_class == "Class 3":
            # Per-element flags if not intentionally added, otherwise all
            if intentionally:
                data["needs_assessment"] = True
            else:
                # At least one route needs assessment
                data["needs_assessment"] = (
                    data.get("oral_assess", False) or
                    data.get("parenteral_assess", False) or
                    data.get("inhalation_assess", False) or
                    data.get("cutaneous_assess", False)
                )
        elif q3d_class == "Other":
            # Only if intentionally added
            data["needs_assessment"] = intentionally
        else:
            data["needs_assessment"] = data.get("assessment_required", False)
    
    return elements


async def analyze_ich_q3d_with_llm(file_content: bytes) -> dict:
    """Analyze ICH Q3D elemental impurities using LLM.
    
    LLM only identifies elements (symbol, source, intentionally_added).
    Script applies Q3D rules from q3d_elements.json.
    """
    from app.modules.research.llm_service import extract_elements_with_llm
    
    # Extract text from DOCX
    text = extract_text_from_docx(file_content)
    steps = parse_process_steps(text)
    
    # LLM extracts elements
    llm_elements = await extract_elements_with_llm(text)
    
    # Build element assessment using skill's identify_elements
    elements_dict = identify_elements({"elements": llm_elements})
    
    # Add frontend-specific fields
    elements_dict = _add_frontend_fields(elements_dict, {"elements": llm_elements})
    
    # Convert to list for JSON serialization
    elements_list = list(elements_dict.values())
    
    # Generate markdown report
    report = generate_report(text, elements_dict)
    
    # Count elements needing assessment
    needs_assessment_count = sum(1 for e in elements_list if e.get("needs_assessment"))
    
    # Count by class
    class_counts = {"Class 1": 0, "Class 2A": 0, "Class 2B": 0, "Class 3": 0, "Other": 0}
    for elem in elements_list:
        q3d_class = elem.get("q3d_class", "")
        if q3d_class in class_counts:
            class_counts[q3d_class] += 1
    
    return {
        "type": "Q3D",
        "text_length": len(text),
        "steps_count": len(steps),
        "elements_found": elements_list,
        "total_elements": len(elements_list),
        "needs_assessment": needs_assessment_count,
        "summary": {
            "class_1": class_counts["Class 1"],
            "class_2a": class_counts["Class 2A"],
            "class_2b": class_counts["Class 2B"],
            "class_3": class_counts["Class 3"],
            "other": class_counts["Other"]
        },
        "report": report,
        "llm_used": True,
        "llm_elements_count": len(llm_elements)
    }


async def analyze_ich_q3c_with_llm(file_content: bytes) -> dict:
    """Analyze ICH Q3C solvent residues using LLM (skill's pipeline).
    
    LLM extracts AND classifies solvents using the full ICH Q3C database.
    Script enriches with PDE/limit values from database and generates report.
    """
    from app.modules.research.llm_service import extract_solvents_with_llm
    from app.modules.research.q3c_solvent_match import (
        load_synonyms, build_solvent_index, classify_solvents
    )
    from app.modules.research.q3c_report_gen import generate_q3c_report
    
    # 1. Extract text and parse steps
    text = extract_text_from_docx(file_content)
    steps = parse_process_steps(text)
    
    # 2. LLM extracts and classifies solvents (step-based structure)
    llm_result = await extract_solvents_with_llm(steps)
    
    # 3. Build solvent index for enrichment
    synonyms = load_synonyms()
    ich_data = Q3C_DATA
    solvent_index = build_solvent_index(ich_data, synonyms)
    
    # 4. Process each step's solvents
    step_analysis = []
    all_solvents = {}
    
    for step_data in llm_result.get("steps", []):
        step_number = step_data.get("step_number", "")
        step_title = step_data.get("step_title", "")
        
        # Collect solvents for this step
        raw_solvents = []
        for solvent_info in step_data.get("solvents", []):
            matched_name = solvent_info.get("matched_name") or solvent_info.get("original_name", "")
            original_name = solvent_info.get("original_name", matched_name)
            ich_class = solvent_info.get("ich_class", "Unlisted")
            
            if not matched_name:
                continue
            
            raw_solvents.append({
                "solvent": matched_name,
                "original_name": original_name,
                "ich_class": ich_class,
                "purpose": solvent_info.get("purpose", ""),
                "amount": solvent_info.get("amount")
            })
        
        # Classify and enrich with PDE/limit
        classified = classify_solvents(raw_solvents, solvent_index)
        
        step_analysis.append({
            "step_number": step_number,
            "step_title": step_title,
            "solvents": classified,
            "solvent_count": len(classified)
        })
        
        # Aggregate all solvents
        for solvent_entry in classified:
            solvent_name = solvent_entry["solvent"]
            if solvent_name not in all_solvents:
                all_solvents[solvent_name] = {
                    **solvent_entry,
                    "steps_used": []
                }
            all_solvents[solvent_name]["steps_used"].append(step_number)
    
    # 5. Build analysis structure for report generation
    analysis = {
        "step_analysis": step_analysis,
        "all_solvents": all_solvents,
        "total_unique_solvents": len(all_solvents),
        "extraction_method": "llm"
    }
    
    # 6. Generate markdown report
    report = generate_q3c_report(analysis, flag_class1=True, ich_data_source="ICH Q3C(R9) 数据库")
    
    # 7. Convert to frontend format (flat list)
    solvents_list = []
    for solvent_name, data in all_solvents.items():
        solvents_list.append({
            "name_en": data.get("solvent", solvent_name),
            "name_cn": data.get("original_name", solvent_name),
            "class": data.get("class", "Unknown"),
            "limit_ppm": data.get("limit"),
            "pde_mg_day": data.get("pde"),
            "purpose": data.get("purpose", ""),
            "found_in_text": True,
            "steps_used": data.get("steps_used", [])
        })
    
    # 8. Compute summary
    summary = {"class_1": 0, "class_2": 0, "class_3": 0, "unknown": 0}
    for solv in solvents_list:
        cls = solv.get("class", "")
        if "1" in str(cls):
            summary["class_1"] += 1
        elif "2" in str(cls):
            summary["class_2"] += 1
        elif "3" in str(cls):
            summary["class_3"] += 1
        else:
            summary["unknown"] += 1
    
    return {
        "type": "Q3C",
        "text_length": len(text),
        "steps_count": len(steps),
        "solvents_found": solvents_list,
        "total_solvents": len(solvents_list),
        "summary": summary,
        "report": report,
        "step_analysis": step_analysis,
        "llm_used": True,
        "llm_solvents_count": len(solvents_list)
    }

