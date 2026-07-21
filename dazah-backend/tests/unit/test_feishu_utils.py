from app.platform.integrations.feishu.utils import (
    normalize_app_token,
    normalize_table_id,
    parse_bitable_url,
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


def test_normalize_table_id_accepts_url_labelled_text_and_raw_id() -> None:
    url = (
        "https://example.feishu.cn/base/IpMdbEFSlaZRoJstpFLcbTzPn2e"
        "?table=tblVpo4DkpnA4MY9&view=vewYHsNQ2G"
    )

    assert normalize_table_id(url) == "tblVpo4DkpnA4MY9"
    assert normalize_table_id("table_id: tblVpo4DkpnA4MY9") == "tblVpo4DkpnA4MY9"
    assert normalize_table_id("tblVpo4DkpnA4MY9") == "tblVpo4DkpnA4MY9"
