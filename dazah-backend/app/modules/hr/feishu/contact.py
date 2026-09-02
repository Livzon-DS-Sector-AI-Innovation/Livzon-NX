"""Feishu Contact API - department and user operations."""

import asyncio
import logging
from typing import Any, cast

from app.modules.hr.feishu.client import FeishuClient

logger = logging.getLogger(__name__)

# 飞书 API 重试配置：最多 3 次重试，指数退避 (1s, 2s)
FEISHU_MAX_RETRIES = 3


class FeishuContactError(RuntimeError):
    """飞书通讯录 API 调用失败（含翻页中途失败）。

    抛出异常而非返回半截数据，让上层重试/失败机制能够感知错误。
    """


async def _retry_api_call(
    func: Any, *args: Any, context: str = "", **kwargs: Any
) -> dict[str, Any] | None:
    """对飞书 API 调用最多重试 3 次，指数退避。

    每次 attempt 重新调用 func(*args,**kwargs) 创建新协程，避免协程复用 bug。
    """
    last_error = None
    for attempt in range(FEISHU_MAX_RETRIES):
        try:
            result = await func(*args, **kwargs)
            return cast(dict[str, Any], result) if isinstance(result, dict) else None
        except Exception as e:
            last_error = e
            if attempt < FEISHU_MAX_RETRIES - 1:
                wait = 2**attempt  # 1s, 2s
                logger.warning(
                    "Feishu API retry %d/%d for %s after %.0fs: %s",
                    attempt + 1,
                    FEISHU_MAX_RETRIES,
                    context,
                    wait,
                    e,
                )
                await asyncio.sleep(wait)
            else:
                logger.error("Feishu API exhausted retries for %s: %s", context, e)
    raise last_error  # type: ignore[misc]


class FeishuContact:
    """飞书通讯录 API 封装

    凭证由调用方显式传入（人事模块 DB 配置）；不传时回退 env（兼容历史调用）。
    """

    def __init__(
        self, app_id: str | None = None, app_secret: str | None = None,
    ) -> None:
        self.client = FeishuClient(app_id=app_id, app_secret=app_secret)

    async def _make_request(
        self, url: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """发送飞书 API 请求，带重试机制。"""
        return await _retry_api_call(
            self._do_request, url, params, context=f"{url.split('?')[0]}"
        )

    async def _do_request(
        self, url: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """实际执行 HTTP 请求。"""
        from app.modules.hr.feishu.auth import FeishuAuth

        token = await FeishuAuth.get_tenant_access_token(
            app_id=self.client.app_id, app_secret=self.client.app_secret
        )
        headers = {"Authorization": f"Bearer {token}"}
        resp = await self.client._get_client()
        response = await resp.get(url, headers=headers, params=params or {})
        if response.status_code != 200:
            logger.warning(
                "Feishu API returned %d for %s: %s",
                response.status_code,
                url,
                response.text,
            )
            raise FeishuContactError(
                f"Feishu API returned {response.status_code}: {response.text[:200]}"
            )
        payload = response.json()
        return cast(dict[str, Any], payload if isinstance(payload, dict) else {})

    async def get_department_children(self, department_id: str) -> list[dict[str, Any]]:
        """获取指定部门的子部门列表。

        Args:
            department_id: 部门的 open_department_id

        Returns:
            子部门列表
        """
        all_items = []
        page_token = None

        while True:
            params = {
                "department_id_type": "open_department_id",
                "page_size": 50,
            }
            if page_token:
                params["page_token"] = page_token

            url = f"/contact/v3/departments/{department_id}/children"
            data = await self._make_request(url, params)

            if not data or data.get("code") != 0:
                msg = data.get("msg") if data else "no response"
                logger.error(
                    "Failed to get department children for %s: %s", department_id, msg
                )
                # 翻页中途失败必须抛异常，避免静默返回半截部门列表
                raise FeishuContactError(
                    f"获取部门 {department_id} 的子部门失败: {msg}"
                )

            items = data.get("data", {}).get("items", [])
            all_items.extend(items)

            has_more = data.get("data", {}).get("has_more", False)
            if not has_more:
                break

            page_token = data.get("data", {}).get("page_token")

        return all_items

    async def get_all_departments(
        self, root_department_id: str = "0"
    ) -> list[dict[str, Any]]:
        """从指定根部门广度优先遍历飞书全部子部门。

        Args:
            root_department_id: 起始根部门 ID，默认为 "0"（整个租户）。

        Returns:
            部门列表，每项含 open_department_id、name，首项为根部门。

        Raises:
            FeishuContactError: 任一层级拉取失败时抛出，避免静默漏掉部门。
        """
        all_depts: list[dict[str, Any]] = [
            {"open_department_id": root_department_id, "name": "根部门"}
        ]
        queue: list[str] = [root_department_id]
        seen: set[str] = {root_department_id}
        while queue:
            current = queue.pop(0)
            children = await self.get_department_children(current)
            for child in children:
                child_id = child.get("open_department_id", "")
                if child_id and child_id not in seen:
                    seen.add(child_id)
                    all_depts.append(child)
                    queue.append(child_id)
        return all_depts

    async def get_user_name(self, user_id: str) -> str | None:
        """获取用户姓名。

        Args:
            user_id: 用户的 open_id

        Returns:
            用户姓名，获取失败返回 None
        """
        url = f"/contact/v3/users/{user_id}"
        params = {"user_id_type": "open_id"}
        data = await self._make_request(url, params)

        if not data or data.get("code") != 0:
            logger.warning(
                "Failed to get user %s: %s",
                user_id,
                data.get("msg") if data else "no response",
            )
            return None

        user_data = data.get("data", {}).get("user", {})
        name = user_data.get("name") if isinstance(user_data, dict) else None
        return str(name) if name is not None else None

    async def get_department_users(self, department_id: str) -> list[dict[str, Any]]:
        """获取指定部门下的用户列表。

        Args:
            department_id: 部门的 open_department_id

        Returns:
            用户列表，每项含 name, open_id, department_ids, job_title 等
        """
        all_users = []
        page_token = None

        while True:
            params = {
                "department_id_type": "open_department_id",
                "page_size": 50,
                "department_id": department_id,
            }
            if page_token:
                params["page_token"] = page_token

            url = "/contact/v3/users/find_by_department"
            data = await self._make_request(url, params)

            if not data or data.get("code") != 0:
                msg = data.get("msg") if data else "no response"
                logger.warning(
                    "Failed to get users for dept %s: %s", department_id, msg
                )
                # 翻页中途失败必须抛异常：若静默 break 会返回半截用户列表，
                # 导致上层重试机制失效、同步数据不完整
                raise FeishuContactError(f"获取部门 {department_id} 成员失败: {msg}")

            items = data.get("data", {}).get("items", [])
            all_users.extend(items)

            has_more = data.get("data", {}).get("has_more", False)
            if not has_more:
                break

            page_token = data.get("data", {}).get("page_token")

        return all_users
