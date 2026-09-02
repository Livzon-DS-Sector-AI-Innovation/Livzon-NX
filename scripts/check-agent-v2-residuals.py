"""Fail CI when removed Agent/Gateway paths return to production sources."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (
    ROOT / "Hermes-Lite" / "services",
    ROOT / "Hermes-Lite" / "tools",
    ROOT / "Hermes-Lite" / "README.md",
    ROOT / "Hermes-Lite" / "docs",
    ROOT / "dazah-backend" / "app",
    ROOT / "dazah-backend" / ".env.example",
    ROOT / "dazah-frontend" / "src",
)
RULES = {
    "removed backend Feishu WebSocket flag": re.compile(
        r"LIVZON_FEISHU_(?:EVENT|CARD_CALLBACK)_WS_ENABLED"
    ),
    "removed backend Feishu consumer": re.compile(r"\bfeishu_card_ws\b"),
    "removed AgentBackend V1 route": re.compile(
        r"(?<!/llm)(?<!/coding)/v1/chat(?:/stream)?(?!/completions)"
    ),
    "removed AgentBackend legacy URL setting": re.compile(r"\bHERMES_AGENT_URL\b"),
    "removed per-operation Hermes registry": re.compile(r"\bALLOWED_OPERATIONS\b"),
    "removed user tool endpoint": re.compile(r"/tools/execute/user\b"),
    "removed Feishu delivery tool alias": re.compile(
        r"identity\.send_feishu_(?:message|text_message|card_message)"
    ),
}
PATH_RULES = {
    ROOT / "dazah-backend" / "app" / "modules" / "agent" / "service.py": {
        "removed backend legacy stream event": re.compile(
            r'_sse_(?:backend_)?event\(\s*"(?:start|delta|done)"'
        ),
    },
    ROOT / "dazah-frontend" / "src" / "lib" / "api" / "agent.ts": {
        "removed frontend legacy stream event": re.compile(
            r'event\s*===?\s*"(?:start|delta|done)"'
        ),
    },
    ROOT / "Hermes-Lite" / "services" / "feishu_gateway_worker.py": {
        "removed permissive event-name fallback": re.compile(
            r'data\.get\("type"\)\s*or\s*event_name'
        ),
    },
}


def _files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return [
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".ts", ".tsx", ".md", ".yml", ".yaml", ".example"}
        and ".venv" not in path.parts
        and "generated" not in path.parts
    ]


def main() -> int:
    failures: list[str] = []
    for root in SCAN_ROOTS:
        for path in _files(root):
            text = path.read_text(encoding="utf-8")
            for label, pattern in RULES.items():
                for match in pattern.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    failures.append(f"{path.relative_to(ROOT)}:{line}: {label}")
            for label, pattern in PATH_RULES.get(path, {}).items():
                for match in pattern.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    failures.append(f"{path.relative_to(ROOT)}:{line}: {label}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("AgentBackend V2 residual scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
