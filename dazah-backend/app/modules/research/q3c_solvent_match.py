#!/usr/bin/env python3
"""
Classify LLM-extracted solvents against ICH Q3C database.

This script receives solvent names from llm_extract.py and classifies them
against the ICH Q3C(R9) database.
"""

import sys
import json
from pathlib import Path


def load_synonyms():
    """Load solvent synonym database."""
    try:
        from app.modules.research.ich_service import DATA_DIR
        synonym_file = DATA_DIR / "solvent-synonyms.json"
        if synonym_file.exists():
            with open(synonym_file, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def build_solvent_index(ich_data, synonyms):
    """
    Build a searchable index of solvents from ICH data and synonyms.
    
    Returns:
    {
        "normalized_name": {
            "canonical": "official ICH name",
            "class": "class1|class2|class3",
            "pde": "...",
            "limit": "...",
            "aliases": [...]
        }
    }
    """
    index = {}
    
    # Handle both flat structure and nested structure (from ich-q3c-full.json)
    classes_data = ich_data.get("classes", ich_data)
    
    # Add solvents from ICH classes
    for class_name in ["class1", "class2", "class3"]:
        class_solvents = classes_data.get(class_name, {})
        if isinstance(class_solvents, dict):
            solvent_list = class_solvents.get("solvents", [])
        else:
            solvent_list = class_solvents
        
        for solvent in solvent_list:
            if isinstance(solvent, str):
                # Class 3 solvents are strings
                canonical = solvent.lower().strip()
                index[canonical] = {
                    "canonical": solvent,
                    "class": class_name,
                    "pde": None,
                    "limit": "5000",
                    "aliases": [canonical]
                }
            else:
                # Class 1/2 solvents are dicts
                canonical = solvent["name"].lower().strip()
                index[canonical] = {
                    "canonical": solvent["name"],
                    "class": class_name,
                    "pde": solvent.get("pde_mg_day") or solvent.get("pde"),
                    "limit": solvent.get("ppm") or solvent.get("limit"),
                    "aliases": [canonical]
                }
    
    # Add synonyms
    for canonical, alias_list in synonyms.items():
        canonical_lower = canonical.lower()
        
        if canonical_lower in index:
            for alias in alias_list:
                alias_lower = alias.lower()
                index[canonical_lower]["aliases"].append(alias_lower)
                if alias_lower not in index:
                    index[alias_lower] = index[canonical_lower]
    
    return index


def classify_solvents(solvents, solvent_index):
    """
    Classify LLM-extracted solvents against ICH database.
    
    If LLM already provided ich_class, use it and just enrich with PDE/limit.
    Otherwise, use solvent_index for matching (fallback).
    
    Args:
        solvents: List of solvent dicts with 'solvent' and optionally 'ich_class' keys
        solvent_index: ICH solvent database
    
    Returns:
        List of classified solvents
    """
    classified = []
    
    for solvent_entry in solvents:
        solvent_name = solvent_entry.get("solvent", "")
        solvent_lower = solvent_name.lower().strip()
        llm_class = solvent_entry.get("ich_class")  # LLM may have already classified
        
        # Check if LLM already classified this solvent
        if llm_class and llm_class != "pending":
            # LLM already did the classification - just enrich with PDE/limit from database
            lookup_name = solvent_lower
            
            # For Class 3 solvents, LLM may use short names - normalize for lookup
            if llm_class == "Class 3":
                # Try direct match first
                if solvent_lower not in solvent_index:
                    # Try common variations
                    for name_var in [solvent_lower, solvent_name.lower(), solvent_name]:
                        if name_var.lower() in solvent_index:
                            lookup_name = name_var.lower()
                            break
            
            if lookup_name in solvent_index:
                ich_data = solvent_index[lookup_name]
                classified.append({
                    "solvent": ich_data["canonical"],
                    "original_name": solvent_entry.get("original_name", solvent_name),
                    "matched_as": solvent_name,
                    "class": ich_data["class"],
                    "pde": ich_data.get("pde"),
                    "limit": ich_data.get("limit"),
                    "purpose": solvent_entry.get("purpose", "unknown"),
                    "amount": solvent_entry.get("amount")
                })
            else:
                # LLM classified but not in our index - use LLM class, no PDE/limit
                classified.append({
                    "solvent": solvent_name,
                    "original_name": solvent_entry.get("original_name", solvent_name),
                    "matched_as": solvent_name,
                    "class": llm_class.lower().replace(" ", ""),  # "Class 3" -> "class3"
                    "pde": None,
                    "limit": None,
                    "purpose": solvent_entry.get("purpose", "unknown"),
                    "amount": solvent_entry.get("amount")
                })
        else:
            # Fallback: LLM didn't classify, use solvent_index matching
            if solvent_lower in solvent_index:
                ich_data = solvent_index[solvent_lower]
                classified.append({
                    "solvent": ich_data["canonical"],
                    "original_name": solvent_entry.get("original_name", solvent_name),
                    "matched_as": solvent_name,
                    "class": ich_data["class"],
                    "pde": ich_data.get("pde"),
                    "limit": ich_data.get("limit"),
                    "purpose": solvent_entry.get("purpose", "unknown"),
                    "amount": solvent_entry.get("amount")
                })
            else:
                # Unknown solvent - not in ICH list
                classified.append({
                    "solvent": solvent_name,
                    "original_name": solvent_entry.get("original_name", solvent_name),
                    "matched_as": solvent_name,
                    "class": "unknown",
                    "pde": None,
                    "limit": None,
                    "purpose": solvent_entry.get("purpose", "unknown"),
                    "amount": solvent_entry.get("amount"),
                    "warning": "Not found in ICH Q3C - requires toxicological justification"
                })
    
    return classified


def analyze_steps(llm_data, solvent_index):
    """
    Analyze LLM-extracted solvents and classify against ICH database.
    
    Args:
        llm_data: Output from llm_extract.py
        solvent_index: ICH solvent database
    
    Returns:
        Structured analysis
    """
    analysis = []
    all_solvents = {}
    
    for step_data in llm_data.get("step_analysis", []):
        step_number = step_data["step_number"]
        step_title = step_data["step_title"]
        raw_solvents = step_data.get("solvents", [])
        
        # Classify solvents
        classified = classify_solvents(raw_solvents, solvent_index)
        
        analysis.append({
            "step_number": step_number,
            "step_title": step_title,
            "solvents": classified,
            "solvent_count": len(classified)
        })
        
        # Aggregate
        for solvent_entry in classified:
            solvent_name = solvent_entry["solvent"]
            if solvent_name not in all_solvents:
                all_solvents[solvent_name] = {
                    **solvent_entry,
                    "steps_used": []
                }
            all_solvents[solvent_name]["steps_used"].append(step_number)
    
    return {
        "step_analysis": analysis,
        "all_solvents": all_solvents,
        "total_unique_solvents": len(all_solvents)
    }


def main():
    if len(sys.argv) < 3:
        print("Usage: solvent_match.py --llm <llm_analysis_json> <ich_json> [output_json]")
        print("  llm_analysis_json: Output from llm_extract.py")
        print("  ich_json: ICH Q3C data (data/ich-q3c-full.json)")
        print("  output_json: Output path (optional, defaults to stdout)")
        sys.exit(1)
    
    if sys.argv[1] != "--llm":
        print("Error: --llm flag is required", file=sys.stderr)
        sys.exit(1)
    
    llm_path = sys.argv[2]
    ich_path = sys.argv[3]
    output_path = sys.argv[4] if len(sys.argv) > 4 else None
    
    # Load ICH data
    with open(ich_path, 'r') as f:
        ich_data = json.load(f)
    
    # Load synonyms
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent / "data"
    synonyms = load_synonyms()
    
    print(f"Building solvent index...", file=sys.stderr)
    solvent_index = build_solvent_index(ich_data, synonyms)
    
    # Load LLM-extracted analysis
    with open(llm_path, 'r') as f:
        llm_data = json.load(f)
    
    print(f"Classifying LLM-extracted solvents...", file=sys.stderr)
    analysis = analyze_steps(llm_data, solvent_index)
    
    # Output results
    if output_path:
        with open(output_path, 'w') as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False)
        print(f"Saved to {output_path}", file=sys.stderr)
    else:
        print(json.dumps(analysis, indent=2, ensure_ascii=False))
    
    print(f"\nSummary:", file=sys.stderr)
    print(f"  Total unique solvents: {analysis['total_unique_solvents']}", file=sys.stderr)
    
    # Class breakdown
    class_counts = {"class1": 0, "class2": 0, "class3": 0, "unknown": 0}
    for solvent in analysis["all_solvents"].values():
        class_counts[solvent["class"]] += 1
    
    for cls, count in class_counts.items():
        if count > 0:
            print(f"  {cls}: {count}", file=sys.stderr)


if __name__ == "__main__":
    main()
