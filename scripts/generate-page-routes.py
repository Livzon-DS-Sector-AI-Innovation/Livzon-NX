"""Generate/check the frontend route inventory shipped with the backend."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dazah-backend/app/platform/identity"))

from page_route_catalog import (  # noqa: E402
    CATALOG_PATH,
    collect_frontend_page_routes,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    routes = collect_frontend_page_routes(ROOT / "dazah-frontend/src/app")
    if not routes:
        print(
            "No frontend pages were found; inventory was not written.", file=sys.stderr
        )
        return 1
    content = (
        json.dumps({"version": 1, "routes": routes}, indent=2, ensure_ascii=False)
        + "\n"
    )
    if args.check:
        if (
            not CATALOG_PATH.exists()
            or CATALOG_PATH.read_text(encoding="utf-8") != content
        ):
            print(
                "Frontend page inventory is stale. "
                "Run: python scripts/generate-page-routes.py",
                file=sys.stderr,
            )
            return 1
    else:
        CATALOG_PATH.write_text(content, encoding="utf-8", newline="\n")
    print(
        f"Frontend page inventory {'verified' if args.check else 'generated'} "
        f"({len(routes)} routes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
