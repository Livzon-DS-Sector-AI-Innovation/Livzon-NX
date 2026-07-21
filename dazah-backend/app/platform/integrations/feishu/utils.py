"""Stateless Feishu parsing and connectivity helpers."""

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx

from app.core.redis import cache_get, cache_set

OPEN_API_BASE_URL = "https://open.feishu.cn/open-apis"
FEISHU_BITABLE_RECORD_CHANGED_EVENT = "feishu.bitable_record_changed"


@dataclass(frozen=True)
class BitableReference:
    app_token: str | None = None
    table_id: str | None = None
    view_id: str | None = None


@dataclass(frozen=True)
class ConnectivityStep:
    name: str
    status: str
    message: str


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def parse_bitable_url(value: str | None) -> BitableReference:
    """Parse a Feishu Bitable URL or copied text into app/table/view IDs."""
    text = _clean_text(value)
    if not text:
        return BitableReference()

    parsed = urlparse(text)
    query = parse_qs(parsed.query)
    app_token: str | None = None

    base_match = re.search(r"/base/([^/?#\s]+)", text)
    if base_match:
        app_token = base_match.group(1)

    return BitableReference(
        app_token=app_token,
        table_id=(query.get("table") or [None])[0],
        view_id=(query.get("view") or [None])[0],
    )


def normalize_app_token(value: str | None) -> str | None:
    """Extract a Bitable app_token from a URL, labelled text, or raw token."""
    text = _clean_text(value)
    if not text:
        return None

    parsed = parse_bitable_url(text)
    if parsed.app_token:
        return parsed.app_token

    label_match = re.search(
        r"(?:app[_\s-]?token|多维表格\s*app[_\s-]?token)\s*[:：]\s*([A-Za-z0-9_-]+)",
        text,
        re.IGNORECASE,
    )
    if label_match:
        return label_match.group(1)

    token_match = re.search(r"\b([A-Za-z0-9_-]{10,})\b", text)
    return token_match.group(1) if token_match else text


def normalize_table_id(value: str | None) -> str | None:
    """Extract a Bitable table_id from a URL, labelled text, or raw table ID."""
    text = _clean_text(value)
    if not text:
        return None

    parsed = parse_bitable_url(text)
    if parsed.table_id:
        return parsed.table_id.strip()

    label_match = re.search(
        r"(?:table[_\s-]?id|table)\s*[:：]\s*(tbl[A-Za-z0-9_-]+)",
        text,
        re.IGNORECASE,
    )
    if label_match:
        return label_match.group(1)

    table_match = re.search(r"\b(tbl[A-Za-z0-9_-]+)\b", text)
    return table_match.group(1) if table_match else text


def _extract_table_id_from_reference(value: str | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    parsed = parse_bitable_url(text)
    if parsed.table_id:
        return parsed.table_id.strip()
    label_match = re.search(
        r"(?:table[_\s-]?id|table)\s*[:：]\s*(tbl[A-Za-z0-9_-]+)",
        text,
        re.IGNORECASE,
    )
    if label_match:
        return label_match.group(1)
    table_match = re.search(r"\b(tbl[A-Za-z0-9_-]+)\b", text)
    return table_match.group(1) if table_match else None


def resolve_bitable_reference(
    *,
    app_token: str | None = None,
    table_id: str | None = None,
    fallback_app_token: str | None = None,
    fallback_table_id: str | None = None,
) -> BitableReference:
    """Resolve Bitable app/table IDs from raw IDs, labelled text, URLs or fallbacks."""
    resolved_app_token = normalize_app_token(app_token) or normalize_app_token(
        fallback_app_token
    )
    resolved_table_id = (
        normalize_table_id(table_id)
        or _extract_table_id_from_reference(app_token)
        or normalize_table_id(fallback_table_id)
        or _extract_table_id_from_reference(fallback_app_token)
    )
    return BitableReference(
        app_token=resolved_app_token,
        table_id=resolved_table_id,
    )


def build_bitable_client(
    *,
    app_token: str | None,
    app_id: str | None,
    app_secret: str | None,
):
    """Build a Bitable client after applying the shared Feishu reference parser."""
    from app.platform.integrations.feishu.bitable import BitableClient

    reference = resolve_bitable_reference(app_token=app_token)
    return BitableClient(
        app_token=reference.app_token,
        app_id=app_id.strip() if isinstance(app_id, str) else app_id,
        app_secret=app_secret,
    )


async def get_tenant_access_token(
    app_id: str,
    app_secret: str,
    *,
    cache_key: str | None = None,
) -> str:
    """Get tenant_access_token from explicit app credentials."""
    if not app_id or not app_secret:
        raise RuntimeError("App ID 或 App Secret 未配置")

    if cache_key:
        try:
            cached = await cache_get(f"feishu:tenant_access_token:{cache_key}")
            if cached:
                return cached
        except Exception:
            pass

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{OPEN_API_BASE_URL}/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
        )
        resp.raise_for_status()
        body = resp.json()

    if body.get("code") != 0:
        raise RuntimeError(body.get("msg") or str(body))

    token = body.get("tenant_access_token")
    if not token:
        raise RuntimeError("tenant_access_token 响应为空")

    if cache_key:
        try:
            await cache_set(f"feishu:tenant_access_token:{cache_key}", token, ex=6600)
        except Exception:
            pass

    return token


async def test_bitable_table_with_token(
    *,
    tenant_access_token: str,
    app_token: str,
    table_id: str,
    name: str = "多维表格",
) -> ConnectivityStep:
    """Test one Bitable table using an explicit token and table reference."""
    if not app_token:
        return ConnectivityStep(
            name=name,
            status="error",
            message="多维表格 app_token 未配置",
        )
    if not table_id:
        return ConnectivityStep(
            name=name,
            status="error",
            message="多维表格 table_id 未配置",
        )

    try:
        async with httpx.AsyncClient(
            base_url=OPEN_API_BASE_URL,
            timeout=15.0,
        ) as client:
            resp = await client.get(
                f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
                headers={"Authorization": f"Bearer {tenant_access_token}"},
                params={"page_size": 1},
            )
            resp.raise_for_status()
            body = resp.json()
    except Exception as exc:
        return ConnectivityStep(
            name=name,
            status="error",
            message=f"读取表字段失败：{exc}",
        )

    if body.get("code") == 0:
        return ConnectivityStep(name=name, status="ok", message="table_id 可访问")

    return ConnectivityStep(
        name=name,
        status="error",
        message=f"飞书多维表格访问失败：{body.get('msg') or body}",
    )


async def test_bitable_table(
    *,
    app_id: str,
    app_secret: str,
    app_token: str,
    table_id: str,
    name: str = "多维表格",
) -> ConnectivityStep:
    """Test one Bitable table using explicit Feishu app credentials."""
    try:
        token = await get_tenant_access_token(app_id, app_secret)
    except Exception as exc:
        return ConnectivityStep(
            name="应用凭证",
            status="error",
            message=f"飞书认证失败：{exc}",
        )

    return await test_bitable_table_with_token(
        tenant_access_token=token,
        app_token=app_token,
        table_id=table_id,
        name=name,
    )
