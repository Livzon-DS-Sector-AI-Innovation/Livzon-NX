#!/usr/bin/env python3
"""
Generate Markdown compliance report from solvent analysis.
"""

import sys
import json
import os
import re
from datetime import datetime


def load_solvent_synonyms():
    """Load solvent synonyms including Chinese names."""
    try:
        from app.modules.research.ich_service import DATA_DIR
        synonyms_file = DATA_DIR / "solvent-synonyms.json"
        if synonyms_file.exists():
            with open(synonyms_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def get_chinese_name(solvent_name, synonyms):
    """Get Chinese name for a solvent if available."""
    # Normalize solvent name for lookup
    normalized = solvent_name.lower().strip()
    
    # Check if this solvent has synonyms
    if normalized in synonyms:
        synonym_list = synonyms[normalized]
        # Find Chinese name (contains Chinese characters)
        for synonym in synonym_list:
            # Check if contains Chinese characters
            if any('\u4e00' <= char <= '\u9fff' for char in synonym):
                return synonym
    return solvent_name  # Return original if no Chinese name found


def generate_q3c_report(analysis, flag_class1=True, ich_data_source=""):
    """
    Generate Markdown report from analysis results.
    
    Follows the three-section structure per SKILL.md specification:
    1. 各步骤使用的溶剂
    2. 需要控制的溶剂
       2.1 批批检验
       2.2 10% 标准 - 仅工艺控制
    3. 推荐测试方法
    
    Args:
        analysis: Output from solvent_match.py
        flag_class1: Whether to highlight Class 1 violations
        ich_data_source: Source of ICH data (for documentation)
    
    Returns:
        Markdown string (in Chinese)
    """
    lines = []
    
    # Load solvent synonyms for Chinese names
    synonyms = load_solvent_synonyms()
    
    # Header
    lines.append("# ICH Q3C 溶剂残留合规报告")
    lines.append("")
    lines.append(f"**生成时间:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**ICH 数据来源:** {ich_data_source or '预提取 ICH Q3C(R9) 数据'}")
    lines.append("")
    
    all_solvents = analysis.get("all_solvents", {})
    step_analysis = analysis.get("step_analysis", [])
    
    # Count by class
    class_counts = {"class1": 0, "class2": 0, "class3": 0, "unknown": 0}
    for solvent in all_solvents.values():
        class_counts[solvent["class"]] += 1
    
    # Class 1 warning
    if flag_class1 and class_counts["class1"] > 0:
        lines.append("⚠️ **合规问题:** 检出 {} 种 Class 1 溶剂!".format(class_counts['class1']))
        lines.append("")
        lines.append("**根据 ICH Q3C 第 3.1 节:** Class 1 溶剂不应使用，除非能提供**强有力的科学依据**,即使残留量低于限值。")
        lines.append("")
    
    # ============================================================
    # Section 1: Solvents Used in Each Step
    # ============================================================
    lines.append("## 1. 各步骤使用的溶剂")
    lines.append("")
    
    # Build step title map from step_analysis
    step_titles = {}
    for step_info in step_analysis:
        step_num = step_info.get("step_number", "")
        step_title = step_info.get("step_title", "")
        step_titles[step_num] = step_title
    
    # Group solvents by step, deduplicate within each step
    step_solvents = {}
    for solvent_name, data in all_solvents.items():
        solvent_english = data.get("canonical") or data.get("solvent") or solvent_name
        solvent_display = get_chinese_name(solvent_english, synonyms)
        class_display = data["class"].replace("class", "Class ") if data["class"] != "unknown" else "未列出"
        limit = data.get("limit") or "N/A"
        # Convert limit to string for consistent display
        if isinstance(limit, int):
            limit = str(limit)
        # Deduplicate steps_used
        steps_unique = list(dict.fromkeys(data["steps_used"]))
        for step in steps_unique:
            if step not in step_solvents:
                step_solvents[step] = []
            step_solvents[step].append({
                "solvent": solvent_display,
                "class": class_display,
                "limit": limit
            })
    
    # Generate separate table for each step
    for step in sorted(step_solvents.keys()):
        solvents_in_step = step_solvents[step]
        description = step_titles.get(step, "")
        
        lines.append(f"### {step}: {description}")
        lines.append("")
        lines.append("| 溶剂 | ICH 类别 | ICH 限值 (ppm) |")
        lines.append("|------|----------|---------------|")
        
        # Sort solvents within step for consistent output
        for s in sorted(solvents_in_step, key=lambda x: x["solvent"]):
            lines.append(f"| {s['solvent']} | {s['class']} | {s['limit']} |")
        
        lines.append("")
    
    # ============================================================
    # Section 2: Solvents to Be Controlled
    # ============================================================
    lines.append("## 2. 需要控制的溶剂")
    lines.append("")
    
    # Determine final step (last step in synthesis)
    final_step = None
    if step_analysis:
        # Get the last step number
        final_step = step_analysis[-1].get("step_number")
    
    # Categorize solvents: Routine Release vs 10% Criteria
    routine_release = []
    dev_control_10pct = []
    
    for solvent_name, data in all_solvents.items():
        if data["class"] not in ["class2", "class3"]:
            continue
            
        solvent_english = data.get("canonical") or data.get("solvent") or solvent_name
        solvent_display = get_chinese_name(solvent_english, synonyms)
        class_display = data["class"].replace("class", "Class ")
        limit = data.get("limit")
        steps_used = data["steps_used"]
        
        # Check if used in final step
        in_final_step = final_step in steps_used if final_step else False
        
        if in_final_step:
            # Routine release: used in final step
            routine_release.append({
                "solvent": solvent_display,
                "class": class_display,
                "limit": limit or "N/A",
                "reason": f"用于最终步骤 ({final_step})"
            })
        else:
            # 10% criteria: used in early steps only (Class 2 AND Class 3)
            if limit and limit != "N/A":
                try:
                    # Convert to string first (limit might be int or "720 ppm" format)
                    limit_str = str(limit)
                    match = re.search(r'(\d+)', limit_str)
                    if match:
                        limit_val = float(match.group(1))
                        threshold = limit_val * 0.1
                        # Deduplicate steps for display
                        steps_unique = list(dict.fromkeys(steps_used))
                        dev_control_10pct.append({
                            "solvent": solvent_display,
                            "class": class_display,
                            "limit": limit,
                            "threshold": f"{threshold:.1f}",
                            "reason": f"用于早期步骤 ({', '.join(steps_unique)})"
                        })
                except (ValueError, TypeError):
                    pass
    
    lines.append("### 2.1 批批检验 (Routine Release)")
    lines.append("")
    lines.append("| 溶剂 | ICH 类别 | 限值 (ppm) | 原因 |")
    lines.append("|------|----------|-----------|------|")
    
    if routine_release:
        for item in routine_release:
            lines.append(f"| {item['solvent']} | {item['class']} | {item['limit']} | {item['reason']} |")
    else:
        lines.append("| - | - | - | 无溶剂需要批批检验 |")
    
    lines.append("")
    
    lines.append("### 2.2 10% 标准 - 仅工艺控制 (Development Control)")
    lines.append("")
    lines.append("如有代表性数据证明残留量 ≤ ICH 限值的 10%,以下溶剂可豁免批批检验:")
    lines.append("")
    lines.append("| 溶剂 | ICH 类别 | ICH 限值 (ppm) | 10% 阈值 (ppm) | 原因 |")
    lines.append("|------|----------|--------------|-------------|------|")
    
    if dev_control_10pct:
        for item in dev_control_10pct:
            lines.append(f"| {item['solvent']} | {item['class']} | {item['limit']} | {item['threshold']} | {item['reason']} |")
    else:
        lines.append("| - | - | - | - | No solvents qualify for development control only |")
    
    lines.append("")
    
    # ============================================================
    # Section 3: Recommended Testing Methods
    # ============================================================
    lines.append("## 3. 推荐测试方法")
    lines.append("")
    
    # Determine solvent classes present
    has_class2 = class_counts["class2"] > 0
    has_class3 = class_counts["class3"] > 0
    
    # Simple rule-based strategy
    if has_class2 and has_class3:
        strategy = "Class 2 用 GC, Class 3 可用 GC 或 LOD"
        rationale = "Class 2 溶剂必须用 GC 测试;Class 3 溶剂可用 GC 或 LOD ≤0.5%"
    elif has_class2:
        strategy = "全部溶剂使用 GC"
        rationale = "仅含 Class 2 溶剂，必须使用 GC"
    elif has_class3:
        strategy = "GC 或 LOD ≤0.5%"
        rationale = "仅含 Class 3 溶剂，两种方法均可接受"
    else:
        strategy = "N/A"
        rationale = "未检出 Class 2 或 Class 3 溶剂"
    
    lines.append(f"**测试策略:** {strategy}")
    lines.append("")
    lines.append(f"**依据:** {rationale}")
    lines.append("")
    
    lines.append("| 溶剂 | ICH 类别 | 推荐方法 |")
    lines.append("|------|----------|----------|")
    
    # Sort solvents for consistent output
    sort_order = {"class1": 0, "class2": 1, "class3": 2, "unknown": 3}
    sorted_solvents = sorted(
        all_solvents.items(),
        key=lambda x: (sort_order.get(x[1]["class"], 3), x[0])
    )
    
    for solvent_name, data in sorted_solvents:
        if data["class"] not in ["class2", "class3"]:
            continue
            
        solvent_english = data.get("canonical") or data.get("solvent") or solvent_name
        solvent_display = get_chinese_name(solvent_english, synonyms)
        
        if data["class"] == "class2":
            method = "GC (定量分析)"
        else:  # class3
            method = "LOD ≤0.5% 或 GC"
        
        lines.append(f"| {solvent_display} | {data['class'].replace('class', 'Class ')} | {method} |")
    
    lines.append("")
    
    # Add general recommendations
    lines.append("### 说明:")
    lines.append("")
    lines.append("- **Class 2 溶剂:** 根据 ICH Q3C 第 3.5 节，必须使用 GC 进行定量测试")
    lines.append("- **Class 3 溶剂:** 根据 ICH Q3C 第 3.5 节，LOD ≤0.5% 可接受，或使用已验证的 GC 方法")
    lines.append("- **10% 标准:** 第 2.2 节中的溶剂可通过工艺开发阶段控制，提供代表性数据证明残留量持续 ≤10% ICH 限值，可豁免批批检验。根据 EMA/EDQM CEP 要求，代表性数据需来自 **6 批连续中试规模批次** 或 **3 批连续工业生产规模批次** (EMA Annex I, CPMP/QWP/450/03-Rev.1)")
    lines.append("")
    
    # Unknown solvents section
    
    # Unknown solvents section
    if class_counts["unknown"] > 0:
        lines.append("## 未列入 ICH Q3C 的溶剂")
        lines.append("")
        lines.append("以下溶剂未在 ICH Q3C 指南中列出，需要额外评估:")
        lines.append("")
        
        for solvent_name, data in all_solvents.items():
            if data["class"] == "unknown":
                solvent_english = data.get("canonical") or data.get("solvent") or solvent_name
                solvent_display = get_chinese_name(solvent_english, synonyms)
                matched_as = data.get("matched_as", solvent_name)
                lines.append(f"- **{solvent_display}** (匹配为：{matched_as})")
        
        lines.append("")
        lines.append("**注意:** 这些溶剂可能需要根据 ICH Q3C 第 5 节进行毒理学评估。")
        lines.append("")
    
    # When to consult original documents
    needs_consultation = []
    if class_counts["class1"] > 0:
        needs_consultation.append("检出 Class 1 溶剂 (需要根据 ICH Q3C 第 3.1 节提供获益/风险评估依据)")
    if class_counts["unknown"] > 0:
        needs_consultation.append("未列出溶剂需要根据 ICH Q3C 第 5 节进行毒理学评估")
    
    if needs_consultation:
        lines.append("## ⚠️ 需要查阅原始监管文件")
        lines.append("")
        lines.append("以下项目需要查阅原始监管文件:")
        lines.append("")
        for item in needs_consultation:
            lines.append(f"- {item}")
        lines.append("")
        lines.append("**参考文件:**")
        lines.append("- ICH Q3C(R9): https://database.ich.org/sites/default/files/ICH_Q3C-R9_Guideline_2024_2024_Approved.pdf")
        lines.append("- EMA/EDQM CEP: PA/PH/CEP (04) 1, 7R (2024 年 3 月)")
        lines.append("")
    
    lines.append("---")
    lines.append("*报告由 ich-solvent-analysis 技能生成*")
    
    return "\n".join(lines)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate ICH Q3C compliance report")
    parser.add_argument("analysis_json", help="Path to analysis JSON from solvent_match.py")
    parser.add_argument("-o", "--output", default="-", help="Output file (default: stdout)")
    parser.add_argument("--no-flag-class1", action="store_true", help="Don't highlight Class 1 violations")
    parser.add_argument("--ich-data-source", default="", help="Source of ICH data for documentation")
    
    args = parser.parse_args()
    
    # Load analysis
    with open(args.analysis_json, 'r') as f:
        analysis = json.load(f)
    
    # Generate report
    report = generate_q3c_report(
        analysis,
        flag_class1=not args.no_flag_class1,
        ich_data_source=args.ich_data_source
    )
    
    # Output
    if args.output == "-":
        print(report)
    else:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"Report saved to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
