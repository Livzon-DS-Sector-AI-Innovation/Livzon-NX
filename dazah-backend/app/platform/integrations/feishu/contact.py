"""Feishu contact: departments, users with Redis caching."""

import json
import logging

from app.core.config import get_settings
from app.core.redis import cache_get, cache_set

logger = logging.getLogger(__name__)

settings = get_settings()
CONTACT_PAGE_SIZE = 50


async def _get_feishu_client(
    app_id: str | None = None,
    app_secret: str | None = None,
):
    import lark_oapi as lark

    resolved_app_id = app_id or settings.FEISHU_APP_ID
    resolved_app_secret = app_secret or settings.FEISHU_APP_SECRET
    return (
        lark.Client.builder()
        .app_id(resolved_app_id)
        .app_secret(resolved_app_secret)
        .domain(lark.FEISHU_DOMAIN)
        .app_type(lark.AppType.SELF)
        .build()
    )


async def _get_tenant_token(
    client,
    *,
    app_id: str | None = None,
    app_secret: str | None = None,
    tenant_access_token: str | None = None,
) -> str:
    import json as _json

    from lark_oapi.api.auth.v3 import (
        InternalTenantAccessTokenRequest,
        InternalTenantAccessTokenRequestBody,
    )

    if tenant_access_token:
        return tenant_access_token

    resolved_app_id = app_id or settings.FEISHU_APP_ID
    resolved_app_secret = app_secret or settings.FEISHU_APP_SECRET
    req = (
        InternalTenantAccessTokenRequest.builder()
        .request_body(
            InternalTenantAccessTokenRequestBody.builder()
            .app_id(resolved_app_id)
            .app_secret(resolved_app_secret)
            .build()
        )
        .build()
    )
    resp = await client.auth.v3.tenant_access_token.ainternal(req)
    if not resp.success():
        raise RuntimeError(
            f"Failed to get tenant token: code={resp.code}, msg={resp.msg}",
        )
    if resp.raw and resp.raw.content:
        data = _json.loads(resp.raw.content.decode("utf-8"))
        return data.get("tenant_access_token", "")
    raise RuntimeError("Empty tenant token response")


# ── Department helpers ──────────────────────────────────────────────


def _department_to_dict(item, parent_department_id: str = "") -> dict:
    oid = item.open_department_id or item.department_id or ""
    name = item.name or oid
    order_val = item.order or 0
    try:
        order_val = int(order_val)
    except (ValueError, TypeError):
        order_val = 0
    return {
        "department_id": oid,
        "raw_department_id": item.department_id or "",
        "open_department_id": item.open_department_id or "",
        "name": name,
        "parent_department_id": parent_department_id,
        "leader_user_id": item.leader_user_id or "",
        "member_count": item.member_count or 0,
        "status_is_deleted": False,
        "order": order_val,
    }


async def get_contact_scope(
    *,
    app_id: str | None = None,
    app_secret: str | None = None,
    tenant_access_token: str | None = None,
) -> dict:
    """读取当前应用被授权的通讯录范围，用于诊断授权范围问题。"""
    client = await _get_feishu_client(app_id, app_secret)
    token = await _get_tenant_token(
        client,
        app_id=app_id,
        app_secret=app_secret,
        tenant_access_token=tenant_access_token,
    )

    from lark_oapi.api.contact.v3 import ListScopeRequest

    department_ids: list[str] = []
    user_ids: list[str] = []
    group_ids: list[str] = []
    page_token = ""
    while True:
        req = (
            ListScopeRequest.builder()
            .department_id_type("open_department_id")
            .user_id_type("user_id")
            .page_size(CONTACT_PAGE_SIZE)
            .page_token(page_token)
            .build()
        )
        req.headers["Authorization"] = f"Bearer {token}"
        resp = await client.contact.v3.scope.alist(req)
        if not resp.success():
            raise RuntimeError(
                f"Failed to list contact scope: code={resp.code}, msg={resp.msg}",
            )
        if not resp.data:
            break
        department_ids.extend(resp.data.department_ids or [])
        user_ids.extend(resp.data.user_ids or [])
        group_ids.extend(resp.data.group_ids or [])
        if not resp.data.has_more:
            break
        page_token = resp.data.page_token or ""
        if not page_token:
            break

    return {
        "department_ids": department_ids,
        "user_ids": user_ids,
        "group_ids": group_ids,
    }


async def get_all_departments(
    *,
    root_department_id: str = "0",
    app_id: str | None = None,
    app_secret: str | None = None,
    tenant_access_token: str | None = None,
) -> list[dict]:
    """BFS 递归获取全公司所有部门（含名称），包括叶子节点。

    返回扁平列表。
    """
    client = await _get_feishu_client(app_id, app_secret)
    token = await _get_tenant_token(
        client,
        app_id=app_id,
        app_secret=app_secret,
        tenant_access_token=tenant_access_token,
    )

    from lark_oapi.api.contact.v3 import ChildrenDepartmentRequest

    all_depts: list[dict] = []
    root_id = root_department_id or "0"
    visited: set[str] = {root_id}
    page_token = ""
    while True:
        req = (
            ChildrenDepartmentRequest.builder()
            .department_id_type("open_department_id")
            .user_id_type("user_id")
            .department_id(root_id)
            .fetch_child(True)
            .page_size(50)
            .page_token(page_token)
            .build()
        )
        req.headers["Authorization"] = f"Bearer {token}"
        resp = await client.contact.v3.department.achildren(req)
        if not resp.success():
            raise RuntimeError(
                f"Failed to list child departments: code={resp.code}, msg={resp.msg}",
            )
        if not resp.data:
            break

        for item in resp.data.items or []:
            oid = item.open_department_id or item.department_id or ""
            if not oid or oid in visited:
                continue
            visited.add(oid)
            parent_id = item.parent_department_id or ""
            if parent_id == root_id:
                parent_id = ""
            all_depts.append(_department_to_dict(item, parent_id))

        if not resp.data.has_more:
            break
        page_token = resp.data.page_token or ""
        if not page_token:
            break

    logger.info("Fetched %d departments from Feishu (BFS)", len(all_depts))
    return all_depts


async def get_department_members(
    dept_id: str,
    *,
    app_id: str | None = None,
    app_secret: str | None = None,
    tenant_access_token: str | None = None,
) -> list[dict]:
    """获取部门成员列表，优先读 Redis"""
    cache_key = f"feishu:{app_id or 'default'}:dept:{dept_id}:members"
    cached = await cache_get(cache_key)
    if cached:
        return json.loads(cached)

    client = await _get_feishu_client(app_id, app_secret)
    token = await _get_tenant_token(
        client,
        app_id=app_id,
        app_secret=app_secret,
        tenant_access_token=tenant_access_token,
    )

    from lark_oapi.api.contact.v3 import ListUserRequest

    all_members = []
    page_token = ""
    while True:
        req = (
            ListUserRequest.builder()
            .department_id(dept_id)
            .page_size(CONTACT_PAGE_SIZE)
            .page_token(page_token)
            .user_id_type("user_id")
            .build()
        )
        req.headers["Authorization"] = f"Bearer {token}"
        resp = await client.contact.v3.user.alist(req)
        if not resp.success():
            logger.error("Failed to list users for dept %s: %s", dept_id, resp.msg)
            break

        raw = resp.raw.content if resp.raw else None
        if raw:
            data = json.loads(raw.decode("utf-8")).get("data", {})
            items = data.get("items", [])
            for item in items:
                all_members.append({
                    "user_id": item.get("user_id", ""),
                    "name": item.get("name", ""),
                    "employee_no": item.get("employee_no", ""),
                    "department_id": dept_id,
                })
            if not data.get("has_more"):
                break
            page_token = data.get("page_token", "")
        else:
            break

    await cache_set(cache_key, json.dumps(all_members, ensure_ascii=False), ex=86400)
    return all_members


async def get_department_detail(
    dept_id: str,
    *,
    app_id: str | None = None,
    app_secret: str | None = None,
    tenant_access_token: str | None = None,
) -> dict | None:
    """获取单个部门的名称和组织标识。"""
    client = await _get_feishu_client(app_id, app_secret)
    token = await _get_tenant_token(
        client,
        app_id=app_id,
        app_secret=app_secret,
        tenant_access_token=tenant_access_token,
    )

    from lark_oapi.api.contact.v3 import GetDepartmentRequest

    req = (
        GetDepartmentRequest.builder()
        .department_id(dept_id)
        .department_id_type("open_department_id")
        .user_id_type("user_id")
        .build()
    )
    req.headers["Authorization"] = f"Bearer {token}"
    resp = await client.contact.v3.department.aget(req)
    if not resp.success():
        logger.error("Failed to get department %s: %s", dept_id, resp.msg)
        return None

    raw = resp.raw.content if resp.raw else None
    if not raw:
        return None
    department = (
        json.loads(raw.decode("utf-8")).get("data", {}).get("department", {})
    )
    name = str(department.get("name") or "").strip()
    if not name:
        return None
    return {
        "department_id": department.get("open_department_id") or dept_id,
        "department_name": name,
        "parent_department_id": department.get("parent_department_id"),
    }


async def get_department_leader(
    dept_id: str,
    *,
    app_id: str | None = None,
    app_secret: str | None = None,
    tenant_access_token: str | None = None,
) -> dict | None:
    """获取部门主管"""
    cache_key = f"feishu:dept:{dept_id}:leader"
    cached = await cache_get(cache_key)
    if cached:
        return json.loads(cached)

    client = await _get_feishu_client(app_id, app_secret)
    token = await _get_tenant_token(
        client,
        app_id=app_id,
        app_secret=app_secret,
        tenant_access_token=tenant_access_token,
    )

    from lark_oapi.api.contact.v3 import GetDepartmentRequest

    req = (
        GetDepartmentRequest.builder()
        .department_id(dept_id)
        .user_id_type("user_id")
        .build()
    )
    req.headers["Authorization"] = f"Bearer {token}"
    resp = await client.contact.v3.department.aget(req)
    if not resp.success():
        logger.error("Failed to get department %s: %s", dept_id, resp.msg)
        return None

    raw = resp.raw.content if resp.raw else None
    if raw:
        dept = json.loads(raw.decode("utf-8")).get("data", {}).get("department", {})
        leader_id = dept.get("leader_user_id")
        if leader_id:
            result = {"user_id": leader_id}
            await cache_set(cache_key, json.dumps(result, ensure_ascii=False), ex=86400)
            return result

    return None


async def is_department_member(user_id: str, dept_id: str) -> bool:
    """检查用户是否为部门成员"""
    members = await get_department_members(dept_id)
    return any(m.get("user_id") == user_id for m in members)


# ── User helpers ────────────────────────────────────────────────────


async def get_all_users(
    *,
    app_id: str | None = None,
    app_secret: str | None = None,
    tenant_access_token: str | None = None,
) -> list[dict]:
    """获取所有可见用户（全公司范围，分页）。

    每个元素包含 user_id, open_id, name, employee_no, email, mobile,
    department_ids, job_title, positions, department_path 等。
    """
    client = await _get_feishu_client(app_id, app_secret)
    token = await _get_tenant_token(
        client,
        app_id=app_id,
        app_secret=app_secret,
        tenant_access_token=tenant_access_token,
    )

    from lark_oapi.api.contact.v3 import ListUserRequest

    all_users: list[dict] = []
    page_token = ""
    while True:
        req = (
            ListUserRequest.builder()
            .user_id_type("user_id")
            .page_size(CONTACT_PAGE_SIZE)
            .page_token(page_token)
            .build()
        )
        req.headers["Authorization"] = f"Bearer {token}"
        resp = await client.contact.v3.user.alist(req)
        raw = resp.raw.content if resp.raw else None
        if raw:
            data = json.loads(raw.decode("utf-8")).get("data", {})
            for u in data.get("items", []):
                all_users.append({
                    "user_id": u.get("user_id", ""),
                    "open_id": u.get("open_id", ""),
                    "name": u.get("name", ""),
                    "employee_no": u.get("employee_no", ""),
                    "email": u.get("email", ""),
                    "mobile": u.get("mobile", ""),
                    "job_title": u.get("job_title", ""),
                    "department_ids": u.get("department_ids", []),
                })
            if not data.get("has_more"):
                break
            page_token = data.get("page_token", "")
        else:
            break

    logger.info("Fetched %d users from Feishu", len(all_users))
    return all_users


async def find_users_by_department(
    department_id: str,
    *,
    app_id: str | None = None,
    app_secret: str | None = None,
    tenant_access_token: str | None = None,
) -> list[dict]:
    """按部门获取所有用户详情（含 department_ids、position、job_title 等）。

    每个元素包含：
    - user_id, open_id, name, employee_no, email, mobile,
    - department_ids (list[str]), job_title, positions, department_path
    """
    client = await _get_feishu_client(app_id, app_secret)
    token = await _get_tenant_token(
        client,
        app_id=app_id,
        app_secret=app_secret,
        tenant_access_token=tenant_access_token,
    )

    from lark_oapi.api.contact.v3 import FindByDepartmentUserRequest

    all_users: list[dict] = []
    page_token = ""
    while True:
        req = (
            FindByDepartmentUserRequest.builder()
            .user_id_type("user_id")
            .department_id_type("open_department_id")
            .department_id(department_id)
            .page_size(CONTACT_PAGE_SIZE)
            .page_token(page_token)
            .build()
        )
        req.headers["Authorization"] = f"Bearer {token}"
        resp = await client.contact.v3.user.afind_by_department(req)
        if not resp.success():
            raise RuntimeError(
                "Failed to find users by department "
                f"{department_id}: code={resp.code}, msg={resp.msg}"
            )

        if resp.data and resp.data.items:
            for u in resp.data.items:
                positions: list[dict] = []
                if u.positions:
                    for p in u.positions:
                        positions.append({
                            "position_code": p.position_code,
                            "position_name": p.position_name,
                            "department_id": p.department_id,
                            "is_major": p.is_major,
                        })

                department_path: list[dict] = []
                if u.department_path:
                    for dp in u.department_path:
                        dept_name = ""
                        if dp.department_name:
                            dept_name = dp.department_name.name or ""
                        dept_id_val = (
                            str(dp.department_id)
                            if dp.department_id else ""
                        )
                        department_path.append({
                            "department_id": dept_id_val,
                            "department_name": dept_name,
                        })

                all_users.append({
                    "user_id": u.user_id or "",
                    "open_id": u.open_id or "",
                    "name": u.name or "",
                    "en_name": u.en_name or "",
                    "email": u.email or "",
                    "mobile": u.mobile or "",
                    "employee_no": u.employee_no or "",
                    "job_title": u.job_title or "",
                    "department_ids": u.department_ids or [],
                    "positions": positions,
                    "department_path": department_path,
                    "avatar_key": u.avatar_key or "",
                    "join_time": u.join_time or 0,
                    "is_frozen": u.is_frozen if u.is_frozen is not None else False,
                })

            if not resp.data.has_more:
                break
            page_token = resp.data.page_token or ""
        else:
            break

    logger.info(
        "Fetched %d users from department %s", len(all_users), department_id,
    )
    return all_users


async def get_user_detail(
    user_id: str,
    user_id_type: str = "user_id",
    *,
    app_id: str | None = None,
    app_secret: str | None = None,
    tenant_access_token: str | None = None,
) -> dict | None:
    """获取单个用户详细信息。

    返回包含 department_ids, positions, department_path 等完整字段。
    """
    client = await _get_feishu_client(app_id, app_secret)
    token = await _get_tenant_token(
        client,
        app_id=app_id,
        app_secret=app_secret,
        tenant_access_token=tenant_access_token,
    )

    from lark_oapi.api.contact.v3 import GetUserRequest

    req = (
        GetUserRequest.builder()
        .user_id_type(user_id_type)
        .user_id(user_id)
        .build()
    )
    req.headers["Authorization"] = f"Bearer {token}"
    resp = await client.contact.v3.user.aget(req)
    if not resp.success():
        logger.error(
            "Failed to get user %s: code=%s, msg=%s",
            user_id, resp.code, resp.msg,
        )
        return None

    if resp.data and resp.data.user:
        u = resp.data.user
        positions: list[dict] = []
        if u.positions:
            for p in u.positions:
                positions.append({
                    "position_code": p.position_code,
                    "position_name": p.position_name,
                    "department_id": p.department_id,
                    "is_major": p.is_major,
                })

        department_path: list[dict] = []
        if u.department_path:
            for dp in u.department_path:
                dept_name = ""
                if dp.department_name:
                    dept_name = dp.department_name.name or ""
                department_path.append({
                    "department_id": str(dp.department_id) if dp.department_id else "",
                    "department_name": dept_name,
                })

        return {
            "user_id": u.user_id or "",
            "open_id": u.open_id or "",
            "name": u.name or "",
            "en_name": u.en_name or "",
            "email": u.email or "",
            "mobile": u.mobile or "",
            "employee_no": u.employee_no or "",
            "job_title": u.job_title or "",
            "department_ids": u.department_ids or [],
            "positions": positions,
            "department_path": department_path,
            "avatar_key": u.avatar_key or "",
            "join_time": u.join_time or 0,
            "is_frozen": u.is_frozen if u.is_frozen is not None else False,
        }

    return None
