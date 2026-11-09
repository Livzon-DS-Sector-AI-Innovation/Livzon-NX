"""Discover Next.js pages from read-only development sources or a shipped snapshot."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import unquote

CATALOG_PATH = Path(__file__).with_name("page_route_catalog.json")
_BACKEND_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOTS = (
    _BACKEND_ROOT.parent / "dazah-frontend" / "src" / "app",
    _BACKEND_ROOT / "frontend-pages",
)


class PageRouteCatalogError(ValueError):
    """A missing or unreadable inventory must not produce a passing check."""


def collect_frontend_page_routes(source: Path) -> list[str]:
    routes: set[str] = set()

    def failed(error: OSError) -> None:
        raise error

    for directory, folders, files in os.walk(source, onerror=failed, followlinks=False):
        folders[:] = sorted(name for name in folders if not name.startswith("_"))
        if not any(
            name in files for name in ("page.tsx", "page.ts", "page.jsx", "page.js")
        ):
            continue
        segments: list[str] = []
        for segment in Path(directory).relative_to(source).parts:
            if segment.startswith("@") or (
                segment.startswith("(") and segment.endswith(")")
            ):
                continue
            if segment.startswith("(...)"):
                segments.clear()
                segment = segment[5:]
            while segment.startswith("(..)"):
                if segments:
                    segments.pop()
                segment = segment[4:]
            if segment.startswith("(.)"):
                segment = segment[3:]
            segments.append(unquote(segment))
        routes.add("/" + "/".join(segments))
    return sorted(routes)


def load_frontend_page_routes() -> list[str]:
    try:
        for source in SOURCE_ROOTS:
            if source.is_dir():
                routes = collect_frontend_page_routes(source)
                if not routes:
                    raise PageRouteCatalogError("前端源码目录没有可检查的页面")
                return routes
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1:
            raise PageRouteCatalogError("前端页面目录版本无效")
        snapshot_routes: object = data.get("routes")
        if not isinstance(snapshot_routes, list) or not snapshot_routes:
            raise PageRouteCatalogError("前端页面目录格式无效")
        validated_routes: list[str] = []
        for route in snapshot_routes:
            if not isinstance(route, str) or not route.startswith("/"):
                raise PageRouteCatalogError("前端页面目录格式无效")
            validated_routes.append(route)
        return sorted(set(validated_routes))
    except (OSError, ValueError) as error:
        raise PageRouteCatalogError("无法读取前端页面目录") from error
