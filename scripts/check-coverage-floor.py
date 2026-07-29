#!/usr/bin/env python3
"""Check independent line and branch floors in a Cobertura coverage report."""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-file", type=Path, required=True)
    parser.add_argument("--min-lines", type=float, required=True)
    parser.add_argument("--min-branches", type=float, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = ET.parse(args.coverage_file).getroot()
    line_rate = float(root.attrib.get("line-rate", "0")) * 100
    branches_valid = int(root.attrib.get("branches-valid", "0"))
    branch_rate = float(root.attrib.get("branch-rate", "0")) * 100

    print(
        f"Coverage floors: lines {line_rate:.2f}%/{args.min_lines:.2f}%, "
        f"branches {branch_rate:.2f}%/{args.min_branches:.2f}%."
    )
    failures: list[str] = []
    if line_rate + 1e-9 < args.min_lines:
        failures.append("line coverage")
    if branches_valid == 0:
        failures.append("branch coverage was not collected")
    elif branch_rate + 1e-9 < args.min_branches:
        failures.append("branch coverage")
    if failures:
        print("Coverage floor failed: " + ", ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
