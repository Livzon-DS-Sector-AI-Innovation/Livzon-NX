from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AppException
from app.platform.integrations.feishu import utils as feishu_utils
from app.platform.integrations.feishu.utils import (
    extract_wiki_node_token,
    normalize_app_token,
    normalize_table_id,
    parse_bitable_url,
    resolve_wiki_bitable_app_token,
)


def test_parse_bitable_url_extracts_base_table_and_view() -> None:
    ref = parse_bitable_url(
        "https://example.feishu.cn/base/IpMdbEFSlaZRoJstpFLcbTzPn2e"
        "?table=tblVpo4DkpnA4MY9&view=vewYHsNQ2G"
    )

    assert ref.app_token == "IpMdbEFSlaZRoJstpFLcbTzPn2e"
    assert ref.table_id == "tblVpo4DkpnA4MY9"
    assert ref.view_id == "vewYHsNQ2G"


def test_normalize_app_token_accepts_labelled_text_and_raw_token() -> None:
    assert (
        normalize_app_token("app_token: IpMdbEFSlaZRoJstpFLcbTzPn2e")
        == "IpMdbEFSlaZRoJstpFLcbTzPn2e"
    )
    assert (
        normalize_app_token("IpMdbEFSlaZRoJstpFLcbTzPn2e")
        == "IpMdbEFSlaZRoJstpFLcbTzPn2e"
    )


def test_extract_wiki_node_token_from_wiki_link_or_text() -> None:
    assert (
        extract_wiki_node_token(
            "https://j0eukrlohu.feishu.cn/wiki/TeBUwZkJEiOPK2kKLxxcZ1SCnWg"
            "?table=tblivbUvnYDjATiL"
        )
        == "TeBUwZkJEiOPK2kKLxxcZ1SCnWg"
    )
    assert extract_wiki_node_token("/wiki/WikiNode123") == "WikiNode123"
    assert extract_wiki_node_token("https://example.feishu.cn/base/bascn123") is None
    assert extract_wiki_node_token("  ") is None


def test_normalize_app_token_rejects_wiki_and_non_base_urls() -> None:
    # 回归：wiki 链接曾被兜底正则误提取为租户子域名 j0eukrlohu 并存库
    assert (
        normalize_app_token(
            "https://j0eukrlohu.feishu.cn/wiki/TeBUwZkJEiOPK2kKLxxcZ1SCnWg"
            "?table=tblivbUvnYDjATiL"
        )
        is None
    )
    assert normalize_app_token("https://example.feishu.cn/sheets/SomeToken") is None
    assert (
        normalize_app_token("https://example.feishu.cn/base/bascn123?table=tbl1")
        == "bascn123"
    )


def test_normalize_table_id_accepts_url_labelled_text_and_raw_id() -> None:
    url = (
        "https://example.feishu.cn/base/IpMdbEFSlaZRoJstpFLcbTzPn2e"
        "?table=tblVpo4DkpnA4MY9&view=vewYHsNQ2G"
    )

    assert normalize_table_id(url) == "tblVpo4DkpnA4MY9"
    assert normalize_table_id("table_id: tblVpo4DkpnA4MY9") == "tblVpo4DkpnA4MY9"
    assert normalize_table_id("tblVpo4DkpnA4MY9") == "tblVpo4DkpnA4MY9"


class _FakeWikiResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class _FakeWikiHttpClient:
    response: _FakeWikiResponse | None = None

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> "_FakeWikiHttpClient":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def get(
        self,
        path: str,
        headers: dict | None = None,
        params: dict | None = None,
    ) -> _FakeWikiResponse:
        assert path == "/wiki/v2/spaces/get_node"
        assert params is not None and params["token"] == "NodeToken123"
        assert self.response is not None
        return self.response


def _patch_wiki_http(monkeypatch, payload: dict) -> None:
    _FakeWikiHttpClient.response = _FakeWikiResponse(payload)
    monkeypatch.setattr(feishu_utils.httpx, "AsyncClient", _FakeWikiHttpClient)
    monkeypatch.setattr(
        feishu_utils,
        "get_tenant_access_token",
        AsyncMock(return_value="tenant-access-token"),
    )


async def test_resolve_wiki_bitable_app_token_returns_obj_token(
    monkeypatch,
) -> None:
    _patch_wiki_http(
        monkeypatch,
        {
            "code": 0,
            "data": {
                "node": {
                    "obj_type": "bitable",
                    "obj_token": "NIEJbSxylaHBp4shlPjcpVSzXn2e",
                }
            },
        },
    )

    token = await resolve_wiki_bitable_app_token(
        app_id="cli_app",
        app_secret="secret",
        node_token="NodeToken123",
    )
    assert token == "NIEJbSxylaHBp4shlPjcpVSzXn2e"


async def test_resolve_wiki_bitable_app_token_rejects_non_bitable_node(
    monkeypatch,
) -> None:
    _patch_wiki_http(
        monkeypatch,
        {"code": 0, "data": {"node": {"obj_type": "doc", "obj_token": "docx123"}}},
    )

    with pytest.raises(AppException, match="不是多维表格"):
        await resolve_wiki_bitable_app_token(
            app_id="cli_app",
            app_secret="secret",
            node_token="NodeToken123",
        )


async def test_resolve_wiki_bitable_app_token_maps_api_error(
    monkeypatch,
) -> None:
    _patch_wiki_http(monkeypatch, {"code": 131002, "msg": "node not found"})

    with pytest.raises(AppException, match="解析飞书知识库节点失败"):
        await resolve_wiki_bitable_app_token(
            app_id="cli_app",
            app_secret="secret",
            node_token="NodeToken123",
        )
