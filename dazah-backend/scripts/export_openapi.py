#!/usr/bin/env python3
"""Export the FastAPI OpenAPI specification deterministically."""

import json
import os
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set dummy values for required env vars that aren't needed for spec generation
# This allows the script to run in CI without a .env file
os.environ.setdefault("FEISHU_APP_ID", "dummy")
os.environ.setdefault("FEISHU_APP_SECRET", "dummy")
os.environ.setdefault("FEISHU_REDIRECT_URI", "http://localhost/callback")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")

from app.main import app


def main() -> None:
    spec = app.openapi()
    output_path = Path(__file__).parent.parent / "openapi.json"
    output_path.write_text(
        f"{json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    print(f"OpenAPI spec exported to {output_path}")


if __name__ == "__main__":
    main()
