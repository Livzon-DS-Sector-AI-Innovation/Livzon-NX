"""Export the live backend registry without connecting to a database or model.

Run with the backend Python runtime and a configured backend environment.
Only public tool contracts are exported; runtime credentials are never included.
"""

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(root / "dazah-backend"))
    from app.modules.agent.tool_registration import ensure_agent_tools_registered
    from app.modules.agent.tools import tool_registry

    ensure_agent_tools_registered()
    active = [spec.public_dict() for spec in tool_registry.list()]
    excluded = [
        {**spec.public_dict(), "exclusion_reason": reason}
        for spec, reason in tool_registry.excluded()
    ]
    document = {"active": active, "excluded": excluded}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Exported {len(active)} active and {len(excluded)} excluded tools")


if __name__ == "__main__":
    main()
