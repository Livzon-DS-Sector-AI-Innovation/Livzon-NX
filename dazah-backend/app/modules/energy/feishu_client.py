"""Read-only Feishu Wiki and Sheets client owned by the energy module."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from urllib.parse import quote, urlparse

import httpx

from app.platform.integrations.feishu.client import FeishuClient

T = TypeVar("T")
_WIKI_TOKEN_RE = re.compile(r"/wiki/([^/?#\s]+)")
_SPREADSHEET_TOKEN_RE = re.compile(r"/sheets/([^/?#\s]+)")


class EnergyFeishuRequestError(RuntimeError):
    """A safe, module-scoped representation of a Feishu API failure."""

    def __init__(
        self,
        *,
        path: str,
        status_code: int,
        feishu_code: int | None,
        feishu_message: str | None,
        request_log_id: str | None,
    ) -> None:
        self.path = path
        self.status_code = status_code
        self.feishu_code = feishu_code
        self.feishu_message = feishu_message or "未提供错误说明"
        self.request_log_id = request_log_id
        detail = f"HTTP {status_code}"
        if feishu_code is not None:
            detail += f"，飞书错误码 {feishu_code}"
        detail += f"：{self.feishu_message}"
        if request_log_id:
            detail += f"（请求日志 ID：{request_log_id}）"
        super().__init__(detail)

    @property
    def is_retryable(self) -> bool:
        return self.status_code >= 500 or self.feishu_code in {131001, 1310217, 1310235}


class EnergyFeishuClient:
    """Thin business client for the APIs needed by energy ingestion.

    It deliberately delegates authentication to the platform's generic client
    while keeping Wiki traversal and spreadsheet semantics inside the module.
    """

    def __init__(self, *, app_id: str, app_secret: str) -> None:
        self._client = FeishuClient(app_id=app_id, app_secret=app_secret)

    @staticmethod
    def parse_wiki_token(value: str) -> str:
        text = value.strip()
        match = _WIKI_TOKEN_RE.search(text)
        if match:
            return match.group(1)
        parsed = urlparse(text)
        if parsed.path.startswith("/wiki/"):
            return parsed.path.removeprefix("/wiki/").split("/")[0]
        if text and "/" not in text:
            return text
        raise ValueError("无法从链接解析 Wiki 节点 token")

    @staticmethod
    def is_spreadsheet_url(value: str) -> bool:
        return _SPREADSHEET_TOKEN_RE.search(value.strip()) is not None

    @staticmethod
    def parse_spreadsheet_token(value: str) -> str:
        text = value.strip()
        match = _SPREADSHEET_TOKEN_RE.search(text)
        if match:
            return match.group(1)
        parsed = urlparse(text)
        if parsed.path.startswith("/sheets/"):
            return parsed.path.removeprefix("/sheets/").split("/")[0]
        if text and "/" not in text:
            return text
        raise ValueError("无法从链接解析电子表格 token")

    async def get_wiki_node(self, token: str) -> dict[str, Any]:
        data = await self._retry(
            lambda: self._request_data(
                "GET", "/wiki/v2/spaces/get_node", params={"token": token}
            )
        )
        node = data.get("node")
        if not isinstance(node, dict):
            raise RuntimeError("飞书未返回 Wiki 节点信息")
        return node

    async def list_child_nodes(
        self, *, space_id: str, parent_node_token: str
    ) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params: dict[str, Any] = {
                "parent_node_token": parent_node_token,
                "page_size": 50,
            }
            if page_token:
                params["page_token"] = page_token
            data = await self._retry(
                lambda: self._request_data(
                    "GET", f"/wiki/v2/spaces/{space_id}/nodes", params=params
                )
            )
            nodes.extend(
                item for item in data.get("items", []) if isinstance(item, dict)
            )
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break
        return nodes

    async def discover_tree(self, root_token: str) -> list[dict[str, Any]]:
        """Return root and descendants with a display path for each node."""
        root = await self.get_wiki_node(root_token)
        space_id = str(root.get("space_id") or "")
        if not space_id:
            raise RuntimeError("飞书 Wiki 节点缺少 space_id")

        root_title = str(root.get("title") or root_token)
        discovered: list[dict[str, Any]] = [
            {**root, "node_path": [{"token": root_token, "title": root_title}]}
        ]
        queue: list[dict[str, Any]] = [discovered[0]]
        while queue:
            parent = queue.pop(0)
            parent_token = str(parent.get("node_token") or "")
            if not parent_token or not parent.get("has_child"):
                continue
            children = await self.list_child_nodes(
                space_id=space_id, parent_node_token=parent_token
            )
            parent_path = list(parent["node_path"])
            for child in children:
                child_token = str(child.get("node_token") or "")
                child_title = str(child.get("title") or child_token)
                expanded = {
                    **child,
                    "space_id": child.get("space_id") or space_id,
                    "node_path": [
                        *parent_path,
                        {"token": child_token, "title": child_title},
                    ],
                }
                discovered.append(expanded)
                queue.append(expanded)
        return discovered

    async def list_workbook_sheets(
        self, spreadsheet_token: str
    ) -> list[dict[str, Any]]:
        data = await self._retry(
            lambda: self._request_data(
                "GET",
                f"/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query",
            )
        )
        sheets = data.get("sheets")
        if not isinstance(sheets, list):
            return []
        normalized: list[dict[str, Any]] = []
        for item in sheets:
            if not isinstance(item, dict):
                continue
            sheet = dict(item)
            raw_grid = item.get("grid_properties") or item.get("gridProperties")
            if isinstance(raw_grid, dict):
                sheet["grid_properties"] = {
                    "row_count": raw_grid.get("row_count") or raw_grid.get("rowCount"),
                    "column_count": raw_grid.get("column_count")
                    or raw_grid.get("columnCount"),
                }
            normalized.append(sheet)
        return normalized

    async def read_sheet_values(
        self,
        *,
        spreadsheet_token: str,
        sheet_id: str,
        row_count: int | None = None,
        column_count: int | None = None,
        value_render_option: str = "UnformattedValue",
    ) -> tuple[list[list[Any]], str | None]:
        """Read the complete grid, recursively splitting oversized responses."""
        if not isinstance(row_count, int) or row_count < 1:
            raise RuntimeError("飞书未返回工作表行数，无法保证完整读取")
        if not isinstance(column_count, int) or column_count < 1:
            raise RuntimeError("飞书未返回工作表列数，无法保证完整读取")

        normalized: list[list[Any]] = []
        revision: str | None = None
        for start_row in range(1, row_count + 1, 500):
            end_row = min(start_row + 499, row_count)
            rows, tile_revision = await self._read_value_tile(
                spreadsheet_token=spreadsheet_token,
                sheet_id=sheet_id,
                start_row=start_row,
                end_row=end_row,
                start_column=1,
                end_column=column_count,
                value_render_option=value_render_option,
            )
            normalized.extend(rows)
            if tile_revision is not None:
                revision = tile_revision

        for row in normalized:
            while row and self._is_empty_cell(row[-1]):
                row.pop()
        while normalized and not normalized[-1]:
            normalized.pop()
        return normalized, revision

    async def _read_value_tile(
        self,
        *,
        spreadsheet_token: str,
        sheet_id: str,
        start_row: int,
        end_row: int,
        start_column: int,
        end_column: int,
        value_render_option: str,
    ) -> tuple[list[list[Any]], str | None]:
        row_span = end_row - start_row + 1
        column_span = end_column - start_column + 1
        range_ref = quote(
            f"{sheet_id}!{self._column_label(start_column)}{start_row}:"
            f"{self._column_label(end_column)}{end_row}",
            safe="!",
        )
        try:
            data = await self._retry(
                lambda: self._request_data(
                    "GET",
                    f"/sheets/v2/spreadsheets/{spreadsheet_token}/values/{range_ref}",
                    params={
                        "valueRenderOption": value_render_option,
                        "dateTimeRenderOption": "FormattedString",
                    },
                )
            )
        except Exception as exc:
            if not self._is_response_too_large(exc):
                raise
            if row_span > 1 and (row_span >= column_span or column_span == 1):
                middle_row = (start_row + end_row) // 2
                top, top_revision = await self._read_value_tile(
                    spreadsheet_token=spreadsheet_token,
                    sheet_id=sheet_id,
                    start_row=start_row,
                    end_row=middle_row,
                    start_column=start_column,
                    end_column=end_column,
                    value_render_option=value_render_option,
                )
                bottom, bottom_revision = await self._read_value_tile(
                    spreadsheet_token=spreadsheet_token,
                    sheet_id=sheet_id,
                    start_row=middle_row + 1,
                    end_row=end_row,
                    start_column=start_column,
                    end_column=end_column,
                    value_render_option=value_render_option,
                )
                return top + bottom, bottom_revision or top_revision
            if column_span > 1:
                middle_column = (start_column + end_column) // 2
                left, left_revision = await self._read_value_tile(
                    spreadsheet_token=spreadsheet_token,
                    sheet_id=sheet_id,
                    start_row=start_row,
                    end_row=end_row,
                    start_column=start_column,
                    end_column=middle_column,
                    value_render_option=value_render_option,
                )
                right, right_revision = await self._read_value_tile(
                    spreadsheet_token=spreadsheet_token,
                    sheet_id=sheet_id,
                    start_row=start_row,
                    end_row=end_row,
                    start_column=middle_column + 1,
                    end_column=end_column,
                    value_render_option=value_render_option,
                )
                left_width = middle_column - start_column + 1
                merged: list[list[Any]] = []
                for index in range(row_span):
                    row = list(left[index])
                    if len(row) < left_width:
                        row.extend([None] * (left_width - len(row)))
                    row.extend(right[index])
                    merged.append(row)
                return merged, right_revision or left_revision
            raise RuntimeError(
                "飞书单个单元格响应仍超过大小限制，无法完整读取"
            ) from exc

        value_range = data.get("valueRange")
        if not isinstance(value_range, dict):
            value_range = data.get("value_range", {})
        raw_values = (
            value_range.get("values", []) if isinstance(value_range, dict) else []
        )
        if not isinstance(raw_values, list):
            raw_values = []
        rows = [
            list(row) if isinstance(row, list) else [row]
            for row in raw_values[:row_span]
        ]
        rows.extend([] for _ in range(row_span - len(rows)))
        raw_revision = data.get("revision")
        revision = str(raw_revision) if raw_revision is not None else None
        return rows, revision

    @staticmethod
    def _is_empty_cell(value: Any) -> bool:
        return value is None or value == ""

    @staticmethod
    def _column_label(column_count: int) -> str:
        label = ""
        current = column_count
        while current > 0:
            current, remainder = divmod(current - 1, 26)
            label = chr(65 + remainder) + label
        return label

    @staticmethod
    def _is_response_too_large(exc: Exception) -> bool:
        message = str(exc).lower()
        return "90221" in message or "data exceeded 10485760 bytes" in message

    async def _request_data(
        self, method: str, path: str, *, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            data = await self._client.request(method, path, params=params)
            if not isinstance(data, dict):
                raise RuntimeError("飞书未返回对象格式的数据")
            return data
        except httpx.HTTPStatusError as exc:
            response = exc.response
            payload: dict[str, Any] = {}
            try:
                raw_payload = response.json()
                if isinstance(raw_payload, dict):
                    payload = raw_payload
            except ValueError:
                pass
            code = payload.get("code")
            raise EnergyFeishuRequestError(
                path=path,
                status_code=response.status_code,
                feishu_code=code if isinstance(code, int) else None,
                feishu_message=(
                    str(payload.get("msg")) if payload.get("msg") is not None else None
                ),
                request_log_id=response.headers.get("x-tt-logid"),
            ) from exc

    async def _retry(self, operation: Callable[[], Awaitable[T]]) -> T:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                return await operation()
            except Exception as exc:  # third-party errors are normalized by service
                last_error = exc
                if attempt == 2 or not self._is_retryable(exc):
                    raise
                await asyncio.sleep(2**attempt)
        assert last_error is not None
        raise last_error

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, EnergyFeishuRequestError):
            return exc.is_retryable
        message = str(exc).lower()
        non_retryable = (
            "permission",
            "forbidden",
            "unauthorized",
            "invalid",
            "not found",
            "90221",
            "data exceeded 10485760 bytes",
        )
        return not any(marker in message for marker in non_retryable)
